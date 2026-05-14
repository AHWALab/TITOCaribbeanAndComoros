domain = "Caribbean_Comoros"
subdomain = "Regional"
model_resolution = "90m"
regions_to_run = ["Antigua", "Barbados", "Comoros", "Guatemala", "Haiti"]
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
ef5Path = "/Dedicated/Humberto/EF5Binary/EF5V1.2.7/EF5/bin/ef5" 
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
templatePath = "templates/"
templates = "ef5_Antigua_control_template.txt"  # legacy fallback; region templates are auto-selected
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

# HSAF credentials/settings (required only when qpe_source == "HSAF")
hsaf_ftp_user = "naman-mehta@uiowa.edu"
hsaf_ftp_pass = "change_me1234"
hsaf_latency_minutes = 10

# SCaMPR settings (required only when qpe_source == "SCAMPR")
# No credentials needed — data is fetched from the public AWS S3 bucket:
#   s3://noaa-enterprise-rainrate-pds/BLEND/RainRate-Blend-INST/
# pip install boto3 botocore xarray rasterio  (once per environment)
scampr_latency_minutes = 20  # expected product delay in minutes

# ── STREAM-Sat ensemble configuration ──────────────────────────────────────
# Used when qpe_source == "STREAM_SAT" in region_forcing_map.
# STREAM-Sat repo lives inside the TITO directory:
#   TITO_Stream_Sat/STREAM-Sat-realtime/
# The orchestrator auto-resolves paths relative to its own location.
stream_sat_ensemble_size = 10       # number of ensemble members (reduce for testing)
stream_sat_window_hours = 48        # operational window (h) passed to run_pipeline
stream_sat_warmup_hours = 12        # AR(1) warm-up (h) passed to run_pipeline

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
stream_sat_tif_naming = "streamsat"

# Unit conversion factor for STREAM-Sat netCDF → GeoTIFF.
# 1.0 → keep mm/h (EF5 supports mm/h natively).
# 2.0 → convert mm/h to mm/30min (legacy EF5 format).
stream_sat_divide_by = 1.0

# Max parallel workers for STREAM-Sat NC→TIF conversion.
# None → auto-detect (CPU count).
stream_sat_max_workers = None

# Timeout (seconds) for the STREAM-Sat pipeline subprocess.
stream_sat_pipeline_timeout = 7200  # 2 hours

# ── STREAM-Sat gap-fill mode ───────────────────────────────────────────
# When qpe_source == "STREAM_SAT", this controls what happens after the
# STREAM-Sat window ends (T−4h due to IMERG latency):
#
#   "SCAMPR_QPF"   — SCaMPR fills T−4h→T, then QPF (GFS/AROME) T→T+24h
#                    States NOT saved for this phase.
#
#   "SCAMPR_ONLY"  — SCaMPR only (no QPF). States NOT saved.
#
#   "NONE"         — No gap fill. Only STREAM-Sat window is simulated.
#
stream_sat_gap_fill_mode = "SCAMPR_QPF"

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
If Hindcast and LR_mode is True, user MUST define StartLRtime, EndLRTime, LR_timestep,GFS_archive_path
If running in operational mode (Hindcast False) and LR_mode = True, user only have to define LR_timestep, GFS_archive_path
"""
HindCastMode = False 
# Default hindcast run time for regions not listed in region_hindcast_dates.
HindCastDate = "2024-07-04 09:00" #"%Y-%m-%d %H:%M" UTC

# Optional per-region hindcast run time (independent regional pipelines).
# Format: "%Y-%m-%d %H:%M" UTC
region_hindcast_dates = {
	"Antigua": "2024-07-04 09:00",
	"Barbados": "2024-07-04 09:00",
	"Comoros": "2024-07-04 09:00",
	"Guatemala": "2024-07-04 09:00",
	"Haiti": "2024-07-04 09:00",
}

run_LR = True
# In the new flow, LR always starts at each region simulation time.
# StartLRtime/EndLRTime are only used to infer LR duration when HindCastMode=True.
StartLRtime = "2024-07-04 11:00" #"%Y-%m-%d %H:%M" UTC.

# ── QPE Gap-Fill Mode ─────────────────────────────────────────────────────────
# Controls how the IMERG 4-hour latency gap is filled.  Applies to BOTH
# operational real-time runs AND hindcast experiments.
#
#   "IMERG_SCAMPR"  — IMERG base (T−6h → T−4h) + SCaMPR gap fill (T−4h → T).
#                     Converts SCaMPR 10-min instantaneous rates (mm/h) to
#                     30-min accumulations (mm) to match IMERG format.
#                     SCaMPR sourced from NOAA RRQPE S3 bucket (public, no creds).
#                     States saved at T−4h (last real IMERG boundary).
#                     NOWCAST (ML) disabled — SCaMPR fills the gap instead.
#                     Each cycle downloads 2 new IMERG files + fresh SCaMPR.
#
#   "IMERG_HSAF"    — IMERG base + HSAF H40B gap fill (Indian Ocean / Africa).
#                     Requires hsaf_ftp_user/hsaf_ftp_pass credentials.
#                     States saved at T−4h.
#
#   "IMERG_ONLY"    — Only IMERG up to T−4h.  No gap fill.
#                     States saved at T−4h.
#
#   "IMERG_NOWCAST" — IMERG base + ML ConvLSTM nowcast gap fill.
#                     States saved at T−4h; EF5 outputs extend to T.
#
qpe_gap_fill_mode = "IMERG_SCAMPR"

# Backward-compat alias used by hindcast_manager.py.
hindcast_qpe_experiment = qpe_gap_fill_mode

# IMERG-only warmup controls.
# These apply only to IMERG-only EF5 runs:
#   - standalone IMERG_ONLY mode
#   - the IMERG state-building phase inside IMERG_SCAMPR operations
#
# If no usable states are found, TITO falls back to an IMERG-only cold start with:
#   TIME_BEGIN   = simulation_end - post_warmup_duration - warmup_duration
#   TIME_WARMEND = simulation_end - post_warmup_duration
#   TIME_END     = simulation_end
#
# Default example for a 16:00 cycle (IMERG end = 12:00):
#   TIME_BEGIN=04:00, TIME_WARMEND=10:00, TIME_END=12:00
#
# For first-time setup you can enable a longer warmup, e.g. "1month" or "3months".
# That longer warmup is used only when no states are found.
imerg_cold_start_warmup = "6h"
imerg_post_warmup_duration = "2h"
initial_imerg_warmup_enabled = False
initial_imerg_warmup_duration = "1month"

EndLRTime = "2024-07-04 18:00" #"%Y-%m-%d %H:%M" UTC.

# Optional explicit LR duration in hours for hindcast (overrides StartLRtime/EndLRTime difference).
# hindcast_lr_duration_hours = 7
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
