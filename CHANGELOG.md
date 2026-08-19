# Changelog

All notable changes to TITOWA (TITO West Africa 1km) will be documented here.

---

## [Unreleased] - feature/ibf-receptors

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

## [1.0.0] - 2026-03-13 — Initial Commit

### Added

- Added HSAF precipitation input support; pipeline can now select between IMERG and HSAF as the QPE source.
- Added GFS for LR (Long Range) forecasting; GFS QPF can be paired with either IMERG or HSAF QPE inputs.
