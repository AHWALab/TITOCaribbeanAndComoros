"""
EF5 job pipeline: stage QPF → build jobs → run EF5 → cleanup.

Called by the orchestrator after precip prep and region_configs are ready.
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from tito_utils.file_utils.file_handling import mkdir_p, newline
from tito_utils.file_utils.cleanup import cleanup_staged_precip_folders
from tito_utils.ef5.ef5_routines import run_ef5_simulations_parallel
from tito_utils.logging_utils import console
from tito_utils.qpf_utils.arome_downloader import get_arome_domain_for_region
from tito_utils.ef5.jobs.helpers import copy_tifs_from_shared
from tito_utils.ef5.jobs.builders import (
    JobBatch,
    build_imerg_job,
    build_lr_jobs,
    build_jobs_parallel,
    build_streamsat_jobs_parallel,
)


def _stage_qpf(
    regions_to_run: Sequence[str],
    region_configs: Mapping[str, dict],
    shared: Any,
) -> None:
    print("***_________Staging QPF to per-region qpf_store_________***")
    for region in regions_to_run:
        cfg = region_configs[region]
        ck = cfg["cycle_time_key"]
        store = cfg["region_qpf_store"]
        mkdir_p(store)

        for qpf_src in cfg["qpf_sources"]:
            if qpf_src == "GFS" and ck in shared.gfs_cache:
                dest = os.path.join(store, "gfs_data")
                copy_tifs_from_shared(shared.gfs_cache[ck], dest)
            elif qpf_src == "AROME":
                try:
                    domain = get_arome_domain_for_region(region)
                    akey = (ck, domain)
                    if akey in shared.arome_cache:
                        dest = os.path.join(store, "arome_data")
                        copy_tifs_from_shared(shared.arome_cache[akey], dest)
                except ValueError:
                    print(f"    AROME: no domain for {region} — skip")


def _ensure_region_dirs(
    regions_to_run: Sequence[str],
    region_configs: Mapping[str, dict],
    region_qpe_sources: Mapping[str, str],
) -> None:
    print("***_________Creating per-region directories_________***")
    for region in regions_to_run:
        cfg = region_configs[region]
        is_streamsat = region_qpe_sources.get(region, "").upper() == "STREAM_SAT"
        if not is_streamsat:
            mkdir_p(cfg["region_states_path"])
        mkdir_p(cfg["region_data_path"])
        mkdir_p(cfg["region_qpf_store"])
        print(f"    {region}: states={cfg['region_states_path']} "
              f"({'STREAM_SAT=per-member' if is_streamsat else 'IMERG/default'}), "
              f"data={cfg['region_data_path']}")


def _cleanup(
    batch: JobBatch,
    regions_to_run: Sequence[str],
    region_configs: Mapping[str, dict],
    qpf_store_path: str,
) -> None:
    if batch.staged_precip_folders:
        print("***_________Cleaning staged precipEF5 folders_________***")
        removed = cleanup_staged_precip_folders(batch.staged_precip_folders)
        print(f"    Removed {removed} staged precip files")

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


def run_ef5_job_pipeline(
    *,
    regions_to_run: Sequence[str],
    region_configs: Dict[str, dict],
    region_qpe_sources: Mapping[str, str],
    shared: Any,
    config: Any,
    hindcast_mode: bool,
    lr_run: bool,
    qpe_gap_fill_mode: str,
    cycle_time,
    t_start: float,
    master_log: Optional[Any] = None,
    # EF5 / system context
    ef5Path: str,
    systemModel: str,
    systemName: str,
    modelStates: list,
    templatePath: str,
    basicPath: str,
    parametersPath: str,
    LR_TimeStep: str,
    precipEF5Folder: str,
    model_resolution: str,
    region_resolution_map,
    SEND_ALERTS: bool,
    alert_recipients,
    smtp_config: dict,
    qpf_store_path: str,
) -> JobBatch:
    """
    Build and run all EF5 jobs for one cycle.

    Returns the :class:`JobBatch` (useful for tests / summaries).
    """
    ctx = {
        "ef5Path": ef5Path,
        "systemModel": systemModel,
        "systemName": systemName,
        "modelStates": modelStates,
        "templatePath": templatePath,
        "basicPath": basicPath,
        "parametersPath": parametersPath,
        "LR_TimeStep": LR_TimeStep,
        "precipEF5Folder": precipEF5Folder,
        "model_resolution": model_resolution,
        "region_resolution_map": region_resolution_map,
        "SEND_ALERTS": SEND_ALERTS,
        "alert_recipients": alert_recipients,
        "smtp_config": smtp_config,
    }

    _ensure_region_dirs(regions_to_run, region_configs, region_qpe_sources)

    if lr_run:
        _stage_qpf(regions_to_run, region_configs, shared)

    batch = JobBatch()
    build_kwargs = dict(
        region_configs=region_configs,
        shared=shared,
        batch=batch,
        config=config,
        ctx=ctx,
    )

    try:
        # ── STREAM-Sat ensemble ────────────────────────────────────────
        ss_regions = [
            r for r in regions_to_run
            if region_qpe_sources.get(r, "").upper() == "STREAM_SAT"
        ]
        if ss_regions:
            stream_sat_gap_mode = getattr(
                config, "stream_sat_gap_fill_mode", "SCAMPR_QPE"
            ).strip().upper()
            if hindcast_mode:
                stream_sat_gap_mode = "NONE"
                console.info(
                    "[bold]HINDCAST:[/] STREAM-Sat gap fill disabled — QPF-only from states"
                )

            build_streamsat_jobs_parallel(
                ss_regions,
                hindcast_mode=hindcast_mode,
                stream_sat_gap_mode=stream_sat_gap_mode,
                stream_sat_state_root=getattr(
                    config, "stream_sat_state_folder", "states/stream_sat/"),
                stream_sat_output_root=getattr(
                    config, "stream_sat_output_folder", "outputs/stream_sat/"),
                master_log=master_log,
                **build_kwargs,
            )

            if batch.streamsat_jobs:
                print(f"***_________Phase SS-A: STREAM-Sat EF5 "
                      f"({len(batch.streamsat_jobs)} jobs)_________***")
                run_ef5_simulations_parallel(
                    batch.streamsat_jobs,
                    max_workers=min(
                        len(batch.streamsat_jobs),
                        max(1, (os.cpu_count() or 4)),
                    ),
                )
                print("    STREAM-Sat ensemble runs complete — states saved at window end")

            if batch.streamsat_lr_jobs:
                print(f"***_________Phase SS-B: SCaMPR+QPF EF5 "
                      f"({len(batch.streamsat_lr_jobs)} jobs)_________***")
                run_ef5_simulations_parallel(
                    batch.streamsat_lr_jobs,
                    max_workers=min(
                        len(batch.streamsat_lr_jobs),
                        max(1, (os.cpu_count() or 4)),
                    ),
                )
                print("    STREAM-Sat SCaMPR+QPF ensemble runs complete")

            if batch.streamsat_jobs or batch.streamsat_lr_jobs:
                newline(2)
                print("******** STREAM-Sat EF5 Outputs are ready!!! ********")
                _log_streamsat_summary(
                    regions_to_run, shared, batch, cycle_time, t_start, master_log,
                )

        # ── IMERG / SCaMPR flow (non–STREAM_SAT regions) ───────────────
        non_ss = [
            r for r in regions_to_run
            if region_qpe_sources.get(r, "").upper() != "STREAM_SAT"
        ]

        if qpe_gap_fill_mode == "IMERG_SCAMPR":
            print("***_________Phase 2a: IMERG EF5 control files_________***")
            build_jobs_parallel(build_imerg_job, non_ss, **build_kwargs)

            if batch.imerg_jobs:
                print("***_________Running IMERG EF5 simulations_________***")
                run_ef5_simulations_parallel(
                    batch.imerg_jobs, max_workers=len(batch.imerg_jobs))
                print("    IMERG EF5 runs complete — states saved at T−4h")
            else:
                print("    No IMERG EF5 jobs prepared.")

            if lr_run:
                print("***_________Phase 2b: LR EF5 control files_________***")
                build_jobs_parallel(build_lr_jobs, non_ss, **build_kwargs)
                if batch.lr_jobs:
                    print("***_________Running LR EF5 simulations_________***")
                    run_ef5_simulations_parallel(
                        batch.lr_jobs, max_workers=len(batch.lr_jobs))
                else:
                    print("    No LR EF5 jobs prepared.")

            if batch.imerg_jobs or batch.lr_jobs:
                newline(2)
                print("******** EF5 Outputs are ready!!! ********")
            elif not (batch.streamsat_jobs or batch.streamsat_lr_jobs):
                print("No EF5 jobs were prepared.")

        else:
            print("***_________Preparing EF5 control files_________***")
            build_jobs_parallel(build_imerg_job, non_ss, **build_kwargs)
            if batch.imerg_jobs:
                print("***_________Running EF5 simulations_________***")
                run_ef5_simulations_parallel(
                    batch.imerg_jobs, max_workers=len(batch.imerg_jobs))
                newline(2)
                print("******** EF5 Outputs are ready!!! ********")
            elif not (batch.streamsat_jobs or batch.streamsat_lr_jobs):
                print("No EF5 jobs were prepared.")

    finally:
        _cleanup(batch, regions_to_run, region_configs, qpf_store_path)

    return batch


def _log_streamsat_summary(
    regions_to_run, shared, batch, cycle_time, t_start, master_log,
) -> None:
    summary = [
        "=" * 60,
        "  SIMULATION SUMMARY",
        "=" * 60,
        f"  Cycle:  {cycle_time.strftime('%Y-%m-%d %H:%M')} UTC",
    ]
    for region in regions_to_run:
        ss_info = shared.streamsat_info.get(region, {})
        if ss_info and "error" not in ss_info:
            summary.append(f"  {region}:")
            summary.append(f"    STREAM-Sat members: {ss_info.get('ensemble_size', '?')}")
            summary.append(f"    GeoTIFFs root:     {ss_info.get('tif_root', '?')}")
    summary.append(
        f"  Phase SS-A jobs: {len(batch.streamsat_jobs)}  (STREAM-Sat only, save states)")
    summary.append(
        f"  Phase SS-B jobs: {len(batch.streamsat_lr_jobs)}  (SCaMPR + QPF)")
    summary.append(f"  IMERG EF5 jobs:  {len(batch.imerg_jobs)}")
    summary.append(f"  LR EF5 jobs:     {len(batch.lr_jobs)}")
    elapsed = time.time() - t_start
    summary.append(f"  Total time:      {elapsed:.1f}s ({elapsed/60:.1f} min)")
    summary.append("=" * 60)
    for line in summary:
        print(line)
        if master_log:
            master_log.info(line)
