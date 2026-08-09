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

import shutil
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
from tito_utils.qpe_utils import get_new_precip, get_gpm_files, get_new_hsaf_precip, get_new_scampr_precip, fill_imerg_gap_with_scampr, fill_imerg_gap_with_hsaf
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

    # Parse CLI arguments.  Supports legacy positional-only and new named overrides:
    #   python orchestrator.py config.py                     # standard
    #   python orchestrator.py config.py --hindcast-date "YYYY-MM-DD HH:MM"
    #   python orchestrator.py config.py --regions Antigua,Haiti
    import importlib
    import argparse as _argparse
    _ap = _argparse.ArgumentParser(add_help=False)
    _ap.add_argument("config", nargs="?", default="Caribbean_Comoros_config")
    _ap.add_argument("--hindcast-date", default=None, dest="hindcast_date",
                     help="Override HindCastDate and force HindCastMode=True")
    _ap.add_argument("--regions", default=None,
                     help="Comma-separated region names to run (overrides config)")
    _cli, _ = _ap.parse_known_args(args[1:])
    _cli_hindcast_date = _cli.hindcast_date
    _cli_regions = [r.strip() for r in _cli.regions.split(",") if r.strip()] if _cli.regions else None
    config_module_name = os.path.splitext(os.path.basename(_cli.config))[0]
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
    # CLI --regions override (useful for hindcast experiments targeting specific regions).
    if _cli_regions:
        regions_to_run = [r for r in _cli_regions if r]
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

    # CLI --hindcast-date override: forces hindcast mode with a single shared date.
    # Clears per-region dates so all regions use the same cycle time (required
    # for the sequential hindcast_manager.py stepping logic).
    if _cli_hindcast_date:
        HindCastMode = True
        HindCastDate = _cli_hindcast_date
        region_hindcast_dates = {}
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

    # QPE gap-fill mode — applies to both operational and hindcast runs.
    # Controls how the IMERG 4-hour latency gap is filled.
    _VALID_QPE_EXPERIMENTS = {"IMERG_ONLY", "IMERG_SCAMPR", "IMERG_HSAF", "IMERG_NOWCAST", "NONE"}
    hindcast_qpe_experiment = getattr(config_file, "hindcast_qpe_experiment", "IMERG_NOWCAST").strip().upper()
    if hindcast_qpe_experiment not in _VALID_QPE_EXPERIMENTS:
        print(f"    Warning: unknown hindcast_qpe_experiment '{hindcast_qpe_experiment}', defaulting to IMERG_NOWCAST")
        hindcast_qpe_experiment = "IMERG_NOWCAST"
    # qpe_gap_fill_mode supersedes hindcast_qpe_experiment and applies to all run modes.
    _qpe_gap_fill_mode = getattr(config_file, "qpe_gap_fill_mode", hindcast_qpe_experiment).strip().upper()
    if _qpe_gap_fill_mode not in _VALID_QPE_EXPERIMENTS:
        print(f"    Warning: unknown qpe_gap_fill_mode '{_qpe_gap_fill_mode}', defaulting to IMERG_NOWCAST")
        _qpe_gap_fill_mode = "IMERG_NOWCAST"
    hsaf_ftp_user = getattr(config_file, "hsaf_ftp_user", "")
    hsaf_ftp_pass = getattr(config_file, "hsaf_ftp_pass", "")
    hsaf_latency_minutes = int(getattr(config_file, "hsaf_latency_minutes", 20))
    scampr_precip_root = getattr(config_file, "scampr_precip_folder", "precip/scampr/")
    scampr_latency_minutes = int(getattr(config_file, "scampr_latency_minutes", 20))
    nowcast_domains_cfg = getattr(config_file, "nowcast_domains", None)
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

    def _parse_duration(value, label, default_unit="hours"):
        if isinstance(value, timedelta):
            return value
        if isinstance(value, (int, float)):
            if default_unit == "hours":
                return timedelta(hours=float(value))
            if default_unit == "days":
                return timedelta(days=float(value))
            if default_unit == "minutes":
                return timedelta(minutes=float(value))
            raise ValueError(f"Unsupported default unit '{default_unit}' for {label}")

        text = str(value).strip().lower()
        if not text:
            raise ValueError(f"Duration for {label} cannot be empty")

        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+)?", text)
        if not match:
            raise ValueError(
                f"Invalid duration for {label}: {value}. Use values like '6h', '2d', '1month', or 6"
            )

        amount = float(match.group(1))
        unit = match.group(2) or {
            "hours": "h",
            "days": "d",
            "minutes": "min",
        }.get(default_unit, "h")

        if unit in {"m", "min", "mins", "minute", "minutes"}:
            return timedelta(minutes=amount)
        if unit in {"h", "hr", "hrs", "hour", "hours"}:
            return timedelta(hours=amount)
        if unit in {"d", "day", "days"}:
            return timedelta(days=amount)
        if unit in {"w", "wk", "wks", "week", "weeks"}:
            return timedelta(weeks=amount)
        if unit in {"mo", "mon", "mons", "month", "months"}:
            return timedelta(days=30 * amount)

        raise ValueError(
            f"Unsupported duration unit for {label}: {value}. Supported units are minutes, hours, days, weeks, months"
        )

    imerg_cold_start_warmup = _parse_duration(
        getattr(config_file, "imerg_cold_start_warmup", "6h"),
        "imerg_cold_start_warmup",
    )
    imerg_post_warmup_duration = _parse_duration(
        getattr(config_file, "imerg_post_warmup_duration", "2h"),
        "imerg_post_warmup_duration",
    )
    initial_imerg_warmup_enabled = bool(
        getattr(config_file, "initial_imerg_warmup_enabled", False)
    )
    initial_imerg_warmup_duration = _parse_duration(
        getattr(config_file, "initial_imerg_warmup_duration", "1month"),
        "initial_imerg_warmup_duration",
    )
    if imerg_cold_start_warmup <= timedelta(0):
        raise ValueError("imerg_cold_start_warmup must be greater than zero")
    if imerg_post_warmup_duration <= timedelta(0):
        raise ValueError("imerg_post_warmup_duration must be greater than zero")
    if initial_imerg_warmup_duration <= timedelta(0):
        raise ValueError("initial_imerg_warmup_duration must be greater than zero")

    def _resolve_imerg_only_cold_start_window(simulation_end_time):
        warmup_duration = (
            initial_imerg_warmup_duration
            if initial_imerg_warmup_enabled
            else imerg_cold_start_warmup
        )
        warm_end_time = simulation_end_time - imerg_post_warmup_duration
        start_time = warm_end_time - warmup_duration
        if warm_end_time >= simulation_end_time:
            raise ValueError(
                "IMERG-only warmup requires imerg_post_warmup_duration to end before the simulation end time"
            )
        if start_time >= warm_end_time:
            raise ValueError(
                "IMERG-only warmup requires a positive warmup window before TIME_WARMEND"
            )
        return start_time, warm_end_time, warmup_duration

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

    # Hindcast QPE experiment: force all regions to use IMERG as base QPE source
    # (overrides region_forcing_map) so the chosen gap-fill strategy can be applied.
    # In operational mode (HindCastMode=False) this block never executes.
    if HindCastMode and hindcast_qpe_experiment not in ("NONE",):
        for _r in regions_to_run:
            region_qpe_sources[_r] = "IMERG"
        imerg_needed = True
        requested_qpe_sources = {"IMERG"}

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
        realtime_cycle_time = _round_cycle_time(datetime.now(timezone.utc).replace(tzinfo=None))
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

    # NOWCAST (ML ConvLSTM) fills the IMERG 4-hour latency gap only when
    # qpe_gap_fill_mode == "IMERG_NOWCAST".  In IMERG_SCAMPR / IMERG_HSAF /
    # IMERG_ONLY modes the gap is handled by IR QPE or left unfilled, so the
    # ML nowcast is disabled regardless of whether this is a hindcast or
    # operational run.
    if not imerg_needed:
        NOWCAST = False
    elif _qpe_gap_fill_mode != "IMERG_NOWCAST":
        NOWCAST = False  # SCaMPR/HSAF/none gap fill used instead of ML nowcast

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

        # Determine the effective IMERG offset and QPE experiment for this region.
        # The offset controls when EF5 saves states (TIME_WARMEND / TIME_STATE):
        #   All IMERG-based experiments → offset = 4h (state snapshot at T−4h,
        #   the last real IMERG boundary).  For IMERG_SCAMPR / IMERG_HSAF the
        #   EF5 simulation still runs to T using gap-fill precip for outputs and
        #   alerts, but the state file is always anchored at T−4h to keep
        #   state chaining clean — both in hindcast steps and across operational
        #   hourly cycles ("save state at last IMERG" requirement).
        #   SCaMPR/HSAF primary sources always use offset = 0 (no IMERG latency).
        if _qpe == "IMERG":
            _effective_experiment = _qpe_gap_fill_mode  # same in operational and hindcast
            _imerg_offset = timedelta(hours=4)  # state always at T−4h (last real IMERG)
        else:
            _effective_experiment = "N/A"
            _imerg_offset = timedelta(0)

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

        # r_imerg_end / r_scampr_end are used by the IMERG-SCaMPR chained pipeline
        # (operational IMERG_SCAMPR mode).  For IMERG QPE the IMERG run ends at T-4h
        # (last available IMERG file), then a separate SCaMPR run covers T-4h → T.
        _r_imerg_end  = region_current_time - timedelta(hours=4) if _qpe == "IMERG" else region_current_time
        _r_scampr_end = region_current_time

        region_configs[region] = {
            "region_key":           region_key,
            "region_current_time":  region_current_time,
            "output_timestamp_str": output_timestamp_str,
            "qpe_source":           _qpe,
            "qpe_experiment":       _effective_experiment,
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
            # Chained pipeline time boundaries (IMERG_SCAMPR operational mode)
            "r_imerg_end":          _r_imerg_end,   # T-4h: end of IMERG run, save state here
            "r_scampr_end":         _r_scampr_end,  # T:    end of SCaMPR run, save state here
        }

    # ── Per-domain nowcast bbox mapping (built from nowcast_domains_cfg) ────────────────
    # Maps each region to (xmin, ymin, xmax, ymax) and a domain name for the
    # IMERG_NOWCAST hindcast path.  Falls back to the global bbox for regions
    # not listed in any domain, and is ignored entirely outside IMERG_NOWCAST.
    _region_nowcast_bbox = {}   # region → (xmin, ymin, xmax, ymax)
    _region_nowcast_domain = {} # region → domain name
    if nowcast_domains_cfg:
        for _dn, _dcfg in nowcast_domains_cfg.items():
            _dx1 = _dcfg.get("xmin", xmin)
            _dy1 = _dcfg.get("ymin", ymin)
            _dx2 = _dcfg.get("xmax", xmax)
            _dy2 = _dcfg.get("ymax", ymax)
            for _r in _dcfg.get("regions", []):
                if _r in regions_to_run:
                    _region_nowcast_bbox[_r] = (_dx1, _dy1, _dx2, _dy2)
                    _region_nowcast_domain[_r] = _dn
    # Fallback: any IMERG region not covered by a domain uses the global bbox
    for _r in regions_to_run:
        if _r not in _region_nowcast_bbox:
            _region_nowcast_bbox[_r] = (xmin, ymin, xmax, ymax)
            _region_nowcast_domain[_r] = "_default"

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

    # ── Shared IMERG pre-download (serial; one download shared by all IMERG regions) ──
    # IMERG uses the same global bounding box and time window for all regions.
    # Download once to the first IMERG region's folder then copy to all others to
    # avoid redundant NASA PPS requests and parallel write conflicts.
    imerg_shared_done = set()   # cycle_time_keys where shared IMERG download succeeded

    if imerg_needed and not NOWCAST:
        _imerg_groups = {}
        for region in regions_to_run:
            cfg = region_configs[region]
            if cfg["qpe_source"] == "IMERG":
                key = cfg["cycle_time_key"]
                _imerg_groups.setdefault(key, []).append(region)

        for cycle_key, _ir_list in _imerg_groups.items():
            _ref_region = _ir_list[0]
            _ref_cfg    = region_configs[_ref_region]
            _ref_folder = _ref_cfg["region_precip_folder"]
            makedirs(_ref_folder, exist_ok=True)
            makedirs(_ref_cfg["region_qpf_store_path"], exist_ok=True)
            n_imerg = len(_ir_list)
            print(f"***_________Downloading shared IMERG for cycle {cycle_key} "
                  f"(shared by {n_imerg} region(s))_________***")

            try:
                get_new_precip(
                    _ref_cfg["region_current_time"], server, _ref_folder,
                    email_gpm, HindCastMode, _ref_cfg["region_qpf_store_path"],
                    xmin, ymin, xmax, ymax,
                )
                imerg_shared_done.add(cycle_key)

                # Copy freshly downloaded files to every other IMERG region.
                _imerg_tifs = sorted(glob.glob(
                    os.path.join(_ref_folder, "imerg.qpe.*.30minAccum.tif")
                ))
                for _other in _ir_list[1:]:
                    _oth_folder = region_configs[_other]["region_precip_folder"]
                    makedirs(_oth_folder, exist_ok=True)
                    _copied = 0
                    for _src in _imerg_tifs:
                        try:
                            shutil.copy2(_src, os.path.join(_oth_folder, os.path.basename(_src)))
                            _copied += 1
                        except Exception as _ce:
                            print(f"    Warning: IMERG copy to {_other} failed "
                                  f"({os.path.basename(_src)}): {_ce}")
                    print(f"    IMERG: {_copied} file(s) copied to {_other}")
            except Exception as _ie:
                print(f"    Shared IMERG download failed for {cycle_key}: {_ie}. "
                      f"Regions will download individually.")

    # ── Step 3: Parallel per-region forcing prep ─────────────────────────────────────
    _lock = threading.Lock()
    staged_precip_folders = set()
    region_imerg_folders_used = []
    ef5_jobs        = []   # used by legacy/hindcast path
    imerg_ef5_jobs  = []   # IMERG_SCAMPR chain: run 1 (IMERG QPE only, saves state at T-4h)
    lr_ef5_jobs     = []   # IMERG_SCAMPR chain: run 2 (SCaMPR QPE T-4h→T + GFS/AROME QPF T→T+24h)

    # ── Phase 1 worker: QPE cleanup + download only (no nowcast) ───────────────────
    # Nowcast is pulled out of the parallel loop and run once after all IMERG
    # downloads finish, then the gap-fill files are copied to every IMERG region.
    # This fixes two bugs: (a) shared HDF5 temp-file race conditions when nowcast
    # ran in parallel across regions, and (b) too many output files being generated
    # (the model generated T+2 h of extra files; now truncated to cycle time T).
    def _qpe_download_for_region(region):
        cfg = region_configs[region]
        region_key          = cfg["region_key"]
        region_current_time = cfg["region_current_time"]
        local_qpe_source    = cfg["qpe_source"]
        local_qpe_experiment = cfg.get("qpe_experiment", "IMERG_NOWCAST")
        region_precip_folder   = cfg["region_precip_folder"]
        region_qpf_store_path  = cfg["region_qpf_store_path"]
        region_gfs_archive_path = cfg["region_gfs_archive_path"]
        region_arome_archive_path = cfg["region_arome_archive_path"]
        region_states_path  = cfg["region_states_path"]
        region_data_path    = cfg["region_data_path"]
        cycle_time_key      = cfg["cycle_time_key"]

        for dirpath in [region_precip_folder, region_qpf_store_path,
                        region_gfs_archive_path, region_arome_archive_path,
                        region_states_path, region_data_path]:
            makedirs(dirpath, exist_ok=True)

        print(f"***_________Preparing forcings for {region} at "
              f"{region_current_time.strftime('%Y-%m-%d_%H:%M')} UTC_________***")

        # ── QPE cleanup ────────────────────────────────────────────────────────────
        # Keep SCAMPR/HSAF gap-fill IMERG files from the previous cycle so EF5
        # can use them — applies in both operational and hindcast SCAMPR/HSAF modes.
        _keep_gap_fill = local_qpe_experiment in ("IMERG_SCAMPR", "IMERG_HSAF")
        # For IMERG_NOWCAST the ConvLSTM model needs in_seq_length=12 input frames
        # (12 × 30 min = 6 h) ending at the IMERG latency boundary (currentTime − 4 h).
        # The oldest frame needed is therefore currentTime − 10 h.  Use 10 h as the
        # QPE retention window so cleanup_precip never removes those frames.
        # All other experiments use the default 6.5 h window (EF5's 6 h sim window
        # with a 30 min buffer).
        _older_qpe_hours = 10.0 if NOWCAST else 6.5
        try:
            cleanup_precip(region_current_time, region_precip_folder, region_qpf_store_path,
                           keep_gap_fill=_keep_gap_fill, older_qpe_hours=_older_qpe_hours)
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
            if cycle_time_key in imerg_shared_done:
                # Shared pre-download already populated every IMERG region folder
                # (including stale gap-fill strip). Nothing more to do here.
                print(f"    {region}: IMERG files ready (shared pre-download)")
            else:
                # Shared download not attempted (NOWCAST mode) or failed — fall
                # back to per-region download.
                if local_qpe_experiment in ("IMERG_SCAMPR", "IMERG_HSAF"):
                    _prev_imerg_end = region_current_time - timedelta(hours=5)
                    for _fn in list(os.listdir(region_precip_folder)):
                        if not (_fn.startswith("imerg.qpe.") and _fn.endswith(".30minAccum.tif")):
                            continue
                        try:
                            _fdt = datetime.strptime(_fn[10:22], "%Y%m%d%H%M")
                            if _fdt > _prev_imerg_end:
                                os.remove(os.path.join(region_precip_folder, _fn))
                        except Exception:
                            pass
                # In IMERG_NOWCAST mode use the domain-specific bbox.
                _imerg_dl_xmin, _imerg_dl_ymin, _imerg_dl_xmax, _imerg_dl_ymax = (
                    _region_nowcast_bbox.get(region, (xmin, ymin, xmax, ymax))
                    if NOWCAST else (xmin, ymin, xmax, ymax)
                )
                try:
                    get_new_precip(
                        region_current_time, server, region_precip_folder,
                        email_gpm, HindCastMode, region_qpf_store_path,
                        _imerg_dl_xmin, _imerg_dl_ymin, _imerg_dl_xmax, _imerg_dl_ymax,
                    )
                    print(f"    {region}: IMERG files are ready")
                except Exception as _ie:
                    print(f"    There was a problem with IMERG retrieval for {region}: {_ie}. Continuing.")
            # Nowcast is handled in the shared step below — not here.

    # ── Phase 2 worker: hindcast gap fill + QPF + EF5 control file prep ────────────
    def _prep_qpf_ef5_for_region(region):
        cfg = region_configs[region]
        region_key          = cfg["region_key"]
        region_current_time = cfg["region_current_time"]
        output_timestamp_str = cfg["output_timestamp_str"]
        local_qpe_source    = cfg["qpe_source"]
        local_qpe_experiment = cfg.get("qpe_experiment", "IMERG_NOWCAST")
        qpf_source_list     = cfg["qpf_source"]    # list of QPF sources ([] when QPE-only)
        qpf_requested       = cfg["qpf_requested"]  # same list
        region_precip_folder   = cfg["region_precip_folder"]
        region_qpf_store_path  = cfg["region_qpf_store_path"]
        region_gfs_archive_path = cfg["region_gfs_archive_path"]
        region_arome_archive_path = cfg["region_arome_archive_path"]
        region_states_path  = cfg["region_states_path"]
        region_data_path    = cfg["region_data_path"]
        region_template     = cfg["region_template"]
        r_start_lr   = cfg["r_start_lr"]
        r_end_lr     = cfg["r_end_lr"]
        r_end_time   = cfg["r_end_time"]
        r_state_end  = cfg["r_state_end"]
        r_warm_end   = cfg["r_warm_end"]
        r_system_start = cfg["r_system_start"]
        r_fail_time    = cfg["r_fail_time"]
        cycle_time_key  = cfg["cycle_time_key"]
        cold_start_begin_time = None
        cold_start_warm_end_time = None

        # ── IMERG gap fills (SCAMPR / HSAF) — operational and hindcast ───────────
        # Nowcast (IMERG_NOWCAST) is handled in the shared step between phases.
        # SCaMPR and HSAF gap fills run per-region here in both modes.
        if local_qpe_source == "IMERG" and not NOWCAST:
            if local_qpe_experiment == "IMERG_SCAMPR":
                # ── Fill the 4-h IMERG gap with SCaMPR (global NOAA RRQPE) ─────
                _gap_start = region_current_time - timedelta(hours=4)
                _gap_end   = region_current_time
                if scampr_shared_folder:
                    # Use the shared SCaMPR download — no per-region S3 fetch needed.
                    _scampr_source = scampr_shared_folder
                else:
                    # Fallback: shared download failed; download per-region.
                    _scampr_source = os.path.join(scampr_precip_root, region_key, "")
                    os.makedirs(_scampr_source, exist_ok=True)
                    _scampr_older_than = region_current_time - timedelta(hours=6.5)
                    for _sf in list(os.listdir(_scampr_source)):
                        _m = re.match(r"scampr\.qpe\.(\d{12})\.mmhInst\.tif$", _sf)
                        if _m:
                            try:
                                if datetime.strptime(_m.group(1), "%Y%m%d%H%M") < _scampr_older_than:
                                    os.remove(os.path.join(_scampr_source, _sf))
                            except Exception:
                                pass
                    try:
                        _gap_latency = 0 if HindCastMode else scampr_latency_minutes
                        get_new_scampr_precip(
                            current_timestamp=region_current_time,
                            precipFolder=_scampr_source,
                            xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
                            latency_minutes=_gap_latency,
                        )
                    except Exception as _sc_dl_e:
                        print(f"    {region}: SCaMPR download failed: {_sc_dl_e}. Skipping gap fill.")
                        _scampr_source = None
                try:
                    if _scampr_source:
                        _filled = fill_imerg_gap_with_scampr(
                            region_precip_folder, _scampr_source, _gap_start, _gap_end
                        )
                        print(f"    {region}: SCaMPR→IMERG gap fill complete ({_filled} 30-min windows)")
                except Exception as _gf_e:
                    print(f"    {region}: SCaMPR gap fill failed: {_gf_e}. Continuing without gap fill.")

            elif local_qpe_experiment == "IMERG_HSAF":
                # ── Case 2b: Fill the 4-h IMERG gap with HSAF H40B (Comoros/Africa) ─
                _gap_start = region_current_time - timedelta(hours=4)
                _gap_end   = region_current_time
                _hsaf_gap_folder = os.path.join(hsaf_precip_root, region_key, "")
                os.makedirs(_hsaf_gap_folder, exist_ok=True)
                try:
                    if not hsaf_ftp_user or not hsaf_ftp_pass:
                        raise ValueError(
                            "IMERG_HSAF experiment requires hsaf_ftp_user/hsaf_ftp_pass in config."
                        )
                    _gap_latency = 0 if HindCastMode else hsaf_latency_minutes
                    get_new_hsaf_precip(
                        current_timestamp=region_current_time,
                        precipFolder=_hsaf_gap_folder,
                        ftp_user=hsaf_ftp_user, ftp_pass=hsaf_ftp_pass,
                        xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
                        latency_minutes=_gap_latency,
                    )
                    _filled = fill_imerg_gap_with_hsaf(
                        region_precip_folder, _hsaf_gap_folder, _gap_start, _gap_end
                    )
                    print(f"    {region}: HSAF→IMERG gap fill complete ({_filled} 30-min windows)")
                except Exception as _gf_e:
                    print(f"    {region}: HSAF gap fill failed: {_gf_e}. Continuing without gap fill.")
            # IMERG_ONLY: no gap fill — simulation ends at T − 4h, nothing more to do.

        # ── QPF (LR) — loop over every requested QPF source ────────────────────────
        # For each QPF source in qpf_source_list we create one EF5 job.
        # QPE warm-up always runs but states are saved only once:
        #   • First / only QPF (GFS/WRF): save_states=True
        #   • Additional QPF sources (AROME): save_states=False → no state overwrite
        # Dynamic output folder naming: tmp_output_{model}_{qpe}_{qpf}

        # Build list of (actual_qpf, tmp_output, stage_precip, save_states)
        _qpf_jobs_to_build = []

        if not LR_run:
            # QPE-only simulation — single job, no QPF
            _qpe_only_tmp = os.path.join(
                region_data_path, f"tmp_output_{systemModel}_{local_qpe_source.lower()}"
            )
            if local_qpe_source == "IMERG" and local_qpe_experiment == "IMERG_ONLY":
                cold_start_begin_time, cold_start_warm_end_time, _ = _resolve_imerg_only_cold_start_window(
                    r_state_end
                )
                r_system_start = r_state_end - timedelta(minutes=30)
                r_fail_time = r_state_end - timedelta(hours=6)
                r_warm_end = cold_start_warm_end_time
                r_end_time = r_state_end
            _qpf_jobs_to_build.append(("none", _qpe_only_tmp, True, True))
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

                # Dynamic output folder: tmp_output_{model}_{qpe}_{qpf}
                # AROME does not overwrite states (keeps GFS/WRF state intact).
                _tmp_out = os.path.join(
                    region_data_path,
                    f"tmp_output_{systemModel}_{local_qpe_source.lower()}_{actual_qpf.lower()}"
                )
                _save_states = actual_qpf != "AROME"

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
                cold_start_begin_time=cold_start_begin_time,
                cold_start_warm_end_time=cold_start_warm_end_time,
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

    # ── IMERG_SCAMPR chained pipeline: two preparation functions ────────────────────
    # Used only when not HindCastMode and _qpe_gap_fill_mode == "IMERG_SCAMPR".
    # Each function appends to a dedicated job list (imerg_ef5_jobs / lr_ef5_jobs)
    # that is run sequentially in the execution block below.

    def _prep_imerg_ef5_for_region(region):
        """Run 1 of 2: IMERG-only EF5 simulation (30-min, T-start → T-4h). Saves state at T-4h."""
        cfg = region_configs[region]
        region_key          = cfg["region_key"]
        region_current_time = cfg["region_current_time"]
        output_timestamp_str = cfg["output_timestamp_str"]
        region_precip_folder   = cfg["region_precip_folder"]
        region_qpf_store_path  = cfg["region_qpf_store_path"]
        region_states_path  = cfg["region_states_path"]
        region_data_path    = cfg["region_data_path"]
        region_template     = cfg["region_template"]
        r_imerg_end = cfg["r_imerg_end"]  # T-4h
        cold_start_begin_time, cold_start_warm_end_time, _ = _resolve_imerg_only_cold_start_window(
            r_imerg_end
        )

        # Determine the IMERG download bounding box for this region.
        # In IMERG_NOWCAST mode (hindcast) use the per-domain bbox; otherwise
        # the global bbox applies.
        _imerg_dl_xmin, _imerg_dl_ymin, _imerg_dl_xmax, _imerg_dl_ymax = (
            _region_nowcast_bbox.get(region, (xmin, ymin, xmax, ymax))
            if NOWCAST else (xmin, ymin, xmax, ymax)
        )
        # Parameters needed by prepare_ef5 to backfill IMERG if an older state is found.
        # initial_imerg_end is r_imerg_end (T-4h) — the end of the IMERG window that was
        # already downloaded before EF5 preparation started.
        _imerg_download_params = {
            "precipFolder":   region_precip_folder,
            "initial_imerg_end": r_imerg_end,   # T-4h: end of already-downloaded IMERG
            "server":         server,
            "email_gpm":      email_gpm,
            "xmin":           _imerg_dl_xmin,
            "ymin":           _imerg_dl_ymin,
            "xmax":           _imerg_dl_xmax,
            "ymax":           _imerg_dl_ymax,
        }

        _tmp_out = os.path.join(region_data_path, f"tmp_output_{systemModel}_imerg")
        region_precip_ef5_folder = os.path.join(precipEF5Folder, region_key, "imerg_none")
        makedirs(region_precip_ef5_folder, exist_ok=True)
        makedirs(_tmp_out, exist_ok=True)

        try:
            realSystemStartTime, controlFile, run_output_path = prepare_ef5(
                region_precip_ef5_folder,
                region_precip_folder,
                _with_sep(region_states_path),
                modelStates,
                r_imerg_end - timedelta(minutes=30),  # systemStartTime: look for state here
                r_imerg_end - timedelta(days=7),     # failTime: look back up to 7 days
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
                r_imerg_end,   # systemStartLRTime (TIMEBEGINLR — unused, LR_run=False)
                cold_start_warm_end_time,
                r_imerg_end,   # systemStateEndTime (TIMESTATE   = T-4h)
                r_imerg_end,   # systemEndTime      (TIMEEND     = T-4h)
                LR_TimeStep,
                False,         # LR_run
                region,
                model_resolution,
                basicPath,
                parametersPath,
                "IMERG",       # qpe_source
                "none",        # qpf_source
                stage_precip=True,
                output_timestamp_str=output_timestamp_str,
                qpf_store_forcing_path=region_qpf_store_path,
                save_states=True,
                cold_start_begin_time=cold_start_begin_time,
                cold_start_warm_end_time=cold_start_warm_end_time,
                imerg_download_params=_imerg_download_params,
            )
            print(f"    {region} [IMERG run]: start {realSystemStartTime.strftime('%Y%m%d_%H%M')}"
                  f" → end {r_imerg_end.strftime('%Y%m%d_%H%M')}, control {controlFile}")
            with _lock:
                staged_precip_folders.add(region_precip_ef5_folder)
                imerg_ef5_jobs.append({
                    "region":               region,
                    "ef5Path":              ef5Path,
                    "tmpOutput":            run_output_path + "/",
                    "controlFile":          controlFile,
                    "output_timestamp_str": output_timestamp_str,
                })
        except Exception as _exc:
            print(f"    !!! {region} IMERG EF5 prep failed: {_exc}")

    def _prep_lr_ef5_for_region(region):
        """Run 2 of 2: LR EF5 simulations — SCaMPR QPE warm-up (T-4h → T) + GFS/AROME QPF (T → T+24h).

        Both GFS and AROME runs start from the IMERG-saved state at T-4h, run the
        SCaMPR QPE phase (10-min) to advance to T, then branch into their respective
        LR QPF forecasts (60-min) out to T+24h.  This avoids a separate SCaMPR-only
        run and saves states independently for each QPF branch.

        Output folders follow the pattern  tmp_output_{model}_scampr_{qpf}  so they
        are always self-descriptive regardless of the active forcing configuration.
        """
        cfg = region_configs[region]
        region_key          = cfg["region_key"]
        region_current_time = cfg["region_current_time"]
        output_timestamp_str = cfg["output_timestamp_str"]
        qpf_source_list     = cfg["qpf_source"]
        region_qpf_store_path  = cfg["region_qpf_store_path"]
        region_gfs_archive_path = cfg["region_gfs_archive_path"]
        region_arome_archive_path = cfg["region_arome_archive_path"]
        region_states_path  = cfg["region_states_path"]
        region_data_path    = cfg["region_data_path"]
        region_template     = cfg["region_template"]
        cycle_time_key      = cfg["cycle_time_key"]
        r_imerg_end  = cfg["r_imerg_end"]   # T-4h: load IMERG state from here
        r_scampr_end = cfg["r_scampr_end"]  # T:    end of SCaMPR QPE warm-up / start of QPF
        r_lr_end     = cfg["r_end_lr"]       # T+24h: end of LR forecast

        _scampr_precip = _with_sep(
            scampr_shared_folder if scampr_shared_folder
            else os.path.join(scampr_precip_root, "_shared")
        )

        for _qpf_item in qpf_source_list:
            actual_qpf = _qpf_item

            # ── WRF with GFS fallback ────────────────────────────────────────────
            if _qpf_item == "WRF":
                wrf_ok = False
                if WRF_archive_path:
                    try:
                        wrf_ok = WRF_searcher(
                            WRF_archive_path, region_qpf_store_path,
                            r_scampr_end, r_lr_end,
                            LR_TimeStep, WRF_var_name, WRF_filename_template,
                        )
                    except Exception as _we:
                        print(f"    WRF processing failed for {region}: {_we}")
                actual_qpf = "WRF" if wrf_ok else "GFS"
                if not wrf_ok and WRF_archive_path:
                    print(f"    {region}: WRF not available — falling back to GFS")

            # ── GFS ─────────────────────────────────────────────────────────────
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
                            r_scampr_end, r_lr_end,
                            xmin, xmax, ymin, ymax,
                        )
                    except Exception as _ge:
                        print(f"    GFS problem for {region}: {_ge}. Continuing.")

            # ── AROME ────────────────────────────────────────────────────────────
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
                            r_scampr_end, r_lr_end,
                            xmin, xmax, ymin, ymax,
                            arome_domain,
                        )
                except Exception as _ae:
                    print(f"    AROME problem for {region}: {_ae}. Skipping AROME run.")
                    continue

            # Dynamic output folder: tmp_output_{model}_scampr_{qpf}
            # LR runs never save states — only the IMERG run saves states (at T-4h).
            _tmp_out = os.path.join(
                region_data_path,
                f"tmp_output_{systemModel}_scampr_{actual_qpf.lower()}"
            )
            _save_states = False

            forcing_folder = f"scampr_{actual_qpf.lower()}"
            region_precip_ef5_folder = os.path.join(precipEF5Folder, region_key, forcing_folder)
            makedirs(region_precip_ef5_folder, exist_ok=True)

            try:
                realSystemStartTime, controlFile, run_output_path = prepare_ef5(
                    region_precip_ef5_folder,
                    _scampr_precip,      # precipFolder: SCaMPR 10-min files for QPE warm-up
                    _with_sep(region_states_path),
                    modelStates,
                    r_imerg_end,         # systemStartTime: find IMERG state at T-4h
                    r_imerg_end,         # failTime: do not search beyond T-4h
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
                    r_scampr_end,   # systemStartLRTime (TIMEBEGINLR = T)
                    r_scampr_end,   # systemWarmEndTime  (TIMEWARMEND = T, SCaMPR QPE T-4h → T)
                    r_lr_end,       # systemStateEndTime (TIMESTATE   = T+24h)
                    r_lr_end,       # systemEndTime      (TIMEEND     = T+24h)
                    LR_TimeStep,
                    True,           # LR_run
                    region,
                    model_resolution,
                    basicPath,
                    parametersPath,
                    "SCAMPR",       # qpe_source → _apply_scampr_control_overrides → TIMESTEP=10u
                    actual_qpf,     # qpf_source (GFS / WRF / AROME)
                    stage_precip=True,
                    output_timestamp_str=output_timestamp_str,
                    qpf_store_forcing_path=region_qpf_store_path,
                    save_states=_save_states,
                )
                print(f"    {region} [SCaMPR+{actual_qpf}]: "
                      f"start {realSystemStartTime.strftime('%Y%m%d_%H%M')} "
                      f"(IMERG state T-4h) → QPE→T → QPF→{r_lr_end.strftime('%Y%m%d_%H%M')}, "
                      f"control {controlFile}")
                with _lock:
                    staged_precip_folders.add(region_precip_ef5_folder)
                    lr_ef5_jobs.append({
                        "region":               region,
                        "ef5Path":              ef5Path,
                        "tmpOutput":            run_output_path + "/",
                        "controlFile":          controlFile,
                        "output_timestamp_str": output_timestamp_str,
                    })
            except Exception as _exc:
                print(f"    !!! {region} LR ({actual_qpf}) EF5 prep failed: {_exc}")

    try:
        # ── Phase 1: parallel QPE downloads ─────────────────────────────────────────
        print("***_________Downloading QPE for all regions_________***")
        with _ThreadPoolExecutor(max_workers=len(regions_to_run)) as executor:
            futures = {executor.submit(_qpe_download_for_region, r): r for r in regions_to_run}
            for future in _as_completed(futures):
                r = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(f"    !!! Region {r} QPE download raised an exception: {exc}")

        # ── Shared nowcast: run once on the first IMERG region, copy to all others ──
        # All IMERG regions share the same bounding box so the nowcast output is
        # valid for every region.  Running here (after Phase 1 downloads, before
        # Phase 2 QPF/EF5 prep) prevents the HDF5 race condition that occurred
        # when regions ran run_convlstm in parallel against the same temp files.
        # Nowcast now also only generates files up to cycle time T — not T+2.5 h.
        if NOWCAST and imerg_needed:
            _imerg_regions = [r for r in regions_to_run
                              if region_configs[r]["qpe_source"] == "IMERG"]

            # Group IMERG regions by nowcast domain so each domain gets its own
            # ConvLSTM run over a geographically appropriate bbox.
            # This keeps the model centred on the Caribbean or on Comoros rather
            # than producing a mid-Atlantic centre-crop from the full combined bbox.
            _domain_groups = {}  # domain_name → [region, ...]
            for _r in _imerg_regions:
                _dn = _region_nowcast_domain.get(_r, "_default")
                _domain_groups.setdefault(_dn, []).append(_r)

            for _dname, _d_regions in _domain_groups.items():
                _ref_region = _d_regions[0]
                _ref_folder = region_configs[_ref_region]["region_precip_folder"]
                _ref_time   = region_configs[_ref_region]["region_current_time"]
                _gap_start  = _ref_time - timedelta(hours=4)
                _nc_xmin, _nc_ymin, _nc_xmax, _nc_ymax = _region_nowcast_bbox.get(
                    _ref_region, (xmin, ymin, xmax, ymax)
                )
                print(
                    f"***_________Running shared nowcast on {_ref_region} [{_dname}] "
                    f"(fills {_gap_start.strftime('%Y-%m-%d_%H:%M')} → "
                    f"{_ref_time.strftime('%Y-%m-%d_%H:%M')} UTC)_________***"
                )
                # ── Backfill historical IMERG so ConvLSTM always has enough input ──
                # model_picker.predict() → prediction_function(input_precip[-12:]) as
                # batch_x, and zeros(input_precip.shape) as batch_y.  When T_all < 7,
                # test_dat.shape[1] = 2*T_all, and 2*T_all - out_seq_length - 1 < 0.
                # A fresh hindcast folder often has only 1-4 recent IMERG files because
                # get_new_precip only downloads forward.  We need T_all ≥ 12 (full
                # in_seq_length) ending at T-4h, so the oldest file must be at T-9.5h.
                _qpe_needed_oldest = _ref_time - timedelta(hours=9, minutes=30)
                _target_latency   = _ref_time - timedelta(hours=4)
                _existing_qpe = sorted(
                    f for f in os.listdir(_ref_folder)
                    if f.startswith('imerg.qpe.') and f.endswith('.30minAccum.tif')
                )
                _oldest_qpe_dt = (
                    datetime.strptime(_existing_qpe[0][10:22], '%Y%m%d%H%M')
                    if _existing_qpe else _ref_time  # sentinel: force full backfill
                )
                if _oldest_qpe_dt > _qpe_needed_oldest:
                    # Cap download ceiling at T-4h+30min to avoid requesting files
                    # that the IMERG server hasn't published yet.
                    _backfill_newest = min(_oldest_qpe_dt,
                                          _target_latency + timedelta(minutes=30))
                    _bf_start = _qpe_needed_oldest - timedelta(minutes=30)
                    _bf_end   = _backfill_newest - timedelta(hours=1)
                    print(
                        f"    Backfilling IMERG for nowcast input: "
                        f"{_qpe_needed_oldest.strftime('%Y-%m-%d %H:%M')} → "
                        f"{(_backfill_newest - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M')} UTC"
                    )
                    try:
                        get_gpm_files(
                            _ref_folder, _bf_start, _bf_end,
                            server, email_gpm,
                            _nc_xmin, _nc_ymin, _nc_xmax, _nc_ymax,
                        )
                    except Exception as _bf_e:
                        print(f"    IMERG backfill warning: {_bf_e}. Nowcast may use fewer input frames.")
                try:
                    run_convlstm(_ref_time, _ref_folder, nowcast_model_name,
                                 _nc_xmin, _nc_ymin, _nc_xmax, _nc_ymax)
                    region_imerg_folders_used.append((_ref_folder, _ref_time))

                    # Collect the newly created gap-fill files (timestamps > T−4h)
                    _nc_files = []
                    for _pattern in ["imerg.qpe.*.30minAccum.tif",
                                     "imerg.qpf.*.30minAccum.tif"]:
                        for _src in glob.glob(os.path.join(_ref_folder, _pattern)):
                            try:
                                _dt_str = os.path.basename(_src).split('.')[2]
                                _dt = datetime.strptime(_dt_str, '%Y%m%d%H%M')
                                if _dt > _gap_start:
                                    _nc_files.append(_src)
                            except Exception:
                                pass

                    # Copy nowcast files to every other region in this domain
                    for _other_region in _d_regions[1:]:
                        _other_folder = region_configs[_other_region]["region_precip_folder"]
                        _other_time   = region_configs[_other_region]["region_current_time"]
                        makedirs(_other_folder, exist_ok=True)
                        _copied = 0
                        for _src in _nc_files:
                            try:
                                shutil.copy2(
                                    _src,
                                    os.path.join(_other_folder, os.path.basename(_src))
                                )
                                _copied += 1
                            except Exception as _ce:
                                print(f"    Warning: could not copy {os.path.basename(_src)}"
                                      f" to {_other_region}: {_ce}")
                        region_imerg_folders_used.append((_other_folder, _other_time))
                        print(f"    Copied {_copied} nowcast file(s) to {_other_region}")

                except Exception as _ne:
                    print(f"    Shared nowcast [{_dname}] failed: {_ne}. Continuing without nowcast gap fill.")

        # ── Shared SCaMPR download (serial, used by all IMERG_SCAMPR regions) ─────────
        # In the chained pipeline (operational IMERG_SCAMPR) this is the QPE source
        # for Run 2 (10-min SCaMPR EF5).  In hindcast IMERG_SCAMPR mode the same
        # folder is used by the legacy gap-fill path in _prep_qpf_ef5_for_region.
        # SCaMPR covers the same global bbox for all regions so we download once.
        scampr_shared_folder = None   # path to shared SCaMPR TIF folder, or None

        if _qpe_gap_fill_mode == "IMERG_SCAMPR" and imerg_needed:
            _scampr_shared_path = _with_sep(os.path.join(scampr_precip_root, "_shared"))
            makedirs(_scampr_shared_path, exist_ok=True)

            _scampr_ref_cfg = next(
                (region_configs[r] for r in regions_to_run
                 if region_configs[r]["qpe_source"] == "IMERG"),
                None,
            )
            if _scampr_ref_cfg is not None:
                _n_scampr = sum(
                    1 for r in regions_to_run if region_configs[r]["qpe_source"] == "IMERG"
                )
                print(f"***_________Downloading shared SCaMPR "
                      f"(used by {_n_scampr} region(s))_________***")

                # Remove SCaMPR files older than 6.5 h from the shared folder.
                _sc_older_than = _scampr_ref_cfg["region_current_time"] - timedelta(hours=6.5)
                for _sf in list(os.listdir(_scampr_shared_path)):
                    _m = re.match(r"scampr\.qpe\.(\d{12})\.mmhInst\.tif$", _sf)
                    if _m:
                        try:
                            if datetime.strptime(_m.group(1), "%Y%m%d%H%M") < _sc_older_than:
                                os.remove(os.path.join(_scampr_shared_path, _sf))
                        except Exception:
                            pass

                try:
                    _sc_latency = 0 if HindCastMode else scampr_latency_minutes
                    get_new_scampr_precip(
                        current_timestamp=_scampr_ref_cfg["region_current_time"],
                        precipFolder=_scampr_shared_path,
                        xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
                        latency_minutes=_sc_latency,
                    )
                    scampr_shared_folder = _scampr_shared_path
                except Exception as _sc_e:
                    print(f"    Shared SCaMPR download failed: {_sc_e}. "
                          f"Regions will attempt individual downloads.")

        # ── Phase 2: EF5 simulation chain ────────────────────────────────────────────
        # Operational IMERG_SCAMPR mode: two sequential EF5 batches
        #   2a  IMERG run      (30-min, T-start → T-4h, saves state at T-4h)
        #   2b  LR GFS+AROME   each starts from IMERG state at T-4h, runs SCaMPR QPE
        #                      warm-up (10-min, T-4h → T) then QPF forecast (60-min, T → T+24h)
        # All other modes (hindcast / IMERG_NOWCAST / IMERG_ONLY): single legacy batch.
        if not HindCastMode and _qpe_gap_fill_mode == "IMERG_SCAMPR" and imerg_needed:

            # ── Phase 2a: IMERG EF5 prep (parallel) + run ────────────────────────
            print("***_________Phase 2a: Preparing IMERG EF5 control files_________***")
            with _ThreadPoolExecutor(max_workers=len(regions_to_run)) as executor:
                futures = {executor.submit(_prep_imerg_ef5_for_region, r): r for r in regions_to_run}
                for future in _as_completed(futures):
                    r = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"    !!! Region {r} IMERG EF5 prep raised: {exc}")

            if imerg_ef5_jobs:
                print("***_________Running IMERG EF5 simulations for all regions_________***")
                run_ef5_simulations_parallel(imerg_ef5_jobs, max_workers=len(imerg_ef5_jobs))
                newline(1)
                print("    IMERG EF5 runs complete — states saved at T-4h")
            else:
                print("    No IMERG EF5 jobs prepared.")

            # ── Phase 2b: LR EF5 prep (parallel) + run ───────────────────────────
            # Each LR job starts from the IMERG state at T-4h, runs SCaMPR QPE
            # (10-min) to T, then branches into its QPF forecast to T+24h.
            if LR_run:
                print("***_________Phase 2b: Preparing LR (SCaMPR+GFS/AROME) EF5 control files_________***")
                with _ThreadPoolExecutor(max_workers=len(regions_to_run)) as executor:
                    futures = {executor.submit(_prep_lr_ef5_for_region, r): r for r in regions_to_run}
                    for future in _as_completed(futures):
                        r = futures[future]
                        try:
                            future.result()
                        except Exception as exc:
                            print(f"    !!! Region {r} LR EF5 prep raised: {exc}")

                if lr_ef5_jobs:
                    print("***_________Running LR EF5 simulations for all regions_________***")
                    run_ef5_simulations_parallel(lr_ef5_jobs, max_workers=len(lr_ef5_jobs))
                else:
                    print("    No LR EF5 jobs prepared.")

            if imerg_ef5_jobs or lr_ef5_jobs:
                newline(2)
                print("******** EF5 Outputs are ready!!! ********")
            else:
                print("No EF5 jobs were prepared.")

        else:
            # ── Legacy single-batch path (hindcast or non-SCAMPR modes) ──────────
            print("***_________Phase 2: Preparing QPF/EF5 control files (legacy path)_________***")
            with _ThreadPoolExecutor(max_workers=len(regions_to_run)) as executor:
                futures = {executor.submit(_prep_qpf_ef5_for_region, r): r for r in regions_to_run}
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

        # ── Phase 3: FIM scenario-library lookup (optional, config-driven) ──────────
        # A region runs FIM when one or more YAMLs named fim_config/<Region>*.yaml
        # exist (the examples/ subfolder is ignored). One YAML per FIM site, so a
        # country can carry several basins, e.g. Guatemala_SantaInesPetapa.yaml and
        # Guatemala_Morales.yaml. A top-level "enabled: false" line in a YAML skips
        # that site (used while a site's flood map store is not built yet).
        # Configs with a "hazards:" block use the pluvial + fluvial runner
        # (pipeline_pf); classic configs keep the v0.2 ensemble runner.
        # Fully non-fatal: any failure here never breaks the operational pipeline.
        # See README_FIM.md, fim_config/README.md and tito_utils/fim_utils/.
        _fim_config_dir = getattr(config_file, "fim_config_dir", "fim_config")
        if os.path.isdir(_fim_config_dir):
            print("***_________Phase 3: FIM scenario-library lookup_________***")
            try:
                import glob as _fim_glob
                for _fim_region in regions_to_run:
                    _fim_yamls = sorted(_fim_glob.glob(
                        os.path.join(_fim_config_dir, f"{_fim_region}*.yaml")))
                    if not _fim_yamls:
                        continue
                    _fim_rc = region_configs.get(_fim_region, {})
                    _fim_cycle = _fim_rc.get("output_timestamp_str")
                    for _fim_yaml in _fim_yamls:
                        _fim_site = os.path.splitext(os.path.basename(_fim_yaml))[0]
                        try:
                            _fim_is_pf = False
                            _fim_enabled = True
                            with open(_fim_yaml) as _fh:
                                for _l in _fh:
                                    if _l.strip().startswith("hazards:"):
                                        _fim_is_pf = True
                                    if (not _l[:1].isspace()
                                            and _l.split("#")[0].strip().lower()
                                            in ("enabled: false", "enabled: no")):
                                        _fim_enabled = False
                            if not _fim_enabled:
                                print(f"    FIM {_fim_site}: disabled in its YAML "
                                      "(enabled: false), skipped")
                                continue
                            if _fim_is_pf:
                                from tito_utils.fim_utils.pipeline_pf import (
                                    load_pf_config as _fim_load,
                                    run_pf_cycle as _fim_run)
                            else:
                                from tito_utils.fim_utils.pipeline_ensemble import (
                                    load_ensemble_config as _fim_load,
                                    run_ensemble_cycle as _fim_run)
                            _fim_cfg = _fim_load(_fim_yaml)
                            _fim_summary = _fim_run(_fim_cfg, cycle=_fim_cycle)
                            print(f"    FIM {_fim_site} [{_fim_cycle}]: "
                                  f"{_fim_summary.get('status', 'unknown')}")
                        except Exception as _fim_exc:
                            print(f"    !!! FIM {_fim_site} failed "
                                  f"(non-fatal): {_fim_exc}")
            except Exception as _fim_exc:
                print(f"    !!! FIM step unavailable (non-fatal): {_fim_exc}")
        # ── End Phase 3 ──────────────────────────────────────────────────────────────────
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

