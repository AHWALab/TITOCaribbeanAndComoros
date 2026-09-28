"""Probability-product discovery and receptor sampling.

Discovery understands both product namings:

    prob_depth_ge_{tag}.{cycle}.tif            fim_utils >= 0.4 (tag: 10cm, 76cm, ...)
    qpeprob.{cycle}.{threshold} meters.tif     legacy    (threshold: 0.3048, ...)

The threshold in metres is parsed from the filename and is the single
source of truth. This fixes a real defect found in the IBFv1.0 script,
which hard-mapped ``qpeprob...0.1524 meters`` (15.24 cm, 6 in) to a
variable named ``probability_7p62cm`` and so on for the other grids:
every threshold was labelled one class shallower than the water it
represents. Here the tag is always derived from the parsed value
(0.1524 -> ``15p24cm``), never assumed.

Sampling reads each raster once into memory (FIM windows are small) and
reduces the cells under every receptor geometry: buildings take the
footprint maximum (all_touched retry for sub-cell footprints), roads the
maximum over all touched cells, matching the exactextract "max" semantics
of the IBFv1.0 script without the extra dependency.

The cell selection is vectorized (numpy candidate cells + one shapely
predicate call per chunk) with the rasterize rules of the original
per-feature loop: polygon cells by centre-in-polygon, all_touched cells by
interior intersection, points by containing cell. The per-feature loop
(``_InMemoryRaster.reduce``) cost ~2 ms per geometry, i.e. tens of minutes
per cycle for the dense 90m sites (Port-au-Prince plain: ~150k window
buildings x 4 grids); it stays as the reference implementation and as the
fallback for rotated grids and very large geometries.
"""

import os
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds

from .domain import coerce_crs

RE_NEW = re.compile(
    r"^prob_depth_ge_(?P<tag>[0-9p]+)cm(?P<ob>_overbank)?\.(?P<cycle>\d{8}\.\d{6})\.tif$"
)
RE_LEGACY = re.compile(r"^qpeprob\.(?P<cycle>\d{8}\.\d{6})\.(?P<m>[0-9.]+) ?meters\.tif$")


def _tag_from_meters(m: float) -> str:
    cm = m * 100.0
    if abs(cm - round(cm)) < 1e-6:
        return f"{int(round(cm))}cm"
    return f"{cm:.2f}".rstrip("0").rstrip(".").replace(".", "p") + "cm"


@dataclass
class ProbabilityLayer:
    path: str
    threshold_m: float
    tag: str  # canonical, derived from threshold_m
    cycle: str
    overbank: bool = False

    @property
    def field(self) -> str:
        return f"p_ge_{self.tag}"


def parse_probability_filename(name: str):
    """Return ProbabilityLayer (path=name) or None if not a probability grid."""
    base = os.path.basename(name)
    m = RE_NEW.match(base)
    if m:
        meters = float(m.group("tag").replace("p", ".")) / 100.0
        return ProbabilityLayer(
            name, meters, _tag_from_meters(meters), m.group("cycle"), bool(m.group("ob"))
        )
    m = RE_LEGACY.match(base)
    if m:
        meters = float(m.group("m"))
        return ProbabilityLayer(name, meters, _tag_from_meters(meters), m.group("cycle"), False)
    return None


