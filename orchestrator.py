"""
Real-time model/subdomain execution script

This is an IMERG-based operational system that integrates either Ml routines or 
NWP outputs from public available sources to produce a flash flood forecast in real time. 


Contributors:
Vanessa Robledo - vrobledodelgado@uiowa.edu
Humberto Vergara - humberto-vergaraarrieta@uiowa.edu
V.2.0 - October 01, 2025

Please use this script and a configuration file as follows:

    $> python orchestrator.py <configuration_file.py>

"""

from shutil import rmtree, copy
import os
from os import makedirs, listdir, rename, remove
import glob
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import threading
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor, as_completed as _as_completed
import numpy as np
import re
import subprocess
import sys
from tito_utils.file_utils import cleanup_precip, cleanup_nowcast_qpe, cleanup_staged_precip_folders, newline
from tito_utils.qpe_utils import get_new_precip, get_new_hsaf_precip, get_new_scampr_precip
from tito_utils.qpf_utils import run_convlstm, download_GFS, GFS_searcher, WRF_searcher, AROME_searcher, get_arome_domain_for_region 
from tito_utils.ef5 import prepare_ef5, run_ef5_simulations_parallel
print(">>> Modules imported")

"""
Setup Environment Variables for Linux Shared Libraries and OpenMP Threads (PARA USAR ML de AGRHYMET)

"""

