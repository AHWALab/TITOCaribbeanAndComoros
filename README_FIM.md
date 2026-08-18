# FIM in TITO: probabilistic flood inundation maps from a scenario library

`tito_utils/fim_utils` (v0.5.0) adds flood inundation mapping to the TITO
pipeline. No hydraulic model runs in real time. Instead, each site has a
library of pre simulated flood maps (RainyDay storms run through a hydraulic
model once, offline). At forecast time every EF5 ensemble member is matched
to the closest scenario in that library, and the members then vote pixel by
pixel: the probability that flood depth exceeds a threshold is the fraction
of members whose matched map exceeds it. Products are probability rasters
plus IBF likelihood class rasters (Very Low, Low, Medium, High) that feed
the likelihood axis of the flood risk matrix.

The approach follows Speight et al. (2018, J Flood Risk Management,
doi:10.1111/jfr3.12281) and the offline forecast databases of Bhola et al.
(2018, Geosciences 8:346), with EF5 in the role Grid-to-Grid played in the
Glasgow pilot.

This document is written for whoever operates TITO next. Read this section
and the next two and you can run everything; the rest is reference.

## What is new in v0.5 (August 2026)

1. FIM is switched on and off PER REGION from the main configuration file.
   The `fim_regions` block in `Caribbean_Comoros_config.py` is the only
   place operators touch: `enabled` per region, and `thresholds_m` with the
   depth thresholds in meters (defaults 0.10, 0.30, 0.70, 1.00). The
   thresholds set there override the site YAMLs, so changing them never
   requires editing `tito_utils/fim_utils` or `fim_config`.
2. One store folder per country under `fim_store/`: Guatemala, Antigua
   (Antigua and Barbuda), Barbados, Comoros and Haiti. Every folder holds a
   README_ADD_STORE.md with the five step drop-in checklist, so a country
   activates the day its analog maps are ready, with no code changes.
3. Stores travel as one `<name>.zarr.zip` per site and
   `python fim_store/unzip_stores.py` extracts whatever is not yet
   unzipped, safely and repeatably, after any clone or pull.
4. Default depth thresholds are now 0.10, 0.30, 0.70 and 1.00 m (0.70
   replaces 0.50; product names change accordingly, for example
   `prob_depth_ge_70cm`).

## What was new in v0.4 (August 2026)

1. Two hazard routines instead of one. Pluvial (P) matches each member by
   its rainfall total over the area of concern. Fluvial (F) matches each
   member by its maximum discharge at named upstream boundary gauges, ported
   from the MATLAB standalone prototype and verified bit for bit against its
   outputs. Joint sites also get the combined product (PF): per member, per
   pixel maximum of the two matched maps.
2. Hazards are declared per site in the config. Guatemala sites run pluvial
   plus fluvial plus combined. Sites in other countries run pluvial only.
   Same code, one switch (see "How FIM is activated" below).
3. Depth thresholds are a user input, any list of values in meters. Since
   v0.5 they live in the `fim_regions` block of the main config; current
   default set for all regions: 0.10, 0.30, 0.70, 1.00.
4. Overbank variants of every product. Pixels that are already wet in a near
   zero inflow reference scenario are masked, so the maps read as hazard
   beyond the permanent river channel. Use the overbank maps for impact work.
5. One country can carry several FIM sites. Guatemala has two basins so far:
   Santa Ines Petapa (ready) and Morales (prepared, waiting for its flood
   map library).
6. The Guatemala Santa Ines Petapa scenario store ships WITH the repository
   under `fim_store/`, with real data on both matching axes: RainyDay storm
   totals as pluvial magnitudes (0 to 1051 mm over the area of concern) and
   maximum boundary discharges (Q1, Q2) as the fluvial index.
7. Everything was validated on the 20 to 22 June 2023 hindcast (49 hourly
   cycles): the fluvial routine reached High likelihood 6 to 9 hours before
   the CONRED flood reports in Aldea Santa Ines Petapa on 21 June 2023.

## How FIM is activated, per country and per site

The orchestrator runs FIM as Phase 3, right after the EF5 outputs of a cycle
are ready. Activation is file based, no code changes:

1. A region runs FIM when `fim_config/` holds one or more YAML files whose
   name starts with the region name from `Caribbean_Comoros_config.py`
   (`regions_to_run`). Example: region `Guatemala` picks up both
   `fim_config/Guatemala_SantaInesPetapa.yaml` and
   `fim_config/Guatemala_Morales.yaml`. One YAML = one FIM site, so a
   country with several pilot basins simply has several files.
2. The `fim_regions` block in `Caribbean_Comoros_config.py` is the master
   switch per region and carries the depth thresholds. A region set to
   `enabled: False` there is skipped even if its site YAMLs exist; the
   `thresholds_m` list there overrides every site YAML of the region.
3. Inside each YAML, the `hazards:` block declares what runs at that site:

       hazards:
         pluvial: {enabled: true}                # all sites
         fluvial: {enabled: true, ...}           # Guatemala sites
         # other countries: fluvial: {enabled: false}

   Pluvial only countries set `fluvial: enabled: false` and get pluvial
   products alone. There is a ready template:
   `fim_config/examples/PluvialOnly_country_template.yaml`.
