# Changelog

All notable changes to TITO Caribbean and Comoros will be documented here.

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
