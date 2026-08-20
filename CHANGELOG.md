# Changelog

All notable changes to TITO Caribbean and Comoros will be documented here.

---

## [1.3.0] - 2026-08-20 - IBF static data for the islands, user thresholds, domain fix

### Added

- `ibf_data/Antigua/` and `ibf_data/Barbados/`: complete IBF receptor
  preloads IN the repo, nothing to download. Per country: Overture Maps
  buildings and roads GeoPackage (71,255 buildings and 15,042 road
  segments for Antigua and Barbuda; 204,764 and 31,312 for Barbados),
  admin units with census population (2018 Statistics Division estimates
  for the Antigua parishes, Barbuda 2025 estimate; 2021 Barbados
  Statistical Service estimates), and the GHS BUILT-C functional class
  crop (10 m) for the dasymetric population weights. Sources and counts in
  each `manifest_ibf_<Country>.json` and in the population CSVs.
- `fim_config/ibf/`: 18 island IBF site YAMLs, one per FIM unit site,
  paired by name (`<Site>_ibf.yaml`).
- `fim_dev/build_island_ibf_static.py` and `fim_dev/gen_island_ibf_yamls.py`:
  reproducible builders for the preloads and the YAMLs.
- `Caribbean_Comoros_config.py`: Antigua and Barbados switched on in
  `ibf_regions`. USER defaults made explicit: hazard_flag_cutoff 0.50
  (50 percent likelihood; IBFv1.0 reference runs used 0.30) and severity
  depths equal to the FIM thresholds of each region (islands 10/30/70 cm,
  Guatemala 10/30/76 cm).

### Fixed

- `ibf_utils/domain.py`: the domain buffer was applied in DOMAIN units
  before reprojection, so with EPSG:4326 FIM products the 250 m buffer
  became 250 degrees: the receptor window silently grew to the whole
  country, caches and outputs bloated to every admin unit, and every
  cycle sampled the entire national receptor stock. The buffer is now
  applied after reprojection, in meters. Receptor cache keys carry a
  version salt so stale country-wide caches are not reused; delete
  `outputs/ibf_cache/` on machines that ran IBF before this fix.

---

## [1.2.0] - 2026-08-20 - FIM island stores, IBF in the cycle, no LFS for stores

### Added

- `fim_store/Antigua/` (7 zips) and `fim_store/Barbados/` (11 zips): per
  ADM1 unit scenario stores for Antigua and Barbuda and for Barbados. Each
  administrative unit is its own area of concern with its own zarr store,
  clipped from the 200 hydrodynamic samples of the island models, with real
  pluvial magnitudes (storm totals averaged over the unit polygon). Country
  manifests and per-unit magnitude tables included.
- `fim_config/`: 18 island site YAMLs plus their AOC polygons under
  `fim_config/aoc/`. One YAML per unit; the country key in `fim_regions`
  switches all of a country's units at once.
- `fim_dev/build_admin_stores.py`: reproducible builder for the per-unit
  stores (shapefile + dmax + pcpout in, stores + YAMLs + manifests out).
- `tito_hook.py`: IBF receptor stage chained right after each FIM site run
  (STEP 8). Config gated via `ibf_enabled` / `ibf_regions`; consumes the
  cycle's fresh probability rasters; non-fatal like FIM.
- `Caribbean_Comoros_config.py`: new IBF block (`ibf_enabled`,
  `ibf_regions` with per-region severity thresholds, hazard flag cutoff and
  reporting threshold). Antigua and Barbados switched on in `fim_regions`.

### Changed

- Store zips are now plain git files: `*.zarr.zip` removed from
  `.gitattributes`, and `fim_store/Guatemala/fim_store_SantaInesPetapa_v1.zarr.zip`
  converted from an LFS pointer to a regular file. Download ZIP and plain
  clones now always deliver working stores. The `*.tif` LFS rule is unchanged.
- `fim_utils` version 0.6.0. README.md, README_FIM.md, fim_config/README.md
  and fim_store/README_STORES.md refreshed to match.

---

## [1.1.0] - 2026-08-16 - feature/ibf-receptors (merged to main as PR 3)

### Added

- `tito_utils/ibf_utils/`: impact-based forecasting receptor layer. Consumes the
  probabilistic FIM products (`prob_depth_ge_{tag}.{cycle}.tif`, legacy `qpeprob`
  naming supported with correct unit parsing) and produces per-cycle receptor
  warning products: buildings and roads with per-threshold exceedance
  probabilities, flood-risk-matrix warning classes (Speight et al. 2018 / FGS
  standard) and IBFv1.0-compatible hazard/IWF fields; admin units with exposure
  summaries and impact warning flags. Receptor base (national Overture preload,
  GHS BUILT-C classing, dasymetric census population) is clipped to the FIM
  domain and cached, so warm cycles run in seconds.
- `fim_config/ibf/Guatemala_SantaInesPetapa_ibf.yaml`: region config example.
- `tests/test_ibf_utils.py`: filename/unit parsing regressions, matrix
  invariants, synthetic end-to-end cycle, cache-reuse test.
- tito_env.yml: geopandas + pyogrio (vector IO for ibf_utils).

---

## [1.0.0] - 2026-03-13 - Initial Commit

### Added

- Added HSAF precipitation input support; pipeline can now select between IMERG and HSAF as the QPE source.
- Added GFS for LR (Long Range) forecasting; GFS QPF can be paired with either IMERG or HSAF QPE inputs.
