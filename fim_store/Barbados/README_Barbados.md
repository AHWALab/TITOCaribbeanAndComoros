# FIM store folder: Barbados (region key: Barbados)

STATUS: READY. One scenario store per ADM1 parish (11 stores), built by
fim_dev/build_admin_stores.py from the barbados hydrodynamic sample library
and the pcpout rain outputs. Unzip with: python fim_store/unzip_stores.py

    BB01 Christ Church   BB05 Saint John     BB09 Saint Peter
    BB02 Saint Andrew    BB06 Saint Joseph   BB10 Saint Philip
    BB03 Saint George    BB07 Saint Lucy     BB11 Saint Thomas
    BB04 Saint James     BB08 Saint Michael

Each store: 200 scenarios, max depth in meters on the model grid clipped to
the parish (depths from the dmax product, uint8 centimeters, saturated at
2.55 m), extent mask at 0.05 m, and REAL pluvial magnitudes: the storm total
(sum of the pcpout time series, mm) averaged over the parish polygon.
Site configs: fim_config/Barbados_<Parish>.yaml (pluvial only). Country
switch and thresholds: fim_regions["Barbados"] in Caribbean_Comoros_config.py.
magnitudes tables: magnitudes_Barbados_per_unit.json and manifest_Barbados.csv.
