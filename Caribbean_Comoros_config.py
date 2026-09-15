domain = "Caribbean_Comoros"
subdomain = "Regional"
# Console: "user" or "debug". Override: export TITO_CONSOLE_VERBOSITY=debug
console_verbosity = "user"

# Resolutions run in this order in one cycle (precip prepared once).
# string: {"Guatemala": "900m"}   list: {"Guatemala": ["900m", "90m"]}
# Layers/templates/states/outputs use {region}_{resolution} (e.g. guatemala_90m).
# FIM runs on 90m only.
region_resolution_map = {"Comoros": "30m"}
regions_to_run = ["Comoros"]

systemModel = "crest"
systemTimestep = 60  # minutes; operational cycle is rounded to this step
systemName = systemModel.upper() + " " + domain.upper() + " " + subdomain.upper()

# Clip box for IMERG / SCaMPR / GFS. StormLab uses its own domain yaml.
xmin = -95.0
xmax = 45.0
ymin = -12.5
ymax = 24.0

# ── EF5 runtime ────────────────────────────────────────────────────────────
# Docker: EF5_RUNTIME=docker → ef5-container:latest
# Apptainer: EF5_RUNTIME=local → EF5/bin/ef5
import os as _os

_ef5_rt = _os.environ.get("EF5_RUNTIME", "").strip().lower()
if _ef5_rt == "docker":
    ef5Path = _os.environ.get("EF5_IMAGE", "ef5-container:latest")
elif _ef5_rt in ("local", "embedded"):
    ef5Path = _os.environ.get("EF5_LOCAL_BIN", "EF5/bin/ef5")
else:
    ef5Path = "EF5/ef5-container.sif"

# ── Paths ──────────────────────────────────────────────────────────────────
statesPath = "EF5_conf/states/"
precipFolder = "EF5_conf/precip/"
imerg_precip_folder = "EF5_conf/precip/imerg/"
hsaf_precip_folder = "EF5_conf/precip/hsaf/"
scampr_precip_folder = "EF5_conf/precip/scampr/"
precipEF5Folder = "EF5_conf/precipEF5/"
templatePath = "EF5_conf/templates/"
templates = "ef5_Comoros_30m_control_template.txt"
basicPath = "EF5_conf/basic/"
parametersPath = "EF5_conf/parameters/"
dataPath = "outputs/"
qpf_store_path = "EF5_conf/qpf_store/"
modelStates = ["crest_SM", "kwr_IR", "kwr_pCQ", "kwr_pOQ"]

# ── Forcing ────────────────────────────────────────────────────────────────
# QPE: STREAM_SAT | IMERG | SCAMPR | HSAF
# QPF: STORMLAB | AROME | GFS | WRF
# String or list. Lists = Cartesian product (ops), each pair with SCaMPR gap:
#   STREAM_SAT + STORMLAB
#   STREAM_SAT + AROME
#   IMERG + STORMLAB
#   IMERG + AROME
#   IMERG + GFS
qpe_source = "HSAF"
qpf_source = "AROME"
# Operational QPE is HSAF. Pair with AROME (default) or GFS.
# Do not combine IMERG with HSAF. Warmup precip is always IMERG.
region_forcing_map = {
    "Comoros": {"qpe_source": "HSAF", "qpf_source": "AROME"},
}

# STREAM-Sat Phase B (ops): "SCAMPR" | "HSAF" | "NONE"
# Hindcast always skips gap-fill regardless of this value.
stream_sat_gap_fill_mode = "NONE"
# HSAF runs through T; no SCaMPR/IMERG gap-fill on the HSAF chain.
qpe_gap_fill_mode = "IMERG_ONLY"
scampr_latency_minutes = 20

# ── Warmup / retention ─────────────────────────────────────────────────────
warmup_enabled = True
warmup_days = 90
imerg_max_workers = 8
clear_precip_after_cycle = True
postprocess_outputs = True
states_keep_hours = 100
outputs_keep_hours = 24
# tito_hourly_*.log and pipeline_*.log under outputs/logs/
logs_keep_hours = 100
warmup_precip_source_map = {
    "Comoros": "IMERG",
}

