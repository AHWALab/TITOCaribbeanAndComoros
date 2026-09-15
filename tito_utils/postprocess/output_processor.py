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
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from tito_utils.file_utils.file_handling import mkdir_p


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


def _load_one(path):
    import rasterio

    with rasterio.open(path) as src:
        a = _mask_nodata(src.read(1), src.nodata)
        return a, src.profile.copy(), src.transform, src.width, src.height


def _read_stack(paths: list):
    import rasterio

    if not paths:
        return None, None
    first, prof, transform, width, height = _load_one(paths[0])
    n = len(paths)
    stack = np.empty((n, height, width), dtype=np.float32)
    stack[0] = first
    workers = min(8, max(1, n - 1))

    def _read_i(i_p):
        i, p = i_p
        with rasterio.open(p) as src:
            a = _mask_nodata(src.read(1), src.nodata)
            if src.width != width or src.height != height:
                return i, None
            return i, a

    if n > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, a in pool.map(_read_i, ((i, p) for i, p in enumerate(paths[1:], 1))):
                if a is None:
                    a, _, _, _, _ = _load_one(paths[i])
                    if a.shape != first.shape:
                        a = a[:height, :width] if a.size >= first.size else first
                stack[i] = a
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
    return stack, prof


def _write_stats(stack, profile, out_dir: str, prefix: str, cycle_ts: str) -> dict:
    import rasterio

    mkdir_p(out_dir)
    fill = np.float32(-9999.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mn = np.nanmin(stack, axis=0)
        md = np.nanmedian(stack, axis=0)
        mx = np.nanmax(stack, axis=0)
    stats = {"min": mn, "median": md, "max": mx}
    written = {}
    for name, arr in stats.items():
        out = np.where(np.isfinite(arr), arr, fill).astype(np.float32)
        path = os.path.join(out_dir, f"{prefix}_{name}.{cycle_ts}.tif")
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(out, 1)
        written[name] = path
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
    member_dirs: list, base: str, cycle_ts: str, out_dir: str, prefix: str
) -> dict:
    paths = [p for p in (_find_grid(d, base, cycle_ts) for d in member_dirs) if p]
    if not paths:
        return {}
    if len(paths) == 1:
        dest = _copy_one(paths[0], out_dir, prefix, cycle_ts)
        return {"single": dest} if dest else {}
    stack, prof = _read_stack(paths)
    if stack is None:
        return {}
    return _write_stats(stack, prof, out_dir, prefix, cycle_ts)


def process_cycle_outputs(
    cycle_ts: str,
    rkey: str,
    data_path: str = "outputs/",
    verbose: bool = True,
) -> dict:
    """Write ensemble (or deterministic) summary GeoTIFFs under ``…/summary/``."""
    log = print if verbose else (lambda *a, **k: None)
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
        if ss_dirs:
            sc_by_n = {_ens_n(d): d for d in sc_dirs}
            ss_paths, sc_paths = [], []
            for d in ss_dirs:
                p_ss = _find_grid(d, "qpeaccum", cycle_ts)
                if not p_ss:
                    continue
                ss_paths.append(p_ss)
                sc = sc_by_n.get(_ens_n(d))
                sc_paths.append(_find_grid(sc, "qpeaccum", cycle_ts) if sc else None)
            stack_ss, prof = _read_stack(ss_paths)
            if stack_ss is not None and prof is not None:
                if sc_paths and all(sc_paths) and len(sc_paths) == len(ss_paths):
                    stack_sc, _ = _read_stack(sc_paths)
                    if stack_sc is not None and stack_sc.shape == stack_ss.shape:
                        stack_ss = np.where(
                            np.isfinite(stack_ss) & np.isfinite(stack_sc),
                            stack_ss + stack_sc,
                            np.where(np.isfinite(stack_ss), stack_ss, stack_sc),
                        )
                summary["qpeaccum_nowcast"] = _write_stats(
                    stack_ss, prof, out_dir, "qpeaccum_nowcast", cycle_ts
                )
                log(
                    f"    postprocess: nowcast qpeaccum min/median/max "
                    f"(n={stack_ss.shape[0]}, SS+SCaMPR on model grid)"
                )
        elif sc_dirs:
            summary["qpeaccum_nowcast"] = _stats_from_members(
                sc_dirs, "qpeaccum", cycle_ts, out_dir, "qpeaccum_nowcast"
            )

        if sl_dirs:
            summary["qpeaccum_forecast"] = _stats_from_members(
                sl_dirs, "qpeaccum", cycle_ts, out_dir, "qpeaccum_forecast"
            )
            log(f"    postprocess: forecast qpeaccum min/median/max (n={len(sl_dirs)} StormLab)")

        uq_src = sc_dirs or ss_dirs
        if uq_src:
            summary["maxunitq_nowcast"] = _stats_from_members(
                uq_src, "maxunitq", cycle_ts, out_dir, "maxunitq_nowcast"
            )
            summary["maxsm_nowcast"] = _stats_from_members(
                uq_src, "maxsm", cycle_ts, out_dir, "maxsm_nowcast"
            )
        if sl_dirs:
            summary["maxunitq_forecast"] = _stats_from_members(
                sl_dirs, "maxunitq", cycle_ts, out_dir, "maxunitq_forecast"
            )
            summary["maxsm_forecast"] = _stats_from_members(
                sl_dirs, "maxsm", cycle_ts, out_dir, "maxsm_forecast"
            )
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
