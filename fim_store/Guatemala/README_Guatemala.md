# FIM store folder: Guatemala (region key: Guatemala)

Two sites planned, one live:

1. Santa Ines Petapa (cuenca Villalobos): READY.
   fim_store_SantaInesPetapa_v1.zarr.zip holds the 200 scenario library
   with REAL data on both matching axes (RainyDay storm totals 0 to 1051 mm
   for pluvial; boundary discharges Q1, Q2 for fluvial). Unzip once:
       python fim_store/unzip_stores.py
   Site config: fim_config/Guatemala_SantaInesPetapa.yaml.
   Storm totals table: magnitudes_SantaInesPetapa_real.csv.

2. Morales (Rio Motagua): PREPARED, waiting for its flood map library.
   Its storm totals are already here (magnitudes_Morales_real.csv) and its
   site config ships disabled with the activation checklist written inside
   (fim_config/Guatemala_Morales.yaml). Build the store into this folder as
   fim_store_Morales_v1.zarr.zip when the library arrives.

Region switch and depth thresholds: fim_regions block in
Caribbean_Comoros_config.py.
