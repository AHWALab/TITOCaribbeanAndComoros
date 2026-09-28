"""Build IBF receptor preloads from the IBF team's IBFv1.0 country packages.

The IBF team ships one zip per country (IBF_v10_<COUNTRY>.zip) with the
national Overture GeoPackage, admin units with population, and the GHS
BUILT-C FUN raster. The national files are multi GB (Haiti 2.2 GB,
Guatemala 6.3 GB) while FIM, and therefore IBF, only covers a few basins
(the 90m FIM sites). This script cuts the package down to what the
receptor layer actually reads:

    admin units   every unit whose polygon touches a FIM site footprint
                  (plus --site-buffer-m), kept WHOLE: the dasymetric
                  population share and the IWF baselines span each unit's
                  full receptor stock, not only the FIM window
    overture      buildings, roads (segments subtype=road) and places
                  inside the union of those units
    GHS BUILT-C   crop to the same union (Mollweide, 10 m)

Output, under --out/<Country>/ (the layout the island preloads use):

    <slug>_overture_bld_rds.gpkg      layers buildings (id, subtype, class),
                                      roads (id, class), places (id, name,
                                      category, confidence) when the
                                      package has places
    <Country>_admin_population.gpkg   layer admin: ADM_ID, ADM_NAME,
                                      population, pop_source, plus the
                                      package's own id/name fields
    <Country>_GHS_BUILT_C_FUN_E2018_R2023A_54009_10.tif
    manifest_ibf_<Country>.json       sources, sites, counts, file sizes

Site footprints come from the FIM store grids (meta.json crs + transform
+ grid_shape) and/or the AOC geojsons, so a site whose store exists but
whose FIM YAML is not active yet (Guatemala Morales) is covered too.

Jobs file: fim_dev/ibf_preload_jobs_v10.json. Paths in a job resolve
against --root (the deployment folder); zip members are extracted once
into --workdir.

Run:  python fim_dev/build_ibf_preload_v10.py --jobs fim_dev/ibf_preload_jobs_v10.json \
          --country Haiti --root . --out ibf_data --workdir /scratch/ibf_v10
"""

import argparse
import json
import os
import shutil
import tempfile
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window, from_bounds
from shapely.geometry import box


def log(msg):
    print(msg, flush=True)


def _abs(root, path):
    return path if os.path.isabs(path) else os.path.join(root, path)


def extract_member(zip_path, member, workdir):
    """Extract one zip member (or a shapefile's sidecars) once; return path."""
    out = os.path.join(workdir, member)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        stem, ext = os.path.splitext(member)
        wanted = [member]
        if ext.lower() == ".shp":
            wanted = [n for n in names if os.path.splitext(n)[0] == stem]
        for name in wanted:
            dest = os.path.join(workdir, name)
            info = zf.getinfo(name)
            if os.path.isfile(dest) and os.path.getsize(dest) == info.file_size:
                continue
            log(f"    extract {name} ({info.file_size / 1e6:,.0f} MB)")
            zf.extract(name, workdir)
    return out


def site_footprints(root, sites):
    """One EPSG:4326 polygon per FIM site from store grid and/or AOC."""
    out = []
    for site in sites:
        polys = []
        meta_path = (
            _abs(root, os.path.join(site["store"], "meta.json")) if site.get("store") else ""
        )
        if meta_path and os.path.isfile(meta_path):
            with open(meta_path) as fh:
                meta = json.load(fh)
            a, _, c, _, e, f = meta["transform"][:6]
            rows, cols = meta["grid_shape"]
            x0, x1 = sorted((c, c + a * cols))
            y0, y1 = sorted((f, f + e * rows))
            tr = Transformer.from_crs(CRS.from_user_input(meta["crs"]), 4326, always_xy=True)
            polys.append(box(*tr.transform_bounds(x0, y0, x1, y1)))
        aoc = _abs(root, site["aoc"]) if site.get("aoc") else ""
        if aoc and os.path.isfile(aoc):
            polys.append(gpd.read_file(aoc).to_crs(4326).geometry.union_all())
        if not polys:
            raise FileNotFoundError(f"site {site['name']}: neither store meta.json nor AOC found")
        out.append((site["name"], gpd.GeoSeries(polys, crs=4326).union_all()))
    return out


