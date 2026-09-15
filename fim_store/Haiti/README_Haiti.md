# FIM store folder: Haiti (region key: Haiti)

STATUS: READY and ACTIVE since v1.8.0. Two basin stores, both with ALL 200
scenarios and both matching on pluvial rain AND on fluvial boundary
discharge, the same setup as the Guatemala basins. Unzip with:
python fim_store/unzip_stores.py

    fim_store_Haiti_Gris_v1.zarr.zip       Riviere Grise, Port-au-Prince plain
                                           200 scenarios, 7160 x 4995 at 2 m
                                           (50 real maps + 150 placeholders)
    fim_store_Haiti_LaQuinte_v1.zarr.zip   La Quinte, Gonaives
                                           200 scenarios, 3417 x 3557 at 2 m
                                           (all real)

Both ship as split parts; unzip_stores.py joins them first. Grid EPSG:32618
(WGS 84 / UTM zone 18N), extent mask at 0.05 m.

## Why the previous Haiti tables looked empty

The first Haiti rain delivery was symlink stubs, so the first build carried
placeholder RANK magnitudes and both site YAMLs were switched off on
purpose. That is exactly what the reviewer saw as an empty magnitude_mm
column and disabled configs. The second delivery is complete and real, and
everything here is rebuilt from it: REAL pluvial magnitudes for all 200
scenarios at both sites (RainyDay scenario rain, area weighted over the
model footprint, coverage 99.36 and 99.38 percent) and REAL fluvial
indexes (per scenario maximum CREST discharge; Gris one gauge, La Quinte
two, no gauge is nan anywhere).

## Store format (since v1.8.0)

Depth is stored as uint16 CENTIMETRES with a depth_scale attribute of
0.01; FimStore.depth() applies the scale, so every consumer keeps seeing
float32 metres and nothing else changed. The source data is stored at 1 cm
precision either way, so this is lossless relative to the previous format
and about a third smaller (half the raw bytes, and quantized integers
compress better than the float32 encoding of the same values, with zstd
level 19). Older stores without the attribute read exactly as before.

Why split parts at all: GitHub refuses any single file over 100 MB and
this repo deliberately avoids LFS, so every store zip over 100 MB travels
as .partNN pieces. unzip_stores.py joins them automatically, so on disk it
is always exactly ONE .zarr folder per domain.

## GRIS PLACEHOLDERS, PLEASE READ

Only 50 of the 200 Gris flood maps were delivered (samples 0001 to 0050).
By request the store still holds all 200 scenarios so the full pipeline
runs now: the 150 undelivered scenarios carry a COPY of sample_0004's map
(a real delivered Gris flood, 146,026 wet pixels, 2.63 m max depth) as a
stand in. Their magnitudes and discharges are real; only the MAP is
borrowed. They are listed in the store attribute placeholder_scenarios and
marked placeholder_copy_of_sample_0004 in the store's index.csv and in
magnitudes_Gris.csv, so it is always visible which maps are real.
PRODUCTS MATCHED TO A PLACEHOLDER SCENARIO SHOW sample_0004's FLOODING,
NOT THE SCENARIO'S OWN. When the remaining maps arrive, rerun
fim_dev/build_haiti_stores.py and nothing else changes.

## Depths: only the maximum depth layer

The two deliveries total 457 GB, almost all of it the output-time-maps
archives. Only MaximumDepth.tif inside each sample's MaxVeloc-dept.zip is
needed, so the build read those members straight out of the delivery zips
by byte range (11.2 GB actually read) and never extracted the rest. The
kept layers are archived as compact georeferenced GeoTIFFs (uint16
centimetres, verified pixel exact) in FIM_version Data under
Haitii/max_depth_only, which replaces the two delivery zips; the full
originals remain on ownCloud. Scripts: fim_dev/haiti_extract/.

## Delivery notes

- GRIS: four of the 50 delivered maps (samples 0003, 0010, 0027, 0028) are
  byte identical and fully dry. sample_0010 is the overbank reference.
- LA QUINTE: sample_0011 arrived on a 1367 x 1423 grid at 5 m instead of
  3417 x 3557 at 2 m; same origin and same extent, so it is a coarser
  rendering of the same domain and it is resampled nearest neighbour onto
  the 2 m site grid (noted in the store's resampling_notes attribute).
- LA QUINTE: two pairs of scenarios are byte identical in the delivery,
  0002 with 0007 and 0181 with 0182.
- Maximum depths reach 16.9 m at Gris and 12.6 m at La Quinte. Delivered
  values, carried through unchanged; worth a sanity look from the
  modelling side.

Full tables: magnitudes_Gris.csv and magnitudes_LaQuinte.csv (200 rows
each: storm_id, scenario_name, magnitude_mm, map_status, per gauge Qmax).
Site configs: fim_config/Haiti_Gris.yaml and fim_config/Haiti_LaQuinte.yaml.
Country switch and thresholds: fim_regions["Haiti"] in
Caribbean_Comoros_config.py.

## Still needed before cycles produce anything

Haiti EF5 domain data (DEM, FAC, FDIR, CREST and KW parameters, basin
list, control template). FIM only fires on EF5 unit discharge, and the
basin list must write the gauge series with outputts=true so the runtime
member folders contain ts.cuenca_griss.crest.<cycle>.csv and the two
ts.cuenca_laquinta_*.crest.<cycle>.csv files.
