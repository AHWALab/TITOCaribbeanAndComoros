# Changelog

All notable changes to the TITO Barbados deployment package are documented here.

---

## [Unreleased]

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
