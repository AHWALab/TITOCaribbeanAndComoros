# TITO — Caribbean and Comoros Regional Deployments

Operational flash-flood forecasting packages for the WMO Caribbean and Comoros project, built on **TITO** (Threading Inputs to Outputs) and the **EF5** distributed hydrologic model, with satellite QPE, ensemble nowcasting/QPF, and flood-inundation mapping (FIM/IBF).

This `main` branch is the repository index — it contains **no code**. Each regional deployment lives on its own branch as a self-contained, runnable package (configuration, orchestrator, EF5 inputs, tests, CI/CD, and documentation).

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Containers](https://img.shields.io/badge/containers-Docker%20%7C%20Apptainer-2496ED.svg)](#get-a-region-running)

---

## Regional branches

| Region | Branch | Grid | QPE → gap-fill → forecast | FIM | IBF |
|--------|--------|------|---------------------------|-----|-----|
| Guatemala | [`TITO_Guatemala`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Guatemala) | 900 m + 90 m | STREAM-Sat → SCaMPR → StormLab | 90 m — Santa Ines Petapa (Morales store ready, site pending) | on — 90 m FIM sites |
| Antigua and Barbuda | [`TITO_Antigua`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Antigua) | 30 m | STREAM-Sat → SCaMPR → StormLab | 30 m — 7 ADM1 unit sites + country mosaic | on — 7 ADM1 units |
| Barbados | [`TITO_Barbados`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Barbados) | 30 m | STREAM-Sat → SCaMPR → StormLab (50 members) | 30 m — 11 parish sites + country mosaic | on — 11 parishes |
| Haiti | [`TITO_Haiti`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Haiti) | 900 m + 90 m | STREAM-Sat → SCaMPR → StormLab | 90 m — Riviere Grise, La Quinte | on — 90 m FIM sites |
| Comoros | [`TITO_Comoros`](https://github.com/AHWALab/TITOCaribbeanAndComoros/tree/TITO_Comoros) | 30 m | STREAM-Sat → **HSAF** → StormLab | 30 m — 55 ADM3 municipality sites + country mosaic | off — no receptor data yet |

Every region runs **STREAM-Sat (10 members) → gap-fill → StormLab (5 members; 50 in Barbados)** operationally, set per region in `region_forcing_map`. The gap-fill is **SCaMPR** everywhere except **Comoros (HSAF)**. IMERG, AROME, GFS and WRF are supported options, not the operational default. On the 90 m grids (Guatemala, Haiti) EF5 runs only the FIM basins, not the whole country.

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
- Comoros uses **HSAF** as the Phase B gap-fill between STREAM-Sat and StormLab (every other region uses SCaMPR); IMERG is never combined with HSAF.
- EF5 states are chained per product with a **48 h lookback**; warmup ends at **T−40 h**; forecast runs never save states.
- FIM runs only after the forecast phase. Each FIM site writes `fim/<chain>/<Site>/`; island regions also merge the sites into a country mosaic `fim/<chain>/<mode>/`.
- IBF (receptor impacts) runs right after each FIM site that has `fim_config/ibf/<Site>_ibf.yaml`, writing `ibf/<Site>/`.
- Outputs are cycle-first: `outputs/<YYYYMMDD.HHMMSS>/<region>_<resolution>/`.

### Retention, warmup and EF5 workers (per region, `Caribbean_Comoros_config.py`)
| Region | EF5 states | Cycle outputs | Logs | Warmup | `ef5_max_workers` |
|--------|-----------|---------------|------|--------|-------------------|
| Guatemala | 48 h | 24 h | 24 h | 45 d | 2 |
| Antigua and Barbuda | 48 h | 24 h | 100 h | 45 d | 4 |
| Barbados | 48 h | 24 h | 100 h | 90 d | 12 |
| Haiti | 48 h | 24 h | 24 h | 90 d | 9 |
| Comoros | 48 h | 24 h | 24 h | 90 d | 4 |

States are kept 48 h to match the Phase A lookback: each cycle warm-starts from the newest state in that window (normally the previous hour's), so 48 h is the longest outage that resumes without a cold start.

### Deployment environment variables (all optional)
| Variable | Effect |
|----------|--------|
| `EF5_MAX_WORKERS` | Concurrent EF5 jobs per phase; overrides `ef5_max_workers` (forwarded by `tito-run.sh`). Size it to the host's memory. |
| `STREAM_SAT_OUTPUT_DIR` | STREAM-Sat half-hourly output folder (default: inside the code tree). Relative = from the project root. |
| `STREAM_SAT_STATE_DIR` | STREAM-Sat noise-state folder, for cross-run continuity (default: inside the code tree). |

A STREAM-Sat noise-state cold start is logged as `STREAM-Sat [<domain>]: noise state COLD START`.

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
- FIM stores ship through Git LFS as `fim_store/<Region>/<name>.zarr.zip` (or split `.partNN` archives); `./container-build.sh` fetches them (`git lfs pull`) and unpacks them in its Step 0 (`--stores-only` runs just that step; manual: `python fim_store/unzip_stores.py <Region>`).
- IBF receptor preloads ship through Git LFS in `ibf_data/<Country>/` (each branch carries only its own country). The IBF team's multi-GB country packages are not in the repository; `fim_dev/build_ibf_preload_v10.py` cuts them down to the FIM basins.
- Container images are built locally (`container-build.sh`) or converted for HPC (`docker-to-apptainer.sh`).
- Credentials are never stored in the repository; SMTP, HSAF FTP, and GPM accounts are provided through environment variables (`TITO_SMTP_*`, `TITO_HSAF_FTP_*`, `TITO_GPM_EMAIL`).

## Citation

Robledo Delgado, V., & Vergara, H. (2025). Threading Inputs to Outputs (TITO) (v2.0.0). Zenodo. https://doi.org/10.5281/zenodo.17246491

## Contact

AHWA Laboratory, University of Iowa

- Naman Mehta — naman-mehta@uiowa.edu
- Vanessa Robledo — vanessa-robledodelgado@uiowa.edu
- https://ahwa.lab.uiowa.edu/