def discover_probability_products(
    directory: str, cycle: str = None, extra_paths=None, prefer_overbank: bool = False
):
    """All probability layers in a directory (plus explicit extra paths),
    filtered to one cycle when given, sorted by threshold.

    Returns (layers, skipped): skipped lists files of OTHER cycles so a
    mixed-vintage folder (the second defect found in the IBFv1.0 inputs:
    three grids from one cycle, the fourth from the previous day) is
    surfaced instead of silently blended. Explicit extra_paths are always
    kept, with a flag when their cycle differs.
    """
    found = []
    if directory and os.path.isdir(directory):
        for base in sorted(os.listdir(directory)):
            layer = parse_probability_filename(os.path.join(directory, base))
            if layer:
                found.append(layer)
    for p in extra_paths or []:
        layer = parse_probability_filename(p)
        if layer:
            layer.explicit = True
            found.append(layer)

    if cycle is None and found:
        cycles = sorted({lyr.cycle for lyr in found})
        cycle = cycles[-1]

    layers, skipped = [], []
    for lyr in found:
        if lyr.cycle != cycle and not getattr(lyr, "explicit", False):
            skipped.append(lyr)
            continue
        layers.append(lyr)

    if prefer_overbank:
        ob_thresholds = {lyr.threshold_m for lyr in layers if lyr.overbank}
        layers = [lyr for lyr in layers if lyr.overbank or lyr.threshold_m not in ob_thresholds]
    else:
        layers = [lyr for lyr in layers if not lyr.overbank]

    # one layer per threshold
    seen = {}
    for lyr in layers:
        seen.setdefault(round(lyr.threshold_m, 4), lyr)
    layers = sorted(seen.values(), key=lambda lyr: lyr.threshold_m)
    return layers, skipped, cycle


class _InMemoryRaster:
    """Band 1 in memory with NaN nodata, plus a per-geometry reducer."""

    def __init__(self, path: str, bounds=None):
        with rasterio.open(path) as src:
            self.crs = coerce_crs(src.crs)
            if bounds is not None:
                win = from_bounds(*bounds, transform=src.transform)
                win = (
                    win.round_offsets()
                    .round_lengths()
                    .intersection(Window(0, 0, src.width, src.height))
                )
                data = src.read(1, window=win, masked=True)
                self.transform = src.window_transform(win)
            else:
                data = src.read(1, masked=True)
                self.transform = src.transform
            self.data = np.ma.filled(data.astype("float64"), np.nan)

    def reduce(self, geom, op: str, all_touched: bool):
        """max / mode of raster cells under one geometry; NaN if none."""
        rows, cols = self.data.shape
        if rows == 0 or cols == 0 or geom is None or geom.is_empty:
            return np.nan
        minx, miny, maxx, maxy = geom.bounds
        inv = ~self.transform
        c0, r0 = inv * (minx, maxy)
        c1, r1 = inv * (maxx, miny)
        r_lo, r_hi = int(np.floor(min(r0, r1))), int(np.ceil(max(r0, r1)))
        c_lo, c_hi = int(np.floor(min(c0, c1))), int(np.ceil(max(c0, c1)))
        r_lo, c_lo = max(r_lo, 0), max(c_lo, 0)
        r_hi, c_hi = min(r_hi, rows), min(c_hi, cols)
        if r_hi <= r_lo:
            r_hi = min(r_lo + 1, rows)
        if c_hi <= c_lo:
            c_hi = min(c_lo + 1, cols)
        if r_hi <= r_lo or c_hi <= c_lo:
            return np.nan
        window_transform = self.transform * rasterio.Affine.translation(c_lo, r_lo)
        shape = (r_hi - r_lo, c_hi - c_lo)
        mask = rasterize(
            [(geom, 1)],
            out_shape=shape,
            transform=window_transform,
            fill=0,
            all_touched=all_touched,
            dtype="uint8",
        )
        if not mask.any() and not all_touched:
            mask = rasterize(
                [(geom, 1)],
                out_shape=shape,
                transform=window_transform,
                fill=0,
                all_touched=True,
                dtype="uint8",
            )
        values = self.data[r_lo:r_hi, c_lo:c_hi][mask == 1]
        values = values[~np.isnan(values)]
        if values.size == 0:
            return np.nan
        if op == "max":
            return float(values.max())
        if op == "mode":
            uniq, counts = np.unique(values, return_counts=True)
            return float(uniq[np.argmax(counts)])
        raise ValueError(f"Unknown op '{op}'")


_POINT_TYPES = (0, 4)  # Point, MultiPoint (shapely type ids)
_LINE_TYPES = (1, 2, 5)  # LineString, LinearRing, MultiLineString
_MAX_CANDIDATES = 2_000_000  # per chunk; bigger geometries use the loop


