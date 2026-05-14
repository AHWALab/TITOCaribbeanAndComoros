"""
prepare_precip.py
================
Centralised precipitation preparation for TITO.

IMERG QPE is shared across **all** regions that use it (one download per
cycle time, regardless of QPF differences).  Other QPE sources (HSAF,
SCaMPR) and all QPF sources (GFS, AROME) are grouped by their forcing
signature for sharing.

Staging (copying to ``precipEF5/<region>/``) is left to the EF5 routines
(``rename_ef5_precip``), called by the orchestrator via
``prepare_ef5(…, stage_precip=True)``.

For IMERG QPE, available states are checked first (7-day lookback).  If a
state exists at T_state, IMERG is only downloaded from T_state forward.
The effective start time is returned to the orchestrator.

Usage (from orchestrator)::

    from tito_utils.file_utils.prepare_precip import prepare_all_precip

    shared = prepare_all_precip(
        regions_to_run,
        region_cycle_times,
        region_qpe_sources,
        region_qpf_requested,
        config,
    )
    # shared.imerg_folders    → {cycle_key: imerg_folder}
    # shared.imerg_eff_starts → {region: datetime}
    # shared.gfs_cache         → {cycle_key: gfs_data_folder}
    # shared.arome_cache       → {(cycle_key, domain): arome_data_folder}
    # shared.scampr_folder     → path or None
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from tito_utils.file_utils.cleanup import cleanup_precip
from tito_utils.file_utils.file_handling import mkdir_p, newline
from tito_utils.ef5.ef5_routines import find_available_states
from tito_utils.qpe_utils import (
    get_gpm_files,
    get_new_hsaf_precip,
    get_new_scampr_precip,
)
from tito_utils.qpf_utils import (
    GFS_searcher,
    AROME_searcher,
    get_arome_domain_for_region,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _with_sep(path: str) -> str:
    return os.path.join(path, "")


def _parse_scampr_ts(filename: str) -> Optional[datetime]:
    m = re.match(r"scampr\.qpe\.(\d{12})\.mmhInst\.tif$", filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d%H%M")
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------

@dataclass
class SharedPrecip:
    """Returned by :func:`prepare_all_precip`."""
    # IMERG — one folder per cycle_time (shared across ALL IMERG regions)
    imerg_folders: Dict[str, str] = field(default_factory=dict)       # cycle_key → folder
    imerg_eff_starts: Dict[str, datetime] = field(default_factory=dict)  # region → effective start

    # QPF — shared caches
    gfs_cache: Dict[str, str] = field(default_factory=dict)           # cycle_key → gfs_data/
    arome_cache: Dict[Tuple[str, str], str] = field(default_factory=dict)  # (ck, domain) → arome_data/

    # SCaMPR — shared folder (for gap-fill and direct LR QPE)
    scampr_folder: Optional[str] = None

    # STREAM-Sat — per-region dict: region → {"tif_root": ..., "ensemble_size": ...}
    streamsat_info: Dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# IMERG state-aware download window
# ---------------------------------------------------------------------------

def _resolve_imerg_download_window(
    region: str,
    cycle_time: datetime,
    states_path: str,
    model_states: List[str],
    cold_start_warmup: timedelta,
    cold_start_post_warmup: timedelta,
) -> Tuple[datetime, datetime]:
    """Return (dl_start, effective_start) for IMERG download.

    Checks states up to 7 days back from T−4h.  Includes a 30-min buffer
    before the effective start so that ``_imerg_files_present`` in
    ``prepare_ef5`` always finds a complete set of files.
    """
    target = cycle_time - timedelta(hours=4)        # T−4h
    fail_time = target - timedelta(days=7)

    found, state_time = find_available_states(
        _with_sep(states_path), model_states, target, fail_time,
    )

    if found:
        dl_start = state_time - timedelta(minutes=30)   # 30-min buffer
        effective = state_time
        print(f"    {region}: states at {state_time.strftime('%Y%m%d_%H%M')} → "
              f"IMERG from {dl_start.strftime('%Y%m%d_%H%M')}")
    else:
        warm_end = target - cold_start_post_warmup
        dl_start = warm_end - cold_start_warmup - timedelta(minutes=30)
        effective = dl_start + timedelta(minutes=30)
        print(f"    {region}: no states → cold-start IMERG from "
              f"{dl_start.strftime('%Y%m%d_%H%M')}")

    return dl_start, effective


# ---------------------------------------------------------------------------
# QPF helpers
# ---------------------------------------------------------------------------

def _copy_tifs_from_shared(shared_folder: str, dest_folder: str):
    mkdir_p(dest_folder)
    for src in glob.glob(os.path.join(shared_folder, "*.tif")):
        try:
            shutil.copy2(src, dest_folder)
        except Exception as exc:
            print(f"    Warning: tif copy {os.path.basename(src)}: {exc}")


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def prepare_all_precip(
    regions_to_run: List[str],
    region_cycle_times: Dict[str, datetime],
    region_qpe_sources: Dict[str, str],
    region_qpf_requested: Dict[str, List[str]],
    config: Any,
    master_log: Any = None,
) -> SharedPrecip:
    """Download all QPE/QPF to shared folders.  No staging to precipEF5/.

    Key design decisions
    --------------------
    * IMERG is downloaded ONCE per cycle time — **all** regions that use
      IMERG (regardless of QPF) share a single download folder.
    * GFS is downloaded ONCE per cycle time.
    * AROME is downloaded ONCE per (cycle time × domain).
    * SCaMPR is downloaded ONCE (global).
    * The IMERG 4-hour latency gap is filled ONCE per IMERG cycle folder.
    """
    # config shortcuts
    precip_root = getattr(config, "imerg_precip_folder",
                          getattr(config, "precipFolder", "precip/"))
    qpf_store_root = getattr(config, "qpf_store_path", "qpf_store/")
    states_root = getattr(config, "statesPath", "states/")
    model_states = getattr(config, "modelStates",
                           ["crest_SM", "kwr_IR", "kwr_pCQ", "kwr_pOQ"])
    gap_mode = getattr(config, "qpe_gap_fill_mode", "IMERG_ONLY").strip().upper()

    cold_warmup = timedelta(hours=6)
    cold_post = timedelta(hours=2)
    if hasattr(config, "imerg_cold_start_warmup"):
        raw = config.imerg_cold_start_warmup
        if isinstance(raw, timedelta):
            cold_warmup = raw
    if hasattr(config, "imerg_post_warmup_duration"):
        raw = config.imerg_post_warmup_duration
        if isinstance(raw, timedelta):
            cold_post = raw

    result = SharedPrecip()
    _lock = threading.Lock()

    # ═══════════════════════════════════════════════════════════════════
    # 1. Partition regions for sharing
    # ═══════════════════════════════════════════════════════════════════

    # IMERG regions grouped by cycle_time_key only (IGNORE QPF differences)
    imerg_cycle_regions: Dict[str, List[str]] = {}
    # Per-cycle: the cycle_time for that key
    imerg_cycle_times: Dict[str, datetime] = {}
    # STREAM-Sat regions (separate pipeline, not IMERG)
    streamsat_regions: Dict[str, str] = {}  # region → cycle_key
    # Non-IMERG regions (HSAF, SCaMPR)
    other_qpe_regions: List[str] = []

    for region in regions_to_run:
        qpe = region_qpe_sources.get(region, "IMERG").upper()
        ct = region_cycle_times[region]
        ck = ct.strftime("%Y%m%d%H%M")
        if qpe == "IMERG":
            imerg_cycle_regions.setdefault(ck, []).append(region)
            imerg_cycle_times[ck] = ct
        elif qpe == "STREAM_SAT":
            streamsat_regions[region] = ck
        else:
            other_qpe_regions.append(region)

    # QPF regions grouped by cycle_time_key (for GFS / AROME sharing)
    gfs_regions_by_cycle: Dict[str, List[str]] = {}
    arome_regions_by_cycle_domain: Dict[Tuple[str, str], List[str]] = {}

    for region in regions_to_run:
        qpf_list = region_qpf_requested.get(region, [])
        ck = region_cycle_times[region].strftime("%Y%m%d%H%M")

        for src in qpf_list:
            src_u = src.upper()
            if src_u in ("GFS", "WRF"):
                gfs_regions_by_cycle.setdefault(ck, []).append(region)
            elif src_u == "AROME":
                try:
                    domain = get_arome_domain_for_region(region)
                    arome_regions_by_cycle_domain.setdefault((ck, domain), []).append(region)
                except ValueError:
                    print(f"    AROME: no domain for {region} — skip")

    # ═══════════════════════════════════════════════════════════════════
    # 2. Shared GFS download (one per cycle_time_key)
    # ═══════════════════════════════════════════════════════════════════

    for ck, rlist in gfs_regions_by_cycle.items():
        ct = imerg_cycle_times.get(ck, region_cycle_times[rlist[0]])
        shared_store = _with_sep(os.path.join(qpf_store_root, "_shared", ck))
        mkdir_p(shared_store)
        print(f"***_________Shared GFS cycle {ck} "
              f"({len(set(rlist))} region(s))_________***")
        try:
            GFS_searcher(
                getattr(config, "GFS_precip_path", "precip/gfs/"),
                shared_store,
                ct,
                ct + timedelta(hours=24),
                config.xmin, config.xmax, config.ymin, config.ymax,
            )
            result.gfs_cache[ck] = os.path.join(shared_store, "gfs_data")
        except Exception as exc:
            print(f"    Shared GFS failed for {ck}: {exc}")

    # ═══════════════════════════════════════════════════════════════════
    # 3. Shared AROME download (one per cycle × domain)
    # ═══════════════════════════════════════════════════════════════════

    for (ck, domain), rlist in arome_regions_by_cycle_domain.items():
        ct = imerg_cycle_times.get(ck, region_cycle_times[rlist[0]])
        shared_store = _with_sep(
            os.path.join(qpf_store_root, "_shared_arome", ck, domain))
        mkdir_p(shared_store)
        print(f"***_________Shared AROME ({domain}) cycle {ck} "
              f"({len(set(rlist))} region(s))_________***")
        try:
            AROME_searcher(
                getattr(config, "AROME_precip_path", "precip/arome/"),
                shared_store,
                ct,
                ct + timedelta(hours=24),
                config.xmin, config.xmax, config.ymin, config.ymax,
                domain,
            )
            result.arome_cache[(ck, domain)] = os.path.join(shared_store, "arome_data")
        except Exception as exc:
            print(f"    Shared AROME failed for ({ck}, {domain}): {exc}")

    # ═══════════════════════════════════════════════════════════════════
    # 4. Shared SCaMPR download
    # ═══════════════════════════════════════════════════════════════════

    if gap_mode == "IMERG_SCAMPR" or any(
        region_qpe_sources.get(r, "").upper() == "SCAMPR" for r in regions_to_run
    ) or any(
        # Also download SCaMPR if STREAM_SAT regions need it for gap fill
        region_qpe_sources.get(r, "").upper() == "STREAM_SAT"
        and getattr(config, "stream_sat_gap_fill_mode", "SCAMPR_QPF").strip().upper() in ("SCAMPR_QPF", "SCAMPR_ONLY")
        for r in regions_to_run
    ):
        scampr_root = getattr(config, "scampr_precip_folder", "precip/scampr/")
        result.scampr_folder = _with_sep(os.path.join(scampr_root, "_shared"))
        mkdir_p(result.scampr_folder)

        ref_ct = list(region_cycle_times.values())[0]
        older_than = ref_ct - timedelta(hours=6.5)
        for fname in os.listdir(result.scampr_folder):
            ts = _parse_scampr_ts(fname)
            if ts and ts < older_than:
                try:
                    os.remove(os.path.join(result.scampr_folder, fname))
                except Exception:
                    pass

        print("***_________Shared SCaMPR download_________***")
        try:
            get_new_scampr_precip(
                current_timestamp=ref_ct, precipFolder=result.scampr_folder,
                xmin=config.xmin, ymin=config.ymin,
                xmax=config.xmax, ymax=config.ymax,
                latency_minutes=int(getattr(config, "scampr_latency_minutes", 20)),
            )
        except Exception as exc:
            print(f"    Shared SCaMPR failed: {exc}")
            result.scampr_folder = None

    # ═══════════════════════════════════════════════════════════════════
    # 5. IMERG QPE download — ONE per cycle_time_key
    # ═══════════════════════════════════════════════════════════════════

    for ck, imerg_regions in imerg_cycle_regions.items():
        ct = imerg_cycle_times[ck]
        imerg_folder = _with_sep(os.path.join(precip_root, "_shared", ck))
        result.imerg_folders[ck] = imerg_folder
        mkdir_p(imerg_folder)

        # cleanup
        try:
            cleanup_precip(ct, imerg_folder, imerg_folder,
                           keep_gap_fill=False, older_qpe_hours=6.5)
        except Exception as exc:
            print(f"    Warning: IMERG cleanup [{ck}]: {exc}")

        # Determine the earliest download start across all regions using IMERG.
        # Use the first region's state check; all IMERG regions share the same
        # global bbox so the download is identical.
        ref_region = imerg_regions[0]
        ref_states_path = os.path.join(states_root, ref_region.lower())
        dl_start, eff_start = _resolve_imerg_download_window(
            ref_region, ct, ref_states_path, model_states,
            cold_warmup, cold_post,
        )

        imerg_end = ct - timedelta(hours=4)

        # Check what we already have
        existing = sorted(glob.glob(os.path.join(
            imerg_folder, "imerg.qpe.*.30minAccum.tif")))
        if existing:
            latest_dt = datetime.strptime(
                os.path.basename(existing[-1])[10:22], "%Y%m%d%H%M")
            if latest_dt >= imerg_end - timedelta(minutes=30):
                print(f"    IMERG [{ck}] up to date — skip download")
            else:
                dl_start = max(dl_start, latest_dt + timedelta(minutes=30))
                _do_imerg_download(imerg_folder, dl_start, imerg_end, ck, config)
        else:
            _do_imerg_download(imerg_folder, dl_start, imerg_end, ck, config)

        # Record effective start for each region in this cycle
        for region in imerg_regions:
            result.imerg_eff_starts[region] = eff_start

    # ═══════════════════════════════════════════════════════════════════
    # 6. STREAM-Sat QPE — run pipeline + convert NC → GeoTIFFs
    # ═══════════════════════════════════════════════════════════════════
    #
    # STREAM-Sat uses one config per DOMAIN (not per region):
    #   Caribbean config → Antigua + Barbados + Guatemala + Haiti
    #   Comoros config  → Comoros only
    # So we group regions by domain and run ONCE per domain.

    if streamsat_regions:
        # ── Group regions by STREAM-Sat domain ──────────────────────
        from tito_utils.qpe_utils.stream_sat_utils import (
            run_and_convert_streamsat,
            get_domain_for_region,
        )
        domain_regions: Dict[str, List[str]] = {}
        for region in streamsat_regions:
            try:
                domain = get_domain_for_region(region)
            except ValueError:
                print(f"    STREAM-Sat: unknown domain for {region} — skip")
                continue
            domain_regions.setdefault(domain, []).append(region)

        ens_size = int(getattr(config, "stream_sat_ensemble_size", 10))
        win_hours = int(getattr(config, "stream_sat_window_hours", 48))
        warm_hours = int(getattr(config, "stream_sat_warmup_hours", 12))
        divide_by = float(getattr(config, "stream_sat_divide_by", 1.0))
        max_w = getattr(config, "stream_sat_max_workers", None)
        timeout_s = int(getattr(config, "stream_sat_pipeline_timeout", 7200))
        tif_root_base = getattr(config, "stream_sat_precip_folder", "precip/stream_sat/")
        tif_naming = getattr(config, "stream_sat_tif_naming", "streamsat")

        # Resolve tif_root_base relative to TITO root
        tito_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        if not os.path.isabs(tif_root_base):
            tif_root_base = os.path.join(tito_root, tif_root_base)

        # ── Run STREAM-Sat ONCE per domain ──────────────────────────
        for domain, domains_regions in domain_regions.items():
            representative = domains_regions[0]
            ck = streamsat_regions[representative]

            # Domain-specific precip folder:
            #   precip/stream_sat/caribbean/ensP1/...  (Caribbean regions)
            #   precip/stream_sat/comoros/ensP1/...    (Comoros)
            domain_tif_root = os.path.join(tif_root_base, domain)

            print(f"***_________STREAM-Sat [{domain}] for {domains_regions} [{ck}]_________***")
            if master_log:
                master_log.info("STREAM-Sat [%s] start — regions: %s", domain, domains_regions)

            try:
                info = run_and_convert_streamsat(
                    region=representative,
                    ensemble_size=ens_size,
                    window_hours=win_hours,
                    warmup_hours=warm_hours,
                    end_dt=None,
                    tif_root=domain_tif_root,
                    divide_by=divide_by,
                    max_workers=max_w,
                    keep_scratch=False,
                    tif_naming=tif_naming,
                    pipeline_log=master_log,
                )

                # Share result across ALL regions in this domain
                for region in domains_regions:
                    result.streamsat_info[region] = info
                print(f"    [{domain}]: STREAM-Sat ready — "
                      f"{info['ensemble_size']} members in {info['tif_root']}"
                      f" (shared: {', '.join(domains_regions)})")

            except Exception as exc:
                print(f"    STREAM-Sat [{domain}] failed: {exc}")
                for region in domains_regions:
                    result.streamsat_info[region] = {"error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════
    # 7. Non-IMERG QPE download (HSAF, SCaMPR) — serial, per-region
    # ═══════════════════════════════════════════════════════════════════

    for region in other_qpe_regions:
        qpe = region_qpe_sources[region].upper()
        ct = region_cycle_times[region]
        ck = ct.strftime("%Y%m%d%H%M")
        folder = _with_sep(os.path.join(precip_root, "_shared", f"{qpe.lower()}_{ck}"))
        mkdir_p(folder)

        print(f"***_________{qpe} QPE for {region}_________***")
        try:
            cleanup_precip(ct, folder, folder, keep_gap_fill=False,
                           older_qpe_hours=6.5)
        except Exception as exc:
            print(f"    Warning: {qpe} cleanup [{region}]: {exc}")

        if qpe == "HSAF":
            try:
                get_new_hsaf_precip(
                    current_timestamp=ct, precipFolder=folder,
                    ftp_user=config.hsaf_ftp_user,
                    ftp_pass=config.hsaf_ftp_pass,
                    xmin=config.xmin, ymin=config.ymin,
                    xmax=config.xmax, ymax=config.ymax,
                    latency_minutes=int(getattr(config, "hsaf_latency_minutes", 20)),
                )
            except Exception as exc:
                print(f"    HSAF failed for {region}: {exc}")
        elif qpe == "SCAMPR":
            try:
                get_new_scampr_precip(
                    current_timestamp=ct, precipFolder=folder,
                    xmin=config.xmin, ymin=config.ymin,
                    xmax=config.xmax, ymax=config.ymax,
                    latency_minutes=int(getattr(config, "scampr_latency_minutes", 20)),
                )
            except Exception as exc:
                print(f"    SCaMPR failed for {region}: {exc}")

        # Store in result so orchestrator can find it
        if not hasattr(result, '_other_qpe'):
            result._other_qpe = {}
        result._other_qpe[region] = folder

    # ═══════════════════════════════════════════════════════════════════
    # 8. Done — no gap fill needed.  The two-phase EF5 pipeline handles
    #    the IMERG latency natively:
    #      Phase 2a (IMERG run):  T-start → T−4h, saves state at T−4h
    #      Phase 2b (SCaMPR+X):   loads state at T−4h, SCaMPR QPE (10-min)
    #                             T−4h→T, then X QPF T→T+24h
    #    SCaMPR runs use raw SCaMPR files — no conversion to IMERG format.
    # ═══════════════════════════════════════════════════════════════════

    newline(2)
    print("******** Precipitation preparation complete ********")
    return result


# ---------------------------------------------------------------------------
# internal: single IMERG download
# ---------------------------------------------------------------------------

def _do_imerg_download(
    folder: str,
    dl_start: datetime,
    imerg_end: datetime,
    label: str,
    config: Any,
) -> None:
    """Download IMERG files from *dl_start* to *imerg_end* into *folder*."""
    if dl_start >= imerg_end:
        print(f"    IMERG [{label}] window empty")
        return

    print(f"    IMERG [{label}]: {dl_start.strftime('%Y%m%d_%H%M')} → "
          f"{imerg_end.strftime('%Y%m%d_%H%M')}")

    get_gpm_files(
        folder,
        dl_start,
        imerg_end - timedelta(minutes=30),
        config.server, config.email_gpm,
        config.xmin, config.ymin, config.xmax, config.ymax,
    )
