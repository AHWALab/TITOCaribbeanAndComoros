"""Agency-grade verification of the ensemble FIM run on real Guatemala data.

Independently recomputes what the pipeline computed and checks consistency:
totals, round-up matching, probability arithmetic, class bands, quiet path.
"""

import csv
import json
import os
import sys

import numpy as np
import rasterio
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tito_utils.fim_utils.ensemble import zone_stat
from tito_utils.fim_utils.store import FimStore
from tito_utils.fim_utils.pipeline_ensemble import load_ensemble_config, run_ensemble_cycle

ROOT = os.environ.get("FIM_GT_DATA", ".")  # folder with ef5_outputs/, fimlib/, store, AOC
CYC = "20260730.150000"
CHECKS = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    CHECKS.append(cond)


summary = json.load(open(f"{ROOT}/fim_out/{CYC}/fim_summary.json"))
rows = list(csv.DictReader(open(f"{ROOT}/fim_out/{CYC}/member_matches.csv")))
trig = list(csv.DictReader(open(f"{ROOT}/fim_out/{CYC}/trigger_maxuq.csv")))
store = FimStore(f"{ROOT}/fim_store_SantaInesPetapa_v1.zarr")

check("50 forecast members in matches table", len(rows) == 50, str(len(rows)))
check("70 runs checked for the trigger (10+10+50)", len(trig) == 70, str(len(trig)))
check("trigger max UQ recorded and >= 1", summary["trigger"]["max_uq"] >= 1.0,
      str(summary["trigger"]["max_uq"]))
check("all trigger reads flagged as expanded sampling (AOC is nodata in EF5)",
      all("sampling_expanded" in (t["flags"] or "") for t in trig))

# Independent recomputation of one member's total (ens1 sl1)
bounds = (-90.5898, 14.4294, -90.484, 14.537)
paths = {
    "qpe_streamsat": f"{ROOT}/ef5_outputs/outputs/stream_sat/ensOut1/guatemala/tmp_output_crest_streamsat/{CYC}/qpeaccum.{CYC}.tif",
    "qpe_scampr": f"{ROOT}/ef5_outputs/outputs/scampr/ensOut1/guatemala/tmp_output_crest_gap_scampr/{CYC}/qpeaccum.{CYC}.tif",
    "rain_stormlab": f"{ROOT}/ef5_outputs/outputs/stormlab/ensOut1_sl1/guatemala/tmp_output_crest_stormlab/{CYC}/qpeaccum.{CYC}.tif",
}
manual = {k: zone_stat(p, bounds, "mean").value for k, p in paths.items()}
manual_total = round(sum(manual.values()), 2)
row = next(r for r in rows if r["member_id"] == "ens01_sl01")
check("member ens01_sl01 total matches independent recomputation",
      abs(float(row["total_mm"]) - manual_total) < 0.05,
      f"pipeline {row['total_mm']} vs manual {manual_total}")

# Round-up rule on every member
ok_round = True
for r in rows:
    if not r["total_mm"]:
        continue
    total, mag = float(r["total_mm"]), float(r["storm_magnitude_mm"])
    flags = r["flags"] or ""
    if mag < total and not any(f in flags for f in ("rounded_down", "beyond_catalog")):
        ok_round = False
check("round-up rule respected for all 50 members", ok_round)

# Probability arithmetic: recompute from the matches table
indices = [store.index_of(r["storm_id"]) for r in rows if r["storm_id"]]
acc = np.zeros(store.grid_shape)
for i in indices:
    acc += store.depth(i) >= 0.30
manual_prob = (acc / len(indices)).astype("float32")
with rasterio.open(f"{ROOT}/fim_out/{CYC}/prob_depth_ge_30cm.{CYC}.tif") as s:
    prob = s.read(1)
    check("probability raster on the FIM grid (EPSG:3857, 5 m)",
          str(s.crs) == "EPSG:3857" and s.res == (5.0, 5.0))
check("probability raster equals independent recomputation",
      np.allclose(prob, manual_prob, atol=1e-6),
      f"max abs diff {np.abs(prob - manual_prob).max():.2e}")
check("probability within [0, 1]", float(prob.min()) >= 0 and float(prob.max()) <= 1,
      f"max {prob.max():.3f}")

with rasterio.open(f"{ROOT}/fim_out/{CYC}/likelihood_class.{CYC}.tif") as s:
    classes = s.read(1)
sel_high = classes == 4
check("high-likelihood class implies probability > 0.6",
      bool((prob[sel_high] > 0.6).all()) if sel_high.any() else True,
      f"high px {int(sel_high.sum())}")
check("summary carries placeholder-magnitude flag",
      "placeholder" in summary["catalog"]["magnitude_source"])

# Quiet path: absurd threshold -> quiet, no probability product
cfg = load_ensemble_config(f"{ROOT}/Guatemala_SantaInes.yaml", root=ROOT)
cfg["trigger"]["threshold"] = 99.0
cfg["products_root"] = "fim_out_quiet_test"
s2 = run_ensemble_cycle(cfg, cycle=CYC, verbose=False)
check("absurd threshold gives quiet status", s2["status"] == "quiet")
check("quiet cycle writes summary but no probability raster",
      os.path.isfile(f"{ROOT}/fim_out_quiet_test/{CYC}/fim_summary.json")
      and not any(f.startswith("prob_") for f in os.listdir(f"{ROOT}/fim_out_quiet_test/{CYC}")))

print()
failed = len([c for c in CHECKS if not c])
if failed:
    print(f"REAL-DATA VERIFICATION: {failed} FAILED of {len(CHECKS)}")
    sys.exit(1)
print(f"REAL-DATA VERIFICATION: all {len(CHECKS)} checks passed")
