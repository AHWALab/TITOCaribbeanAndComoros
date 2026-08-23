# fim_store/Haiti: scenario stores for the two Haiti pilot sites

Two analog map libraries arrived in August 2026 and their stores are
built and shipped here. BOTH SITES ARE PREPARED BUT NOT ACTIVE, because
the rain scenario netcdf zips for Haiti contained symlink stubs instead
of data: no real RainyDay storm totals exist yet, so the stores carry
PLACEHOLDER magnitudes (wet volume ranks 1..N, clearly marked in each
store's magnitude_source attribute). Do not switch Haiti on in
fim_regions until real totals are attached.

    fim_store_Haiti_Gris_v1.zarr.zip       Riviere Grise (Port-au-Prince
        plain). 40 of the nominal 200 scenarios were delivered
        (samples 0001..0040); 6 of the 40 are fully dry at the 5 cm
        extent threshold. 2 m grid, EPSG 32618, depths at 1 cm precision.
    fim_store_Haiti_LaQuinte_v1.zarr.zip   La Quinte (Gonaives). 143
        usable scenarios: 144 were delivered, sample_0011 was EXCLUDED
        because its grid differs from the rest (1367x1423 vs 3417x3557);
        samples 93-99 and most of 151-181 are missing from the delivery.
        Shipped as split parts (.zarr.zip.part01, .part02, ...);
        fim_store/unzip_stores.py joins them automatically. 2 m grid,
        EPSG 32618, depths at 1 cm precision.

Only the maximum depth layer of each scenario was kept, as agreed; the
velocity and time step maps of the delivery were not used and are not in
the repo.

To make the sites operational:

1. Real storm totals: magnitude_template_Gris.csv and
   magnitude_template_LaQuinte.csv list every scenario name (from the
   RainyDay file names) and whether the sample is in the store. Fill
   magnitude_mm from the RainyDay side, then attach with
   fim_utils.store.attach_magnitudes (it re-sorts the store).
2. Enable each site YAML (fim_config/Haiti_Gris.yaml,
   Haiti_LaQuinte.yaml) and switch Haiti on in fim_regions.
3. Haiti EF5 domain data (DEM, FAC, FDIR, parameters, basin list,
   control template) is also still needed before cycles produce rain
   inputs for these sites.
