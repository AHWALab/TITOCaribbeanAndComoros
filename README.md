# TITO — Caribbean and Comoros Regional Deployments

Operational flash-flood forecasting packages for the WMO Caribbean and Comoros project, built on **TITO** (Threading Inputs to Outputs) and the **EF5** distributed hydrologic model, with satellite QPE, ensemble nowcasting/QPF, and flood-inundation mapping (FIM/IBF).

This `main` branch is the repository index — it contains **no code**. Each regional deployment lives on its own branch as a self-contained, runnable package (configuration, orchestrator, EF5 inputs, tests, CI/CD, and documentation).

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Containers](https://img.shields.io/badge/containers-Docker%20%7C%20Apptainer-2496ED.svg)](#get-a-region-running)

---

## Regional branches

| Region | Branch | Grid | QPE → gap-fill → forecast | FIM |
|--------|--------|------|---------------------------|-----|
| Guatemala | [`TITO_Guatemala`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Guatemala) | 900 m + 90 m | STREAM-Sat → SCaMPR → StormLab | 90 m — Santa Ines Petapa, Morales |
| Antigua and Barbuda | [`TITO_Antigua`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Antigua) | 30 m | IMERG → SCaMPR → AROME | 30 m — 7 ADM1 unit stores |
| Barbados | [`TITO_Barbados`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Barbados) | 30 m | IMERG → SCaMPR → StormLab (50 members) | 30 m — 11 parish stores |
| Haiti | [`TITO_Haiti`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Haiti) | 90 m | STREAM-Sat → SCaMPR → StormLab | 90 m — Riviere Grise, La Quinte |
| Comoros | [`TITO_Comoros`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Comoros) | 30 m | HSAF → AROME (warmup always IMERG) | 30 m — 55 ADM3 municipalities |

Each branch README carries the full configuration reference, `EF5_conf/` documentation, output layout, operational procedures, and troubleshooting for that domain.

## Get a region running

```bash
git clone --branch TITO_Guatemala \
  https://github.com/AHWALab/TITOCaribbeanAndComoros.git tito-guatemala
cd tito-guatemala

# 1. Build the Docker images locally (TITO + EF5). First run ~10–15 min.
./container-build.sh

# 2. Apptainer / Singularity hosts only: convert the images to SIF.
./docker-to-apptainer.sh

# 3. One operational cycle
./tito-run.sh operational --regions Guatemala
# Apptainer:
TITO_RUNTIME=apptainer ./tito-run.sh operational --regions Guatemala

# 4. Hourly operations (hh:05 UTC)
./manage_cron.sh install
./manage_cron.sh status
./manage_cron.sh run
```

Windows CMD equivalents are included (`tito-run.cmd`, `load-docker-images.cmd`). No docker image tarballs are distributed through GitHub — every site builds its own images.

## Common conventions

### Pipeline
- One orchestrator invocation per cycle. Resolutions listed in `region_resolution_map` run in order and share a single precipitation preparation.
- Phase A QPE ensemble → Phase B gap-fill → Phase C forecast-as-QPE → FIM → ensemble summaries → retention.
- Warmup precipitation is always **IMERG**, for every region (never HSAF).
- HSAF regions (Comoros) never combine IMERG with HSAF; HSAF gap-fill is for rendering only.
- EF5 states are chained per product with a **48 h lookback**; warmup ends at **T−40 h**; forecast runs never save states.
- FIM runs only after the forecast phase.
- Outputs are cycle-first: `outputs/<YYYYMMDD.HHMMSS>/<region>_<resolution>/`.

### Retention defaults
- EF5 states: 100 h · cycle outputs: 24 h · logs: 100 h.

### EF5 inputs (`EF5_conf/`)
| Folder | Contents |
|--------|----------|
| `basic/` | DEM, flow accumulation, flow direction per resolution |
| `parameters/` | CREST (`Wm`, `b`, `Fc/Ksat`, IM) and kinematic-wave (`alpha`, `beta`, `alpha0`) grids |
| `pet/` | Monthly PET climatology `PET.01.tif` … `PET.12.tif` |
| `templates/` | EF5 control templates and basin lists |
| `states/`, `precip/`, `precipEF5/`, `qpf_store/` | Runtime trees, cleaned after each cycle |

## CI/CD

Every regional branch ships the same automation:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push / pull request | ruff check + format (pinned 0.16.3), shellcheck, pytest |
| `docker.yml` | container input changes | build TITO + EF5 images, import and binary smoke tests |
| `release.yml` | `v*` tag | publish `ghcr.io/<owner>/<repo>/tito-<region>` with provenance and SBOM |

Dependabot keeps GitHub Actions, Docker, and Python dependencies current. Workflow runs for every region are listed at [Actions](https://github.com/AHWALab/TITOCaribbeanAndComoros/actions).

## Data and artifacts

- `outputs/`, EF5 states, and extracted FIM stores are never committed.
- FIM stores ship as `<name>.zarr.zip` (or split `.partNN` archives) and are unzipped locally with `python fim_store/unzip_stores.py`.
- Container images are built locally (`container-build.sh`) or converted for HPC (`docker-to-apptainer.sh`).
- Credentials are never stored in the repository; SMTP, HSAF FTP, and GPM accounts are provided through environment variables (`TITO_SMTP_*`, `TITO_HSAF_FTP_*`, `TITO_GPM_EMAIL`).

## Citation

Robledo Delgado, V., & Vergara, H. (2025). Threading Inputs to Outputs (TITO) (v2.0.0). Zenodo. https://doi.org/10.5281/zenodo.17246491

## Contact

AHWA Laboratory, University of Iowa

- Naman Mehta — naman-mehta@uiowa.edu
- Vanessa Robledo — vanessa-robledodelgado@uiowa.edu
- https://ahwa.lab.uiowa.edu/
