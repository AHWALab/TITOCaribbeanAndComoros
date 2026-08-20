# fim_store: scenario flood map stores, one folder per country

Layout: fim_store/<Region>/ where <Region> is the exact region key from
regions_to_run in Caribbean_Comoros_config.py.

    Guatemala/   Santa Ines Petapa store READY (real indexes on both axes);
                 Morales prepared, waiting for its flood map library
    Antigua/     READY: 7 stores, one per ADM1 unit of Antigua and Barbuda
                 (Barbuda AG01 + six Antigua parishes; Redonda has no store,
                 it lies outside both island model domains)
    Barbados/    READY: 11 stores, one per parish
    Comoros/     waiting for analog maps
    Haiti/       waiting for analog maps

Each store is a zarr library of pre-simulated flood maps (max depth and
extent per scenario) carrying the matching indexes: rainfall magnitude per
scenario for the pluvial routine, and where the site is also fluvial the
maximum boundary discharges per scenario. One store serves all routines of
its site; nothing is duplicated. The island stores carry REAL rain
magnitudes: the storm total of each of the 200 samples averaged over the
unit polygon. manifest_<Country>.csv in each island folder lists every
unit, its store zip and its magnitude range.

Workflow: stores travel through git as a single <name>.zarr.zip per site
inside the country folder. These zips are PLAIN git files; LFS is not used
for stores anymore, so plain clones and GitHub Download ZIP always deliver
working files. After every clone or pull that brings a new store, run once:

    python fim_store/unzip_stores.py

It extracts every zip that is not yet unzipped and skips the rest, so it is
always safe to run. The unzipped .zarr folders and all model outputs stay
out of git.

Adding a country or site: the README_ADD_STORE.md inside each waiting
country folder is the five step drop-in checklist (upload zip, unzip, AOC
polygon, site YAML from the template, switch the region on in the main
config).

Building and indexing stores: fim_dev/build_store_guatemala.py builds a
store from a flood map library, with fim_dev/attach_real_magnitudes_santaines.py
as the worked example for attaching real magnitudes and the fluvial index.
fim_dev/build_admin_stores.py rebuilds all island per-unit stores from the
ADM1 shapefile plus the dmax and pcpout rasters of the island models.
