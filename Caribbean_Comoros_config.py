domain = "Caribbean_Comoros"
subdomain = "Regional"
model_resolution = "90m"
# Per-region resolution overrides.
# Barbados uses 30m (higher-res DEM, FAC, FDIR, CREST, KW parameter sets).
region_resolution_map = {"Barbados": "30m"}
regions_to_run = ["Antigua", "Barbados", "Comoros", "Guatemala", "Haiti"]
# regions_to_run = ["Guatemala"]
systemModel = "crest"
systemTimestep = 60 #in minutes

# Coordinates used for generating Nowcast / QPF files.
# For ML-based nowcasting, these coordinates should cover a region of size 518 x 360 pixels.
# These also define the bounding box for SCaMPR GeoTIFF clipping — use the
# tightest box that covers ALL regions you are running.
# For Caribbean-only runs (Antigua, Barbados, Guatemala, Haiti):
#   xmin=-95.0, xmax=-58.0, ymin=9.0, ymax=24.0
# For Caribbean + Comoros combined, extend to include Comoros (-12.5 to 45 E, -12.5 to 13 N):
xmin = -95.0
xmax = 45.0
ymin = -12.5
ymax = 24.0
nowcast_model_name = "convlstm" 
systemName = systemModel.upper() + " " + domain.upper() + " " + subdomain.upper()
# ── EF5 container configuration ─────────────────────────────────────────────
# Docker partners:   EF5_RUNTIME=docker  → ef5-container image via docker.sock
# Apptainer partners: EF5_RUNTIME=local → glibc binary EF5/bin/ef5 (NO nesting)
# Host SIF fallback:  EF5/ef5-container.sif when Apptainer is available on host
import os as _os
_ef5_rt = _os.environ.get("EF5_RUNTIME", "").strip().lower()
if _ef5_rt == "docker":
    ef5Path = _os.environ.get("EF5_IMAGE", "ef5-container:latest")
elif _ef5_rt in ("local", "embedded"):
    ef5Path = _os.environ.get("EF5_LOCAL_BIN", "EF5/bin/ef5")
else:
    ef5Path = "EF5/ef5-container.sif"

# Legacy binary paths (no longer used):
# ef5Path = "/Dedicated/Humberto/EF5Binary/EF5V1.2.7/EF5/bin/ef5"
# ef5Path = "/home/nammehta/EF5Master/EF5/bin/ef5"
statesPath = "states/"
# Legacy combined precip folder (kept for backward compatibility).
precipFolder = "precip/"

# Source-specific precip roots (recommended).
# The orchestrator creates per-region subfolders inside these roots.
imerg_precip_folder = "precip/imerg/"
hsaf_precip_folder = "precip/hsaf/"
scampr_precip_folder = "precip/scampr/"  # SCaMPR — public AWS S3, no credentials needed
precipEF5Folder = "precipEF5/"
modelStates = ["crest_SM", "kwr_IR", "kwr_pCQ", "kwr_pOQ"]
# Required state layers EF5 must find together at one timestamp.
# find_available_states() checks ALL of these exist (non-empty) before warm-start.
templatePath = "templates/"
templates = "ef5_Antigua_control_template.txt"  # legacy fallback ONLY if ef5_<Region>_control_template.txt is missing
# Prefer per-region files: templates/ef5_Guatemala_control_template.txt (auto-selected)
basicPath = "basic/"
parametersPath = "parameters/"
dataPath = "outputs/"
qpf_store_path = 'qpf_store/'
# Note: the orchestrator writes QPF working files to per-region folders:
# qpf_store/<region>/gfs_data/ and qpf_store/<region>/wrf_data/
tmpOutput = dataPath + "tmp_output_" + systemModel + "/"

# QPE source configuration.
# Options: "IMERG" (default), "HSAF", "SCAMPR"
qpe_source = "IMERG"