def main(args):
    """Main function of the script.
    
    This function reads the real-time configuration script, makes sure the necessary files to run EF5 exist and are in the right place, runs the model(s), writes the outputs and states, and reports vie email if an error occurs during execution.
    
    Arguments:
        args {list} -- the first argument ([1]) corresponds to a real-time configuration file.
    """
    ###-------------------------- SETTING SECTION --------------------------------
    #set true of False to fill 4h imerg latency and create +2h hours (nowcast)
    NOWCAST = True 
    
    # Read the configuration file from command line argument
    # Usage: python orchestrator.py <configuration_file.py>
    import importlib
    config_module_name = os.path.splitext(os.path.basename(args[1]))[0] if len(args) > 1 else 'Caribbean_Comoros_config'
    config_file = importlib.import_module(config_module_name)
    print(">>> Config file loaded")

    #Configuration file
    domain = config_file.domain
    subdomain = config_file.subdomain
    xmin = config_file.xmin
    ymin = config_file.ymin
    xmax = config_file.xmax
    ymax = config_file.ymax
    systemModel = config_file.systemModel
    model_resolution = getattr(config_file, "model_resolution", "90m")
    regions_to_run = getattr(config_file, "regions_to_run", [subdomain])
    if isinstance(regions_to_run, str):
        regions_to_run = [regions_to_run]
    regions_to_run = [str(region).strip() for region in regions_to_run if str(region).strip()]
    if not regions_to_run:
        raise ValueError("No regions were configured to run. Set regions_to_run in the config.")
    systemName = config_file.systemName
    systemTimestep = config_file.systemTimestep
    ef5Path = config_file.ef5Path
    precipFolder = getattr(config_file, "precipFolder", "precip/")
    imerg_precip_root = getattr(config_file, "imerg_precip_folder", precipFolder)
    hsaf_precip_root = getattr(config_file, "hsaf_precip_folder", precipFolder)
    statesPath = config_file.statesPath
    precipEF5Folder = config_file.precipEF5Folder
    modelStates = config_file.modelStates
    templatePath = config_file.templatePath
    template = config_file.templates
    region_template_map = getattr(config_file, "region_template_map", {})
    basicPath = getattr(config_file, "basicPath", "basic/")
    parametersPath = getattr(config_file, "parametersPath", "parameters/")
    nowcast_model_name = config_file.nowcast_model_name
    dataPath = config_file.dataPath
    qpf_store_path = config_file.qpf_store_path
    tmpOutput = config_file.tmpOutput
    SEND_ALERTS = config_file.SEND_ALERTS
    alert_recipients = config_file.alert_recipients
    HindCastMode = config_file.HindCastMode
    HindCastDate = config_file.HindCastDate
    region_hindcast_dates = getattr(config_file, "region_hindcast_dates", {})
    LR_run = config_file.run_LR
    LR_TimeStep = config_file.LR_timestep
    GFS_archive_path = config_file.QPF_archive_path  # legacy fallback
    WRF_archive_path = getattr(config_file, "WRF_archive_path", "")
    WRF_var_name = getattr(config_file, "WRF_var_name", "PREC_ACC_C")
    WRF_filename_template = getattr(config_file, "WRF_filename_template", "PREC_d01_YYYY-MM-DD_HH_mm_SS.nc")
    GFS_precip_path = getattr(config_file, "GFS_precip_path", GFS_archive_path)
    AROME_precip_path = getattr(config_file, "AROME_precip_path", "precip/arome/")
    email_gpm = config_file.email_gpm
    server = config_file.server
    qpe_source = getattr(config_file, "qpe_source", "IMERG").strip().upper()
    qpf_source_default = getattr(config_file, "qpf_source", "GFS").strip().upper()
    region_forcing_map = getattr(config_file, "region_forcing_map", {})
    hsaf_ftp_user = getattr(config_file, "hsaf_ftp_user", "")
    hsaf_ftp_pass = getattr(config_file, "hsaf_ftp_pass", "")
    hsaf_latency_minutes = int(getattr(config_file, "hsaf_latency_minutes", 20))
    scampr_precip_root = getattr(config_file, "scampr_precip_folder", "precip/scampr/")
    scampr_latency_minutes = int(getattr(config_file, "scampr_latency_minutes", 20))
    smtp_config = {
        'smtp_server': config_file.smtp_server,
        'smtp_port': config_file.smtp_port,
        'account_address': config_file.account_address,
        'account_password': config_file.account_password,
        'alert_sender': config_file.alert_sender}

    def _parse_datetime_utc(date_text, label):
        try:
            return datetime.strptime(str(date_text), "%Y-%m-%d %H:%M")
        except Exception as exc:
            raise ValueError(f"Invalid datetime for {label}: {date_text}. Expected format YYYY-MM-DD HH:MM") from exc

    def _round_cycle_time(input_time):
        if systemTimestep == 30:
            minutes = int(np.floor(input_time.minute / 30.0) * 30)
        elif systemTimestep == 60:
            minutes = 0
        else:
            step = max(1, int(systemTimestep))
            minutes = int(np.floor(input_time.minute / float(step)) * step)
        return input_time.replace(minute=minutes, second=0, microsecond=0)

    def _with_sep(path_value):
        return os.path.join(path_value, "")

    def _normalize_qpe_source(value, fallback):
        candidate = str(value).strip().upper()
        if candidate in {"IMERG", "HSAF", "SCAMPR"}:
            return candidate
        return fallback

    _VALID_QPF_SOURCES = {"GFS", "WRF", "AROME"}

    def _normalize_qpf_sources(value, fallback):
        """Normalise QPF source(s) to a list. Accepts a string or a list/tuple.

        Examples
        --------
        "GFS"            → ["GFS"]
        ["GFS", "AROME"] → ["GFS", "AROME"]
        "UNKNOWN"        → [fallback]
        """
        if isinstance(value, (list, tuple)):
            result = []
            for v in value:
                c = str(v).strip().upper()
                if c in _VALID_QPF_SOURCES:
                    result.append(c)
            return result if result else [fallback.upper()]
        candidate = str(value).strip().upper()
        if candidate in _VALID_QPF_SOURCES:
            return [candidate]
        return [fallback.upper()]

    region_qpe_sources = {}
    region_qpf_requested = {}
    for region in regions_to_run:
        region_cfg = {}
        if isinstance(region_forcing_map, dict):
            region_cfg = region_forcing_map.get(region, {})
        if not isinstance(region_cfg, dict):
            region_cfg = {}

        region_qpe_sources[region] = _normalize_qpe_source(
            region_cfg.get("qpe_source", region_cfg.get("qpe", qpe_source)),
            qpe_source,
        )
        # qpf_source may now be a list (e.g. ["GFS", "AROME"]) — always stored as list
        _default_qpf_list = _normalize_qpf_sources(qpf_source_default, qpf_source_default)
        region_qpf_requested[region] = _normalize_qpf_sources(
            region_cfg.get("qpf_source", region_cfg.get("qpf", qpf_source_default)),
            qpf_source_default,
        )

    requested_qpe_sources = set(region_qpe_sources.values())
    imerg_needed = "IMERG" in requested_qpe_sources
    
    newline(2)
    
    region_cycle_times = {}
    if HindCastMode:
        default_hindcast_time = _round_cycle_time(_parse_datetime_utc(HindCastDate, "HindCastDate"))
        for region in regions_to_run:
            region_time_text = default_hindcast_time.strftime("%Y-%m-%d %H:%M")
            if isinstance(region_hindcast_dates, dict) and region in region_hindcast_dates:
                region_time_text = region_hindcast_dates[region]
            region_cycle_times[region] = _round_cycle_time(
                _parse_datetime_utc(region_time_text, f"region_hindcast_dates[{region}]")
            )
        print("*** Starting hindcast run cycle (region-specific timestamps) ***")
        for region in regions_to_run:
            print(f"    {region}: {region_cycle_times[region].strftime('%Y-%m-%d_%H:%M')} UTC")
        newline(2)
    else:
        realtime_cycle_time = _round_cycle_time(datetime.now(timezone.utc))
        for region in regions_to_run:
            region_cycle_times[region] = realtime_cycle_time
        print(f"*** Starting real-time run cycle at {realtime_cycle_time.strftime('%Y-%m-%d_%H:%M')} UTC ***")
        newline(2)

    if LR_run:
        if HindCastMode:
            hindcast_lr_hours = getattr(config_file, "hindcast_lr_duration_hours", None)
            if hindcast_lr_hours is not None:
                lr_duration = timedelta(hours=float(hindcast_lr_hours))
            else:
                start_lr = _parse_datetime_utc(config_file.StartLRtime, "StartLRtime")
                end_lr = _parse_datetime_utc(config_file.EndLRTime, "EndLRTime")
                lr_duration = end_lr - start_lr
                if lr_duration.total_seconds() <= 0:
                    raise ValueError("EndLRTime must be later than StartLRtime in hindcast mode.")
        else:
            lr_duration = timedelta(hours=24)
    else:
        lr_duration = timedelta(0)

    # NOWCAST is used for IMERG to fill the 4-hour latency gap up to currentTime.
    # It must run even when LR is enabled so the QPE window is complete before QPF takes over.
    # Disable NOWCAST only if no region needs IMERG.
    if not imerg_needed:
        NOWCAST = False

    ###-------------------------- START EF5 SECTION --------------------------------
    print("***_________Preparing EF5 runs for all configured regions_________***")

    # ── Step 1: Pre-compute all region-specific config (pure computation, no I/O) ──────
    region_configs = {}
    for region in regions_to_run:
        region_key = region.lower()
        region_current_time = region_cycle_times[region]
        output_timestamp_str = region_current_time.strftime("%Y%m%d.%H%M%S")
        _qpe = region_qpe_sources[region]
        _qpf_req = region_qpf_requested[region]

        template_candidate = f"ef5_{region}_control_template.txt"
        region_template = region_template_map.get(region, template_candidate)
        region_template_path = os.path.join(templatePath, region_template)
        if not os.path.isfile(region_template_path):
            region_template = template
            region_template_path = os.path.join(templatePath, region_template)
        if not os.path.isfile(region_template_path):
            raise FileNotFoundError(
                f"Template not found for region {region}: expected {os.path.abspath(region_template_path)}"
            )

        precip_root = (
            imerg_precip_root if _qpe == "IMERG"
            else hsaf_precip_root if _qpe == "HSAF"
            else scampr_precip_root
        )
        region_precip_folder = _with_sep(os.path.join(precip_root, region_key))
        region_qpf_store_path = _with_sep(os.path.join(qpf_store_path, region_key))
        region_gfs_archive_path = _with_sep(os.path.join(GFS_precip_path, region_key))
        region_arome_archive_path = _with_sep(os.path.join(AROME_precip_path, region_key))
        region_states_path = os.path.join(statesPath, region_key)
        region_data_path = os.path.join(dataPath, region_key)
        region_tmp_output = os.path.join(region_data_path, f"tmp_output_{systemModel}")

        # IMERG has a 4-hour latency: EF5 can only simulate up to (cycle_time - 4h).
        # State and warm-end timestamps must reflect this offset so the next cycle
        # can locate the states written by the current run.
        # SCaMPR and HSAF have no meaningful latency, so they use cycle_time directly.
        _imerg_offset = timedelta(hours=4) if _qpe == "IMERG" else timedelta(0)

        if LR_run:
            r_start_lr = region_current_time
            r_end_lr = r_start_lr + lr_duration
            r_end_time = r_end_lr + timedelta(hours=6)
            r_state_end = region_current_time - _imerg_offset
            r_warm_end = region_current_time - _imerg_offset
            r_qpf = _qpf_req        # list of QPF sources, resolved in the worker
        else:
            r_start_lr = region_current_time
            r_end_lr = region_current_time
            r_end_time = region_current_time
            r_qpf = []              # no QPF in QPE-only mode
            r_state_end = region_current_time - _imerg_offset
            r_warm_end = region_current_time - _imerg_offset

        region_configs[region] = {
            "region_key":           region_key,
            "region_current_time":  region_current_time,
            "output_timestamp_str": output_timestamp_str,
            "qpe_source":           _qpe,
            "qpf_source":           r_qpf,          # list; may be empty for QPE-only
            "qpf_requested":        _qpf_req,        # list (same as r_qpf when LR_run)
            "region_precip_folder": region_precip_folder,
            "region_qpf_store_path": region_qpf_store_path,
            "region_gfs_archive_path": region_gfs_archive_path,
            "region_arome_archive_path": region_arome_archive_path,
            "region_states_path":   region_states_path,
            "region_data_path":     region_data_path,
            "region_tmp_output":    region_tmp_output,
            "region_template":      region_template,
            "r_start_lr":           r_start_lr,
            "r_end_lr":             r_end_lr,
            "r_end_time":           r_end_time,
            "r_state_end":          r_state_end,
            "r_warm_end":           r_warm_end,
            # system_start: 30min earlier than the warm/state target so find_available_states
            # has a small search window.  For IMERG this is already offset -4h via r_warm_end.
            "r_system_start":       r_warm_end - timedelta(minutes=30),
            "r_fail_time":          r_warm_end - timedelta(hours=6),
            "cycle_time_key":       region_current_time.strftime("%Y%m%d%H%M"),
        }

    # ── Step 2: GFS pre-download — once per unique cycle_time (deduplication) ──────────
    # In real-time mode all regions share the same cycle_time_key → one download serves all.
    # In hindcast mode with different per-region dates, each unique time downloads once.
    # WRF-requested regions are skipped here (WRF resolution happens in the worker).
    gfs_shared_data_folders = {}   # cycle_time_key → absolute path to gfs_data/ folder

    def _copy_shared_gfs_to_region(shared_gfs_data: str, region_qpf_store: str) -> None:
        from shutil import copy2
        dest = os.path.join(region_qpf_store, "gfs_data")
        makedirs(dest, exist_ok=True)
        for src_f in glob.glob(os.path.join(shared_gfs_data, "*.tif")):
            try:
                copy2(src_f, dest)
            except Exception as _ce:
                print(f"    Warning: could not copy GFS file {os.path.basename(src_f)}: {_ce}")

    if LR_run:
        gfs_groups = {}   # cycle_time_key → lead region cfg (first seen)
        for region in regions_to_run:
            cfg = region_configs[region]
            # Include GFS and WRF (WRF may fall back to GFS at runtime)
            if any(s in cfg["qpf_requested"] for s in ("GFS", "WRF")):
                key = cfg["cycle_time_key"]
                if key not in gfs_groups:
                    gfs_groups[key] = cfg

        for cycle_key, lead_cfg in gfs_groups.items():
            shared_archive = _with_sep(GFS_precip_path)
            shared_store   = _with_sep(os.path.join(qpf_store_path,   "_shared", cycle_key))
            makedirs(shared_archive, exist_ok=True)
            makedirs(shared_store,   exist_ok=True)
            num_regions_using = sum(
                1 for r in regions_to_run
                if region_configs[r]["cycle_time_key"] == cycle_key
                and any(s in region_configs[r]["qpf_requested"] for s in ("GFS", "WRF"))
            )
            print(f"***_________Downloading shared GFS for cycle {cycle_key} "
                  f"(shared by {num_regions_using} region(s))_________***")
            try:
                GFS_searcher(
                    shared_archive,
                    shared_store,
                    lead_cfg["r_start_lr"],
                    lead_cfg["r_end_lr"],
                    xmin, xmax, ymin, ymax,
                )
                gfs_shared_data_folders[cycle_key] = os.path.join(shared_store, "gfs_data")
            except Exception as _gfs_pre_exc:
                print(f"    Shared GFS download failed for {cycle_key}: {_gfs_pre_exc}. "
                      f"Regions will attempt individual downloads.")

    # ── AROME shared pre-download (one per cycle × domain) ──────────────────────────────
    arome_shared_data_folders = {}   # (cycle_time_key, domain) → path to arome_data/

    def _copy_shared_arome_to_region(shared_arome_data: str, region_qpf_store: str) -> None:
        from shutil import copy2
        dest = os.path.join(region_qpf_store, "arome_data")
        makedirs(dest, exist_ok=True)
        for src_f in glob.glob(os.path.join(shared_arome_data, "*.tif")):
            try:
                copy2(src_f, dest)
            except Exception as _ce:
                print(f"    Warning: could not copy AROME file {os.path.basename(src_f)}: {_ce}")

    if LR_run:
        arome_groups = {}   # (cycle_key, domain) → lead region cfg (first seen)
        for region in regions_to_run:
            cfg = region_configs[region]
            if "AROME" not in cfg["qpf_requested"]:
                continue
            try:
                domain = get_arome_domain_for_region(region)
            except ValueError:
                print(f"    AROME: region '{region}' has no AROME domain configured — skipping.")
                continue
            key = (cfg["cycle_time_key"], domain)
            if key not in arome_groups:
                arome_groups[key] = cfg

        for (cycle_key, domain), lead_cfg in arome_groups.items():
            shared_arome_store = _with_sep(
                os.path.join(qpf_store_path, "_shared_arome", cycle_key, domain)
            )
            makedirs(shared_arome_store, exist_ok=True)
            num_arome_regions = sum(
                1 for r in regions_to_run
                if region_configs[r]["cycle_time_key"] == cycle_key
                and "AROME" in region_configs[r]["qpf_requested"]
            )
            print(f"***_________Downloading shared AROME ({domain}) for cycle {cycle_key} "
                  f"(shared by {num_arome_regions} region(s))_________***")
            try:
                AROME_searcher(
                    shared_arome_store,
                    shared_arome_store,
                    lead_cfg["r_start_lr"],
                    lead_cfg["r_end_lr"],
                    xmin, xmax, ymin, ymax,
                    domain,
                )
                arome_shared_data_folders[(cycle_key, domain)] = os.path.join(
                    shared_arome_store, "arome_data"
                )
            except Exception as _arome_pre_exc:
                print(f"    Shared AROME download failed for ({cycle_key}, {domain}): "
                      f"{_arome_pre_exc}. Regions will attempt individual downloads.")

    # ── Step 3: Parallel per-region forcing prep ─────────────────────────────────────
    _lock = threading.Lock()
    staged_precip_folders = set()
    region_imerg_folders_used = []
    ef5_jobs = []

    def _prepare_one_region(region):
        cfg = region_configs[region]
        region_key          = cfg["region_key"]
        region_current_time = cfg["region_current_time"]
        output_timestamp_str = cfg["output_timestamp_str"]
        local_qpe_source    = cfg["qpe_source"]
        qpf_source_list     = cfg["qpf_source"]    # list of QPF sources ([] when QPE-only)
        qpf_requested       = cfg["qpf_requested"]  # same list
        region_precip_folder   = cfg["region_precip_folder"]
        region_qpf_store_path  = cfg["region_qpf_store_path"]
        region_gfs_archive_path = cfg["region_gfs_archive_path"]
        region_arome_archive_path = cfg["region_arome_archive_path"]
        region_states_path  = cfg["region_states_path"]
        region_data_path    = cfg["region_data_path"]
        region_tmp_output   = cfg["region_tmp_output"]
        region_template     = cfg["region_template"]
        r_start_lr   = cfg["r_start_lr"]
        r_end_lr     = cfg["r_end_lr"]
        r_end_time   = cfg["r_end_time"]
        r_state_end  = cfg["r_state_end"]
        r_warm_end   = cfg["r_warm_end"]
        r_system_start = cfg["r_system_start"]
        r_fail_time    = cfg["r_fail_time"]
        cycle_time_key  = cfg["cycle_time_key"]

        for dirpath in [region_precip_folder, region_qpf_store_path,
                        region_gfs_archive_path, region_arome_archive_path,
                        region_states_path, region_data_path]:
            makedirs(dirpath, exist_ok=True)

        print(f"***_________Preparing forcings for {region} at "
              f"{region_current_time.strftime('%Y-%m-%d_%H:%M')} UTC_________***")

        # ── QPE cleanup ────────────────────────────────────────────────────────────
        try:
            cleanup_precip(region_current_time, region_precip_folder, region_qpf_store_path)
        except Exception as _ce:
            print(f"    Warning: precip cleanup failed for {region}: {_ce}")

        # ── QPE retrieval ──────────────────────────────────────────────────────────
        if local_qpe_source == "HSAF":
            try:
                if not hsaf_ftp_user or not hsaf_ftp_pass:
                    raise ValueError("HSAF selected but hsaf_ftp_user/hsaf_ftp_pass are missing in config.")
                get_new_hsaf_precip(
                    current_timestamp=region_current_time,
                    precipFolder=region_precip_folder,
                    ftp_user=hsaf_ftp_user,
                    ftp_pass=hsaf_ftp_pass,
                    xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
                    latency_minutes=hsaf_latency_minutes,
                )
                print(f"    {region}: HSAF files are ready")
            except Exception as _he:
                print(f"    There was a problem with HSAF retrieval for {region}: {_he}. Continuing.")

        elif local_qpe_source == "SCAMPR":
            try:
                get_new_scampr_precip(
                    current_timestamp=region_current_time,
                    precipFolder=region_precip_folder,
                    xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
                    latency_minutes=scampr_latency_minutes,
                )
                print(f"    {region}: SCaMPR files are ready")
            except Exception as _se:
                print(f"    There was a problem with SCaMPR retrieval for {region}: {_se}. Continuing.")

        else:   # IMERG
            try:
                get_new_precip(
                    region_current_time, server, region_precip_folder,
                    email_gpm, HindCastMode, region_qpf_store_path,
                    xmin, ymin, xmax, ymax,
                )
                print(f"    {region}: IMERG files are ready")
            except Exception as _ie:
                print(f"    There was a problem with IMERG retrieval for {region}: {_ie}. Continuing.")

            if NOWCAST:
                try:
                    print(
                        f"    {region}: generating nowcast from "
                        f"{(region_current_time - timedelta(hours=3.5)).strftime('%Y-%m-%d_%H:%M')} to "
                        f"{(region_current_time + timedelta(hours=2.5)).strftime('%Y-%m-%d_%H:%M')}"
                    )
                    run_convlstm(region_current_time, region_precip_folder,
                                 nowcast_model_name, xmin, ymin, xmax, ymax)
                    with _lock:
                        region_imerg_folders_used.append((region_precip_folder, region_current_time))
                except Exception as _ne:
                    print(f"    There was a problem with the nowcast routine for {region}: {_ne}. Continuing.")

        # ── QPF (LR) — loop over every requested QPF source ────────────────────────
        # For each QPF source in qpf_source_list we create one EF5 job.
        # QPE warm-up always runs but states are saved only once:
        #   • First / only QPF (GFS/WRF): save_states=True
        #   • Additional QPF sources (AROME): save_states=False → no state overwrite
        # AROME outputs go to tmp_output_<model>_arome/ to keep results separate.

        # Build list of (actual_qpf, tmp_output, stage_precip, save_states)
        _qpf_jobs_to_build = []

        if not LR_run:
            # QPE-only simulation — single job, no QPF
            _qpf_jobs_to_build.append(("none", region_tmp_output, True, True))
        else:
            for _qpf_item in qpf_source_list:
                actual_qpf = _qpf_item

                # ── WRF (with GFS fallback) ──────────────────────────────────────
                if _qpf_item == "WRF":
                    wrf_ok = False
                    if WRF_archive_path:
                        try:
                            wrf_ok = WRF_searcher(
                                WRF_archive_path, region_qpf_store_path,
                                r_start_lr, r_end_lr,
                                LR_TimeStep, WRF_var_name, WRF_filename_template,
                            )
                        except Exception as _we:
                            print(f"    WRF processing failed for {region}: {_we}")
                    if wrf_ok:
                        actual_qpf = "WRF"
                    else:
                        if WRF_archive_path:
                            print(f"    {region}: WRF not available — falling back to GFS")
                        actual_qpf = "GFS"

                # ── GFS ──────────────────────────────────────────────────────────
                if actual_qpf == "GFS":
                    if cycle_time_key in gfs_shared_data_folders:
                        _copy_shared_gfs_to_region(
                            gfs_shared_data_folders[cycle_time_key],
                            region_qpf_store_path,
                        )
                    else:
                        try:
                            GFS_searcher(
                                region_gfs_archive_path, region_qpf_store_path,
                                r_start_lr, r_end_lr,
                                xmin, xmax, ymin, ymax,
                            )
                        except Exception as _ge:
                            print(f"    GFS problem for {region}: {_ge}. Continuing.")

                # ── AROME ────────────────────────────────────────────────────────
                elif actual_qpf == "AROME":
                    try:
                        arome_domain = get_arome_domain_for_region(region)
                        arome_key = (cycle_time_key, arome_domain)
                        if arome_key in arome_shared_data_folders:
                            _copy_shared_arome_to_region(
                                arome_shared_data_folders[arome_key],
                                region_qpf_store_path,
                            )
                        else:
                            AROME_searcher(
                                region_arome_archive_path, region_qpf_store_path,
                                r_start_lr, r_end_lr,
                                xmin, xmax, ymin, ymax,
                                arome_domain,
                            )
                    except Exception as _ae:
                        print(f"    AROME problem for {region}: {_ae}. Skipping AROME run.")
                        continue

                # AROME outputs to a separate folder; does not overwrite states
                if actual_qpf == "AROME":
                    _tmp_out = os.path.join(
                        region_data_path, f"tmp_output_{systemModel}_arome"
                    )
                    _save_states = False
                else:
                    _tmp_out = region_tmp_output
                    _save_states = True

                _qpf_jobs_to_build.append((
                    actual_qpf,
                    _tmp_out,
                    True,          # always stage QPE: each QPF source has its own precipEF5 folder
                    _save_states,
                ))

        # ── EF5 control file prep — one job per QPF source ─────────────────────────
        for (_qpf_src, _tmp_out, _do_stage, _do_save_states) in _qpf_jobs_to_build:
            forcing_folder = f"{local_qpe_source.lower()}_{_qpf_src.lower()}"
            region_precip_ef5_folder = os.path.join(
                precipEF5Folder, region_key, forcing_folder
            )
            makedirs(region_precip_ef5_folder, exist_ok=True)

            realSystemStartTime, controlFile, run_output_path = prepare_ef5(
                region_precip_ef5_folder,
                region_precip_folder,
                _with_sep(region_states_path),
                modelStates,
                r_system_start,
                r_fail_time,
                region_current_time,
                systemName,
                SEND_ALERTS,
                alert_recipients,
                smtp_config,
                _with_sep(_tmp_out),
                _with_sep(region_data_path),
                region,
                systemModel,
                templatePath,
                region_template,
                r_start_lr,
                r_warm_end,
                r_state_end,
                r_end_time,
                LR_TimeStep,
                LR_run,
                region,
                model_resolution,
                basicPath,
                parametersPath,
                local_qpe_source,
                _qpf_src,
                stage_precip=_do_stage,
                output_timestamp_str=output_timestamp_str,
                qpf_store_forcing_path=region_qpf_store_path,
                save_states=_do_save_states,
            )

            print(
                f"    Region {region} ({local_qpe_source}/{_qpf_src}): "
                f"start {realSystemStartTime.strftime('%Y%m%d_%H%M')} → "
                f"end {r_end_time.strftime('%Y%m%d_%H%M')}, "
                f"control {controlFile}"
            )

            with _lock:
                staged_precip_folders.add(region_precip_ef5_folder)
                ef5_jobs.append({
                    "region":               region,
                    "ef5Path":              ef5Path,
                    "tmpOutput":            run_output_path + "/",
                    "controlFile":          controlFile,
                    "output_timestamp_str": output_timestamp_str,
                })

    try:
        with _ThreadPoolExecutor(max_workers=len(regions_to_run)) as executor:
            futures = {executor.submit(_prepare_one_region, r): r for r in regions_to_run}
            for future in _as_completed(futures):
                r = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"    !!! Region {r} forcing prep raised an exception: {exc}")

        if ef5_jobs:
            print("***_________Running EF5 in parallel for all regions_________***")
            run_ef5_simulations_parallel(ef5_jobs, max_workers=len(ef5_jobs))
            newline(2)
            print("******** EF5 Outputs are ready!!! ********")
        else:
            print("No EF5 jobs were prepared.")
    finally:
        if NOWCAST and imerg_needed and region_imerg_folders_used:
            print("***_________Cleaning end-of-run IMERG nowcast/duplicated files_________***")
            removed_nowcast_total = 0
            cleaned_folders = set()
            for folder_path, cycle_time in region_imerg_folders_used:
                key = (folder_path, cycle_time.strftime("%Y%m%d%H%M"))
                if key in cleaned_folders:
                    continue
                cleaned_folders.add(key)
                removed_nowcast_total += cleanup_nowcast_qpe(cycle_time, folder_path)
            print(f"    Removed {removed_nowcast_total} IMERG nowcast/duplicated files from region folders")
        if staged_precip_folders:
            print("***_________Cleaning staged precipEF5 folders_________***")
            removed_staged = cleanup_staged_precip_folders(staged_precip_folders)
            print(f"    Removed {removed_staged} staged precip files from precipEF5 folders")
        # Prune stale _shared_arome cycle directories (keep only the current run's cycles)
        _shared_arome_root = os.path.join(qpf_store_path, "_shared_arome")
        if os.path.isdir(_shared_arome_root):
            current_arome_cycle_keys = {ck for (ck, _dom) in arome_shared_data_folders}
            for _cycle_dir in os.listdir(_shared_arome_root):
                if _cycle_dir not in current_arome_cycle_keys:
                    _stale = os.path.join(_shared_arome_root, _cycle_dir)
                    try:
                        shutil.rmtree(_stale)
                        print(f"    Removed stale AROME shared cache: {_cycle_dir}")
                    except Exception as _re:
                        print(f"    Warning: could not remove stale AROME cache {_stale}: {_re}")
        
        # Prune stale _shared cycle directories (for GFS)
        _shared_gfs_root = os.path.join(qpf_store_path, "_shared")
        if os.path.isdir(_shared_gfs_root):
            current_gfs_cycle_keys = set(gfs_shared_data_folders.keys())
            for _cycle_dir in os.listdir(_shared_gfs_root):
                if _cycle_dir not in current_gfs_cycle_keys:
                    _stale = os.path.join(_shared_gfs_root, _cycle_dir)
                    try:
                        shutil.rmtree(_stale)
                        print(f"    Removed stale GFS shared cache: {_cycle_dir}")
                    except Exception as _re:
                        print(f"    Warning: could not remove stale GFS cache {_stale}: {_re}")
        
        # Completely wipe the region-specific QPF stores to free space
        print("***_________Cleaning regional qpf_store forecast data_________***")
        for region in regions_to_run:
            if region in region_configs:
                r_store = region_configs[region]["region_qpf_store_path"]
                for subfolder in ["gfs_data", "arome_data", "wrf_data"]:
                    sub_path = os.path.join(r_store, subfolder)
                    if os.path.isdir(sub_path):
                        try:
                            shutil.rmtree(sub_path)
                            print(f"    Removed regional forecast cache: {sub_path}")
                        except Exception as _re:
                            print(f"    Warning: could not remove {sub_path}: {_re}")

"""
Run the main() function when invoked as a script
"""
if __name__ == "__main__":
    main(sys.argv)

