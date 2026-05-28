"""
Real-time operational EF5 execution script
==========================================

IMERG-based operational system that integrates NWP outputs (GFS, AROME)
and SCaMPR gap-fill QPE to produce flash-flood forecasts in real time.

Precipitation download and sharing is delegated to
:mod:`tito_utils.file_utils.prepare_precip`.

Contributors:
    Vanessa Robledo  - vrobledodelgado@uiowa.edu
    Humberto Vergara - humberto-vergaraarrieta@uiowa.edu
    Naman Mehta      - naman-mehta@uiowa.edu

Usage::

    $> python orchestrator.py <configuration_file.py>
    $> python orchestrator.py config.py --regions Antigua,Haiti
"""

import glob
import importlib
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import numpy as np

from tito_utils.file_utils.file_handling import mkdir_p, newline
from tito_utils.file_utils.cleanup import (
    cleanup_staged_precip_folders,
)
from tito_utils.file_utils.prepare_precip import (
    prepare_all_precip,
)
from tito_utils.qpf_utils import (
    get_arome_domain_for_region,
)
from tito_utils.ef5.ef5_routines import (
    prepare_ef5,
    run_ef5_simulations_parallel,
)
from tito_utils.logging_utils import console, setup_run_log

print(">>> Modules imported")


# ═══════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════

def _with_sep(path: str) -> str:
    return os.path.join(path, "")


def _round_cycle_time(dt: datetime, step_minutes: int = 60) -> datetime:
    if step_minutes == 30:
        m = int(np.floor(dt.minute / 30.0) * 30)
    elif step_minutes == 60:
        m = 0
    else:
        step = max(1, int(step_minutes))
        m = int(np.floor(dt.minute / float(step)) * step)
    return dt.replace(minute=m, second=0, microsecond=0)


def _copy_tifs_from_shared(shared_folder: str, dest_folder: str):
    mkdir_p(dest_folder)
    for src in glob.glob(os.path.join(shared_folder, "*.tif")):
        try:
            shutil.copy2(src, dest_folder)
        except Exception as exc:
            print(f"    Warning: copy {os.path.basename(src)}: {exc}")


def _resolve_cold_start_window(config, sim_end):
    """Return (cold_start_begin, cold_start_warm_end) for IMERG-only EF5."""
    imerg_post = timedelta(hours=2)
    imerg_warmup = timedelta(hours=6)
    if hasattr(config, "imerg_post_warmup_duration"):
        raw = config.imerg_post_warmup_duration
        if isinstance(raw, timedelta):
            imerg_post = raw
    if hasattr(config, "imerg_cold_start_warmup"):
        raw = config.imerg_cold_start_warmup
        if isinstance(raw, timedelta):
            imerg_warmup = raw
    warm_end = sim_end - imerg_post
    begin = warm_end - imerg_warmup
    return begin, warm_end


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main(args):
    # ── CLI ──────────────────────────────────────────────────────────────
    import argparse as _argparse
    _ap = _argparse.ArgumentParser(add_help=False)
    _ap.add_argument("config", nargs="?", default="Caribbean_Comoros_config")
    _ap.add_argument("--regions", default=None,
                     help="Comma-separated region names (overrides config)")
    _cli, _ = _ap.parse_known_args(args[1:])
    _cli_regions = ([r.strip() for r in _cli.regions.split(",") if r.strip()]
                    if _cli.regions else None)

    config_module_name = os.path.splitext(os.path.basename(_cli.config))[0]
    config = importlib.import_module(config_module_name)
    print(">>> Config file loaded")

    # ── config ───────────────────────────────────────────────────────────
    regions_to_run = getattr(config, "regions_to_run", [config.subdomain])
    if isinstance(regions_to_run, str):
        regions_to_run = [regions_to_run]
    regions_to_run = [str(r).strip() for r in regions_to_run if str(r).strip()]
    if not regions_to_run:
        raise ValueError("No regions configured.  Set regions_to_run.")
    if _cli_regions:
        regions_to_run = [r for r in _cli_regions if r]

    systemModel      = config.systemModel
    systemTimestep   = config.systemTimestep
    ef5Path          = config.ef5Path
    statesPath       = config.statesPath
    precipEF5Folder  = config.precipEF5Folder
    modelStates      = config.modelStates
    templatePath     = config.templatePath
    default_template = config.templates
    region_template_map = getattr(config, "region_template_map", {})
    basicPath        = getattr(config, "basicPath", "basic/")
    parametersPath   = getattr(config, "parametersPath", "parameters/")
    dataPath         = config.dataPath
    qpf_store_path   = config.qpf_store_path
    SEND_ALERTS      = config.SEND_ALERTS
    alert_recipients  = config.alert_recipients
    smtp_config = {
        "smtp_server":      config.smtp_server,
        "smtp_port":        config.smtp_port,
        "account_address":  config.account_address,
        "account_password": config.account_password,
        "alert_sender":     config.alert_sender,
    }
    model_resolution = getattr(config, "model_resolution", "90m")
    systemName       = config.systemName
    LR_run           = config.run_LR
    LR_TimeStep      = config.LR_timestep
    qpe_source_default = getattr(config, "qpe_source", "IMERG").strip().upper()
    qpf_source_default = getattr(config, "qpf_source", "GFS").strip().upper()
    region_forcing_map = getattr(config, "region_forcing_map", {})
    qpe_gap_fill_mode  = getattr(config, "qpe_gap_fill_mode", "IMERG_ONLY").strip().upper()

    _VALID_QPE = {"IMERG", "HSAF", "SCAMPR", "STREAM_SAT"}
    _VALID_QPF = {"GFS", "WRF", "AROME"}

    def _normalize_qpe(val, fallback):
        c = str(val).strip().upper()
        return c if c in _VALID_QPE else fallback

    def _normalize_qpf(val, fallback):
        if isinstance(val, (list, tuple)):
            return [v for v in (str(x).strip().upper() for x in val)
                    if v in _VALID_QPF] or [fallback]
        c = str(val).strip().upper()
        return [c] if c in _VALID_QPF else [fallback]

    region_qpe_sources = {}
    region_qpf_requested = {}
    for region in regions_to_run:
        rc = region_forcing_map.get(region, {}) if isinstance(region_forcing_map, dict) else {}
        if not isinstance(rc, dict):
            rc = {}
        region_qpe_sources[region] = _normalize_qpe(
            rc.get("qpe_source", rc.get("qpe", qpe_source_default)), qpe_source_default)
        region_qpf_requested[region] = _normalize_qpf(
            rc.get("qpf_source", rc.get("qpf", qpf_source_default)), qpf_source_default)

    # ── cycle times ────────────────────────────────────────────────────
    HindCastMode = getattr(config, "HindCastMode", False)
    if HindCastMode:
        region_cycle_times = {}
        # Single cycle or loop
        hc_dates = []
        hc_start = datetime.strptime(str(getattr(config, "HindCastDate", "2024-07-04 09:00")), "%Y-%m-%d %H:%M")
        hc_end_str = str(getattr(config, "HindCastEndDate", "") or "").strip()
        if hc_end_str:
            hc_end = datetime.strptime(hc_end_str, "%Y-%m-%d %H:%M")
            t = hc_start
            while t <= hc_end:
                hc_dates.append(t)
                t += timedelta(hours=1)
            console.info("[bold]HINDCAST LOOP[/] %s → %s (%d cycles)",
                         hc_start.strftime("%Y-%m-%d %H:%M"),
                         hc_end.strftime("%Y-%m-%d %H:%M"), len(hc_dates))
        else:
            hc_dates = [hc_start]
            console.info("[bold]HINDCAST MODE[/] — single cycle: %s", hc_start.strftime("%Y-%m-%d %H:%M"))

        for cycle_idx, cycle_time in enumerate(hc_dates):
            if len(hc_dates) > 1:
                console.rule(f"[bold]Hindcast cycle {cycle_idx+1}/{len(hc_dates)}: {cycle_time.strftime('%Y-%m-%d %H:%M')} UTC[/]")
            for r in regions_to_run:
                region_cycle_times[r] = cycle_time
            _run_single_cycle(cycle_time, region_cycle_times, config, regions_to_run,
                              systemTimestep, LR_run, region_qpe_sources, region_qpf_requested,
                              qpe_gap_fill_mode, HindCastMode)
    else:
        cycle_time = _round_cycle_time(
            datetime.now(timezone.utc).replace(tzinfo=None), systemTimestep)
        region_cycle_times = {r: cycle_time for r in regions_to_run}
        _run_single_cycle(cycle_time, region_cycle_times, config, regions_to_run,
                          systemTimestep, LR_run, region_qpe_sources, region_qpf_requested,
                          qpe_gap_fill_mode, HindCastMode)


