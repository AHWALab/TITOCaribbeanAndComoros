"""Parity test: Python fluvial matcher vs the MATLAB prototype outputs.

Reproduces the prototype's StreamSat (QPE) likelihood maps for cycle
20230621.070000 and compares bit-for-bit with the GeoTIFFs the colleague
saved from MATLAB. Also documents the prototype's StormLab quirk: its
QPF maps reused each StreamSat member's match index, so qpfprob should
equal qpeprob exactly; the corrected per-member QPF maps differ.

Env vars: FIM_GT_DATA (folder holding ef5_outputs4/... and the store),
PROTO_DIR (staged standalone_prototype folder).
"""

import glob
import os
import sys

import numpy as np
import rasterio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tito_utils.fim_utils.store import FimStore
from tito_utils.fim_utils.fluvial import FluvialMatcher, member_boundary_q

ROOT = os.environ.get("FIM_GT_DATA", ".")
PROTO = os.environ.get("PROTO_DIR", ".")
CYC = "20230621.070000"
OUTROOT = os.path.join(ROOT, "ef5_outputs4/20Jun_22Jun_2023_cuenca_villalobos_90m")
TH = [0.5 * 0.3048, 1.0 * 0.3048, 2.0 * 0.3048]
SERIES = ["ts.cuenca_villalobos_1.crest.{cycle}.csv",
          "ts.cuenca_villalobos_2.crest.{cycle}.csv"]

store = FimStore(os.path.join(ROOT, "fim_store_SantaInesPetapa_v1.zarr"))
fm = FluvialMatcher(store)
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


# ---- QPE loop exactly as the prototype: 10 streamsat members ---------------
counts = {t: np.zeros(store.grid_shape) for t in TH}
qpe_idx = {}
for ss in range(1, 11):
    rd = f"{OUTROOT}/stream_sat/ensOut{ss}/guatemala_90m/tmp_output_crest_streamsat/{CYC}"
    q, _ = member_boundary_q(rd, CYC, SERIES, "max")
    d = fm.match(q, "standardized")
    qpe_idx[ss] = d["storm_index"]
    depth = store.depth(d["storm_index"])
    for t in TH:
        counts[t] += depth > t          # MATLAB uses strict >
print("QPE matches per member:", {k: store.storm_id[v] for k, v in qpe_idx.items()})

for t, tag in zip(TH, ["0.1524", "0.3048", "0.6096"]):
    ours = (counts[t] / 10.0).astype("float64")
    theirs = rasterio.open(
        f"{PROTO}/depth_exceedance_probability_maps/qpeprob.{CYC}.{tag} meters.tif").read(1)
    check(f"QPE parity at {tag} m", np.allclose(ours, theirs, atol=1e-9),
          f"max|diff|={np.abs(ours-theirs).max():.2e}")

# ---- document the prototype QPF quirk --------------------------------------
for tag in ["0.1524", "0.3048", "0.6096"]:
    a = rasterio.open(f"{PROTO}/depth_exceedance_probability_maps/qpeprob.{CYC}.{tag} meters.tif").read(1)
    b = rasterio.open(f"{PROTO}/depth_exceedance_probability_maps/qpfprob.{CYC}.{tag} meters.tif").read(1)
    check(f"prototype qpfprob equals qpeprob at {tag} m (bug signature)",
          np.array_equal(a, b))

# ---- corrected per-member StormLab matching --------------------------------
sl_counts = {t: np.zeros(store.grid_shape) for t in TH}
sl_ids = []
for ss in range(1, 11):
    for sl in range(1, 6):
        rd = (f"{OUTROOT}/stormlab/ensOut{ss}_sl{sl}/guatemala_90m/"
              f"tmp_output_crest_stormlab/{CYC}")
        q, _ = member_boundary_q(rd, CYC, SERIES, "max")
        d = fm.match(q, "standardized")
        sl_ids.append(d["storm_index"])
        depth = store.depth(d["storm_index"])
        for t in TH:
            sl_counts[t] += depth > t
corrected = {t: sl_counts[t] / 50.0 for t in TH}
buggy = {t: counts[t] / 10.0 for t in TH}
diffpx = int((np.abs(corrected[TH[1]] - buggy[TH[1]]) > 1e-9).sum())
check("corrected QPF differs from prototype's reused-index QPF",
      diffpx > 0, f"differing pixels at 1 ft: {diffpx}")
print(f"  distinct fluvial scenarios among 50 corrected members: {len(set(sl_ids))}")

print(f"\nFLUVIAL PARITY RESULT: {sum(CHECKS)}/{len(CHECKS)} checks passed"
      + (" - ALL PASSED" if all(CHECKS) else " - FAILURES PRESENT"))
sys.exit(0 if all(CHECKS) else 1)
