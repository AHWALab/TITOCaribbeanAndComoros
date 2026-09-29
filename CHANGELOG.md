# Changelog

All notable changes to the TITO Barbados deployment package are documented here.

---

## [Unreleased]

### Fixed

- Branch brought in line with the running Barbados deployment: `region_forcing_map` is STREAM-Sat + StormLab (was IMERG), `stormlab_ensemble_size = 5` (was 50, i.e. 500 forecast runs per cycle), the 30 m control template writes `MAXSOILMOISTURE` (needed for the `maxsm` summaries), and the StormLab `lesserantilles` parameters are the current set (26 Aug, identical to TITO_Antigua) instead of the 4 Aug training copy.

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

### Changed

- `ibf_data/` and `fim_config/ibf/` hold only Barbados (Antigua IBF data and the other countries' IBF YAMLs removed).
- README Domain defaults match the config: STREAM-Sat → SCaMPR → StormLab is the operational chain (IMERG/AROME/GFS are options); per-site FIM output layout.

### Added

- GitHub Actions CI: ruff check/format, shellcheck, and pytest.
- Docker CI and tag-based GHCR release workflow.
- Production README (build with `container-build.sh`, then `docker-to-apptainer.sh`).

### Changed

- Pipeline (`orchestrator.py`, `hindcast_manager.py`, `tito_utils/`) aligned with the Guatemala production baseline.
- Config file structure matched to Guatemala; domain-specific forcings, resolution, FIM/IBF kept.
- Credentials overridable via environment variables.
