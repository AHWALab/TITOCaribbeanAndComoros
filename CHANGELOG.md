# Changelog

All notable changes to the TITO Comoros deployment package are documented here.

---

## [Unreleased]

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