def _json_field(value, key):
    """Pull one key out of an Overture struct column stored as JSON text."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, dict):
        return value.get(key)
    try:
        return json.loads(value).get(key)
    except (TypeError, ValueError, AttributeError):
        return None


def build_country(job, root, out_root, workdir, site_buffer_m):
    country, slug = job["country"], job["slug"]
    final_dir = os.path.join(out_root, country)
    # GPKG writes fail with "Failed to start transaction" on NFS / bind
    # mounts (see ibf_utils.receptors.write_gpkg_layers): stage locally,
    # copy the finished files at the end
    outdir = tempfile.mkdtemp(prefix=f"ibf_preload_{slug}_")
    zip_path = _abs(root, job["zip"])
    wd = os.path.join(workdir, country)
    os.makedirs(wd, exist_ok=True)
    log(f"== {country}: {zip_path}")

    # 1. sites -> admin units touched (kept whole) ---------------------------
    sites = site_footprints(root, job["sites"])
    adm = job["admin"]
    adm_path = extract_member(zip_path, adm["member"], wd)
    admin = gpd.read_file(adm_path).to_crs(4326)
    work = CRS.from_user_input(job["work_crs"])
    admin_w = admin.to_crs(work)
    touched = np.zeros(len(admin), dtype=bool)
    site_units = {}
    for name, poly in sites:
        pw = gpd.GeoSeries([poly], crs=4326).to_crs(work).buffer(site_buffer_m).iloc[0]
        hit = admin_w.intersects(pw).values
        site_units[name] = int(hit.sum())
        touched |= hit
        log(f"  site {name}: {hit.sum()} admin units")
    admin = admin[touched].copy()

    ids = admin[adm["id_field"]]
    if pd.api.types.is_float_dtype(ids):
        ids = ids.round().astype("Int64")
    ids = ids.astype(str)
    # units sharing an id (Guatemala lakes all carry CODIGO 0) get a suffix
    dup = ids.duplicated(keep=False)
    ids[dup] = (
        ids[dup]
        + "_"
        + admin.loc[dup, adm["name_field"]].astype(str).str.replace(r"\W+", "", regex=True)
    )
    admin["ADM_ID"] = ids.values
    admin["ADM_NAME"] = admin[adm["name_field"]].astype(str)
    admin["population"] = pd.to_numeric(admin[adm["population_field"]], errors="coerce").fillna(0.0)
    admin["pop_source"] = adm["pop_source"]
    keep = ["ADM_ID", "ADM_NAME", "population", "pop_source"] + [
        c for c in adm.get("keep_fields", []) if c in admin.columns
    ]
    admin = admin[keep + ["geometry"]]
    assert admin["ADM_ID"].is_unique, "admin ids not unique after de-duplication"
    admin_out = os.path.join(outdir, f"{country}_admin_population.gpkg")
    admin.to_file(admin_out, layer="admin", driver="GPKG")
    union = admin.geometry.union_all()
    bbox = union.bounds
    log(
        f"  admin: {len(admin)} units kept, population {admin['population'].sum():,.0f}, "
        f"bbox {[round(b, 4) for b in bbox]}"
    )

    # 2. overture layers, bbox read then union subset ------------------------
    ov = job["overture"]
    ov_path = extract_member(zip_path, ov["member"], wd)
    ov_out = os.path.join(outdir, f"{slug}_overture_bld_rds.gpkg")
    counts = {}

    def read(layer, columns):
        gdf = gpd.read_file(ov_path, layer=layer, bbox=bbox, columns=columns)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        return gdf[gdf.intersects(union)].copy()

    b = read(ov["buildings_layer"], ["id", "subtype", "class"])
    b.to_file(ov_out, layer="buildings", driver="GPKG")
    counts["buildings"] = len(b)
    counts["buildings_with_subtype"] = int(b["subtype"].notna().sum())
    log(f"  buildings: {len(b):,}")
    del b

    r = read(ov["segments_layer"], ["id", "subtype", "class"])
    if "subtype" in r.columns:
        r = r[r["subtype"] == "road"]
    r = r[["id", "class", "geometry"]]
    r.to_file(ov_out, layer="roads", driver="GPKG", mode="a")
    counts["road_segments"] = len(r)
    counts["road_class_top"] = r["class"].value_counts().head(8).to_dict()
    log(f"  roads: {len(r):,}")

    if ov.get("places_layer"):
        p = read(ov["places_layer"], ["id", "names", "categories", "basic_category", "confidence"])
        p["name"] = p["names"].map(lambda v: _json_field(v, "primary"))
        p["category"] = p["basic_category"].fillna(
            p["categories"].map(lambda v: _json_field(v, "primary"))
        )
        p = p[["id", "name", "category", "confidence", "geometry"]]
        p.to_file(ov_out, layer="places", driver="GPKG", mode="a")
        counts["places"] = len(p)
        log(f"  places: {len(p):,}")
    else:
        log("  places: none in this package")

    # 3. GHS BUILT-C crop ----------------------------------------------------
    ghs_path = extract_member(zip_path, job["ghs_member"], wd)
    ghs_out = os.path.join(outdir, f"{country}_GHS_BUILT_C_FUN_E2018_R2023A_54009_10.tif")
    with rasterio.open(ghs_path) as src:
        tr = Transformer.from_crs(4326, src.crs, always_xy=True)
        gb = tr.transform_bounds(*bbox)
        pad = 500.0
        win = from_bounds(gb[0] - pad, gb[1] - pad, gb[2] + pad, gb[3] + pad, src.transform)
        win = win.round_offsets().round_lengths().intersection(Window(0, 0, src.width, src.height))
        data = src.read(window=win)
        meta = src.meta.copy()
        meta.update(
            height=data.shape[1],
            width=data.shape[2],
            transform=src.window_transform(win),
            compress="LZW",
        )
    with rasterio.open(ghs_out, "w", **meta) as dst:
        dst.write(data)
    vals, freq = np.unique(data, return_counts=True)
    log(f"  GHS crop {data.shape[2]}x{data.shape[1]}")

    manifest = {
        "country": country,
        "built_by": "fim_dev/build_ibf_preload_v10.py",
        "package": os.path.basename(zip_path),
        "sources": {
            "admin": {
                "member": adm["member"],
                "id_field": adm["id_field"],
                "name_field": adm["name_field"],
                "population_field": adm["population_field"],
                "pop_source": adm["pop_source"],
            },
            "overture": {"member": ov["member"]},
            "land_use": {"member": job["ghs_member"]},
        },
        "sites": {name: {"admin_units": n} for name, n in site_units.items()},
        "site_buffer_m": site_buffer_m,
        "bbox_4326": list(bbox),
        "counts": {
            "admin_units": len(admin),
            "population_total": float(admin["population"].sum()),
            **counts,
            "ghs_value_histogram": {str(int(v)): int(c) for v, c in zip(vals, freq, strict=False)},
        },
        "files": {os.path.basename(p): os.path.getsize(p) for p in (admin_out, ov_out, ghs_out)},
    }
    with open(os.path.join(outdir, f"manifest_ibf_{country}.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    os.makedirs(final_dir, exist_ok=True)
    for name in os.listdir(outdir):
        shutil.copy2(os.path.join(outdir, name), os.path.join(final_dir, name))
    shutil.rmtree(outdir, ignore_errors=True)
    log(f"  -> {final_dir}")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--country", action="append", help="run only these jobs (repeatable)")
    ap.add_argument("--root", default=".", help="deployment folder the job paths resolve against")
    ap.add_argument("--out", default="ibf_data")
    ap.add_argument("--workdir", required=True, help="scratch folder for extracted zip members")
    ap.add_argument("--site-buffer-m", type=float, default=1000.0)
    a = ap.parse_args()
    with open(a.jobs) as fh:
        jobs = json.load(fh)
    root = os.path.abspath(a.root)
    for job in jobs:
        if a.country and job["country"] not in a.country:
            continue
        build_country(job, root, _abs(root, a.out), a.workdir, a.site_buffer_m)


if __name__ == "__main__":
    main()