4. A top level line `enabled: false` in a YAML skips that one site
   (that is how `Guatemala_Morales.yaml` ships, until its store is built).
5. No YAML for a region means no FIM there, and the pipeline behaves exactly
   as before. Every FIM error is caught and printed as non fatal; FIM can
   never break the operational forecast.

`fim_config/README.md` is the short operator cheat sheet for this folder.

Standalone runs (HPC hindcasts, experiments, reprocessing) use the same
configs without the orchestrator:

    python -m tito_utils.fim_utils.pipeline_pf \
        --config fim_config/Guatemala_SantaInesPetapa.yaml --cycle 20230621.050000

`--hazard P`, `--hazard F` or `--hazard PF` runs one routine alone. Omit
`--cycle` to process the latest cycle found on disk. Classic v0.2 configs
(no `hazards:` block) keep running through `pipeline_ensemble` unchanged.

## One time setup on a fresh checkout

1. Unzip the shipped stores (once per checkout, and after any pull that
   brings a new store):

       python fim_store/unzip_stores.py

2. Make sure the environment has `zarr` version 3 or newer. It is listed in
   `tito_env.yml`; on an existing environment: `pip install "zarr>=3"`.
3. For the fluvial routine in the operational tree: the Guatemala basin list
   (`templates/basin_list/Guatemala_90m_basin_new.txt`) must write the two
   boundary gauge time series used by the config, which means the gauges
   named `cuenca_villalobos_1` and `cuenca_villalobos_2` must exist there
   with `outputts=true`. The shipped basin list carries generic numbered
   gauges with `outputts=false`, so this is a required one time edit before
   fluvial can see any discharge in production. On the HPC hindcast trees
   the series already exist. If the series are missing, the fluvial routine
   does not crash the pipeline; it reports the missing input for that cycle.
4. Smoke test from the repo root:

       python -c "from tito_utils.fim_utils import run_pf_cycle; print('FIM OK')"
       python fim_dev/make_synthetic.py
       python fim_dev/run_e2e_test.py

   Expected: all 21 checks pass, no external data needed.

## What a cycle produces

For a site with both hazards, under `products_root/<cycle>/`:

    pluvial/               P(depth >= t) and likelihood class, per threshold
    fluvial/               same, from discharge matching
    combined/              same, from the per pixel maximum union
    pluvial_overbank/      the three routines again, with the permanent
    fluvial_overbank/      channel masked out (wet in the reference
    combined_overbank/     scenario); use these for impact reading
    member_decisions.csv   per member: rain total, boundary Q, matched
                           scenarios, matching rules, flags
    trigger_maxuq.csv      max unit streamflow per run checked
    pf_summary.json        full decision log for the cycle

Raster names carry the threshold, for example `prob_depth_ge_30cm.<cycle>.tif`
and `likelihood_class_ge_30cm.<cycle>.tif`. With 4 thresholds and both
hazards a cycle writes 48 rasters plus the three tables. A pluvial only site
writes `pluvial/` and `pluvial_overbank/` alone and no combined product.
Class boundaries are left closed (a probability of exactly 0.20 is Low, not
Very Low).

The trigger gate runs first: if no run of the cycle exceeds the unit
streamflow threshold over the area of concern, the cycle writes only the
trigger table and summary, by design.

## Where things live in the repo

    tito_utils/fim_utils/    the package: store.py (zarr store, both indexes),
                             pluvial.py, fluvial.py, combine.py (the routines),
                             pipeline_pf.py (runner for hazards configs),
                             pipeline_ensemble.py (classic v0.2 runner)
    fim_config/              one YAML per FIM site + aoc/ polygons + examples/
    fim_store/<Region>/      scenario stores (zipped) + magnitude tables,
                             one folder per country (Guatemala, Antigua,
                             Barbados, Comoros, Haiti); versioned INPUTS of
                             the method, they stay in git; unzip_stores.py
                             extracts them
    fim_dev/                 tests, store builder, magnitude attach script,
                             architecture notes; nothing here runs operationally
    README_FIM.md            this file
    orchestrator.py          Phase 3 block only (after EF5, before cleanup)

The package uses only relative imports internally, so it also works copied
into another parent package or folder; the only requirement is that the
folder containing it is importable. Relative paths inside a YAML resolve
against, in order: the `root:` key in the YAML, the `TITO_FIM_ROOT`
environment variable, the launch directory. So stores and outputs can live
on scratch or a shared drive by pointing `root:` or `TITO_FIM_ROOT` there;
nothing assumes a specific install location.

## Manual steps before a NEW site can run (once per site)

1. Build the flood map store from the site's pre simulated library (one
   MaximumDepth GeoTIFF per RainyDay storm):

       python fim_dev/build_store_guatemala.py

   Set `FIM_LIB_DIR`, `FIM_RAINYDAY_DIR`, `FIM_STORE_OUT` or adapt the
   script. The store keeps max depth plus a derived extent mask, one
   compressed chunk per storm; a 200 storm library is about 50 MB and one
   lookup reads one chunk, not the whole catalog.