def _ragged_cells(r_lo, r_hi, c_lo, c_hi):
    """(owner, row, col) for every cell of every [r_lo,r_hi) x [c_lo,c_hi) box."""
    nr = np.maximum(r_hi - r_lo, 0)
    nc = np.maximum(c_hi - c_lo, 0)
    n = nr * nc
    owner = np.repeat(np.arange(len(n)), n)
    start = np.repeat(np.cumsum(n) - n, n)
    k = np.arange(n.sum()) - start
    ncol = nc[owner]
    rows = r_lo[owner] + k // np.maximum(ncol, 1)
    cols = c_lo[owner] + k % np.maximum(ncol, 1)
    return owner, rows, cols


def _reduce_values(owner, vals, n, op):
    """Group reduce of cell values per geometry index; NaN where none."""
    out = np.full(n, np.nan)
    ok = ~np.isnan(vals)
    owner, vals = owner[ok], vals[ok]
    if owner.size == 0:
        return out
    if op == "max":
        np.fmax.at(out, owner, vals)
        return out
    if op == "mode":
        # most frequent value, ties to the smallest value (np.unique order,
        # as in _InMemoryRaster.reduce)
        df = pd.DataFrame({"o": owner, "v": vals})
        cnt = df.groupby(["o", "v"]).size().reset_index(name="n")
        cnt = cnt.sort_values(["o", "n", "v"], ascending=[True, False, True])
        best = cnt.drop_duplicates("o")
        out[best["o"].to_numpy()] = best["v"].to_numpy()
        return out
    raise ValueError(f"Unknown op '{op}'")


def _needs_exact_test(gidx, vals, certain, n, op):
    """Candidate cells whose inclusion must be decided by the exact (slow)
    geometry test. NaN cells never change a result; for max, a cell also
    cannot change it when its value does not exceed what the feature's
    certain cells already give. Only features without any valid certain
    cell test everything, so NaN vs value stays exact."""
    finite = ~np.isnan(vals)
    need = ~certain & finite
    if op != "max":
        return need
    cur = np.full(n, -np.inf)
    ok = certain & finite
    np.maximum.at(cur, gidx[ok], vals[ok])
    base = cur[gidx]
    return need & ((vals > base) | ~np.isfinite(base))


