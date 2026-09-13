"""Remove old EF5 states and cycle output folders after each run."""

from __future__ import annotations

import os
import re
import shutil
from datetime import UTC, datetime, timedelta

_STATE_TS = re.compile(r"(\d{8})_(\d{4})")
_CYCLE_DIR = re.compile(r"^(\d{8})\.(\d{6})$")


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _parse_state_time(name: str):
    m = _STATE_TS.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def _parse_cycle_dir(name: str):
    m = _CYCLE_DIR.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _purge_states(states_root: str, cutoff: datetime) -> int:
    removed = 0
    if not os.path.isdir(states_root):
        return 0
    for dirpath, _dirnames, filenames in os.walk(states_root):
        for fn in filenames:
            if not fn.endswith(".tif"):
                continue
            ts = _parse_state_time(fn)
            if ts is None or ts >= cutoff:
                continue
            path = os.path.join(dirpath, fn)
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def _purge_outputs(data_path: str, cutoff: datetime, keep_cycle: str | None) -> int:
    removed = 0
    if not os.path.isdir(data_path):
        return 0
    for name in os.listdir(data_path):
        if name in ("logs", "ibf_cache") or name == keep_cycle:
            continue
        ts = _parse_cycle_dir(name)
        if ts is None or ts >= cutoff:
            continue
        path = os.path.join(data_path, name)
        if not os.path.isdir(path):
            continue
        try:
            shutil.rmtree(path)
            removed += 1
        except OSError:
            pass
    return removed


def manage_archives(
    config,
    cycle_time: datetime,
    *,
    states_path: str | None = None,
    data_path: str | None = None,
    master_log=None,
    verbose: bool = True,
) -> dict:
    """Drop states older than ``states_keep_hours`` and output cycles older
    than ``outputs_keep_hours``. Walks every subfolder under states."""
    log = print if verbose else (lambda *a, **k: None)
    now = _naive_utc(cycle_time)
    st_h = float(getattr(config, "states_keep_hours", 100) or 100)
    out_h = float(getattr(config, "outputs_keep_hours", 168) or 168)
    states_root = states_path or getattr(config, "statesPath", "EF5_conf/states/")
    states_root = os.path.normpath(str(states_root).rstrip("/\\"))
    if os.path.basename(states_root) != "states":
        parent = os.path.dirname(states_root)
        if os.path.basename(parent) == "states":
            states_root = parent
        elif os.path.isdir("EF5_conf/states"):
            states_root = "EF5_conf/states"
    data_root = data_path or getattr(config, "dataPath", "outputs/")
    keep_cycle = now.strftime("%Y%m%d.%H%M%S")

    n_st = _purge_states(states_root, now - timedelta(hours=st_h))
    n_out = _purge_outputs(data_root, now - timedelta(hours=out_h), keep_cycle)
    msg = (
        f"    archive: removed {n_st} state tif(s) older than {st_h:g}h; "
        f"{n_out} output cycle folder(s) older than {out_h:g}h"
    )
    log(msg)
    if master_log:
        master_log.info(msg.strip())
    return {"states_removed": n_st, "output_cycles_removed": n_out}
