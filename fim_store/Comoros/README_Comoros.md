# FIM store folder: Comoros (region key: Comoros)

STATUS: READY. One scenario store per ADM3 administrative unit
(municipality), built by fim_dev/build_comoros_stores.py from the
hydrodynamic sample libraries of the three island models and from the
RainyDay scenario rain of the three model boxes.

All 55 municipalities of the country carry a store. There is no unit
without one.

    Grande Comore (Ngazidja)   KM2   29 units   1017 km2   from the NE_No1 box
    Anjouan (Ndzouani)         KM1   20 units    427 km2   from the SE_No3 box
    Moheli (Mwali)             KM3    6 units    210 km2   from the SW_No2 box

## Which model box is which island

The three rain boxes are named by compass position, the three depth model
folders by island. The pairing was established from the geographic bounds
of the delivered grids, not from the names, and each island grid sits
fully inside its rain box:

    NE_No1  ->  grande    (Grande Comore, the northern island)
    SE_No3  ->  anjouan   (Anjouan, the eastern island)
    SW_No2  ->  moheli    (Moheli, the southern island)

## What is in a store

200 scenarios, the same 200 sample numbers as the island model library.
Depth is the model maximum depth raster clipped to the municipality plus a
ten cell buffer, in metres on the island model grid (EPSG:5629, 30.57 m),
stored at 1 cm precision. Extent is the 0.05 m mask of that depth. Each
store also carries index.csv and meta.json for reading by eye.

Grid resolution and projection are the island model's own, so products
line up cell for cell with the hydrodynamic output.

## Magnitudes (the matching axis)

The pluvial magnitude of every scenario is the AREA WEIGHTED mean of the
band summed storm total of that scenario's rain geotiff over the
municipality polygon: each rain cell counts in proportion to the share of
the cell inside the polygon. The rain grid is about 3 km and several
Comorian municipalities are only a few rain cells across, so a plain cell
centre mask would bias or empty the smallest units. Coverage of the unit
area by the weighted cells came out between 99.21 and 100.59 percent for
all 55 units.

Magnitudes span roughly 0 to 1030 mm; per unit ranges are in
manifest_Comoros.csv and the full 55 x 200 table is in
magnitudes_Comoros_per_unit.json. Rebuild with
fim_dev/rain_magnitudes_from_geotiffs.py.

Every unit has at least one scenario with essentially no rain over it
(0.00 to 0.01 mm). The driest such scenario is the overbank reference of
the site config; its depth map is the baseline standing water of the unit
and covers between 0.00 and 0.61 percent of the store window at 0.10 m,
so the overbank mask removes permanent water rather than flood signal.

## Coverage, one unit to know about

Mledjele (KM331, Moheli) also administers the Nioumachoua islets off the
south coast. Those islets are outside the Moheli hydrodynamic model
domain, so 4.89 km2 of the commune's 37.17 km2 has no depth data, that is
86.85 percent covered. The mainland part of the commune, 31.90 km2, is
fully inside the model grid. The same note is repeated at the top of
fim_config/Comoros_Mledjele.yaml. Every other municipality is covered in
full; depth_coverage_pct in manifest_Comoros.csv carries the number for
each one.

## Hazards

Pluvial only. The Comoros island models were run with rainfall forcing and
no upstream boundary discharge, so there is no fluvial index in these
stores and fluvial is disabled in every site config.

Site configs: fim_config/Comoros_<Unit>.yaml. Country switch and
thresholds: fim_regions["Comoros"] in Caribbean_Comoros_config.py.