# ── STREAM-Sat ─────────────────────────────────────────────────────────────
stream_sat_ensemble_size = 10
ef5_max_workers = 1
stream_sat_window_hours = 48
stream_sat_keep_hours = 48
stream_sat_warmup_hours = 12
stream_sat_precip_folder = "EF5_conf/precip/stream_sat/"
stream_sat_output_folder = "outputs/"
stream_sat_state_folder = "EF5_conf/states/stream_sat/"
scampr_state_folder = "EF5_conf/states/scampr/"
scampr_output_folder = "outputs/"
hsaf_state_folder = "EF5_conf/states/hsaf/"
hsaf_output_folder = "outputs/"
stream_sat_tif_naming = "streamsat"
stream_sat_max_workers = None
stream_sat_pipeline_timeout = 7200

# ── StormLab ───────────────────────────────────────────────────────────────
stormlab_repo = "tito_utils/qpf_utils/StormLab-GFS-realtime"
stormlab_nc_root = "tito_utils/qpf_utils/StormLab-GFS-realtime/output"
stormlab_precip_folder = "EF5_conf/precip/stormlab/"
stormlab_output_folder = "outputs/"
stormlab_ensemble_size = 5
stormlab_forcing_members = 5
stormlab_run_pipeline = True
stormlab_source = "auto"
stormlab_min_age_h = 5.0
stormlab_pipeline_timeout = 14400
stormlab_tif_naming = "stormlab"

# ── Alerts ─────────────────────────────────────────────────────────────────
# Credentials can be overridden with env vars (recommended for deployments).
SEND_ALERTS = False
smtp_server = _os.environ.get("TITO_SMTP_SERVER", "smtp.gmail.com")
smtp_port = int(_os.environ.get("TITO_SMTP_PORT", "587"))
account_address = _os.environ.get("TITO_SMTP_USER", "model_alerts@gmail.com")
account_password = _os.environ.get("TITO_SMTP_PASSWORD", "supersecurepassword9000")
alert_sender = "Real Time Model Alert"
alert_recipients = ["fixer1@company.com", "fixer2@company.com"]
copyToWeb = False

# ── Mode ───────────────────────────────────────────────────────────────────
# Operational: HindCastMode = False
# Hindcast: True + HindCastDate; optional HindCastEndDate for hourly range
HindCastMode = False
HindCastDate = "2024-04-27 00:00"
HindCastEndDate = "2024-04-27 00:00"

run_LR = True
LR_timestep = "60u"
QPF_archive_path = "EF5_conf/qpf_store/archive/"
dry_run_hours = 6

# ── FIM ────────────────────────────────────────────────────────────────────
# After Phase C only. 30m Comoros (55 ADM3 municipality stores, pluvial).
fim_enabled = True
fim_config_dir = "fim_config"
fim_default_thresholds_m = [0.10, 0.30, 0.70, 1.00]
fim_regions = {
    "Comoros": {"enabled": True, "thresholds_m": fim_default_thresholds_m},
}

# ── IBF ────────────────────────────────────────────────────────────────────
ibf_enabled = True
ibf_regions = {
    "Comoros": {"enabled": False},  # FIM is on; IBF waits for receptor data
}

# ── NWP archives ───────────────────────────────────────────────────────────
WRF_archive_path = ""
WRF_var_name = "PREC_ACC_C"
WRF_filename_template = "PREC_d01_YYYY-MM-DD_HH_mm_SS.nc"
GFS_precip_path = (
    "/Dedicated/Humberto/Naman/TITO_Caribbean_Comoros_VM/TITOCaribbeanAndComoros/precip/gfs"
)
AROME_precip_path = "EF5_conf/precip/arome/"

# Credentials: set TITO_GPM_EMAIL / TITO_HSAF_FTP_USER / TITO_HSAF_FTP_PASS
# in the environment instead of committing real accounts here.
email_gpm = _os.environ.get("TITO_GPM_EMAIL", "vrobledodelgado@uiowa.edu")
server = _os.environ.get(
    "TITO_IMERG_SERVER", "https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/early/"
)
hsaf_ftp_user = _os.environ.get("TITO_HSAF_FTP_USER", "naman-mehta@uiowa.edu")
hsaf_ftp_pass = _os.environ.get("TITO_HSAF_FTP_PASS", "change_me1234")
hsaf_latency_minutes = 10