2. Attach the REAL storm magnitudes (rain totals in mm per scenario), and
   for fluvial sites the boundary discharge index. Use
   `fim_dev/attach_real_magnitudes_santaines.py` as the template. Until this
   is done the store carries placeholder magnitudes, every product is
   flagged `magnitude_source=placeholder`, and quicklooks carry a DEMO
   warning. Never distribute placeholder products.
3. Provide the area of concern polygon: a small GeoJSON in EPSG 4326 (for
   example the library extent plus a 5 km buffer) under `fim_config/aoc/`.
4. Write the site YAML in `fim_config/<Region>_<Site>.yaml`. Start from
   `Guatemala_SantaInesPetapa.yaml` (both hazards) or
   `examples/PluvialOnly_country_template.yaml` (pluvial only). The
   `member.template` placeholders (`{qpf}`, `{ens}`, `{sl}`, ...) are free
   names: every folder combination found on disk for the cycle becomes one
   ensemble member, so the same code handles 1 or 2 deterministic QPF
   branches or 50 StormLab members.
5. For fluvial sites: add the named boundary gauges to the region basin list
   with `outputts=true`, so EF5 writes their time series.
6. Check the EF5 basin mask covers the area of concern. EF5 only writes
   grids inside the basins in the control template; if the AOC falls on
   nodata the sampler expands its window and flags every product. Resolved
   for Guatemala in August 2026 (the guatemala domain includes the cuenca
   Villalobos basin and its gauges; products carry no sampling flags), but
   check it for every new region.
7. Zip the store and commit it under `fim_store/<Region>/` (see the LFS note in
   `.gitattributes`; `*.zarr.zip` is tracked like the parameter tifs).

Current status per site: Santa Ines Petapa has all seven steps done, only
the unzip on each checkout remains. Morales has its magnitudes table ready
(`fim_store/Guatemala/magnitudes_Morales_real.csv`) and waits for its flood map
library; its YAML documents the exact activation steps and ships disabled.

## Things to be careful about

- Placeholder magnitudes (manual step 2). The single most important check
  before trusting a product: `catalog.magnitude_source` in `pf_summary.json`
  must not say `placeholder`. The shipped Santa Ines Petapa store is real on
  both axes.
- In channel depths in the fluvial maps. The library's low flow scenarios
  already hold 30 cm or more inside the river channel, so the raw fluvial
  likelihood shows 1.0 along the channel core even on quiet days. That is
  the river, not overbank hazard. Read impacts from the `*_overbank/`
  products, which mask those pixels.
- Joint forcing ambiguity. The 200 scenarios were simulated with rain and
  inflows together and are indexed both ways, so at low discharges a fluvial
  match can select a scenario whose flooding was rain driven. A future
  library with separated forcings would remove this ambiguity; until then
  treat low flow fluvial maps with care.
- Rainfall double counting. Component totals are summed to one magnitude per
  member. When one branch's `qpeaccum` already contains warm up plus gap
  plus forecast, list other rain sources with `scale: 0.0` (reported, not
  added) or `required: false`.
- Only about 200 scenarios per site. Matching uses banded rules first, then
  nearest with flags. A member far beyond the catalog maximum still returns
  the largest scenario, flagged `beyond_catalog`: treat that map as a lower
  bound. Same logic on the fluvial axis (`beyond_library_q`).
- Coordinate systems differ by design. EF5 grids are geographic (EPSG 4326);
  the stores keep the FIM library grid (Guatemala: EPSG 3857 at 5 m).
  Products are written on the FIM grid; AOC files must be EPSG 4326.
- zarr version 3 is required (`zarr>=3` is in `tito_env.yml`). Storm ids are
  stored as bytes and decoded on read, a v3 unicode quirk. `scipy` is needed
  only if you rebuild the fluvial index from the MATLAB `flood_library.mat`.
- Dry storms are legal. All dry scenarios produce no zarr chunk; the store
  handles them. Do not "fix" a store because chunk counts are below the
  storm count.
- Never commit model outputs or FIM products. `products_root` lives under
  `outputs/`, which is git ignored. The scenario stores are versioned inputs
  and are the one exception that stays in git.

## Testing

- `python fim_dev/make_synthetic.py` then `python fim_dev/run_e2e_test.py`:
  fully synthetic end to end test, 21 checks, no external data. Run it after
  any change.
- `python fim_dev/test_fluvial_parity.py`: bit level parity of the fluvial
  routine against the MATLAB prototype outputs (7 checks; needs the
  prototype folder, paths via `FIM_GT_DATA` and `PROTO_DIR`). The prototype
  reused each StreamSat member index in its StormLab loop; the port matches
  every member and the test documents that difference.
- `python fim_dev/test_guatemala_real.py`: 13 checks against a real outputs
  tree (set `FIM_GT_DATA`).
