"""Build min/median/max grids from EF5 ensemble (and deterministic) outputs.

Uses EF5 products already on the model grid (qpeaccum / maxunitq / maxsm),
so STREAM-Sat vs SCaMPR native resolutions do not matter — EF5 already
resampled both onto the DEM.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from tito_utils.file_utils.file_handling import mkdir_p

# Peak working-set target for the row-blocked stats buffer, and the wall-clock
# cap for one postprocess call. Both exist because the 90m ensemble (50 StormLab
# members on a fine DEM) used to be materialised whole and OOM-killed the run.
_BLOCK_BUDGET_BYTES = 192 << 20
# Measured ~550 s for the worst case (guatemala_90m, 190 member rasters); the
# default leaves ~2x headroom so it only trips on a genuine stall.
_DEFAULT_BUDGET_S = 1200.0


def _cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def _cycle_dir(data_path: str, cycle_ts: str, rkey: str) -> str:
    return os.path.join(str(data_path).rstrip("/\\"), cycle_ts, rkey)


def _member_dirs(product_root: str, pattern: str) -> list:
    if not os.path.isdir(product_root):
        return []
    return sorted(d for d in glob.glob(os.path.join(product_root, pattern)) if os.path.isdir(d))


def _find_grid(member_dir: str, base: str, cycle_ts: str):
    if not member_dir:
        return None
    exact = os.path.join(member_dir, f"{base}.{cycle_ts}.tif")
    if os.path.isfile(exact):
        return exact
    hits = glob.glob(os.path.join(member_dir, f"{base}.*.tif"))
    return hits[0] if hits else None


def _mask_nodata(a, nod):
    a = np.asarray(a, dtype=np.float32)
    if nod is not None and np.isfinite(nod):
        a = np.where(a == np.float32(nod), np.nan, a)
    return a


def _read_window(src, win, nr: int, width: int):
    """Read one block; NaN-pad if a member grid does not match the reference."""
    try:
        a = _mask_nodata(src.read(1, window=win), src.nodata)
    except Exception:
        a = None
    if a is None or a.shape != (nr, width):
        row = np.full((nr, width), np.nan, dtype=np.float32)
        if a is not None and a.size:
            hh, ww = min(nr, a.shape[0]), min(width, a.shape[1])
            row[:hh, :ww] = a[:hh, :ww]
        return row
    return a


def _read_into(task):
    """Worker: fill ``buf[i]`` from ``path``'s ``win`` (rasterio releases the GIL)."""
    import rasterio

    buf, i, path, win, nr, width = task
    with rasterio.open(path) as src:
        buf[i] = _read_window(src, win, nr, width)


