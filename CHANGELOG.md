# Changelog

All notable changes to the TITO Guatemala deployment package are documented here.

---

## [Unreleased]

### Added

- GitHub Actions CI: ruff check/format, shellcheck, and pytest on every push/PR.
- Docker CI: TITO and EF5 image builds with import/binary smoke tests.
- Tag-based release workflow publishing the TITO image to GHCR plus a GitHub release.
- Dependabot updates for GitHub Actions, Docker, and Python dependencies.

### Changed

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
