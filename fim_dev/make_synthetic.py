"""Generate a fully synthetic test setup for fim_utils.

Creates, under fim_dev/sample_data/synthetic/:
    aoc/units.geojson                        3 areas of concern
    catalog_source/storm_meta.csv            12 storms with directions
    catalog_source/maps/R###_depth.tif       fake hydraulic max-depth maps
    catalog_source/rain/R###_rain24.tif      fake 24-h storm rainfall
    outputs/Barbados/tmp_output_crest_scampr_gfs/20240704.090000/...
    outputs/Barbados/tmp_output_crest_scampr_arome/20240704.090000/...
    outputs/Barbados/tmp_output_crest_imerg/20240704.090000/...   (QPE-only)
    plus a quiet cycle and an extreme cycle for edge tests

Then builds the catalog into fim_catalog/Barbados/v1.

Everything is small (100 x 100 pixels) so the whole end-to-end test runs
in seconds without any real data.
"""

import json
import os
import shutil

import numpy as np
import rasterio
from rasterio.transform import from_origin

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "sample_data", "synthetic")

NX = NY = 100
X0, Y1 = -59.70, 13.40           # upper-left corner (lon, lat)
PIX = 0.004
TRANSFORM = from_origin(X0, Y1, PIX, PIX)
CRS = "EPSG:4326"

CYCLE = "20240704.090000"
QUIET_CYCLE = "20240703.090000"
EXTREME_CYCLE = "20240704.150000"

STORM_MAGS = [25, 40, 55, 70, 90, 110, 130, 150, 175, 200, 240, 290]
STORM_DIRS = ["SW", "W", "SW", "NW", "E", "SW", "W", "SW", "SE", "SW", "W", "NW"]


def write_tif(path, data, dtype="float32", nodata=-9999.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    profile = {
        "driver": "GTiff", "height": data.shape[0], "width": data.shape[1],
        "count": 1, "dtype": dtype, "crs": CRS, "transform": TRANSFORM,
        "nodata": nodata, "compress": "lzw",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)


def box_geom(x0, y0, x1, y1):
    return {"type": "Polygon",
            "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def make_aocs():
    features = []
    thirds = [(13.27, 13.40, "AOC_North"), (13.13, 13.27, "AOC_Central"),
              (13.00, 13.13, "AOC_South")]
    for y0, y1, name in thirds:
        features.append({
            "type": "Feature",
            "properties": {"unit": name, "label": name.replace("_", " ")},
            "geometry": box_geom(-59.69, y0, -59.31, y1),
        })
    path = os.path.join(BASE, "aoc", "units.geojson")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    return path


def make_catalog_source():
    src = os.path.join(BASE, "catalog_source")
    maps_dir = os.path.join(src, "maps")
    rain_dir = os.path.join(src, "rain")
    yy, xx = np.mgrid[0:NY, 0:NX]
    valley = np.exp(-((xx - 55) ** 2 + (yy - 60) ** 2) / (2 * 18.0 ** 2))

    lines = ["storm_id,direction"]
    for i, (mag, direction) in enumerate(zip(STORM_MAGS, STORM_DIRS), start=1):
        storm = f"R{i:03d}"
        depth = (valley * mag / 100.0).astype("float32")   # peak depth ~ mag/100 m
        depth[depth < 0.01] = 0.0
        write_tif(os.path.join(maps_dir, f"{storm}_depth.tif"), depth)
        rain = np.full((NY, NX), float(mag), dtype="float32")
        write_tif(os.path.join(rain_dir, f"{storm}_rain24.tif"), rain)
        lines.append(f"{storm},{direction}")

    meta_csv = os.path.join(src, "storm_meta.csv")
    with open(meta_csv, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return meta_csv, maps_dir, rain_dir


def _ef5_cycle(run_dir, cycle, uq_peak, qpe_mm, qpf_mm=None):
    folder = os.path.join(run_dir, cycle)
    yy, xx = np.mgrid[0:NY, 0:NX]
    # UQ blob centred inside AOC_Central (row ~50, col ~50)
    blob = np.exp(-((xx - 50) ** 2 + (yy - 50) ** 2) / (2 * 6.0 ** 2))
    uq = (0.02 + blob * uq_peak).astype("float32")
    write_tif(os.path.join(folder, f"maxunitq.{cycle}.tif"), uq)
    write_tif(os.path.join(folder, f"maxq.{cycle}.tif"), uq * 40.0)
    write_tif(os.path.join(folder, f"qpeaccum.{cycle}.tif"),
              np.full((NY, NX), qpe_mm, dtype="float32"))
    if qpf_mm is not None:
        write_tif(os.path.join(folder, f"qpfaccum.{cycle}.tif"),
                  np.full((NY, NX), qpf_mm, dtype="float32"))


def make_ef5_outputs():
    region_dir = os.path.join(BASE, "outputs", "Barbados")
    gfs = os.path.join(region_dir, "tmp_output_crest_scampr_gfs")
    arome = os.path.join(region_dir, "tmp_output_crest_scampr_arome")
    imerg = os.path.join(region_dir, "tmp_output_crest_imerg")   # QPE-only run

    # Main cycle: triggered, totals 58+63=121 (gfs) and 58+100=158 (arome)
    _ef5_cycle(gfs, CYCLE, uq_peak=1.6, qpe_mm=58.0, qpf_mm=63.0)
    _ef5_cycle(arome, CYCLE, uq_peak=0.7, qpe_mm=58.0, qpf_mm=100.0)
    _ef5_cycle(imerg, CYCLE, uq_peak=1.6, qpe_mm=58.0, qpf_mm=None)

    # Quiet cycle: UQ stays low everywhere
    _ef5_cycle(gfs, QUIET_CYCLE, uq_peak=0.35, qpe_mm=12.0, qpf_mm=8.0)

    # Extreme cycle: totals far beyond the largest catalog storm
    _ef5_cycle(gfs, EXTREME_CYCLE, uq_peak=2.4, qpe_mm=300.0, qpf_mm=200.0)
    _ef5_cycle(arome, EXTREME_CYCLE, uq_peak=1.9, qpe_mm=300.0, qpf_mm=260.0)
    return region_dir


def main():
    if os.path.isdir(BASE):
        shutil.rmtree(BASE)
    os.makedirs(BASE, exist_ok=True)

    aoc_path = make_aocs()
    meta_csv, maps_dir, rain_dir = make_catalog_source()
    make_ef5_outputs()

    import sys
    sys.path.insert(0, os.path.dirname(HERE))  # repo root when run from fim_dev
    from tito_utils.fim_utils.aoc import load_aocs
    from tito_utils.fim_utils.catalog import build_catalog

    aocs = load_aocs(aoc_path, id_field="unit")
    build_catalog(meta_csv, maps_dir,
                  os.path.join(BASE, "fim_catalog", "Barbados", "v1"),
                  aocs=aocs, rain_dir=rain_dir,
                  depth_pattern="{storm_id}_depth.tif",
                  rain_pattern="{storm_id}_rain24.tif")
    print(f"Synthetic test data ready under {BASE}")


if __name__ == "__main__":
    main()
