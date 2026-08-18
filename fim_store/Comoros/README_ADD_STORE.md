# FIM store folder: Comoros (region key: Comoros)

STATUS: waiting for the analog flood map library of this country. The paths
and the pipeline are ready; only the data and one small config file are
missing. When the analog maps are ready, activation is a drop-in:

1. Upload the scenario store here as a single zip:
       fim_store/Comoros/fim_store_<SiteName>_v1.zarr.zip
   Build it from the pre-simulated flood map library with
   fim_dev/build_store_guatemala.py, attach the REAL storm magnitudes (and
   the boundary discharge index if the site is also fluvial) with
   fim_dev/attach_real_magnitudes_santaines.py as the template, then zip it
   FROM INSIDE the store folder so the zarr files sit at the zip root:
       cd fim_store_<SiteName>_v1.zarr
       zip -r ../fim_store_<SiteName>_v1.zarr.zip .
2. Unzip once per checkout (also the step every teammate runs after pull):
       python fim_store/unzip_stores.py
3. Put the site's area of concern polygon (EPSG 4326) at
       fim_config/aoc/Comoros_<SiteName>_aoc.geojson
4. Copy fim_config/examples/PluvialOnly_country_template.yaml to
       fim_config/Comoros_<SiteName>.yaml
   and fill the store, aoc and outputs paths. Pluvial only sites keep
   fluvial disabled in the hazards block; sites with boundary discharge
   analogs enable it and list their gauge series (see the Guatemala
   configs as the worked example).
5. Switch the region on in Caribbean_Comoros_config.py:
       fim_regions["Comoros"]["enabled"] = True
   The depth thresholds also live there and apply to every site of the
   region without touching any other file.

A country can hold several sites: one YAML plus one store per site, all in
this folder. The zip stays in git (tracked through LFS by .gitattributes);
the unzipped store and all model outputs stay out of git.