# Default QPF source for LR control generation.
# Options: "GFS" (default), "WRF", "AROME", or a list e.g. ["GFS", "AROME"]
qpf_source = "GFS"

# Optional per-region forcing override.
# Keys are region names from regions_to_run.
# Values can use either qpe/qpf or qpe_source/qpf_source keys.
# Example:
# region_forcing_map = {
#     "Antigua":   {"qpe_source": "SCAMPR", "qpf_source": "GFS"},  # Caribbean — SCaMPR
#     "Barbados":  {"qpe_source": "SCAMPR", "qpf_source": "GFS"},
#     "Guatemala": {"qpe_source": "SCAMPR", "qpf_source": "GFS"},
#     "Haiti":     {"qpe_source": "SCAMPR", "qpf_source": "GFS"},
#     "Comoros":   {"qpe_source": "HSAF",   "qpf_source": "WRF"},  # Africa — HSAF
# }
region_forcing_map = {
    "Antigua":   {"qpe_source": "STREAM_SAT", "qpf_source": ["GFS", "AROME"]},  # Caribbean — ANTIL domain
    "Barbados":  {"qpe_source": "STREAM_SAT", "qpf_source": ["GFS", "AROME"]},
    "Guatemala": {"qpe_source": "STREAM_SAT", "qpf_source": "GFS"},              # No AROME (outside domain)
    "Haiti":     {"qpe_source": "STREAM_SAT", "qpf_source": ["GFS", "AROME"]},
    "Comoros":   {"qpe_source": "STREAM_SAT", "qpf_source": ["GFS", "AROME"]},  # Indian Ocean — INDIEN domain

    # "Guatemala": {"qpe_source": "STREAM_SAT", "qpf_source": "GFS"},              # STREAM-SAT ensemble for web app

    # All regions: IMERG base QPE (up to T−4h) + SCaMPR gap fill (T−4h → T)
    # controlled by qpe_gap_fill_mode = "IMERG_SCAMPR" below.
    # Dual QPF: one EF5 run with GFS, one with AROME (where available).
    #
    # ── STREAM-Sat ensemble mode ──────────────────────────────────────────
    # To use STREAM-Sat ensemble QPE, set qpe_source to "STREAM_SAT":
    #   "Antigua": {"qpe_source": "STREAM_SAT", "qpf_source": ["GFS", "AROME"]},
    # This will:
    #   1. Run STREAM-Sat pipeline → ensemble NetCDF precip files
    #   2. Convert each member to GeoTIFFs in precip/stream_sat/ensP1..ensPN
    #   3. Run EF5 for each ensemble member (STREAM-Sat QPE → SCaMPR+QPF gap fill)
    #   4. Save states at end of STREAM-Sat window (T−4h) per ensemble member
    # See stream_sat_ensemble_size below for the number of members.
}

# ── STREAM-Sat gap-fill mode ───────────────────────────────────────────
# When qpe_source == "STREAM_SAT", controls post-STREAM-Sat behavior:
#
#   "SCAMPR_QPE"   — SCaMPR QPE fills ss_end→T, then QPF (GFS/AROME) T→T+24h
#                    States NOT saved for this phase.
#
#   "SCAMPR_ONLY"  — SCaMPR QPE only (no QPF). States NOT saved.
#
#   "NONE"         — No gap fill. Only STREAM-Sat window is simulated.
#
stream_sat_gap_fill_mode = "SCAMPR_QPE"

# SCaMPR settings (required only when qpe_source == "SCAMPR")
# No credentials needed — data is fetched from the public AWS S3 bucket:
#   s3://noaa-enterprise-rainrate-pds/BLEND/RainRate-Blend-INST/
# pip install boto3 botocore xarray rasterio  (once per environment)
scampr_latency_minutes = 20  # expected product delay in minutes

