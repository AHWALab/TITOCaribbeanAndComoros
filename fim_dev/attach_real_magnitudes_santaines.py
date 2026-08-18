"""Rebuild helper: attach the real Santa Ines indices to the store.

Reproduces the shipped store from its inputs:
1. pluvial magnitudes from the RainyDay scenario GeoTIFFs (AOC mean of the
   72-band storm total), see fim_store/Guatemala/magnitudes_SantaInesPetapa_real.csv
2. fluvial index (Q1, Q2 per scenario) from flood_library.mat

Usage: set the three paths below, then run once.
"""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tito_utils.fim_utils.store import attach_magnitudes
from tito_utils.fim_utils.fluvial import attach_fluvial_index, reorder_index
from tito_utils.fim_utils.store import FimStore

STORE = "fim_store/Guatemala/fim_store_SantaInesPetapa_v1.zarr"
MAG_CSV = "fim_store/Guatemala/magnitudes_SantaInesPetapa_real.csv"
FLOOD_LIB_MAT = "path/to/flood_library.mat"   # only needed if index missing

mags = {r["storm_id"]: float(r["magnitude_mm_aoc_mean"])
        for r in csv.DictReader(open(MAG_CSV))}
attach_magnitudes(STORE, mags, source="RainyDay storm totals, AOC mean")
print("pluvial magnitudes attached (store re-sorted, fluvial index re-linked)")

import zarr
if "fluvial_q" not in zarr.open_group(STORE, mode="r"):
    from scipy.io import loadmat
    scen = loadmat(FLOOD_LIB_MAT)["scenarios"]
    ids = [f"sample_{i+1:04d}" for i in range(len(scen))]
    st = FimStore(STORE)
    attach_fluvial_index(STORE, reorder_index(scen, ids, list(st.storm_id)),
                         ["Q1_villalobos_1_m3s", "Q2_villalobos_2_m3s"],
                         source="flood_library.mat")
    print("fluvial index attached")
