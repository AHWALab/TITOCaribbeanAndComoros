# fim_store: scenario flood map stores

Layout: fim_store/<Region>/ where <Region> is the exact region key from
regions_to_run in Caribbean_Comoros_config.py.

    Barbados/    READY: 11 stores, one per parish

Each store is a zarr library of pre-simulated flood maps (max depth and
extent per scenario) carrying the matching indexes: rainfall magnitude per
scenario for the pluvial routine, and where the site is also fluvial the
maximum boundary discharges per scenario. One store serves all routines of
its site; nothing is duplicated. The island stores carry REAL rain
magnitudes: the storm total of each of the 200 samples averaged over the
unit polygon. manifest_Barbados.csv lists every unit, its store zip and its
magnitude range.

Workflow: stores travel through git as a single <name>.zarr.zip per site
inside the country folder. These zips are PLAIN git files; LFS is not used
for stores anymore, so plain clones and GitHub Download ZIP always deliver
working files. After every clone or pull that brings a new store, run once:

    python fim_store/unzip_stores.py

It extracts every zip that is not yet unzipped and skips the rest, so it is
always safe to run. The unzipped .zarr folders and all model outputs stay
out of git.

Building and indexing stores: fim_dev/build_store_from_library_zip.py builds
a store from a flood map library. fim_dev/build_admin_stores.py rebuilds the
Barbados per-parish stores from the ADM1 shapefile plus the dmax and pcpout
rasters of the island model.
