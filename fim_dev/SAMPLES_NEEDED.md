# Sample files needed to finish and test the FIM framework

STATUS August 2026: satisfied for Guatemala (Santa Ines Petapa store ships
in fim_store/ with real magnitudes and a real fluvial index; Morales waits
only for its flood map library). Kept as the checklist of what a NEW site
must hand over before its store can be built.

The framework already runs end to end on synthetic data
(`python fim_dev/make_synthetic.py` then `python fim_dev/run_e2e_test.py`).
To lock the real formats, drop the following into
`fim_dev/sample_data/real/` (any subfolder layout is fine; small samples
are enough, 2 or 3 items per category).

## A. To build the catalog (offline, per region; Barbados first)

1. **RainyDay storm metadata** for the 200 storms: whatever exists (CSV,
   Excel, netCDF attributes). Minimum per storm: an id and either the 24-h
   total rainfall or the storm rainfall raster. Direction/track metadata if
   available. A sample of 5 to 10 rows is enough to adapt the reader.
2. **2 or 3 hydraulic max-depth rasters** from the simulations, as delivered
   by the model (format, CRS, resolution, nodata, units). If the model also
   writes a max-extent product, include one; otherwise extent is derived
   from depth >= 0.05 m (threshold configurable).
3. **Per-storm 24-h rainfall rasters** for those same 2 or 3 storms (used to
   compute per-AOC magnitudes with the same zonal code the runtime uses).
   If only storm totals exist (no rasters), say so; domain totals work too.
4. **Areas of Concern**:
   - Haiti and Guatemala: the pilot basin polygon(s) (shp/gpkg/geojson).
   - Antigua, Barbados, Comoros: the admin boundaries you want to warn on
     (which level? one file per country, any of shp/gpkg/geojson).
   - The attribute field to use as the unit id.

## B. To test the real-time side

5. **One full EF5 cycle for one region** (ideally a rainy hindcast, e.g.
   2024-07-04): the whole
   `outputs/<Region>/tmp_output_*/<YYYYMMDD.HHMMSS>/` folder(s), so the run
   discovery, trigger and totals are tested against real
   `maxunitq / qpeaccum / qpfaccum` grids, including the dual GFS + AROME
   members. (This is the only must-have on the real-time side.)
6. Optional: a second cycle from a quiet day, to confirm the quiet path.

## C. Decisions to confirm (no files needed)

- UQ trigger threshold 1.0 m3/s/km2: keep or tune per region.
- Rainfall statistic over the AOC: mean (current) or max.
- Bands 0.9-1.2 T (then 0.8-1.3 T): starting values to tune in validation.
- Direction off for v0 (current): switch on once QPF storm motion is
  extracted, catalog directions are already carried.
- Warm-up handling: totals currently use the full qpeaccum grid (5-h warm
  up). If the accumulation window changes to 3 cycles per day, nothing in
  the code changes; only the EF5 run windows do.

## What happens when the samples arrive

1. Adjust `catalog.py` patterns/reader to the real RainyDay metadata.
2. Build `fim_catalog/Barbados/v1` and check the magnitude histogram
   (coverage of the 200 storms).
3. Point `fim_config/Barbados.yaml` at the real outputs folder and run the
   pipeline on the sample cycle.
4. Wire the call into `orchestrator.py` as a post-EF5 step.
