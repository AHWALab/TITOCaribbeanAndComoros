# fim_store: scenario flood map stores, one folder per country

Layout: fim_store/<Region>/ where <Region> is the exact region key from
regions_to_run in Caribbean_Comoros_config.py.

    Guatemala/   Santa Ines Petapa store READY (real indexes on both axes);
                 Morales prepared, waiting for its flood map library
    Antigua/     Antigua and Barbuda, waiting for analog maps
    Barbados/    waiting for analog maps
    Comoros/     waiting for analog maps
    Haiti/       waiting for analog maps

Each store is a zarr library of pre-simulated flood maps (max depth and
extent per scenario) carrying the matching indexes: rainfall magnitude per
scenario for the pluvial routine, and where the site is also fluvial the
maximum boundary discharges per scenario. One store serves all routines of
its site; nothing is duplicated.

Workflow: stores travel through git as a single <name>.zarr.zip per site
inside the country folder (tracked via LFS). After every clone or pull that
brings a new store, run once:

    python fim_store/unzip_stores.py

It extracts every zip that is not yet unzipped and skips the rest, so it is
always safe to run. The unzipped .zarr folders and all model outputs stay
out of git.

Adding a country or site: the README_ADD_STORE.md inside each country
folder is the five step drop-in checklist (upload zip, unzip, AOC polygon,
site YAML from the template, switch the region on in the main config).

Building and indexing stores: fim_dev/build_store_guatemala.py builds a
store from a flood map library; fim_dev/attach_real_magnitudes_santaines.py
is the worked example for attaching the real magnitudes and the fluvial
index. attach_magnitudes re-sorts the store by magnitude and re-links every
per-scenario index, including the fluvial one.
