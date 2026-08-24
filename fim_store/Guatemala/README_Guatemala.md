# FIM store folder: Guatemala (region key: Guatemala)

STATUS: READY. Two basin stores, both matching on pluvial rain AND on
fluvial boundary discharge. Unzip with: python fim_store/unzip_stores.py

    fim_store_SantaInesPetapa_v1.zarr.zip    200 scenarios, pluvial + fluvial
    fim_store_Morales_v1.zarr.zip            200 scenarios, pluvial + fluvial
                                             (ships as five parts)

Each store: max depth per scenario at 1 cm precision on the model grid,
extent mask at 0.05 m, one pluvial index (magnitude_mm) and one fluvial
index (fluvial_q) inside the same store, so both hazards share one set of
depth chunks.

## Morales, since v1.7.0

Pluvial magnitudes are REAL RainyDay storm totals, the mean of each
scenario's 72 band rain geotiff over the Morales model domain footprint
(column footprint_mean_mm in magnitudes_Morales_real.csv).

The fluvial index is the per scenario MAXIMUM CREST discharge delivered in
GUATEMALA_outputs_Q_MOTAGUA.zip, stored in the store's storm order and
matched by standardized nearest neighbour, the same method as Santa Ines
Petapa.

DATA ISSUE. The delivery carries two gauges per scenario, but
ts.cuenca_motagua_1.crest.csv has NO discharge at all in any of the 200
scenarios: Discharge, SM, Fast Flow and Slow Flow are nan on every row and
only Precip and PET are filled, which is the signature of a gauge point
outside the routed basin. The index is therefore built on cuenca_motagua_2
alone and fim_config/Guatemala_Morales.yaml lists only that gauge. Listing
a gauge that returns nan would make the matcher discard the member with a
missing_discharge flag and silently drop the fluvial map. When gauge 1 is
fixed upstream, rebuild the index with both columns and add the series back
to the YAML.

The Guatemala basin list must write the gauge series with outputts=true so
that runtime member folders contain ts.cuenca_motagua_2.crest.<cycle>.csv.

Country switch and thresholds: fim_regions["Guatemala"] in
Caribbean_Comoros_config.py.
