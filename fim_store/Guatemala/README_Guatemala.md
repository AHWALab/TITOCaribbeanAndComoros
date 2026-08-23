# fim_store/Guatemala

    fim_store_SantaInesPetapa_v1.zarr.zip   Santa Ines Petapa, cuenca
        Villalobos. READY: real indexes on both axes (rainfall magnitudes
        and fluvial boundary discharges).
    fim_store_Morales_v1.zarr.zip           Morales, Rio Motagua. READY
        for pluvial since v1.5.0: 200 scenarios, max depth at 1 cm
        precision, 5 m grid, EPSG 3857, REAL RainyDay storm totals
        (footprint means, see magnitudes_Morales_real.csv). Shipped as
        split parts (.zarr.zip.part01, ...); unzip_stores.py joins them.
        Fluvial waits for the per scenario boundary discharges.
    magnitudes_SantaInesPetapa_real.csv     magnitude table, Santa Ines
    magnitudes_Morales_real.csv             magnitude table, Morales:
        domain_mean_mm (WRF box mean, original catalog column, reverified
        against the delivered geotiffs at 0.02 percent) and
        footprint_mean_mm (mean over the Morales model domain, the store
        axis used for matching)

After clone or pull: python fim_store/unzip_stores.py