def _run_single_cycle(cycle_time, region_cycle_times, _config, regions_to_run,
                      systemTimestep, LR_run, region_qpe_sources, region_qpf_requested,
                      qpe_gap_fill_mode, HindCastMode):
    """Single-cycle pipeline body. Reads all needed variables from config."""
    config = _config

    # ── Config-derived variables (mirrors main()'s setup) ────────────
    systemModel      = config.systemModel
    ef5Path          = config.ef5Path
    statesPath       = config.statesPath
    precipEF5Folder  = config.precipEF5Folder
    modelStates      = config.modelStates
    templatePath     = config.templatePath
    default_template = config.templates
    region_template_map = getattr(config, "region_template_map", {})
    basicPath        = getattr(config, "basicPath", "basic/")
    parametersPath   = getattr(config, "parametersPath", "parameters/")
    dataPath         = config.dataPath
    qpf_store_path   = config.qpf_store_path
    SEND_ALERTS      = config.SEND_ALERTS
    alert_recipients  = config.alert_recipients
    smtp_config = {
        "smtp_server":      config.smtp_server,
        "smtp_port":        config.smtp_port,
        "account_address":  config.account_address,
        "account_password": config.account_password,
        "alert_sender":     config.alert_sender,
    }
    model_resolution = getattr(config, "model_resolution", "90m")
    systemName       = config.systemName
    LR_TimeStep      = config.LR_timestep

    # ── Master pipeline log ──────────────────────────────────────────────
    ss_out_root = getattr(config, "stream_sat_output_folder", "outputs/stream_sat/")
    master_log = setup_run_log(ss_out_root, f"pipeline_{cycle_time.strftime('%Y%m%d_%H%M')}")
    master_log.info("TITO cycle start — %s UTC", cycle_time.strftime("%Y-%m-%d %H:%M"))
    master_log.info("Regions: %s", ", ".join(regions_to_run))
    for r in regions_to_run:
        master_log.info("  %s: qpe=%s qpf=%s", r,
                        region_qpe_sources.get(r, "?"),
                        region_qpf_requested.get(r, []))

    console.rule(f"[bold]TITO Cycle {cycle_time.strftime('%Y-%m-%d %H:%M')} UTC[/]")
    print(f"  Regions: {', '.join(regions_to_run)}")

    # ── Pre-clean: wipe precipEF5 so stale files from a crashed previous
    #    cycle never mix with the current run's precipitation.
    console.info("[bold]Pre-clean:[/] wiping precipEF5 …")
    for root, dirs, files in os.walk(precipEF5Folder, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except OSError:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass
    master_log.info("Pre-clean: wiped precipEF5 (%s)", precipEF5Folder)

    lr_duration = timedelta(hours=24) if LR_run else timedelta(0)

    # ═════════════════════════════════════════════════════════════════════
    # STEP 1 — Download & share all precipitation
    # ═════════════════════════════════════════════════════════════════════
    console.info("[bold]STEP 1:[/] Download & prepare precipitation …")
    shared = prepare_all_precip(
        regions_to_run, region_cycle_times,
        region_qpe_sources, region_qpf_requested,
        config,
        master_log=master_log,
    )
    console.info("[bold]STEP 1:[/] Precipitation ready.")

    # ═════════════════════════════════════════════════════════════════════
    # STEP 2 — Build per-region EF5 configuration dicts
    # ═════════════════════════════════════════════════════════════════════
    region_configs = {}
    for region in regions_to_run:
        rkey = region.lower()
        ct = region_cycle_times[region]
        qpe = region_qpe_sources[region]
        qpf_list = region_qpf_requested[region] if LR_run else []
        imerg_offset = timedelta(hours=4) if qpe == "IMERG" else timedelta(0)
        r_imerg_end = ct - timedelta(hours=4) if qpe == "IMERG" else ct

        # template
        tmpl_candidate = f"ef5_{region}_control_template.txt"
        tmpl = region_template_map.get(region, tmpl_candidate)
        tmpl_path = os.path.join(templatePath, tmpl)
        if not os.path.isfile(tmpl_path):
            tmpl = default_template
            tmpl_path = os.path.join(templatePath, tmpl)

        r_start_lr  = ct
        r_end_lr    = r_start_lr + lr_duration
        r_end_time  = r_end_lr + timedelta(hours=6) if LR_run else ct
        r_state_end = ct - imerg_offset
        r_warm_end  = ct - imerg_offset
        r_sys_start = r_warm_end - timedelta(minutes=30)
        r_fail_time = r_warm_end - timedelta(days=7)
        output_ts   = ct.strftime("%Y%m%d.%H%M%S")

        region_configs[region] = {
            "region_key":           rkey,
            "region_current_time":  ct,
            "output_timestamp_str": output_ts,
            "qpe_source":           qpe,
            "qpf_sources":          qpf_list,
            "region_template":      tmpl,
            "r_start_lr":           r_start_lr,
            "r_end_lr":             r_end_lr,
            "r_end_time":           r_end_time,
            "r_state_end":          r_state_end,
            "r_warm_end":           r_warm_end,
            "r_system_start":       r_sys_start,
            "r_fail_time":          r_fail_time,
            "r_imerg_end":          r_imerg_end,
            "r_scampr_end":         ct,
            "cycle_time_key":       ct.strftime("%Y%m%d%H%M"),
            # ── State path: differs by QPE source ─────────────────────
            # IMERG / HSAF / SCaMPR: states/<region>/
            # STREAM_SAT: states are per-member in states/stream_sat/ensS{N}/<region>/
            #   (set inside _build_streamsat_ensemble_jobs, NOT here)
            "region_states_path":   os.path.join(statesPath, rkey),
            "region_data_path":     os.path.join(dataPath, rkey),
            "region_qpf_store":     _with_sep(os.path.join(qpf_store_path, rkey)),
        }

    # ═════════════════════════════════════════════════════════════════════
    # STEP 3 — Create per-region directories (states, data, qpf_store)
    # ═════════════════════════════════════════════════════════════════════
    print("***_________Creating per-region directories_________***")
    for region in regions_to_run:
        cfg = region_configs[region]
        is_streamsat = region_qpe_sources.get(region, "").upper() == "STREAM_SAT"

        # STREAM_SAT regions use per-member state folders:
        #   states/stream_sat/ensS{N}/<region>/
        # Those are created inside _build_streamsat_ensemble_jobs.
        # Skip the IMERG-style states/<region>/ directory to avoid confusion.
        if not is_streamsat:
            mkdir_p(cfg["region_states_path"])
        mkdir_p(cfg["region_data_path"])
        mkdir_p(cfg["region_qpf_store"])
        print(f"    {region}: states={cfg['region_states_path']} "
              f"({'STREAM_SAT=per-member' if is_streamsat else 'IMERG/default'}), "
              f"data={cfg['region_data_path']}")

    # ═════════════════════════════════════════════════════════════════════
    # STEP 4 — Per-region QPF staging (copy shared → region qpf_store)
    # ═════════════════════════════════════════════════════════════════════
    if LR_run:
        print("***_________Staging QPF to per-region qpf_store_________***")
        for region in regions_to_run:
            cfg = region_configs[region]
            ck = cfg["cycle_time_key"]
            store = cfg["region_qpf_store"]
            mkdir_p(store)

            for qpf_src in cfg["qpf_sources"]:
                if qpf_src == "GFS" and ck in shared.gfs_cache:
                    dest = os.path.join(store, "gfs_data")
                    _copy_tifs_from_shared(shared.gfs_cache[ck], dest)
                elif qpf_src == "AROME":
                    try:
                        domain = get_arome_domain_for_region(region)
                        akey = (ck, domain)
                        if akey in shared.arome_cache:
                            dest = os.path.join(store, "arome_data")
                            _copy_tifs_from_shared(shared.arome_cache[akey], dest)
                    except ValueError:
                        print(f"    AROME: no domain for {region} — skip")

    # ═════════════════════════════════════════════════════════════════════
    # STEP 5 — EF5 job builders
    # ═════════════════════════════════════════════════════════════════════

    _lock = threading.Lock()
    staged_precip_folders: set = set()
    imerg_ef5_jobs: list = []
    lr_ef5_jobs: list = []

    # ── 4a: IMERG-only EF5 job (T-start → T−4h, saves state) ────────────
    def _build_imerg_ef5_job(region: str):
        cfg = region_configs[region]
        rkey  = cfg["region_key"]
        r_imerg_end = cfg["r_imerg_end"]
        ck = cfg["cycle_time_key"]

        # IMERG is shared at cycle level — one folder for ALL IMERG regions
        imerg_qpe_folder = shared.imerg_folders.get(ck, "")
        if not imerg_qpe_folder:
            print(f"    !!! {region}: no IMERG shared folder — skipping")
            return

        cold_begin, cold_warm_end = _resolve_cold_start_window(config, r_imerg_end)

        tmp_out = os.path.join(cfg["region_data_path"],
                               f"tmp_output_{systemModel}_imerg")
        staging = os.path.join(precipEF5Folder, rkey, "imerg_none")
        mkdir_p(staging)
        mkdir_p(tmp_out)

        try:
            job_log = setup_run_log(cfg["region_data_path"], f"ef5_imerg_{rkey}")
            job_log.info("IMERG EF5 prep — region=%s", region)
            eff_start, ctrl_file, run_path = prepare_ef5(
                staging,                        # precipEF5Folder
                imerg_qpe_folder,               # precipFolder (source)
                _with_sep(cfg["region_states_path"]),
                modelStates,
                r_imerg_end - timedelta(minutes=30),
                r_imerg_end - timedelta(days=7),
                cfg["region_current_time"],
                systemName,
                SEND_ALERTS, alert_recipients, smtp_config,
                _with_sep(tmp_out),
                _with_sep(cfg["region_data_path"]),
                region, systemModel,
                templatePath, cfg["region_template"],
                r_imerg_end,                    # systemStartLRTime (unused)
                cold_warm_end,
                r_imerg_end,                    # systemStateEndTime (T−4h)
                r_imerg_end,                    # systemEndTime (T−4h)
                LR_TimeStep,
                False,                          # LR_run
                region, model_resolution,
                basicPath, parametersPath,
                "IMERG", "none",
                stage_precip=True,
                output_timestamp_str=cfg["output_timestamp_str"],
                qpf_store_forcing_path=cfg["region_qpf_store"],
                save_states=True,
                cold_start_begin_time=cold_begin,
                cold_start_warm_end_time=cold_warm_end,
                verbose=True,
                run_log=job_log,
                # NO imerg_download_params — IMERG already fully downloaded
                # by prepare_all_precip with a 30-min buffer.
            )
            print(f"    {region} [IMERG]: {eff_start.strftime('%Y%m%d_%H%M')} → "
                  f"{r_imerg_end.strftime('%Y%m%d_%H%M')}, ctrl={ctrl_file}")
            with _lock:
                staged_precip_folders.add(staging)
                imerg_ef5_jobs.append({
                    "region":               region,
                    "ef5Path":              ef5Path,
                    "tmpOutput":            run_path + "/",
                    "controlFile":          ctrl_file,
                    "output_timestamp_str": cfg["output_timestamp_str"],
                })
        except Exception as exc:
            print(f"    !!! {region} IMERG EF5 prep failed: {exc}")

    # ── 4b: LR EF5 jobs (SCaMPR QPE → GFS/AROME QPF) ────────────────────
    def _build_lr_ef5_jobs(region: str):
        cfg = region_configs[region]
        rkey = cfg["region_key"]
        r_imerg_end  = cfg["r_imerg_end"]
        r_scampr_end = cfg["r_scampr_end"]
        r_lr_end     = cfg["r_end_lr"]

        scampr_precip = shared.scampr_folder
        if not scampr_precip:
            print(f"    !!! {region}: no SCaMPR folder — skipping LR runs")
            return

        for qpf_src in cfg["qpf_sources"]:
            actual_qpf = qpf_src

            # WRF with GFS fallback
            if qpf_src == "WRF":
                wrf_path = getattr(config, "WRF_archive_path", "")
                if wrf_path:
                    try:
                        from tito_utils.qpf_utils import WRF_searcher as _wrf
                        wrf_ok = _wrf(
                            wrf_path, cfg["region_qpf_store"],
                            r_scampr_end, r_lr_end,
                            LR_TimeStep,
                            getattr(config, "WRF_var_name", "PREC_ACC_C"),
                            getattr(config, "WRF_filename_template",
                                    "PREC_d01_YYYY-MM-DD_HH_mm_SS.nc"),
                        )
                        if wrf_ok:
                            actual_qpf = "WRF"
                        else:
                            print(f"    {region}: WRF unavailable → GFS fallback")
                            actual_qpf = "GFS"
                    except Exception:
                        actual_qpf = "GFS"
                else:
                    actual_qpf = "GFS"

            tmp_out = os.path.join(
                cfg["region_data_path"],
                f"tmp_output_{systemModel}_scampr_{actual_qpf.lower()}")
            staging = os.path.join(precipEF5Folder, rkey,
                                   f"scampr_{actual_qpf.lower()}")
            mkdir_p(staging)
            mkdir_p(tmp_out)

            try:
                lr_log = setup_run_log(cfg["region_data_path"],
                                       f"ef5_lr_{rkey}_{actual_qpf.lower()}")
                lr_log.info("LR EF5 prep — region=%s qpf=%s", region, actual_qpf)
                eff_start, ctrl_file, run_path = prepare_ef5(
                    staging,                        # precipEF5Folder
                    scampr_precip,                  # precipFolder (SCaMPR)
                    _with_sep(cfg["region_states_path"]),
                    modelStates,
                    r_imerg_end,                    # find IMERG state at T−4h
                    r_imerg_end,                    # don't search beyond
                    cfg["region_current_time"],
                    systemName,
                    SEND_ALERTS, alert_recipients, smtp_config,
                    _with_sep(tmp_out),
                    _with_sep(cfg["region_data_path"]),
                    region, systemModel,
                    templatePath, cfg["region_template"],
                    r_scampr_end,                   # systemStartLRTime (T)
                    r_scampr_end,                   # systemWarmEndTime (T)
                    r_lr_end,                       # systemStateEndTime
                    r_lr_end,                       # systemEndTime
                    LR_TimeStep,
                    True,                           # LR_run
                    region, model_resolution,
                    basicPath, parametersPath,
                    "SCAMPR", actual_qpf,
                    stage_precip=True,
                    output_timestamp_str=cfg["output_timestamp_str"],
                    qpf_store_forcing_path=cfg["region_qpf_store"],
                    save_states=False,
                    verbose=True,
                    run_log=lr_log,
                )
                print(f"    {region} [SCaMPR+{actual_qpf}]: "
                      f"state@T−4h → QPE→T → QPF→"
                      f"{r_lr_end.strftime('%Y%m%d_%H%M')}, ctrl={ctrl_file}")
                with _lock:
                    staged_precip_folders.add(staging)
                    lr_ef5_jobs.append({
                        "region":               region,
                        "ef5Path":              ef5Path,
                        "tmpOutput":            run_path + "/",
                        "controlFile":          ctrl_file,
                        "output_timestamp_str": cfg["output_timestamp_str"],
                    })
            except Exception as exc:
                print(f"    !!! {region} LR ({actual_qpf}) EF5 prep failed: {exc}")

    # ── 4c: STREAM-Sat ensemble EF5 jobs ─────────────────────────────────
    # Two-phase ensemble approach:
    #   Phase A: STREAM-Sat QPE only → run each member, save state at end
    #   Phase B: SCaMPR + QPF gap fill → start from STREAM-Sat state, no state mgmt

    streamsat_ef5_jobs: list = []       # Phase A: STREAM-Sat only
    streamsat_lr_ef5_jobs: list = []    # Phase B: SCaMPR + QPF

    # Check if any region uses STREAM_SAT
    has_streamsat = any(
        region_qpe_sources.get(r, "").upper() == "STREAM_SAT"
        for r in regions_to_run
    )

    if has_streamsat:
        stream_sat_state_root = getattr(config, "stream_sat_state_folder", "states/stream_sat/")
        stream_sat_output_root = getattr(config, "stream_sat_output_folder", "outputs/stream_sat/")
        stream_sat_gap_mode = getattr(config, "stream_sat_gap_fill_mode", "SCAMPR_QPE").strip().upper()

        # Hindcast mode: no SCaMPR gap fill, QPF-only from STREAM-Sat states
        if HindCastMode:
            stream_sat_gap_mode = "NONE"
            console.info("[bold]HINDCAST:[/] STREAM-Sat gap fill disabled — QPF-only from states")

        def _build_streamsat_ensemble_jobs(region: str):
            """Build EF5 jobs for ALL ensemble members of one STREAM_SAT region."""
            cfg = region_configs[region]
            rkey = cfg["region_key"]
            ct = cfg["region_current_time"]
            ck = cfg["cycle_time_key"]

            ss_info = shared.streamsat_info.get(region, {})
            if "error" in ss_info:
                print(f"    !!! {region}: STREAM-Sat prep failed: {ss_info['error']}")
                return
            if not ss_info:
                print(f"    !!! {region}: no STREAM-Sat info — skipping")
                return

            ens_size = ss_info.get("ensemble_size", 10)
            tif_root = ss_info.get("tif_root", "")
            if not tif_root:
                print(f"    !!! {region}: no tif_root in STREAM-Sat info")
                return

            # Determine STREAM-Sat time window from the GeoTIFFs
            ensP1_dir = os.path.join(tif_root, "ensP1")
            if not os.path.isdir(ensP1_dir):
                print(f"    !!! {region}: STREAM-Sat ensP1 dir not found: {ensP1_dir}")
                return

            # Parse timestamps from GeoTIFF filenames
            tif_pattern = getattr(config, "stream_sat_tif_naming", "streamsat")
            tif_files = sorted(glob.glob(os.path.join(ensP1_dir, f"{tif_pattern}.qpe.*.mmhInst.tif")))
            if not tif_files:
                print(f"    !!! {region}: no STREAM-Sat GeoTIFFs in {ensP1_dir}")
                return

            streamsat_timestamps = []
            for tf in tif_files:
                m = re.search(r"qpe\.(\d{12})\.", os.path.basename(tf))
                if m:
                    try:
                        streamsat_timestamps.append(datetime.strptime(m.group(1), "%Y%m%d%H%M"))
                    except ValueError:
                        pass
            if not streamsat_timestamps:
                print(f"    !!! {region}: could not parse timestamps from GeoTIFFs")
                return

            ss_start = min(streamsat_timestamps)
            ss_end = max(streamsat_timestamps)

            # NOTE: ss_end is the ACTUAL last STREAM-Sat timestep on disk —
            # NOT a hardcoded T−4h. If IMERG is delayed (e.g. T−5h or T−6h),
            # ss_end reflects that naturally. Phase B SCaMPR gap fill spans
            # ss_end → ct dynamically regardless of latency.

            print(f"    {region} [STREAM_SAT]: window {ss_start.strftime('%Y%m%d_%H%M')} → "
                  f"{ss_end.strftime('%Y%m%d_%H%M')} (driven by actual data), {ens_size} members")

            # SCaMPR for gap fill
            scampr_folder = getattr(shared, "scampr_folder", None)
            do_gap_fill = stream_sat_gap_mode in ("SCAMPR_QPE", "SCAMPR_ONLY") and scampr_folder

            for member_idx in range(1, ens_size + 1):
                # ── Per-member paths ──────────────────────────────────
                # STATE SEPARATION: Each ensemble member gets its OWN
                # state folder, completely independent from IMERG states.
                #   IMERG:   states/<region>/crest_SM_*.tif
                #   STREAM:  states/stream_sat/ensS{N}/<region>/crest_SM_*.tif
                member_precip = os.path.join(tif_root, f"ensP{member_idx}", "")
                member_states = os.path.join(stream_sat_state_root, f"ensS{member_idx}", rkey, "")
                member_output = os.path.join(stream_sat_output_root, f"ensOut{member_idx}", rkey, "")
                member_tmp = os.path.join(
                    member_output, f"tmp_output_{systemModel}_streamsat"
                )

                mkdir_p(member_precip)
                mkdir_p(member_states)
                mkdir_p(member_output)
                mkdir_p(member_tmp)

                # ── Phase A: STREAM-Sat QPE only run ──────────────────
                staging_a = os.path.join(
                    precipEF5Folder, rkey, f"streamsat_ens{member_idx:02d}"
                )
                mkdir_p(staging_a)

                try:
                    # Cold start: if no states, use STREAM-Sat window bounds
                    cold_begin = ss_start
                    cold_warm_end = ss_start + timedelta(hours=6)
                    if cold_warm_end > ss_end:
                        cold_warm_end = ss_end

                    # Quiet logging for ensemble members 2+ (first member stays verbose)
                    is_first = (member_idx == 1)
                    run_log = setup_run_log(
                        member_output,
                        f"ef5_ens{member_idx:02d}",
                    ) if not is_first else None

                    eff_start, ctrl_file, run_path = prepare_ef5(
                        staging_a,
                        member_precip,
                        _with_sep(member_states),
                        modelStates,
                        ss_end - timedelta(minutes=30),
                        ss_end - timedelta(days=7),
                        ct,
                        systemName,
                        SEND_ALERTS, alert_recipients, smtp_config,
                        _with_sep(member_tmp),
                        _with_sep(member_output),
                        region, systemModel,
                        templatePath, cfg["region_template"],
                        ss_end,
                        ss_end,
                        ss_end,
                        ss_end,
                        LR_TimeStep,
                        False,                       # LR_run
                        region, model_resolution,
                        basicPath, parametersPath,
                        "STREAM_SAT", "none",
                        stage_precip=True,
                        output_timestamp_str=cfg["output_timestamp_str"],
                        qpf_store_forcing_path=cfg["region_qpf_store"],
                        save_states=True,
                        cold_start_begin_time=cold_begin,
                        cold_start_warm_end_time=cold_warm_end,
                        verbose=is_first,
                        run_log=run_log,
                    )
                    master_log.info("    %s [SS ens%02d]: %s → %s, ctrl=%s",
                                   region, member_idx,
                                   eff_start.strftime('%Y%m%d_%H%M'),
                                   ss_end.strftime('%Y%m%d_%H%M'), ctrl_file)
                    if is_first:
                        print(f"    {region} [SS ens{member_idx:02d}]: "
                              f"{eff_start.strftime('%Y%m%d_%H%M')} → "
                              f"{ss_end.strftime('%Y%m%d_%H%M')}")
                    with _lock:
                        staged_precip_folders.add(staging_a)
                        streamsat_ef5_jobs.append({
                            "region":               region,
                            "member":               member_idx,
                            "ef5Path":              ef5Path,
                            "tmpOutput":            run_path + "/",
                            "controlFile":          ctrl_file,
                            "output_timestamp_str": cfg["output_timestamp_str"],
                        })
                except Exception as exc:
                    print(f"    !!! {region} [SS ens{member_idx:02d}] EF5 prep failed: {exc}")
                    continue

                # ── Phase B: SCaMPR + QPF gap fill (realtime) / Phase H: QPF-only (hindcast) ──
                # Realtime: SCaMPR fills ss_end→ct, then GFS/AROME ct→ct+24h
                # Hindcast:  QPF-only from STREAM-Sat state, no SCaMPR gap fill
                if HindCastMode:
                    # ── Phase H: Hindcast QPF-only (GFS only, skip AROME) ──
                    hindcast_qpf = [s for s in cfg["qpf_sources"] if s.upper() == "GFS"]
                    for qpf_src in hindcast_qpf:
                        actual_qpf = qpf_src
                        if qpf_src == "WRF":
                            actual_qpf = "GFS"
                        staging_h = os.path.join(
                            precipEF5Folder, rkey,
                            f"streamsat_ens{member_idx:02d}_qpf_{actual_qpf.lower()}"
                        )
                        mkdir_p(staging_h)
                        member_tmp_h = os.path.join(
                            member_output,
                            f"tmp_output_{systemModel}_qpf_{actual_qpf.lower()}"
                        )
                        mkdir_p(member_tmp_h)
                        try:
                            # QPF run: start from STREAM-Sat state, no SCaMPR prep
                            eff_start_h, ctrl_file_h, run_path_h = prepare_ef5(
                                staging_h,
                                member_precip,          # reuse STREAM-Sat precip folder (for QPE=None, not used)
                                _with_sep(member_states),
                                modelStates,
                                ss_end,
                                ss_end,
                                ct,
                                systemName,
                                SEND_ALERTS, alert_recipients, smtp_config,
                                _with_sep(member_tmp_h),
                                _with_sep(member_output),
                                region, systemModel,
                                templatePath, cfg["region_template"],
                                ct,                    # systemStartLRTime = cycle time
                                ct,                    # systemWarmEndTime
                                cfg["r_end_lr"],       # systemStateEndTime
                                cfg["r_end_lr"],       # systemEndTime
                                LR_TimeStep,
                                True,                  # LR_run
                                region, model_resolution,
                                basicPath, parametersPath,
                                "STREAM_SAT", actual_qpf,
                                stage_precip=False,    # precip already staged in Phase A
                                output_timestamp_str=cfg["output_timestamp_str"],
                                qpf_store_forcing_path=cfg["region_qpf_store"],
                                save_states=False,
                                verbose=is_first,
                                run_log=run_log,
                            )
                            print(f"    {region} [SS ens{member_idx:02d} QPF+{actual_qpf}]: "
                                  f"state@SS_end → QPF→"
                                  f"{cfg['r_end_lr'].strftime('%Y%m%d_%H%M')}")
                            master_log.info("    %s [SS ens%02d QPF+%s]: state@SS_end → QPF→%s, ctrl=%s",
                                           region, member_idx, actual_qpf,
                                           cfg['r_end_lr'].strftime('%Y%m%d_%H%M'), ctrl_file_h)
                            with _lock:
                                staged_precip_folders.add(staging_h)
                                streamsat_lr_ef5_jobs.append({
                                    "region":               region,
                                    "member":               member_idx,
                                    "ef5Path":              ef5Path,
                                    "tmpOutput":            run_path_h + "/",
                                    "controlFile":          ctrl_file_h,
                                    "output_timestamp_str": cfg["output_timestamp_str"],
                                })
                        except Exception as exc:
                            print(f"    !!! {region} [SS ens{member_idx:02d}] QPF ({actual_qpf}) "
                                  f"EF5 prep failed: {exc}")

                elif do_gap_fill:
                    for qpf_src in cfg["qpf_sources"]:
                        actual_qpf = qpf_src
                        if qpf_src == "WRF":
                            actual_qpf = "GFS"  # WRF fallback

                        staging_b = os.path.join(
                            precipEF5Folder, rkey,
                            f"streamsat_ens{member_idx:02d}_scampr_{actual_qpf.lower()}"
                        )
                        mkdir_p(staging_b)
                        member_tmp_b = os.path.join(
                            member_output,
                            f"tmp_output_{systemModel}_scampr_{actual_qpf.lower()}"
                        )
                        mkdir_p(member_tmp_b)

                        try:
                            eff_start_b, ctrl_file_b, run_path_b = prepare_ef5(
                                staging_b,                 # precipEF5Folder
                                scampr_folder,             # precipFolder (SCaMPR)
                                _with_sep(member_states),
                                modelStates,
                                ss_end,                    # find state at STREAM-Sat end
                                ss_end,                    # don't search beyond
                                ct,
                                systemName,
                                SEND_ALERTS, alert_recipients, smtp_config,
                                _with_sep(member_tmp_b),
                                _with_sep(member_output),
                                region, systemModel,
                                templatePath, cfg["region_template"],
                                ct,                        # systemStartLRTime (T)
                                ct,                        # systemWarmEndTime (T)
                                cfg["r_end_lr"],           # systemStateEndTime
                                cfg["r_end_lr"],           # systemEndTime
                                LR_TimeStep,
                                True,                      # LR_run
                                region, model_resolution,
                                basicPath, parametersPath,
                                "SCAMPR", actual_qpf,
                                stage_precip=True,
                                output_timestamp_str=cfg["output_timestamp_str"],
                                qpf_store_forcing_path=cfg["region_qpf_store"],
                                save_states=False,
                                verbose=is_first,
                                run_log=run_log,
                            )
                            print(f"    {region} [SS ens{member_idx:02d} SCaMPR+{actual_qpf}]: "
                                  f"state@SS_end → QPE→T → QPF→"
                                  f"{cfg['r_end_lr'].strftime('%Y%m%d_%H%M')}")
                            master_log.info("    %s [SS ens%02d SCaMPR+%s]: state@SS_end → QPF→%s, ctrl=%s",
                                           region, member_idx, actual_qpf,
                                           cfg['r_end_lr'].strftime('%Y%m%d_%H%M'), ctrl_file_b)
                            with _lock:
                                staged_precip_folders.add(staging_b)
                                streamsat_lr_ef5_jobs.append({
                                    "region":               region,
                                    "member":               member_idx,
                                    "ef5Path":              ef5Path,
                                    "tmpOutput":            run_path_b + "/",
                                    "controlFile":          ctrl_file_b,
                                    "output_timestamp_str": cfg["output_timestamp_str"],
                                })
                        except Exception as exc:
                            print(f"    !!! {region} [SS ens{member_idx:02d}] LR ({actual_qpf}) "
                                  f"EF5 prep failed: {exc}")

        # ── Dispatch STREAM-Sat ensemble jobs for all STREAM_SAT regions ──
        ss_regions = [
            r for r in regions_to_run
            if region_qpe_sources.get(r, "").upper() == "STREAM_SAT"
        ]
        if ss_regions:
            print("***_________Building STREAM-Sat ensemble EF5 jobs_________***")
            with ThreadPoolExecutor(max_workers=len(ss_regions)) as ex:
                futures = {ex.submit(_build_streamsat_ensemble_jobs, r): r
                           for r in ss_regions}
                for future in as_completed(futures):
                    r = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"    !!! {r} STREAM-Sat EF5 prep raised: {exc}")

    # ═════════════════════════════════════════════════════════════════════
    # STEP 5 — Execute EF5
    # ═════════════════════════════════════════════════════════════════════

    try:
        # ── STREAM-Sat ensemble execution (separate from IMERG flow) ──
        if streamsat_ef5_jobs:
            print(f"***_________Phase SS-A: STREAM-Sat EF5 ({len(streamsat_ef5_jobs)} jobs)_________***")
            run_ef5_simulations_parallel(
                streamsat_ef5_jobs,
                max_workers=min(len(streamsat_ef5_jobs), max(1, (os.cpu_count() or 4))),
            )
            print("    STREAM-Sat ensemble runs complete — states saved at window end")

        if streamsat_lr_ef5_jobs:
            print(f"***_________Phase SS-B: SCaMPR+QPF EF5 ({len(streamsat_lr_ef5_jobs)} jobs)_________***")
            run_ef5_simulations_parallel(
                streamsat_lr_ef5_jobs,
                max_workers=min(len(streamsat_lr_ef5_jobs), max(1, (os.cpu_count() or 4))),
            )
            print("    STREAM-Sat SCaMPR+QPF ensemble runs complete")

        if streamsat_ef5_jobs or streamsat_lr_ef5_jobs:
            newline(2)
            print("******** STREAM-Sat EF5 Outputs are ready!!! ********")

            # ── Simulation summary ────────────────────────────────────
            summary = []
            summary.append("=" * 60)
            summary.append("  SIMULATION SUMMARY")
            summary.append("=" * 60)
            summary.append(f"  Cycle:  {cycle_time.strftime('%Y-%m-%d %H:%M')} UTC")
            # Per-region STREAM-Sat info
            for region in regions_to_run:
                ss_info = shared.streamsat_info.get(region, {})
                if ss_info and "error" not in ss_info:
                    summary.append(f"  {region}:")
                    summary.append(f"    STREAM-Sat members: {ss_info.get('ensemble_size', '?')}")
                    summary.append(f"    GeoTIFFs root:     {ss_info.get('tif_root', '?')}")
            summary.append(f"  Phase SS-A jobs: {len(streamsat_ef5_jobs)}  (STREAM-Sat only, save states)")
            summary.append(f"  Phase SS-B jobs: {len(streamsat_lr_ef5_jobs)}  (SCaMPR + QPF)")
            summary.append(f"  IMERG EF5 jobs:  {len(imerg_ef5_jobs)}")
            summary.append(f"  LR EF5 jobs:     {len(lr_ef5_jobs)}")
            summary.append("=" * 60)
            for line in summary:
                print(line)
                master_log.info(line)

        # ── Original IMERG/SCaMPR flow ────────────────────────────────
        # Filter out STREAM_SAT regions (they are handled separately above)
        non_streamsat_regions = [
            r for r in regions_to_run
            if region_qpe_sources.get(r, "").upper() != "STREAM_SAT"
        ]

        if qpe_gap_fill_mode == "IMERG_SCAMPR":
            # ── 5a: IMERG EF5 ────────────────────────────────────────────
            print("***_________Phase 2a: IMERG EF5 control files_________***")
            with ThreadPoolExecutor(max_workers=len(non_streamsat_regions) or 1) as ex:
                futures = {ex.submit(_build_imerg_ef5_job, r): r
                           for r in non_streamsat_regions}
                for future in as_completed(futures):
                    r = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"    !!! {r} IMERG EF5 prep raised: {exc}")

            if imerg_ef5_jobs:
                print("***_________Running IMERG EF5 simulations_________***")
                run_ef5_simulations_parallel(imerg_ef5_jobs,
                                             max_workers=len(imerg_ef5_jobs))
                print("    IMERG EF5 runs complete — states saved at T−4h")
            else:
                print("    No IMERG EF5 jobs prepared.")

            # ── 5b: LR EF5 ───────────────────────────────────────────────
            if LR_run:
                print("***_________Phase 2b: LR EF5 control files_________***")
                with ThreadPoolExecutor(max_workers=len(non_streamsat_regions) or 1) as ex:
                    futures = {ex.submit(_build_lr_ef5_jobs, r): r
                               for r in non_streamsat_regions}
                    for future in as_completed(futures):
                        r = futures[future]
                        try:
                            future.result()
                        except Exception as exc:
                            print(f"    !!! {r} LR EF5 prep raised: {exc}")

                if lr_ef5_jobs:
                    print("***_________Running LR EF5 simulations_________***")
                    run_ef5_simulations_parallel(lr_ef5_jobs,
                                                 max_workers=len(lr_ef5_jobs))
                else:
                    print("    No LR EF5 jobs prepared.")

            if imerg_ef5_jobs or lr_ef5_jobs:
                newline(2)
                print("******** EF5 Outputs are ready!!! ********")
            else:
                print("No EF5 jobs were prepared.")

        else:
            # Single-batch for non-SCAMPR gap-fill modes
            print("***_________Preparing EF5 control files_________***")
            with ThreadPoolExecutor(max_workers=len(non_streamsat_regions) or 1) as ex:
                futures = {ex.submit(_build_imerg_ef5_job, r): r
                           for r in non_streamsat_regions}
                for future in as_completed(futures):
                    r = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"    !!! {r} EF5 prep raised: {exc}")

            if imerg_ef5_jobs:
                print("***_________Running EF5 simulations_________***")
                run_ef5_simulations_parallel(imerg_ef5_jobs,
                                             max_workers=len(imerg_ef5_jobs))
                newline(2)
                print("******** EF5 Outputs are ready!!! ********")
            else:
                print("No EF5 jobs were prepared.")

    finally:
        # ── cleanup ──────────────────────────────────────────────────────
        if staged_precip_folders:
            print("***_________Cleaning staged precipEF5 folders_________***")
            removed = cleanup_staged_precip_folders(staged_precip_folders)
            print(f"    Removed {removed} staged precip files")

        # Clean regional qpf_store forecast data
        print("***_________Cleaning regional qpf_store_________***")
        for region in regions_to_run:
            store = region_configs[region]["region_qpf_store"]
            for sub in ["gfs_data", "arome_data", "wrf_data"]:
                sp = os.path.join(store, sub)
                if os.path.isdir(sp):
                    try:
                        shutil.rmtree(sp)
                        print(f"    Removed {sp}")
                    except Exception as exc:
                        print(f"    Warning: could not remove {sp}: {exc}")

        # ── Clean STREAM-Sat GeoTIFFs ─────────────────────────────────
        # PAUSED: clearing prevents the skip-existing logic from working.
        # Each cycle only produces ~2 new timesteps; keeping old GeoTIFFs
        # lets the converter skip 98% of files, saving significant time.
        # To re-enable, uncomment the block below.
        #
        # ss_precip_root = getattr(config, "stream_sat_precip_folder", "precip/stream_sat/")
        # if os.path.isdir(ss_precip_root):
        #     for domain_dir in os.listdir(ss_precip_root):
        #         dp = os.path.join(ss_precip_root, domain_dir)
        #         if os.path.isdir(dp):
        #             try:
        #                 shutil.rmtree(dp)
        #                 print(f"    Removed STREAM-Sat precip: {dp}")
        #             except Exception as exc:
        #                 print(f"    Warning: could not remove {dp}: {exc}")

        # Prune shared caches
        for cache_name in ["_shared", "_shared_arome"]:
            cache_root = os.path.join(qpf_store_path, cache_name)
            if os.path.isdir(cache_root):
                for d in os.listdir(cache_root):
                    dp = os.path.join(cache_root, d)
                    try:
                        shutil.rmtree(dp)
                        print(f"    Removed stale cache: {dp}")
                    except Exception as exc:
                        print(f"    Warning: could not remove {dp}: {exc}")


if __name__ == "__main__":
    main(sys.argv)
