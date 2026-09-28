# TITO Comoros — Operational Flash Flood Forecasting

**TITO (Threading Inputs to Outputs)** runs the **EF5** hydrologic model with satellite QPE, ensemble nowcasting/QPF and flood inundation mapping for **Comoros**.

This is the production deployment package for the Comoros domain (30m).

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](CHANGELOG.md)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/AHWALab/TITOCaribbeanAndComoros/actions/workflows/ci.yml/badge.svg?branch=TITO_Comoros)](https://github.com/AHWALab/TITOCaribbeanAndComoros/actions/workflows/ci.yml)
[![Docker](https://github.com/AHWALab/TITOCaribbeanAndComoros/actions/workflows/docker.yml/badge.svg?branch=TITO_Comoros)](https://github.com/AHWALab/TITOCaribbeanAndComoros/actions/workflows/docker.yml)
[![Containers](https://img.shields.io/badge/containers-Docker%20%7C%20Apptainer-2496ED.svg)](#1-build-the-images)

---

## Domain defaults

| | |
|--|--|
| Region | `Comoros` |
| Resolution | `30m` |
| Operational chain | STREAM-Sat (10 members) → HSAF gap-fill → StormLab (5 members), `region_forcing_map` |
| Gap-fill | **HSAF** (`stream_sat_gap_fill_mode = "HSAF"`) — the only region not gap-filled with SCaMPR |
| Optional sources | IMERG, AROME, GFS, WRF — via `region_forcing_map` |
| Warmup | IMERG, `warmup_days = 90` (never HSAF) |
| FIM | 30 m, 55 ADM3 municipality sites (pluvial); per-site products + country mosaic |
| IBF | off (`ibf_regions["Comoros"] = False`) until receptor data is delivered |
| EF5 workers | `ef5_max_workers = 4`; the `EF5_MAX_WORKERS` environment variable overrides it |
| State retention | `states_keep_hours = 48` (the 48 h state lookback) |
| Control template | `EF5_conf/templates/ef5_Comoros_30m_control_template.txt` |
| Hindcast example | `2024-04-27 00:00` |

Operational chain for every TITO region is **STREAM-Sat → gap-fill → StormLab**, set per region in `region_forcing_map`. IMERG, AROME, GFS and WRF remain available as options (edit `region_forcing_map`), not the operational default. The top-level `qpe_source` / `qpf_source` values are only the fallback for a region missing from `region_forcing_map`.

- Do not combine IMERG with HSAF; HSAF is the gap-fill between STREAM-Sat and the StormLab forecast.
- FIM stores ship in git as `fim_store/Comoros/*.zarr.zip` (LFS); `./container-build.sh` fetches (Git LFS) and unpacks them automatically — or run `python fim_store/unzip_stores.py Comoros` yourself (`./container-build.sh --stores-only` does just this step).
- Deployment environment variables (all optional): `EF5_MAX_WORKERS` sets EF5 concurrency (forwarded by `tito-run.sh`); `STREAM_SAT_OUTPUT_DIR` / `STREAM_SAT_STATE_DIR` move STREAM-Sat's half-hourly output and noise state out of the code folder (relative = from the project root). A STREAM-Sat noise-state cold start is logged as `STREAM-Sat [<domain>]: noise state COLD START`.

Warmup precipitation is **always IMERG** (never HSAF), for every region.

---

## 1. Build the images

Build **locally first**. Do not ship a docker image tar; each site creates its own images.

```bash
# TITO image + EF5 image (Docker). 10–15 minutes the first time.
./container-build.sh
```

Useful flags: `./container-build.sh --no-ef5` (TITO only), `--no-cache`.

### Apptainer / Singularity environments

After the Docker images exist, convert them:

```bash
./docker-to-apptainer.sh
```

This produces `tito.sif` (and uses `EF5/bin/ef5` inside the SIF — no nested Apptainer). Then:

```bash
TITO_RUNTIME=apptainer ./tito-run.sh operational --regions Comoros
```

HPC helper: `./sif_convert_on_argon.sh`.

---

## 2. Run

```bash
# One operational cycle
./tito-run.sh operational --regions Comoros

# Hourly cron (hh:05 UTC)
./manage_cron.sh install
./manage_cron.sh status
./manage_cron.sh run
./manage_cron.sh remove

# Hindcast
./tito-run.sh hindcast "2024-04-27 00:00" "2024-04-27 00:00" --regions Comoros

# Shell inside the runtime
./tito-run.sh shell
```

Windows CMD: `tito-run.cmd operational --regions Comoros`.

---

## Pipeline

```mermaid
flowchart LR
    A[Precip prep] --> B{States within 48h?}
    B -- no --> W[IMERG warmup]
    B -- yes --> C[Phase A QPE EF5]
    W --> C
    C --> D[Gap fill if configured]
    D --> E[Phase C forecast as QPE]
    E --> F[FIM after forecast]
    E --> G[Summaries + retention]
```

Retention: states 48 h, outputs 24 h, logs 24 h (`Caribbean_Comoros_config.py`).

---

## EF5 configuration (`EF5_conf/`)

### `basic/`
DEM/FAC/FDIR_comoros_30m.tif — DEM, flow accumulation, flow direction. Injected as `{dem}`, `{ddm}`, `{fam}`.

### `parameters/`
CREST_Comoros_30m/, KW_Comoros_30m/ — CREST (`wm_grid`, `b_grid`, `fc_grid`, `im_grid`) and kinematic wave (`alpha_grid`, `beta_grid`, `alpha0_grid`).

### `pet/`
`PET.01.tif` … `PET.12.tif` monthly climatology (mm/d).

### `templates/`
`ef5_Comoros_30m_control_template.txt` plus `basin_list/`. Job builders fill `{TIMEBEGIN}`, `{TIMEWARMEND}`, `{TIMESTATE}`, `{TIMEEND}`, `{OUTPUTPATH}`, `{STATESPATH}`.

### `states/`
Chained per product, 48 h lookback, warmup ends at T−40 h:

```text
EF5_conf/states/
  stream_sat/ensS<N>/comoros_30m/
  scampr/ensS<N>/...
  hsaf/...
  imerg/comoros_30m/
```

### `precip/` and `precipEF5/`
Live staging, wiped after the cycle when `clear_precip_after_cycle = True`.

### `qpf_store/`
`comoros/gfs_data/`, `stormlab_data/ensQ<N>/`, `arome_data/` as applicable.

EF5 runtime: Docker sibling `ef5-container:latest` or Apptainer local `EF5/bin/ef5`.

---

## Outputs

```text
outputs/<YYYYMMDD.HHMMSS>/comoros_30m/
  <product>/          # imerg, stream_sat, scampr, stormlab, hsaf, arome, gfs
  summary/
  fim/<chain>/<Site>/<mode>/   # per-site FIM products (+ <mode>/ mosaic on islands)
  ibf/<Site>/                  # IBF receptor products, when the site has an IBF YAML
logs/
  tito_hourly_<UTC>.log
  pipeline_<cycle>.log
```

FIM stores: unpacked by `./container-build.sh` (Step 0; `--stores-only` to run just that, `--no-stores` to skip), or manually with `python fim_store/unzip_stores.py Comoros`.

---

## CI/CD

| Workflow | Trigger |
|----------|---------|
| `.github/workflows/ci.yml` | push `TITO_Comoros` / `main`, PRs — ruff 0.16.3, shellcheck, pytest |
| `.github/workflows/docker.yml` | container input changes — TITO + EF5 image smoke tests |
| `.github/workflows/release.yml` | `v*` tag — `ghcr.io/<owner>/<repo>/tito-comoros` |

```bash
ruff check . && ruff format --check .
python -m pytest -q
pre-commit install
```

---

## Security

Override credentials with env vars: `TITO_SMTP_*`, `TITO_HSAF_FTP_*`, `TITO_GPM_EMAIL`, `TITO_IMERG_SERVER`. Do not commit real passwords.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| EF5 exit 137 | OOM — lower `ef5_max_workers` or set `EF5_MAX_WORKERS` |
| EF5 exit 127 | Rebuild TITO image (`./container-build.sh --no-ef5`) |
| Cron skipped | `./manage_cron.sh status` — lock still held |
| Missing states | Check 48 h lookback and UTC clock |
| FIM skipped | Wrong resolution (FIM is 30m only for this domain) |

## Cite

Robledo Delgado, V., & Vergara, H. (2025). Threading Inputs to Outputs (TITO) (v2.0.0). Zenodo. https://doi.org/10.5281/zenodo.17246491

## Contact

Naman Mehta — naman-mehta@uiowa.edu
Vanessa Robledo — vanessa-robledodelgado@uiowa.edu
AHWA Laboratory — https://ahwa.lab.uiowa.edu/ — engr-ahwa-lab@uiowa.edu
