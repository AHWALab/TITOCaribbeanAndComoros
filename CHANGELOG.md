# Changelog

All notable changes to the TITO Haiti deployment package are documented here.

---

## [Unreleased]

### Removed

- Unused config settings `stream_sat_output_folder`, `scampr_output_folder`, `hsaf_output_folder` and `stormlab_output_folder` (left from an older layout; EF5 results follow `dataPath`, i.e. `outputs/<cycle>/<region_res>/<product>/`), and the unused `stream_sat_output_root` builder parameter they fed.

### Added

- `container-build.sh` Step 0 fetches (`git lfs pull`, when the clone only holds LFS pointers) and unpacks the FIM stores, so no separate `unzip_stores.py` run is needed; `--stores-only` runs just that, `--no-stores` skips it. A store problem only warns: it never stops the image build.
- `fim_store/unzip_stores.py` now reports LFS pointer files clearly instead of failing with `BadZipFile`.

### Changed

- EF5 concurrency: the `EF5_MAX_WORKERS` environment variable now overrides `ef5_max_workers` (it used to apply only when the config was `None`), `tito-run.sh` forwards it into Docker/Apptainer, and the config keeps an explicit value. The CPU fallback counts only the CPUs the container may use (affinity + cgroup quota), not the host's.
- `states_keep_hours = 48`, the Phase A state lookback: the longest outage that resumes without a cold start.
- Shell scripts are executable in git (`container-build.sh`, `manage_cron.sh`, ...).

### Added

- Optional `STREAM_SAT_OUTPUT_DIR` / `STREAM_SAT_STATE_DIR` move STREAM-Sat's half-hourly output and noise state out of the code folder (unset = unchanged paths); old NetCDFs there are pruned like the default folder.
- STREAM-Sat `[state]` lines are logged on their own (they fell outside the 50,000-character output tail) and a cold start prints `noise state COLD START`.

### Fixed

- Dockerfile: `|| true` covered the whole `conda env create` chain, so a failed environment build still produced an image; it now fails the build and ends with an import check.

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
- IBF for the 90m FIM basin sites: `ibf_data/Haiti/` (14 GADM adm4 units,
  WorldPop 2025, 704k buildings, 3.4k places, 198 MB, cut from the 2.2 GB
  national package) and `fim_config/ibf/Haiti_Gris_ibf.yaml` and
  `Haiti_LaQuinte_ibf.yaml`. Receptors read the `combined_overbank` grids,
  as in the IBFv1.0 runs. `ibf_regions["Haiti"]` enabled.
- `fim_mosaic_sites = False`: Gris and La Quinte are ~100 km apart on 2 m
  grids.

### Fixed

- README Domain defaults match the config: 900 m + 90 m, STREAM-Sat → SCaMPR → StormLab operational (IMERG/AROME/GFS are options), IBF enabled.
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

### Added

- GitHub Actions CI: ruff check/format, shellcheck, and pytest.
- Docker CI and tag-based GHCR release workflow.
- Production README (build with `container-build.sh`, then `docker-to-apptainer.sh`).

### Changed

- `ibf_data/` and `fim_config/ibf/` hold only this deployment's country (copies of other countries' IBF data and configs removed).
- Pipeline (`orchestrator.py`, `hindcast_manager.py`, `tito_utils/`) aligned with the Guatemala production baseline.
- Config file structure matched to Guatemala; domain-specific forcings, resolution, FIM/IBF kept.
- Credentials overridable via environment variables.
