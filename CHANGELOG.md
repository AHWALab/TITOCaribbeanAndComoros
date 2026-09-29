# Changelog

All notable changes to the TITO Comoros deployment package are documented here.

---

## [Unreleased]

### Security

- Credentials come only from the environment: no e-mail or password defaults in `Caribbean_Comoros_config.py` or the STREAM-Sat YAMLs. STREAM-Sat now also reads `TITO_GPM_EMAIL`, so one variable covers the NASA PPS account (`IMERG_PPS_EMAIL` still works).
- `tito-run.sh` loads an optional git-ignored `tito_credentials.env` (see `tito_credentials.env.example`) and passes credentials into Docker/Apptainer by name (`docker -e VAR`, `APPTAINERENV_VAR`), never as values on a command line.
- HSAF downloads pass the FTP password to curl on stdin (`-K -`) instead of `--user user:pass`, which any user could read with `ps`.

### Changed

- `manage_cron.sh` picks the container runtime automatically: an exported `TITO_RUNTIME` still wins (the HPC job scripts export `apptainer`); otherwise Docker when the TITO image is loaded, else Apptainer/Singularity when `tito.sif` is present. No more per-region hard-coded `docker` / `apptainer`.

### Removed

- Unused config settings `stream_sat_output_folder`, `scampr_output_folder`, `hsaf_output_folder` and `stormlab_output_folder` (left from an older layout; EF5 results follow `dataPath`, i.e. `outputs/<cycle>/<region_res>/<product>/`), and the unused `stream_sat_output_root` builder parameter they fed.

### Added

- `container-build.sh` Step 0 fetches (`git lfs pull`, when the clone only holds LFS pointers) and unpacks the FIM stores, so no separate `unzip_stores.py` run is needed; `--stores-only` runs just that, `--no-stores` skips it. A store problem only warns: it never stops the image build.
- `fim_store/unzip_stores.py` added (this branch had none, although the README pointed to it); it reports LFS pointer files clearly instead of failing with `BadZipFile`.

### Changed

- EF5 concurrency: the `EF5_MAX_WORKERS` environment variable now overrides `ef5_max_workers` (it used to apply only when the config was `None`), `tito-run.sh` forwards it into Docker/Apptainer, and the config keeps an explicit value. The CPU fallback counts only the CPUs the container may use (affinity + cgroup quota), not the host's.
- `states_keep_hours = 48`, the Phase A state lookback: the longest outage that resumes without a cold start.
- Shell scripts are executable in git (`container-build.sh`, `manage_cron.sh`, ...).

### Added

- Optional `STREAM_SAT_OUTPUT_DIR` / `STREAM_SAT_STATE_DIR` move STREAM-Sat's half-hourly output and noise state out of the code folder (unset = unchanged paths); old NetCDFs there are pruned like the default folder.
- STREAM-Sat `[state]` lines are logged on their own (they fell outside the 50,000-character output tail) and a cold start prints `noise state COLD START`.

### Fixed

- Dockerfile: `|| true` covered the whole `conda env create` chain, so a failed environment build still produced an image; it now fails the build and ends with an import check.

### Fixed

- FIM stores now ship: the 55 `fim_store/Comoros/*.zarr.zip` (LFS) were never committed because a local `.git/info/exclude` hid `*.zarr.zip`, so a fresh clone had nothing for `fim_store/unzip_stores.py` to extract.
- README Domain defaults match the config: STREAM-Sat → HSAF gap-fill → StormLab is the operational chain (IMERG/AROME/GFS are options).

### Changed

- `ibf_data/` and `fim_config/ibf/` no longer carry other countries' IBF data and configs (Comoros IBF stays off until receptor data exists).

### Added

- GitHub Actions CI: ruff check/format, shellcheck, and pytest.
- Docker CI and tag-based GHCR release workflow.
- Production README (build with `container-build.sh`, then `docker-to-apptainer.sh`).

### Changed

- Pipeline (`orchestrator.py`, `hindcast_manager.py`, `tito_utils/`) aligned with the Guatemala production baseline.
- Config file structure matched to Guatemala; domain-specific forcings, resolution, FIM/IBF kept.
- Credentials overridable via environment variables.
