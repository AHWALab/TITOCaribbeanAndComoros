"""Build the Santa Ines Petapa FIM store from the 200 hydraulic max-depth maps.

Magnitudes: the RainyDay scenario NetCDFs in 4_RainyDay arrived as broken
symlinks (no data), so this build assigns PLACEHOLDER magnitudes: samples
ranked by flooded area and spread evenly over 25-300 mm. Every product
carries a magnitude_source flag until attach_magnitudes() is run with the
real RainyDay 24-h totals (template CSV written next to the store).
"""

import glob
import os
import sys

import numpy as np
import rasterio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tito_utils.fim_utils.store import build_store, FimStore

FIMLIB = os.environ.get("FIM_LIB_DIR", "fimlib")
RAINYDAY = os.environ.get("FIM_RAINYDAY_DIR", "rainyday/scenarios")
OUT = os.environ.get("FIM_STORE_OUT", "fim_store_SantaInesPetapa_v1.zarr")

depth_files = {}
for d in sorted(glob.glob(os.path.join(FIMLIB, "sample_*"))):
    sample = os.path.basename(d)
    f = os.path.join(d, "MaximumDepth.tif")
    if os.path.isfile(f):
        depth_files[sample] = f
print(f"depth maps found: {len(depth_files)}")

# Rank by flooded area (>= 5 cm) for the placeholder ordering
wet_area = {}
for sample, f in depth_files.items():
    with rasterio.open(f) as src:
        d = src.read(1, masked=True)
        wet_area[sample] = int((d >= 0.05).filled(False).sum())

order = sorted(depth_files, key=lambda s: (wet_area[s], s))
placeholder = np.linspace(25.0, 300.0, len(order))
magnitudes = {s: float(m) for s, m in zip(order, placeholder)}

# Map sample -> RainyDay scenario filename (from the symlink stubs)
scenario_name = {}
for nc in glob.glob(os.path.join(RAINYDAY, "sample_*__scenario_*.nc")):
    base = os.path.basename(nc)
    sample = base.split("__")[0]
    scenario_name[sample] = base.split("__", 1)[1]

build_store(depth_files, OUT, magnitudes,
            extent_threshold_m=0.05,
            magnitude_source="placeholder_rank_by_flooded_area_25_300mm",
            extra_attrs={"site": "SantaInesPetapa", "country": "Guatemala",
                         "library_source": "RainyDay x hydraulic model, 200 samples",
                         "note": "magnitudes are placeholders; run attach_magnitudes() "
                                 "with real RainyDay 24-h totals"})

# Magnitude template for the real values
import csv
with open(os.path.join(OUT, "magnitude_template.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["storm_id", "rainyday_scenario_file", "placeholder_magnitude_mm",
                "magnitude_mm_24h_FILL_ME"])
    for s in sorted(depth_files):
        w.writerow([s, scenario_name.get(s, ""), round(magnitudes[s], 2), ""])

store = FimStore(OUT)
print("store built:", store.n_storms, "storms | grid", store.grid_shape,
      "| crs", store.crs, "| mags", round(float(store.magnitude.min()), 1), "-",
      round(float(store.magnitude.max()), 1), "mm")
du = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs)
print(f"store size on disk: {du/1e6:.1f} MB")
# spot check: one chunk read
d = store.depth(store.n_storms - 1)
print("largest storm wet>=0.30m cells:", int((d >= 0.30).sum()))
