# Changelog

All notable changes to the TITO Guatemala deployment package are documented here.

---

## [Unreleased]

### Added

- IBF: optional `places` receptor layer (Overture points of interest, IBFv1.0
  v10): sampled and classified like buildings, `places_ibf` output layer,
  `places_count` / `res_*_places_count` / `hzrd_*_places_count` per admin
  unit (not part of the IWF flags, as in v10).
- `fim_dev/build_ibf_preload_v10.py` + `ibf_preload_jobs_v10.json`: cut an IBF
  team country package (IBF_v10_*.zip) to the admin units touching the FIM
  sites (kept whole), with normalized `ADM_ID` / `ADM_NAME` / `population`.
- `ibf_data/` bind-mounted in `tito-run.sh` / `tito-run.cmd`, so receptor data
  updates need no image rebuild; `ibf_data/*.zip` excluded from the image.
- IBF for the 90m FIM basin sites: `ibf_data/Guatemala/` (8 municipios, INE
  2018 census, 656k buildings, 196 MB, cut from the 6.3 GB national package)
  and `fim_config/ibf/Guatemala_SantaInesPetapa_ibf.yaml` and
  `Guatemala_Morales_ibf.yaml` (runs once the Morales FIM site is enabled).
  Receptors read the `combined_overbank` grids, as in the IBFv1.0 runs.
- `fim_mosaic_sites = False`: 90m sites are separate basins.

### Fixed

- Morales FIM store now ships as `fim_store/Guatemala/fim_store_Morales_v1.zarr.zip.part01..05` (LFS); it was never committed.
- README gains the Domain defaults table and matches the config: 900 m + 90 m, STREAM-Sat → SCaMPR → StormLab operational (IMERG/AROME/GFS are options), IBF enabled.
- FIM: 90m sites no longer ingest the 900m run's members. `{rkey}` in the
  member / rain / trigger templates was globbed as a wildcard, so with
  `region_resolution_map = ["900m", "90m"]` every cycle fed both
  `<cycle>/<region>_900m/` and `_90m/` into the 90m ensemble (100 members
  with 50 duplicated ids, half with coarse rain and NaN gauge discharge).
  `tito_hook._pin_rkey` pins it to the resolution being processed.
- FIM: every site now writes its own product folder
  `outputs/<cycle>/<rkey>/fim/<chain>/<Site>/<mode>/` (port of the Barbados
  hook). Sites of one region used to share `fim/<chain>/`, so each site
  overwrote the previous one's grids and `pf_summary.json`. New switch
  `fim_mosaic_sites` merges the site grids (max) into `fim/<chain>/<mode>/`
  after the cycle; the mode list now includes `combined_overbank`.
- IBF sampling vectorized (`ibf_utils.sampling`): same cells as the per-feature
  rasterize loop (100 % agreement on real Haiti buildings, roads and places;
  regression test), 30 to 150 times faster. The loop cost ~2 ms per geometry,
  tens of minutes per cycle on the dense 90m sites.
- The Santa Ines Petapa IBF YAML pointed at `../IBFv10_Guatemala/`, at a
  `guatemala_overture_roads` layer that does not exist (the package layer is
  `guatemala_overture_segments`) and at `CODIGO`, which is not unique (the
  three lakes all carry 0).

### Added

- GitHub Actions CI: ruff check/format, shellcheck, and pytest on every push/PR.
- Docker CI: TITO and EF5 image builds with import/binary smoke tests.
- Tag-based release workflow publishing the TITO image to GHCR plus a GitHub release.
- Dependabot updates for GitHub Actions, Docker, and Python dependencies.

### Changed

- `fim_store/` holds Guatemala only (placeholder folders of the other regions removed; README updated with the real Santa Ines Petapa / Morales status).
- `ibf_data/` and `fim_config/ibf/` hold only this deployment's country (copies of other countries' IBF data and configs removed).
- Whole codebase formatted and linted with ruff 0.16.3; the same version is pinned
  in `pyproject.toml`, pre-commit, and CI.
- Credentials in `Caribbean_Comoros_config.py` (SMTP, HSAF FTP, GPM email) can be
  overridden with environment variables instead of being committed.
- Fixed undefined `log_dir` in the IMERG+StormLab Phase C job builder
  (`tito_utils/ef5/jobs/builders.py`).
- Updated stale timeline and region-plan tests to the current contracts
  (AROME rejected in hindcast, cycle-first outputs).

## [1.0.0] - 2026-03-13 — Initial Commit

### Added

- Added HSAF precipitation input support; pipeline can now select between IMERG and HSAF as the QPE source.
- Added GFS for LR (Long Range) forecasting; GFS QPF can be paired with either IMERG or HSAF QPE inputs.
