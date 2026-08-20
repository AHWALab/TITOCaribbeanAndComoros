# FIM store folder: Antigua and Barbuda (region key: Antigua)

STATUS: READY. One scenario store per ADM1 administrative unit, built by
fim_dev/build_admin_stores.py from the hydrodynamic sample libraries of the
two island models (antigua and barbuda) and the pcpout rain outputs.

Seven units carry a store (zip per unit, unzip with
python fim_store/unzip_stores.py):

    AG01 Barbuda        from the barbuda island model
    AG03 Saint George   from the antigua island model
    AG04 Saint John's   from the antigua island model
    AG05 Saint Mary     from the antigua island model
    AG06 Saint Paul     from the antigua island model
    AG07 Saint Peter    from the antigua island model
    AG08 Saint Philip   from the antigua island model

AG02 Redonda is outside both island model domains and has no store.

Each store: 200 scenarios, max depth in meters on the model grid clipped to
the unit (depths come from the dmax product, uint8 centimeters, saturated
at 2.55 m), extent mask at 0.05 m, and REAL pluvial magnitudes: the storm
total (sum of the pcpout time series, mm) averaged over the unit polygon.
Site configs: fim_config/Antigua_<Unit>.yaml (pluvial only). Country
switch and thresholds: fim_regions["Antigua"] in Caribbean_Comoros_config.py.
magnitudes tables: magnitudes_Antigua_per_unit.json and manifest_Antigua.csv.
