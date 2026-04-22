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
# For Caribbean + Comoros combined, extend to include Comoros (-12 to 45 E, -12 to 13 N):
xmin = -95.0
xmax = 45.0
ymin = -12.0
ymax = 24.0
nowcast_model_name = "convlstm" 
systemName = systemModel.upper() + " " + domain.upper() + " " + subdomain.upper()
ef5Path = "/home/nammehta/EF5Master/EF5/bin/ef5" 
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
    "Antigua":   {"qpe_source": "SCAMPR", "qpf_source": ["GFS", "AROME"]},  # Caribbean — ANTIL domain
    "Barbados":  {"qpe_source": "SCAMPR", "qpf_source": ["GFS", "AROME"]},
    "Guatemala": {"qpe_source": "SCAMPR", "qpf_source": "GFS"},              # No AROME (outside domain)
    "Haiti":     {"qpe_source": "SCAMPR", "qpf_source": ["GFS", "AROME"]},
    "Comoros":   {"qpe_source": "HSAF",   "qpf_source": ["GFS", "AROME"]},  # Indian Ocean — INDIEN domain
}

# HSAF credentials/settings (required only when qpe_source == "HSAF")
hsaf_ftp_user = "naman-mehta@uiowa.edu"
hsaf_ftp_pass = "change_me1234"
hsaf_latency_minutes = 20

# SCaMPR settings (required only when qpe_source == "SCAMPR")
# No credentials needed — data is fetched from the public AWS S3 bucket:
#   s3://noaa-enterprise-rainrate-pds/BLEND/RainRate-Blend-INST/
# pip install boto3 botocore xarray rasterio  (once per environment)
scampr_latency_minutes = 20  # expected product delay in minutes

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

# Email associated to GPM account
email_gpm = 'vrobledodelgado@uiowa.edu'
server = 'https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/early/'
