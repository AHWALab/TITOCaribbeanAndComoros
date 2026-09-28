# Changelog

All notable changes to the TITO Antigua and Barbuda deployment package are documented here.

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
- Antigua receptors refreshed from IBF_v10_ANTIGUABARBUDA.zip: Overture
  buildings 71,255 -> 74,801, roads 15,004, new places layer 2,094; the 7
  Antigua IBF YAMLs read places. Census admin layer and GHS crop unchanged;
  previous file in `ibf_data/Antigua/_pre_v10/`.

### Fixed

- FIM stores now ship: the 7 `fim_store/Antigua/*.zarr.zip` (LFS) were never committed because a local `.git/info/exclude` hid `*.zarr.zip`, so a fresh clone had nothing for `fim_store/unzip_stores.py` to extract.
- README Domain defaults match the config: STREAM-Sat → SCaMPR → StormLab is the operational chain (IMERG/AROME/GFS are options), warmup 45 days.
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

### Added

- GitHub Actions CI: ruff check/format, shellcheck, and pytest.
- Docker CI and tag-based GHCR release workflow.
- Production README (build with `container-build.sh`, then `docker-to-apptainer.sh`).

### Changed

- `ibf_data/` and `fim_config/ibf/` hold only this deployment's country (copies of other countries' IBF data and configs removed).
- Pipeline (`orchestrator.py`, `hindcast_manager.py`, `tito_utils/`) aligned with the Guatemala production baseline.
- Config file structure matched to Guatemala; domain-specific forcings, resolution, FIM/IBF kept.
- Credentials overridable via environment variables.
