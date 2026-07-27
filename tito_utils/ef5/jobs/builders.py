"""
EF5 control-file / job builders for IMERG, LR (SCaMPR+QPF), and STREAM-Sat.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set

from tito_utils.file_utils.file_handling import mkdir_p
from tito_utils.ef5.ef5_routines import prepare_ef5
from tito_utils.logging_utils import setup_run_log, console
from tito_utils.ef5.jobs.helpers import (
    with_sep,
    resolve_cold_start_window,
    parse_streamsat_tif_window,
    resolve_region_resolution,
)


class JobBatch:
    """Mutable containers filled by the builders."""

    def __init__(self):
        self.lock = threading.Lock()
        self.staged_precip_folders: Set[str] = set()
        self.imerg_jobs: List[dict] = []
        self.lr_jobs: List[dict] = []
        self.streamsat_jobs: List[dict] = []       # Phase A
        self.streamsat_lr_jobs: List[dict] = []    # Phase B / H


def _job_dict(region, ef5_path, run_path, ctrl_file, output_ts, member=None) -> dict:
    d = {
        "region": region,
        "ef5Path": ef5_path,
        "tmpOutput": run_path + "/",
        "controlFile": ctrl_file,
        "output_timestamp_str": output_ts,
    }
    if member is not None:
        d["member"] = member
    return d


def build_imerg_job(
    region: str,
    *,
    region_configs: Dict[str, dict],
    shared: Any,
    batch: JobBatch,
    config: Any,
    ctx: Dict[str, Any],
) -> None:
    """IMERG-only EF5 job (→ T−4h, saves state)."""
    cfg = region_configs[region]
    rkey = cfg["region_key"]
    r_imerg_end = cfg["r_imerg_end"]
    ck = cfg["cycle_time_key"]

    imerg_qpe_folder = shared.imerg_folders.get(ck, "")
    if not imerg_qpe_folder:
        print(f"    !!! {region}: no IMERG shared folder — skipping")
        return

    cold_begin, cold_warm_end = resolve_cold_start_window(config, r_imerg_end)

    tmp_out = os.path.join(cfg["region_data_path"], f"tmp_output_{ctx['systemModel']}_imerg")
    staging = os.path.join(ctx["precipEF5Folder"], rkey, "imerg_none")
    mkdir_p(staging)
    mkdir_p(tmp_out)

    try:
        job_log = setup_run_log(cfg["region_data_path"], f"ef5_imerg_{rkey}")
        job_log.info("IMERG EF5 prep — region=%s", region)
        eff_start, ctrl_file, run_path = prepare_ef5(
            staging,
            imerg_qpe_folder,
            with_sep(cfg["region_states_path"]),
            ctx["modelStates"],
            r_imerg_end - timedelta(minutes=30),
            r_imerg_end - timedelta(days=7),
            cfg["region_current_time"],
            ctx["systemName"],
            ctx["SEND_ALERTS"], ctx["alert_recipients"], ctx["smtp_config"],
            with_sep(tmp_out),
            with_sep(cfg["region_data_path"]),
            region, ctx["systemModel"],
            ctx["templatePath"], cfg["region_template"],
            r_imerg_end,
            cold_warm_end,
            r_imerg_end,
            r_imerg_end,
            ctx["LR_TimeStep"],
            False,
            region, resolve_region_resolution(
                region, ctx["model_resolution"], ctx["region_resolution_map"]),
            ctx["basicPath"], ctx["parametersPath"],
            "IMERG", "none",
            stage_precip=True,
            output_timestamp_str=cfg["output_timestamp_str"],
            qpf_store_forcing_path=cfg["region_qpf_store"],
            save_states=True,
            cold_start_begin_time=cold_begin,
            cold_start_warm_end_time=cold_warm_end,
            verbose=True,
            run_log=job_log,
        )
        print(f"    {region} [IMERG]: {eff_start.strftime('%Y%m%d_%H%M')} → "
              f"{r_imerg_end.strftime('%Y%m%d_%H%M')}, ctrl={ctrl_file}")
        with batch.lock:
            batch.staged_precip_folders.add(staging)
            batch.imerg_jobs.append(_job_dict(
                region, ctx["ef5Path"], run_path, ctrl_file,
                cfg["output_timestamp_str"]))
    except Exception as exc:
        print(f"    !!! {region} IMERG EF5 prep failed: {exc}")


def build_lr_jobs(
    region: str,
    *,
    region_configs: Dict[str, dict],
    shared: Any,
    batch: JobBatch,
    config: Any,
    ctx: Dict[str, Any],
) -> None:
    """SCaMPR QPE → GFS/AROME QPF long-range jobs (no state save)."""
    cfg = region_configs[region]
    rkey = cfg["region_key"]
    r_imerg_end = cfg["r_imerg_end"]
    r_scampr_end = cfg["r_scampr_end"]
    r_lr_end = cfg["r_end_lr"]

    scampr_precip = shared.scampr_folder
    if not scampr_precip:
        print(f"    !!! {region}: no SCaMPR folder — skipping LR runs")
        return

    for qpf_src in cfg["qpf_sources"]:
        actual_qpf = qpf_src

        if qpf_src == "WRF":
            wrf_path = getattr(config, "WRF_archive_path", "")
            if wrf_path:
                try:
                    from tito_utils.qpf_utils.wrf_manager import WRF_searcher as _wrf
                    wrf_ok = _wrf(
                        wrf_path, cfg["region_qpf_store"],
                        r_scampr_end, r_lr_end,
                        ctx["LR_TimeStep"],
                        getattr(config, "WRF_var_name", "PREC_ACC_C"),
                        getattr(config, "WRF_filename_template",
                                "PREC_d01_YYYY-MM-DD_HH_mm_SS.nc"),
                    )
                    actual_qpf = "WRF" if wrf_ok else "GFS"
                    if not wrf_ok:
                        print(f"    {region}: WRF unavailable → GFS fallback")
                except Exception:
                    actual_qpf = "GFS"
            else:
                actual_qpf = "GFS"

        tmp_out = os.path.join(
            cfg["region_data_path"],
            f"tmp_output_{ctx['systemModel']}_scampr_{actual_qpf.lower()}")
        staging = os.path.join(
            ctx["precipEF5Folder"], rkey, f"scampr_{actual_qpf.lower()}")
        mkdir_p(staging)
        mkdir_p(tmp_out)

        try:
            lr_log = setup_run_log(
                cfg["region_data_path"], f"ef5_lr_{rkey}_{actual_qpf.lower()}")
            lr_log.info("LR EF5 prep — region=%s qpf=%s", region, actual_qpf)
            eff_start, ctrl_file, run_path = prepare_ef5(
                staging,
                scampr_precip,
                with_sep(cfg["region_states_path"]),
                ctx["modelStates"],
                r_imerg_end,
                r_imerg_end,
                cfg["region_current_time"],
                ctx["systemName"],
                ctx["SEND_ALERTS"], ctx["alert_recipients"], ctx["smtp_config"],
                with_sep(tmp_out),
                with_sep(cfg["region_data_path"]),
                region, ctx["systemModel"],
                ctx["templatePath"], cfg["region_template"],
                r_scampr_end,
                r_scampr_end,
                r_lr_end,
                r_lr_end,
                ctx["LR_TimeStep"],
                True,
                region, resolve_region_resolution(
                    region, ctx["model_resolution"], ctx["region_resolution_map"]),
                ctx["basicPath"], ctx["parametersPath"],
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
            with batch.lock:
                batch.staged_precip_folders.add(staging)
                batch.lr_jobs.append(_job_dict(
                    region, ctx["ef5Path"], run_path, ctrl_file,
                    cfg["output_timestamp_str"]))
        except Exception as exc:
            print(f"    !!! {region} LR ({actual_qpf}) EF5 prep failed: {exc}")


def build_streamsat_ensemble_jobs(
    region: str,
    *,
    region_configs: Dict[str, dict],
    shared: Any,
    batch: JobBatch,
    config: Any,
    ctx: Dict[str, Any],
    hindcast_mode: bool,
    stream_sat_gap_mode: str,
    stream_sat_state_root: str,
    stream_sat_output_root: str,
    master_log: Optional[Any] = None,
) -> None:
    """Build Phase A (STREAM-Sat) + Phase B/H (gap+LR) jobs for one region."""
    cfg = region_configs[region]
    rkey = cfg["region_key"]
    ct = cfg["region_current_time"]

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

    ens_p1_dir = os.path.join(tif_root, "ensP1")
    if not os.path.isdir(ens_p1_dir):
        print(f"    !!! {region}: STREAM-Sat ensP1 dir not found: {ens_p1_dir}")
        return

    tif_pattern = getattr(config, "stream_sat_tif_naming", "streamsat")
    parsed = parse_streamsat_tif_window(ens_p1_dir, tif_pattern)
    if parsed is None:
        print(f"    !!! {region}: no STREAM-Sat GeoTIFFs / timestamps in {ens_p1_dir}")
        return
    ss_start, ss_end, all_ts = parsed

    # Hindcast: clamp to cycle time so leftover operational TIFs cannot pull
    # ss_end into the future (EF5 state save / LR must start at T).
    if hindcast_mode:
        # Prefer last TIF at/before T; allow T itself if present.
        valid = [t for t in all_ts if t <= ct]
        if valid:
            ss_end = max(valid)
            win_h = int(getattr(config, "stream_sat_window_hours", 48))
            ss_start = min(t for t in valid if t >= ss_end - timedelta(hours=win_h))
            print(f"    {region} [STREAM_SAT]: window {ss_start.strftime('%Y%m%d_%H%M')} → "
                  f"{ss_end.strftime('%Y%m%d_%H%M')} (hindcast clamp to T="
                  f"{ct.strftime('%Y%m%d_%H%M')}), {ens_size} members")
        else:
            print(f"    !!! {region}: no STREAM-Sat TIFs <= hindcast T "
                  f"{ct.strftime('%Y%m%d_%H%M')} in {ens_p1_dir}")
            return
    else:
        print(f"    {region} [STREAM_SAT]: window {ss_start.strftime('%Y%m%d_%H%M')} → "
              f"{ss_end.strftime('%Y%m%d_%H%M')} (driven by actual data), {ens_size} members")

    scampr_folder = getattr(shared, "scampr_folder", None)
    do_gap_fill = (
        stream_sat_gap_mode in ("SCAMPR_QPE", "SCAMPR_ONLY") and scampr_folder
    )

    for member_idx in range(1, ens_size + 1):
        member_precip = os.path.join(tif_root, f"ensP{member_idx}", "")
        member_states = os.path.join(
            stream_sat_state_root, f"ensS{member_idx}", rkey, "")
        member_output = os.path.join(
            stream_sat_output_root, f"ensOut{member_idx}", rkey, "")
        member_tmp = os.path.join(
            member_output, f"tmp_output_{ctx['systemModel']}_streamsat")

        mkdir_p(member_precip)
        mkdir_p(member_states)
        mkdir_p(member_output)
        mkdir_p(member_tmp)

        staging_a = os.path.join(
            ctx["precipEF5Folder"], rkey, f"streamsat_ens{member_idx:02d}")
        mkdir_p(staging_a)

        is_first = member_idx == 1
        run_log = setup_run_log(
            member_output, f"ef5_ens{member_idx:02d}",
        ) if not is_first else None

        try:
            cold_begin = ss_start
            cold_warm_end = ss_end
            eff_start, ctrl_file, run_path = prepare_ef5(
                staging_a,
                member_precip,
                with_sep(member_states),
                ctx["modelStates"],
                ss_end - timedelta(minutes=30),
                ss_end - timedelta(hours=48),
                ct,
                ctx["systemName"],
                ctx["SEND_ALERTS"], ctx["alert_recipients"], ctx["smtp_config"],
                with_sep(member_tmp),
                with_sep(member_output),
                region, ctx["systemModel"],
                ctx["templatePath"], cfg["region_template"],
                ss_end, ss_end, ss_end, ss_end,
                ctx["LR_TimeStep"],
                False,
                region, resolve_region_resolution(
                    region, ctx["model_resolution"], ctx["region_resolution_map"]),
                ctx["basicPath"], ctx["parametersPath"],
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
            if master_log:
                master_log.info(
                    "    %s [SS ens%02d]: %s → %s, ctrl=%s",
                    region, member_idx,
                    eff_start.strftime("%Y%m%d_%H%M"),
                    ss_end.strftime("%Y%m%d_%H%M"), ctrl_file)
            if is_first:
                print(f"    {region} [SS ens{member_idx:02d}]: "
                      f"{eff_start.strftime('%Y%m%d_%H%M')} → "
                      f"{ss_end.strftime('%Y%m%d_%H%M')}")
            with batch.lock:
                batch.staged_precip_folders.add(staging_a)
                batch.streamsat_jobs.append(_job_dict(
                    region, ctx["ef5Path"], run_path, ctrl_file,
                    cfg["output_timestamp_str"], member=member_idx))
        except Exception as exc:
            print(f"    !!! {region} [SS ens{member_idx:02d}] EF5 prep failed: {exc}")
            continue

        # Phase H: hindcast QPF-only (GFS)
        if hindcast_mode:
            hindcast_qpf = [s for s in cfg["qpf_sources"] if s.upper() == "GFS"]
            for qpf_src in hindcast_qpf:
                actual_qpf = "GFS" if qpf_src == "WRF" else qpf_src
                staging_h = os.path.join(
                    ctx["precipEF5Folder"], rkey,
                    f"streamsat_ens{member_idx:02d}_qpf_{actual_qpf.lower()}")
                mkdir_p(staging_h)
                member_tmp_h = os.path.join(
                    member_output,
                    f"tmp_output_{ctx['systemModel']}_qpf_{actual_qpf.lower()}")
                mkdir_p(member_tmp_h)
                try:
                    _, ctrl_file_h, run_path_h = prepare_ef5(
                        staging_h,
                        member_precip,
                        with_sep(member_states),
                        ctx["modelStates"],
                        ss_end, ss_end, ct,
                        ctx["systemName"],
                        ctx["SEND_ALERTS"], ctx["alert_recipients"], ctx["smtp_config"],
                        with_sep(member_tmp_h),
                        with_sep(member_output),
                        region, ctx["systemModel"],
                        ctx["templatePath"], cfg["region_template"],
                        ct, ct, cfg["r_end_lr"], cfg["r_end_lr"],
                        ctx["LR_TimeStep"],
                        True,
                        region, resolve_region_resolution(
                            region, ctx["model_resolution"], ctx["region_resolution_map"]),
                        ctx["basicPath"], ctx["parametersPath"],
                        "STREAM_SAT", actual_qpf,
                        stage_precip=False,
                        output_timestamp_str=cfg["output_timestamp_str"],
                        qpf_store_forcing_path=cfg["region_qpf_store"],
                        save_states=False,
                        verbose=is_first,
                        run_log=run_log,
                    )
                    print(f"    {region} [SS ens{member_idx:02d} QPF+{actual_qpf}]: "
                          f"state@SS_end → QPF→"
                          f"{cfg['r_end_lr'].strftime('%Y%m%d_%H%M')}")
                    if master_log:
                        master_log.info(
                            "    %s [SS ens%02d QPF+%s]: state@SS_end → QPF→%s, ctrl=%s",
                            region, member_idx, actual_qpf,
                            cfg["r_end_lr"].strftime("%Y%m%d_%H%M"), ctrl_file_h)
                    with batch.lock:
                        batch.staged_precip_folders.add(staging_h)
                        batch.streamsat_lr_jobs.append(_job_dict(
                            region, ctx["ef5Path"], run_path_h, ctrl_file_h,
                            cfg["output_timestamp_str"], member=member_idx))
                except Exception as exc:
                    print(f"    !!! {region} [SS ens{member_idx:02d}] QPF ({actual_qpf}) "
                          f"EF5 prep failed: {exc}")

        elif do_gap_fill:
            for qpf_src in cfg["qpf_sources"]:
                actual_qpf = "GFS" if qpf_src == "WRF" else qpf_src
                staging_b = os.path.join(
                    ctx["precipEF5Folder"], rkey,
                    f"streamsat_ens{member_idx:02d}_scampr_{actual_qpf.lower()}")
                mkdir_p(staging_b)
                member_tmp_b = os.path.join(
                    member_output,
                    f"tmp_output_{ctx['systemModel']}_scampr_{actual_qpf.lower()}")
                mkdir_p(member_tmp_b)
                try:
                    _, ctrl_file_b, run_path_b = prepare_ef5(
                        staging_b,
                        scampr_folder,
                        with_sep(member_states),
                        ctx["modelStates"],
                        ss_end, ss_end, ct,
                        ctx["systemName"],
                        ctx["SEND_ALERTS"], ctx["alert_recipients"], ctx["smtp_config"],
                        with_sep(member_tmp_b),
                        with_sep(member_output),
                        region, ctx["systemModel"],
                        ctx["templatePath"], cfg["region_template"],
                        ct, ct, cfg["r_end_lr"], cfg["r_end_lr"],
                        ctx["LR_TimeStep"],
                        True,
                        region, resolve_region_resolution(
                            region, ctx["model_resolution"], ctx["region_resolution_map"]),
                        ctx["basicPath"], ctx["parametersPath"],
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
                    if master_log:
                        master_log.info(
                            "    %s [SS ens%02d SCaMPR+%s]: state@SS_end → QPF→%s, ctrl=%s",
                            region, member_idx, actual_qpf,
                            cfg["r_end_lr"].strftime("%Y%m%d_%H%M"), ctrl_file_b)
                    with batch.lock:
                        batch.staged_precip_folders.add(staging_b)
                        batch.streamsat_lr_jobs.append(_job_dict(
                            region, ctx["ef5Path"], run_path_b, ctrl_file_b,
                            cfg["output_timestamp_str"], member=member_idx))
                except Exception as exc:
                    print(f"    !!! {region} [SS ens{member_idx:02d}] LR ({actual_qpf}) "
                          f"EF5 prep failed: {exc}")


def build_streamsat_jobs_parallel(
    regions: List[str],
    **kwargs,
) -> None:
    if not regions:
        return
    print("***_________Building STREAM-Sat ensemble EF5 jobs_________***")
    with ThreadPoolExecutor(max_workers=len(regions)) as ex:
        futures = {
            ex.submit(build_streamsat_ensemble_jobs, r, **kwargs): r
            for r in regions
        }
        for future in as_completed(futures):
            r = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"    !!! {r} STREAM-Sat EF5 prep raised: {exc}")


def build_jobs_parallel(builder_fn, regions: List[str], **kwargs) -> None:
    with ThreadPoolExecutor(max_workers=len(regions) or 1) as ex:
        futures = {ex.submit(builder_fn, r, **kwargs): r for r in regions}
        for future in as_completed(futures):
            r = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"    !!! {r} EF5 prep raised: {exc}")