# ── Warmup configuration ───────────────────────────────────────────────────
# When enabled, if no EF5 states exist within 48 hours of the current cycle
# time, a warmup EF5 run is triggered BEFORE the normal operational cycle.
# The warmup simulates from (cycle_time - warmup_days days) to
# (cycle_time - 40 hours), saving states at the end.
# From the next cycle onward, states should exist and warmup will be skipped.
# This applies to BOTH hindcast and operational modes.

warmup_enabled = True              # set to True to enable warmup

# Duration of the warmup simulation in days.
# The simulation starts at (cycle_time - warmup_days days) and ends at
# (cycle_time - 40 hours), saving states at (cycle_time - 40 hours).
# Default: 10 days if not specified.
warmup_days = 5

# Per-region precipitation source for warmup runs.
# Options: "IMERG" (default if region not listed), "HSAF"
# Warmup precip is downloaded only for missing files (skip-existing logic).
# Example:
# warmup_precip_source_map = {
#     "Antigua":   "HSAF",
#     "Barbados":  "IMERG",
#     "Comoros":   "HSAF",
#     "Guatemala": "IMERG",
#     "Haiti":     "IMERG",
# }
warmup_precip_source_map = {
    "Antigua":   "IMERG",
    "Barbados":  "IMERG",
    "Comoros":   "IMERG",
    "Guatemala": "IMERG",
    "Haiti":     "IMERG",
}

# ── STREAM-Sat ensemble configuration ──────────────────────────────────────
# Used when qpe_source == "STREAM_SAT" in region_forcing_map.
# STREAM-Sat repo lives inside the TITO directory:
#   TITO_Stream_Sat/STREAM-Sat-realtime/
stream_sat_ensemble_size = 10      # ← USER-TUNABLE (use 2 for test, 10 for ops)

# ── Informational only (STREAM-Sat pipeline internals — do not treat as knobs) ──
# These are passed through to STREAM-Sat run_pipeline; values below match the
# STREAM-Sat defaults. Prefer changing STREAM-Sat's own config if needed.
stream_sat_window_hours = 48        # operational window (h) — STREAM-Sat controlled
stream_sat_warmup_hours = 12        # AR(1) warm-up (h) — STREAM-Sat controlled

# Where STREAM-Sat GeoTIFFs (one folder per member) are written.
# The orchestrator appends the domain name automatically:
#   precip/stream_sat/caribbean/ensP1/, ensP2/, ...  (Caribbean regions)
#   precip/stream_sat/comoros/ensP1/, ensP2/, ...    (Comoros)
# This keeps Caribbean and Comoros precip isolated.
stream_sat_precip_folder = "precip/stream_sat/"

# Where STREAM-Sat ensemble outputs are written.
# Each member gets: outputs/stream_sat/ensOut1/<region>/
stream_sat_output_folder = "outputs/stream_sat/"

# Where STREAM-Sat ensemble states are saved per member.
# Each member gets: states/stream_sat/ensS1/<region>/
stream_sat_state_folder = "states/stream_sat/"

# STREAM-Sat GeoTIFF naming convention (EF5 forcing name pattern).
# Files are named: streamsat.qpe.YYYYMMDDHHUU.mmhInst.tif
# Unit: mm/h (native, no conversion needed — EF5 supports mm/h)
stream_sat_tif_naming = "streamsat"

# Max parallel workers for STREAM-Sat NC→TIF conversion.
# None → auto-detect (CPU count).
stream_sat_max_workers = None

# Timeout (seconds) for the STREAM-Sat pipeline subprocess.
stream_sat_pipeline_timeout = 7200  # 2 hours

#Alerts configuration
SEND_ALERTS = False
smtp_server = "smtp.gmail.com"
smtp_port = 587
account_address = "model_alerts@gmail.com"
account_password = "supersecurepassword9000"
alert_sender = "Real Time Model Alert" # can also be the same as account_address
alert_recipients = ["fixer1@company.com", "fixer2@company.com", "panic@company.com",...]
copyToWeb = False