def _reduce_many(ras, geoms, op, all_touched):
    """Vectorized _InMemoryRaster.reduce over an array of geometries.

    all_touched: bool array (per geometry). Returns float array, NaN where
    the geometry covers no valid cell.
    """
    n = len(geoms)
    out = np.full(n, np.nan)
    rows, cols = ras.data.shape
    t = ras.transform
    if n == 0 or rows == 0 or cols == 0:
        return out
    if t.b != 0 or t.d != 0:  # rotated grid: reference loop
        for i, g in enumerate(geoms):
            out[i] = ras.reduce(g, op, bool(all_touched[i]))
        return out

    geoms = np.asarray(geoms, dtype=object)
    valid = ~(shapely.is_missing(geoms) | shapely.is_empty(geoms))
    gtype = np.where(valid, shapely.get_type_id(geoms), -1)
    x0, dx, y0, dy = t.c, t.a, t.f, t.e  # dy < 0 for north-up

    def col_of(x):
        return np.floor((x - x0) / dx).astype(np.int64)

    def row_of(y):
        return np.floor((y - y0) / dy).astype(np.int64)

    def cell_boxes(r, c):
        xa, xb = x0 + c * dx, x0 + (c + 1) * dx
        ya, yb = y0 + r * dy, y0 + (r + 1) * dy
        return shapely.box(
            np.minimum(xa, xb), np.minimum(ya, yb), np.maximum(xa, xb), np.maximum(ya, yb)
        )

    def gather(owner, r, c):
        inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
        return owner[inside], r[inside], c[inside]

    def encode(o, r, c):
        return (o.astype(np.int64) * rows + r) * cols + c

    def decode(key):
        oc, c = np.divmod(key, cols)
        o, r = np.divmod(oc, rows)
        return o, r, c

    owners, rr, cc = [], [], []

    # points: the containing cell
    idx = np.flatnonzero(np.isin(gtype, _POINT_TYPES))
    if idx.size:
        xy, own = shapely.get_coordinates(geoms[idx], return_index=True)
        o, r, c = gather(idx[own], row_of(xy[:, 1]), col_of(xy[:, 0]))
        owners.append(o), rr.append(r), cc.append(c)

    # lines: cells within one cell of vertices densified to half a cell,
    # kept where the cell interior meets the line (= rasterize all_touched).
    # GDAL's line walker special-cases lines passing exactly through cell
    # corners and segment ends exactly on cell edges; those grid-exact
    # coordinates never occur for reprojected receptors and are not copied
    is_line = np.isin(gtype, _LINE_TYPES)
    # thin (non all_touched) line burning is never used by the pipeline:
    # keep GDAL's own rule through the reference loop
    for i in np.flatnonzero(is_line & ~all_touched):
        out[i] = ras.reduce(geoms[i], op, False)
    idx = np.flatnonzero(is_line & all_touched)
    if idx.size:
        step = min(abs(dx), abs(dy)) / 2.0
        dense = shapely.segmentize(geoms[idx], step)
        xy, own = shapely.get_coordinates(dense, return_index=True)
        r0, c0 = row_of(xy[:, 1]), col_of(xy[:, 0])
        o = np.repeat(own, 9)
        r = (r0[:, None] + np.repeat(np.arange(-1, 2), 3)[None, :]).ravel()
        c = (c0[:, None] + np.tile(np.arange(-1, 2), 3)[None, :]).ravel()
        o, r, c = decode(np.unique(encode(*gather(o, r, c))))
        # GDAL burns the cell that owns each point of the line under
        # half-open cell bounds (a line lying on a cell edge goes to the
        # cell below / right of it): the owners of the densified vertices
        # are certain hits; other candidates need the interior test
        certain = np.isin(encode(o, r, c), encode(*gather(own, r0, c0)))
        vals = ras.data[r, c]
        hit = certain.copy()
        need = _needs_exact_test(idx[o], vals, certain, n, op)
        if need.any():
            g = dense[o[need]]
            cb = cell_boxes(r[need], c[need])
            hit[need] = shapely.intersects(g, cb) & ~shapely.touches(g, cb)
        owners.append(idx[o[hit]]), rr.append(r[hit]), cc.append(c[hit])

    # polygons: bounding-box candidate cells, then centre-in-polygon (or
    # interior intersection for all_touched); sub-cell footprints that
    # catch no centre retry with all_touched, as the reference loop does
    idx = np.flatnonzero(~np.isin(gtype, _POINT_TYPES + _LINE_TYPES) & (gtype >= 0))
    if idx.size:
        b = shapely.bounds(geoms[idx])
        ca, cb_ = (b[:, 0] - x0) / dx, (b[:, 2] - x0) / dx
        ra, rb = (b[:, 3] - y0) / dy, (b[:, 1] - y0) / dy
        r_lo = np.clip(np.floor(np.minimum(ra, rb)).astype(np.int64), 0, rows)
        r_hi = np.clip(np.ceil(np.maximum(ra, rb)).astype(np.int64), 0, rows)
        c_lo = np.clip(np.floor(np.minimum(ca, cb_)).astype(np.int64), 0, cols)
        c_hi = np.clip(np.ceil(np.maximum(ca, cb_)).astype(np.int64), 0, cols)
        # degenerate (zero width/height) boxes take one cell, as in reduce()
        r_hi = np.where((r_hi <= r_lo) & (r_lo < rows), r_lo + 1, r_hi)
        c_hi = np.where((c_hi <= c_lo) & (c_lo < cols), c_lo + 1, c_hi)
        ncell = np.maximum(r_hi - r_lo, 0) * np.maximum(c_hi - c_lo, 0)
        big = ncell > _MAX_CANDIDATES // 4
        for i in idx[big]:
            out[i] = ras.reduce(geoms[i], op, bool(all_touched[i]))
        keep = ~big
        idx, r_lo, r_hi, c_lo, c_hi = idx[keep], r_lo[keep], r_hi[keep], c_lo[keep], c_hi[keep]
        ncell = ncell[keep]
        # chunk so candidate arrays stay bounded (~_MAX_CANDIDATES cells)
        start = 0
        while start < len(idx):
            acc = np.cumsum(ncell[start:])
            stop = start + max(1, int(np.searchsorted(acc, _MAX_CANDIDATES, side="right")))
            sl = slice(start, stop)
            start = stop
            o, r, c = _ragged_cells(r_lo[sl], r_hi[sl], c_lo[sl], c_hi[sl])
            gi = idx[sl][o]
            g = geoms[gi]
            touched = all_touched[gi]
            cx = x0 + (c + 0.5) * dx
            cy = y0 + (r + 0.5) * dy
            hit = np.zeros(o.size, dtype=bool)
            nt = ~touched
            if nt.any():
                hit[nt] = shapely.contains_xy(g[nt], cx[nt], cy[nt])
                # retry with all_touched where a geometry caught no centre
                got = np.zeros(len(geoms), dtype=bool)
                got[gi[hit]] = True
                retry = nt & ~got[gi]
                touched = touched | retry
            if touched.any():
                # a cell whose centre lies inside is certainly touched; the
                # exact interior test runs only where it can change a result
                certain = np.zeros(o.size, dtype=bool)
                certain[touched] = shapely.contains_xy(g[touched], cx[touched], cy[touched])
                vals = ras.data[r, c]
                need = touched & _needs_exact_test(gi, vals, certain, len(geoms), op)
                hit[touched] = certain[touched]
                if need.any():
                    cbx = cell_boxes(r[need], c[need])
                    gt = g[need]
                    hit[need] = shapely.intersects(gt, cbx) & ~shapely.touches(gt, cbx)
            owners.append(gi[hit]), rr.append(r[hit]), cc.append(c[hit])

    if owners:
        o, r, c = np.concatenate(owners), np.concatenate(rr), np.concatenate(cc)
        if op == "mode":  # each cell counts once per geometry
            o, r, c = decode(np.unique(encode(o, r, c)))
        vals = ras.data[r, c]
        red = _reduce_values(o, vals, n, op)
        done = ~np.isnan(red)
        out[done] = red[done]
    return out


