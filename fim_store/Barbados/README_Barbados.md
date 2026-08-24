# FIM store folder: Barbados (region key: Barbados)

STATUS: READY. One scenario store per ADM1 parish (11 stores), built by
fim_dev/build_admin_stores.py from the barbados hydrodynamic sample library.
Unzip with: python fim_store/unzip_stores.py

    BB01 Christ Church   BB05 Saint John     BB09 Saint Peter
    BB02 Saint Andrew    BB06 Saint Joseph   BB10 Saint Philip
    BB03 Saint George    BB07 Saint Lucy     BB11 Saint Thomas
    BB04 Saint James     BB08 Saint Michael

Each store: 200 scenarios, max depth in meters on the model grid clipped to
the parish (depths from the dmax product, uint8 centimeters, saturated at
2.55 m) and extent mask at 0.05 m.

## Magnitudes (the matching axis), updated August 2026

Since v1.7.0 the pluvial magnitude of every scenario is taken from the
RainyDay SCENARIO RAIN GEOTIFFS delivered for the barbados island model
(200 scenarios, 72 bands, 0.027 degree grid). The magnitude of a parish is
the AREA WEIGHTED mean of the band summed storm total over the parish
polygon: each rain cell counts in proportion to the share of the cell
inside the polygon. That matters here because the rain grid is about 3 km
while the smallest parish covers under 3 rain cells; a plain cell centre
mask would bias or empty them. Coverage of the parish area came out at
99.79 to 100.42 percent. Rebuild with
fim_dev/rain_magnitudes_from_geotiffs.py.

Until v1.7.0 the magnitudes came from pcpout, the rain the hydrodynamic
model itself applied. The two agree closely, which is a useful mutual
validation: correlation 1.000 for every parish, median difference 1.80 to
2.16 percent, largest single difference 27 mm on totals of hundreds of mm,
with the source rain slightly higher throughout. The switch was made
because the real time side matches against QPE and QPF rainfall totals, so
the store index should be the same physical quantity (source rainfall), not
the model's internal applied field. Both columns are kept for provenance in
magnitudes_Barbados_pcpout_vs_rain.csv.

Ranges per parish are in manifest_Barbados.csv, full tables in
magnitudes_Barbados_per_unit.json. One scenario per parish has zero rain
over the parish and can never be matched by a positive rain total; that is
the overbank reference scenario of the site configs.

Site configs: fim_config/Barbados_<Parish>.yaml (pluvial only). Country
switch and thresholds: fim_regions["Barbados"] in Caribbean_Comoros_config.py.
