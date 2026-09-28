# fim_store: scenario flood map stores for Guatemala

Layout: fim_store/Guatemala/ (the region key from regions_to_run in
Caribbean_Comoros_config.py). This deployment carries Guatemala only.

    Guatemala/   Santa Ines Petapa store READY and ACTIVE (90m FIM);
                 Morales store READY (see Guatemala/README_Guatemala.md),
                 FIM site not active: the 90m EF5 basin does not yet
                 simulate the Motagua (fim_config/Guatemala_Morales.yaml)

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

Adding a site: upload the store zip to fim_store/Guatemala/, unzip, add the
AOC polygon and the site YAML, and make sure the 90m EF5 basin list writes
the site's boundary gauge series (outputts=true).

Building and indexing stores: fim_dev/build_store_guatemala.py builds a
store from a flood map library; fim_dev/attach_real_magnitudes_santaines.py
is the worked example for attaching the real magnitudes and the fluvial
index. attach_magnitudes re-sorts the store by magnitude and re-links every
per-scenario index, including the fluvial one.