def sample_raster(
    gdf, raster_path: str, op: str = "max", all_touched: bool = None, bounds_pad_m: float = 100.0
):
    """Sample one raster onto every geometry of a GeoDataFrame.

    Geometries are reprojected to the raster CRS; the raster is read once,
    windowed to the receptors' extent. all_touched defaults to True for
    lines and False (with retry) for polygons.
    """
    if len(gdf) == 0:
        return pd.Series(dtype="float64")
    with rasterio.open(raster_path) as src:
        raster_crs = coerce_crs(src.crs)
    geoms = gdf.geometry.to_crs(raster_crs)
    minx, miny, maxx, maxy = geoms.total_bounds
    ras = _InMemoryRaster(
        raster_path,
        bounds=(minx - bounds_pad_m, miny - bounds_pad_m, maxx + bounds_pad_m, maxy + bounds_pad_m),
    )
    line_like = geoms.geom_type.isin(["LineString", "MultiLineString"]).to_numpy()
    touched = np.full(len(gdf), bool(all_touched)) if all_touched is not None else line_like
    out = _reduce_many(ras, geoms.values, op, touched)
    return pd.Series(out, index=gdf.index)


def sample_probabilities(gdf, layers, fill_zero: bool = True):
    """Add one p_ge_{tag} column per probability layer.

    Max over every cell the feature touches (all_touched=True): the
    worst-case reading, and the same semantics as exactextract's "max"
    used by the IBFv1.0 script, verified feature-by-feature against its
    Guatemala outputs.
    """
    out = gdf.copy()
    for layer in layers:
        vals = sample_raster(out, layer.path, op="max", all_touched=True)
        if fill_zero:
            vals = vals.fillna(0.0)
        out[layer.field] = vals.round(4)
    return out