#Simulation times 
"""
- **HindCastMode:** If you are running an event that happened in the PAST, set `HindCastMode = True` and write the date of interest in `HindCastDate`, use the format "YYYY-MM-DD HH:MM". If you want to run it in Nowcast Mode (meaning TITO will start running in the present time) set `HindCastMode = False`.

- **HindCastEndDate:** When `HindCastMode = True`, set `HindCastEndDate` to run multiple hourly cycles from `HindCastDate` → `HindCastEndDate`. Leave as empty string "" for a single-cycle hindcast.

If Hindcast and LR_mode is True LR_timestep,GFS_archive_path
If running in operational mode (Hindcast False) and LR_mode = True, user only have to define LR_timestep, GFS_archive_path
"""
HindCastMode = False
# Hindcast start time (used when HindCastMode=True)
HindCastDate = "2026-07-22 00:00"  # "%Y-%m-%d %H:%M" UTC
        
# Hindcast end time (optional; if set, runs hourly from HindCastDate → HindCastEndDate)
# Leave as empty string "" for single-cycle hindcast.
HindCastEndDate = "2026-07-23 20:00"  # "%Y-%m-%d %H:%M" UTC

run_LR = True
LR_timestep = "60u"
QPF_archive_path = "qpf_store/archive/"  # legacy; kept for back-compat

# WRF configuration (used when run_LR=True).
# Set WRF_archive_path to the folder containing WRF netCDF files.
# Leave empty ("") to skip WRF and fall back directly to GFS.
WRF_archive_path = ""                               # e.g. "/data/wrf_output/"
WRF_var_name = "PREC_ACC_C"                         # precipitation variable name in WRF netCDFs
WRF_filename_template = "PREC_d01_YYYY-MM-DD_HH_mm_SS.nc"  # WRF filename pattern

# GFS configuration (used when run_LR=True and WRF not available).
# GFS tifs are stored here persistently and reused across cycles.
# The orchestrator writes to per-region subfolders under this root.
GFS_precip_path = "/Dedicated/Humberto/Naman/TITO_Caribbean_Comoros_VM/TITOCaribbeanAndComoros/precip/gfs"                     # persistent GFS tif archive root

# AROME configuration (used when qpf_source includes "AROME").
# AROME tifs are stored per-region under this root as a cache.
# Domain routing is automatic: ANTIL for Caribbean, INDIEN for Comoros.
AROME_precip_path = "precip/arome/"                  # persistent AROME tif cache root

# ── ConvLSTM nowcast domains (used only when qpe_gap_fill_mode == "IMERG_NOWCAST") ──
# Defines per-basin bounding boxes used BOTH for IMERG downloads AND for the
# ConvLSTM run when qpe_gap_fill_mode == "IMERG_NOWCAST".
# Each bbox must be ≥ 51.6° wide × 36.0° tall (the model's 516×360 px input).
# At 0.1°/px those minimums give exactly 516×360 with no centre-crop needed.
#
# Has NO effect in IMERG_SCAMPR / IMERG_HSAF / IMERG_ONLY modes since
# NOWCAST is disabled and IMERG uses the global bbox (xmin/xmax/ymin/ymax).
nowcast_domains = {
    "caribbean": {
        "regions": ["Antigua", "Barbados", "Guatemala", "Haiti"],
        "xmin": -95.0, "xmax": -43.4, "ymin": -6.0, "ymax": 30.0,
    },
    "comoros": {
        "regions": ["Comoros"],
        "xmin": 17.0, "xmax": 68.6, "ymin": -12.0, "ymax": 24.0,
    },
}

# Email associated to GPM account
email_gpm = 'vrobledodelgado@uiowa.edu'
server = 'https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/early/'

# HSAF credentials/settings (required only when qpe_source == "HSAF")
hsaf_ftp_user = "naman-mehta@uiowa.edu"
hsaf_ftp_pass = "change_me1234"
hsaf_latency_minutes = 10