def _block_rows(n_members: int, width: int, budget_bytes: int = _BLOCK_BUDGET_BYTES) -> int:
    """Row height that keeps an ``n_members × rows × width`` float32 buffer in budget."""
    return max(1, int(budget_bytes // max(1, n_members * width * 4)))


def _write_stats(
    paths: list, out_dir: str, prefix: str, cycle_ts: str, add_paths: list = None, log=None
) -> dict:
    """min/median/max across ``paths``, one row block at a time.

    Streams the member rasters instead of materialising the whole ensemble, so
    peak memory stays bounded by ``_BLOCK_BUDGET_BYTES`` regardless of member
    count or DEM size. When ``add_paths`` is given it is summed per member
    (NaN-aware) before the stats, matching the SS + SCaMPR nowcast.
    """
    import rasterio
    from rasterio.windows import Window

    if not paths:
        return {}
    if len(paths) == 1 and not add_paths:
        dest = _copy_one(paths[0], out_dir, prefix, cycle_ts)
        return {"single": dest} if dest else {}

    n = len(paths)
    with rasterio.open(paths[0]) as src0:
        height, width = src0.height, src0.width
        prof = src0.profile.copy()

    prof.update(
        dtype="float32",
        count=1,
        nodata=np.float32(-9999.0),
        compress="deflate",
        zlevel=1,
        tiled=False,
    )
    prof.pop("blockxsize", None)
    prof.pop("blockysize", None)

    rows = min(height, _block_rows(n, width))
    buf = np.empty((n, rows, width), dtype=np.float32)
    abuf = np.empty_like(buf) if add_paths else None

    mkdir_p(out_dir)
    names = ("min", "median", "max")
    dest = {k: os.path.join(out_dir, f"{prefix}_{k}.{cycle_ts}.tif") for k in names}
    written, dst = {}, {}
    if log:
        log(
            f"    postprocess: {prefix} streaming {n} members in "
            f"{rows}-row blocks (buffer {buf.nbytes / 2**20:.0f} MiB)"
        )
    try:
        for k in names:
            dst[k] = rasterio.open(dest[k], "w", **prof)
        workers = max(1, min(_cpu_count(), n))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for r0 in range(0, height, rows):
                nr = min(rows, height - r0)
                win = Window(0, r0, width, nr)
                block = buf[:n, :nr, :]
                list(
                    pool.map(
                        _read_into, ((block, i, p, win, nr, width) for i, p in enumerate(paths))
                    )
                )
                if add_paths:
                    extra = abuf[:n, :nr, :]
                    list(
                        pool.map(
                            _read_into,
                            ((extra, i, p, win, nr, width) for i, p in enumerate(add_paths)),
                        )
                    )
                    block = np.where(
                        np.isfinite(block) & np.isfinite(extra),
                        block + extra,
                        np.where(np.isfinite(block), block, extra),
                    )
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    stats = {
                        "min": np.nanmin(block, axis=0),
                        "median": np.nanmedian(block, axis=0),
                        "max": np.nanmax(block, axis=0),
                    }
                for k in names:
                    arr = np.where(np.isfinite(stats[k]), stats[k], np.float32(-9999.0))
                    dst[k].write(arr.astype(np.float32), 1, window=win)
                    written.setdefault(k, dest[k])
    finally:
        for f in dst.values():
            f.close()
    return written


def _copy_one(src, out_dir: str, prefix: str, cycle_ts: str):
    if not src or not os.path.isfile(src):
        return None
    mkdir_p(out_dir)
    dest = os.path.join(out_dir, f"{prefix}.{cycle_ts}.tif")
    shutil.copy2(src, dest)
    return dest


def _ens_n(dirname: str):
    m = re.search(r"ensOut(\d+)", os.path.basename(dirname))
    return int(m.group(1)) if m else None


def _stats_from_members(
    member_dirs: list,
    base: str,
    cycle_ts: str,
    out_dir: str,
    prefix: str,
    log=None,
) -> dict:
    paths = [p for p in (_find_grid(d, base, cycle_ts) for d in member_dirs) if p]
    if not paths:
        return {}
    return _write_stats(paths, out_dir, prefix, cycle_ts, log=log)


def process_cycle_outputs(
    cycle_ts: str,
    rkey: str,
    data_path: str = "outputs/",
    verbose: bool = True,
    budget_s: float = None,
    log=None,
) -> dict:
    """Write ensemble (or deterministic) summary GeoTIFFs under ``…/summary/``.

    ``budget_s`` caps the wall-clock time spent on summaries (0 disables);
    on overrun the steps already written are kept and the rest are skipped,
    so a slow pass never eats into the next hourly cycle.
    """
    if log is None:
        log = print if verbose else (lambda *a, **k: None)
    budget = _DEFAULT_BUDGET_S if budget_s is None else float(budget_s)
    deadline = time.monotonic() + budget if budget > 0 else None

    def out_of_time(step: str) -> bool:
        if deadline is None or time.monotonic() <= deadline:
            return False
        log(
            f"    postprocess: {budget:.0f}s budget exceeded before {step}; keeping partial summary"
        )
        return True

    root = _cycle_dir(data_path, cycle_ts, rkey)
    if not os.path.isdir(root):
        log(f"    postprocess: no outputs at {root}")
        return {}
    out_dir = os.path.join(root, "summary")
    summary = {"rkey": rkey, "cycle": cycle_ts, "dir": out_dir}

    ss_dirs = _member_dirs(os.path.join(root, "stream_sat"), "ensOut*")
    sc_dirs = _member_dirs(os.path.join(root, "scampr"), "ensOut*")
    sl_dirs = _member_dirs(os.path.join(root, "stormlab"), "ensOut*_sl*")
    ensemble = bool(ss_dirs or sl_dirs or sc_dirs)

    if ensemble:
        if ss_dirs and not out_of_time("qpeaccum_nowcast"):
            sc_by_n = {_ens_n(d): d for d in sc_dirs}
            ss_paths, sc_paths = [], []
            for d in ss_dirs:
                p_ss = _find_grid(d, "qpeaccum", cycle_ts)
                if not p_ss:
                    continue
                ss_paths.append(p_ss)
                sc = sc_by_n.get(_ens_n(d))
                sc_paths.append(_find_grid(sc, "qpeaccum", cycle_ts) if sc else None)
            if ss_paths:
                paired = sc_paths if all(sc_paths) and len(sc_paths) == len(ss_paths) else None
                summary["qpeaccum_nowcast"] = _write_stats(
                    ss_paths,
                    out_dir,
                    "qpeaccum_nowcast",
                    cycle_ts,
                    add_paths=paired,
                    log=log,
                )
                log(
                    f"    postprocess: nowcast qpeaccum min/median/max "
                    f"(n={len(ss_paths)}, {'SS+SCaMPR' if paired else 'SS'} on model grid)"
                )
        elif sc_dirs and not out_of_time("qpeaccum_nowcast"):
            summary["qpeaccum_nowcast"] = _stats_from_members(
                sc_dirs, "qpeaccum", cycle_ts, out_dir, "qpeaccum_nowcast", log=log
            )

        if sl_dirs and not out_of_time("qpeaccum_forecast"):
            summary["qpeaccum_forecast"] = _stats_from_members(
                sl_dirs, "qpeaccum", cycle_ts, out_dir, "qpeaccum_forecast", log=log
            )
            log(f"    postprocess: forecast qpeaccum min/median/max (n={len(sl_dirs)} StormLab)")

        uq_src = sc_dirs or ss_dirs
        if uq_src and not out_of_time("maxunitq_nowcast"):
            summary["maxunitq_nowcast"] = _stats_from_members(
                uq_src, "maxunitq", cycle_ts, out_dir, "maxunitq_nowcast", log=log
            )
            summary["maxsm_nowcast"] = _stats_from_members(
                uq_src, "maxsm", cycle_ts, out_dir, "maxsm_nowcast", log=log
            )
            log(f"    postprocess: nowcast maxunitq/maxsm min/median/max (n={len(uq_src)})")
        if sl_dirs and not out_of_time("maxunitq_forecast"):
            summary["maxunitq_forecast"] = _stats_from_members(
                sl_dirs, "maxunitq", cycle_ts, out_dir, "maxunitq_forecast", log=log
            )
            summary["maxsm_forecast"] = _stats_from_members(
                sl_dirs, "maxsm", cycle_ts, out_dir, "maxsm_forecast", log=log
            )
            log(f"    postprocess: forecast maxunitq/maxsm min/median/max (n={len(sl_dirs)})")
    else:
        candidates = []
        for sub in ("imerg", "scampr_det", "gfs", "arome", "stream_sat", "stormlab"):
            d = os.path.join(root, sub)
            if os.path.isdir(d):
                candidates.append(d)
        if not candidates:
            candidates = [root]
        for base, prefix in (
            ("qpeaccum", "qpeaccum"),
            ("maxunitq", "maxunitq"),
            ("maxsm", "maxsm"),
        ):
            if out_of_time(prefix):
                break
            src = None
            for d in candidates:
                src = _find_grid(d, base, cycle_ts)
                if src:
                    break
            dest = _copy_one(src, out_dir, prefix, cycle_ts) if src else None
            if dest:
                summary[prefix] = dest
                log(f"    postprocess: copied {os.path.basename(dest)}")
    return summary
