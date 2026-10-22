"""Build the Comoros IBF receptor preload from the IBF team's package.

The IBF team's Comoros package (IBF_v1_Comoros_20240427.zip) differs from
the IBFv1.0 v10 packages that fim_dev/build_ibf_preload_v10.py reads:

    admin         GADM 4.1 adm1 only (the three islands) with a WorldPop 2025
                  zonal sum; the FIM sites are the 55 adm3 municipalities
    overture      NOT shipped: the team's workflow downloads buildings and
                  roads at run time with the overturemaps package
    worldpop      com_pop_2025_CN_100m_R2025A_v1.tif (constrained, 100 m)
    GHS BUILT-C   Comoros_GHS_BUILT_C_FUN_E2018_GLOBE_R2023A_54009_10_V1_0.tif

An island-wide adm1 unit would make every municipality's IBF read and
baseline the whole island (the receptor layer keeps admin units WHOLE), so
the admin layer here is the 55 municipalities, taken from the FIM AOC
geojsons (each AOC is the full com_admin3 polygon, see
build_comoros_stores.py), with population summed from the package's
WorldPop raster: the same source the team used for adm1. The per-island
totals are checked against the package's GADM adm1 sums.

Output, under --out/Comoros/ (the layout the other preloads use):

    comoros_overture_bld_rds.gpkg      layers buildings (id, subtype, class),
                                       roads (id, class), places (id, name,
                                       category, confidence)
    Comoros_admin_population.gpkg      layer admin: ADM_ID (adm3 pcode),
                                       ADM_NAME, island, population, pop_source
    Comoros_GHS_BUILT_C_FUN_E2018_R2023A_54009_10.tif
    manifest_ibf_Comoros.json          sources, counts, file sizes

Overture data comes from the overturemaps package (pip install overturemaps;
the TITO image has its dependencies), pinned with --release so a rebuild is
reproducible. Run inside the container:

    python fim_dev/build_comoros_ibf_preload.py \
        --package /path/IBF_v1_Comoros_20240427.zip --root . --out ibf_data \
        --workdir /scratch/ibf_comoros [--release 2026-09-17.0]
"""

import argparse
import glob
import json
import os
import shutil
import tempfile
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.mask import mask as rio_mask
from rasterio.windows import Window, from_bounds

COUNTRY, SLUG = "Comoros", "comoros"
WORLDPOP = "IBF_v1_Comoros/input_data/worldpop2025/com_pop_2025_CN_100m_R2025A_v1.tif"
GADM_ADM1 = "IBF_v1_Comoros/input_data/gadm/COM_gadm_adm1_pop.shp"
GHS = (
    "IBF_v1_Comoros/input_data/residential_use/"
    "Comoros_GHS_BUILT_C_FUN_E2018_GLOBE_R2023A_54009_10_V1_0.tif"
)
POP_SOURCE = (
    "WorldPop 2025 constrained 100 m (com_pop_2025_CN_100m_R2025A_v1), "
    "zonal sum over com_admin3 municipalities, IBF_v1_Comoros package"
)
# FIM AOC island names -> GADM 4.1 NAME_1
GADM_ISLAND = {
    "Anjouan (Ndzouani)": "Nzwani",
    "Mohéli (Mwali)": "Mwali",
    "Grande Comore (Ngazidja)": "Njazídja",
}


def log(msg):
    print(msg, flush=True)


def unpack(package, workdir):
    """Extract the package zip once (or accept an extracted folder)."""
    if os.path.isdir(package):
        return package
    with zipfile.ZipFile(package) as zf:
        files = [n for n in zf.namelist() if not n.endswith("/")]
        if len(files) == 1 and files[0].lower().endswith(".zip"):
            # Drive download wrapper: Comoros/IBF_v1_Comoros_<date>.zip
            zf.extract(files[0], workdir)
            return unpack(os.path.join(workdir, files[0]), workdir)
        out = os.path.join(workdir, "package")
        if not os.path.isdir(out):
            log(f"    extract {os.path.basename(package)} -> {out}")
            zf.extractall(out)
        return out


def admin_units(root, aoc_glob, pkg):
    """The 55 municipalities from the FIM AOCs, WorldPop summed per unit."""
    rows = []
    for path in sorted(glob.glob(os.path.join(root, aoc_glob))):
        g = gpd.read_file(path).to_crs(4326)
        p = g.iloc[0]
        rows.append(
            {
                "ADM_ID": p["pcode"],
                "ADM_NAME": p["name"],
                "island": p["island"],
                "geometry": g.geometry.union_all(),
            }
        )
    if not rows:
        raise SystemExit(f"no AOC geojsons match {aoc_glob}")
    admin = gpd.GeoDataFrame(rows, crs=4326)
    assert admin["ADM_ID"].is_unique, "duplicate adm3 pcodes in the AOCs"

    with rasterio.open(os.path.join(pkg, WORLDPOP)) as src:
        nod = src.nodata
        geoms = admin.to_crs(src.crs).geometry
        pops = []
        for geom in geoms:
            data, _ = rio_mask(src, [geom.__geo_interface__], crop=True, filled=False)
            band = data[0]
            if nod is not None:
                band = np.ma.masked_equal(band, nod)
            pops.append(float(np.ma.masked_invalid(band).sum() or 0.0))
    admin["population"] = np.round(pops, 1)
    admin["pop_source"] = POP_SOURCE

    # cross check: per-island totals against the package's GADM adm1 sums
    gadm = gpd.read_file(os.path.join(pkg, GADM_ADM1))
    check = {}
    for island, sub in admin.groupby("island"):
        name1 = GADM_ISLAND.get(island, island)
        ref = gadm.loc[gadm["NAME_1"] == name1, "wrldpp_sum"]
        ref = float(ref.iloc[0]) if len(ref) else None
        check[island] = {
            "adm3_units": int(len(sub)),
            "worldpop_adm3_sum": round(float(sub["population"].sum()), 1),
            "gadm_adm1_wrldpp_sum": round(ref, 1) if ref is not None else None,
        }
        log(
            f"  {island}: {len(sub)} units, population {sub['population'].sum():,.0f}"
            + (f" (GADM adm1 {ref:,.0f})" if ref is not None else " (no GADM match)")
        )
    return admin, check


def overture_layers(bbox, union, release, workdir):
    from overturemaps import core

    def fetch(otype):
        cache = os.path.join(workdir, f"overture_{release}_{otype}.parquet")
        if os.path.isfile(cache):
            gdf = gpd.read_parquet(cache)
        else:
            log(f"    overture {release} {otype} bbox {[round(b, 4) for b in bbox]}")
            gdf = core.geodataframe(otype, bbox=bbox, release=release)
            gdf = gdf.set_crs(4326, allow_override=True)
            gdf.to_parquet(cache)
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        return gdf[gdf.intersects(union)].copy()

    b = fetch("building")
    b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    bld = b[["id", "subtype", "class", "geometry"]]
    s = fetch("segment")
    roads = s[s["subtype"] == "road"][["id", "class", "geometry"]]
    p = fetch("place")

    def field(v, key):
        return v.get(key) if isinstance(v, dict) else None

    # basic_category first; the primary of taxonomy (releases from late
    # 2026) or of categories (older releases) where it is missing
    category = pd.Series(None, index=p.index, dtype=object)
    if "basic_category" in p.columns:
        category = p["basic_category"].astype(object)
    for col in ("taxonomy", "categories"):
        if col in p.columns:
            category = category.fillna(p[col].map(lambda v: field(v, "primary")))
    places = gpd.GeoDataFrame(
        {
            "id": p["id"],
            "name": p["names"].map(lambda v: field(v, "primary")),
            "category": category,
            "confidence": p["confidence"],
        },
        geometry=p.geometry,
        crs=4326,
    )
    return bld, roads, places


def ghs_crop(pkg, bbox, out):
    with rasterio.open(os.path.join(pkg, GHS)) as src:
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
    with rasterio.open(out, "w", **meta) as dst:
        dst.write(data)
    vals, freq = np.unique(data, return_counts=True)
    log(f"  GHS crop {data.shape[2]}x{data.shape[1]}")
    return {str(int(v)): int(c) for v, c in zip(vals, freq, strict=False)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--package", required=True, help="IBF_v1_Comoros zip or extracted folder")
    ap.add_argument("--root", default=".", help="deployment folder (AOCs resolve against it)")
    ap.add_argument("--aoc-glob", default="fim_config/aoc/Comoros_KM*_aoc.geojson")
    ap.add_argument("--out", default="ibf_data")
    ap.add_argument("--workdir", required=True, help="scratch folder (unzip, overture cache)")
    ap.add_argument("--release", default=None, help="Overture release (default: latest)")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    os.makedirs(a.workdir, exist_ok=True)
    pkg = unpack(a.package, a.workdir)
    release = a.release
    if not release:
        from overturemaps import core

        release = core.get_latest_release()
    log(f"== {COUNTRY}: package {pkg}, Overture release {release}")

    # GPKG writes fail on SMB / bind mounts ("Failed to start transaction"):
    # stage locally, copy the finished files at the end
    outdir = tempfile.mkdtemp(prefix=f"ibf_preload_{SLUG}_")

    admin, pop_check = admin_units(root, a.aoc_glob, pkg)
    admin_out = os.path.join(outdir, f"{COUNTRY}_admin_population.gpkg")
    admin.to_file(admin_out, layer="admin", driver="GPKG")
    union = admin.geometry.union_all()
    bbox = tuple(union.bounds)
    log(
        f"  admin: {len(admin)} units, population {admin['population'].sum():,.0f}, "
        f"bbox {[round(b, 4) for b in bbox]}"
    )

    bld, roads, places = overture_layers(bbox, union, release, a.workdir)
    ov_out = os.path.join(outdir, f"{SLUG}_overture_bld_rds.gpkg")
    bld.to_file(ov_out, layer="buildings", driver="GPKG")
    roads.to_file(ov_out, layer="roads", driver="GPKG", mode="a")
    places.to_file(ov_out, layer="places", driver="GPKG", mode="a")
    log(f"  buildings {len(bld):,}, roads {len(roads):,}, places {len(places):,}")

    ghs_out = os.path.join(outdir, f"{COUNTRY}_GHS_BUILT_C_FUN_E2018_R2023A_54009_10.tif")
    ghs_hist = ghs_crop(pkg, bbox, ghs_out)

    manifest = {
        "country": COUNTRY,
        "built_by": "fim_dev/build_comoros_ibf_preload.py",
        "package": "IBF_v1_Comoros_20240427.zip",
        "sources": {
            "admin": {
                "boundaries": "com_admin3 municipalities via fim_config/aoc/Comoros_KM*_aoc.geojson",
                "pop_source": POP_SOURCE,
                "island_check_vs_gadm_adm1": pop_check,
            },
            "overture": {"release": release, "download": "overturemaps package, admin bbox"},
            "land_use": {"member": GHS},
        },
        "bbox_4326": list(bbox),
        "counts": {
            "admin_units": int(len(admin)),
            "population_total": float(admin["population"].sum()),
            "buildings": int(len(bld)),
            "buildings_with_subtype": int(bld["subtype"].notna().sum()),
            "road_segments": int(len(roads)),
            "road_class_top": {k: int(v) for k, v in roads["class"].value_counts().head(8).items()},
            "places": int(len(places)),
            "ghs_value_histogram": ghs_hist,
        },
        "files": {os.path.basename(p): os.path.getsize(p) for p in (admin_out, ov_out, ghs_out)},
    }
    with open(os.path.join(outdir, f"manifest_ibf_{COUNTRY}.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    final_dir = os.path.join(root, a.out, COUNTRY)
    os.makedirs(final_dir, exist_ok=True)
    for name in os.listdir(outdir):
        shutil.copy2(os.path.join(outdir, name), os.path.join(final_dir, name))
    shutil.rmtree(outdir, ignore_errors=True)
    log(f"  -> {final_dir}")


if __name__ == "__main__":
    main()
