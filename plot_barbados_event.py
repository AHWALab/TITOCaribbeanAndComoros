#!/usr/bin/env python3
"""Barbados Aug 16–17 2026: domain-max maxunitq + FIM-trigger maps.

Cycle-first layout:
  outputs/<cycle>/barbados_30m/stream_sat/ensOutN/maxunitq.<cycle>.tif
  outputs/<cycle>/barbados_30m/stormlab/ensOutN_slM/maxunitq.<cycle>.tif
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm, Normalize
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / "outputs"
CYCLE_RE = re.compile(r"^(\d{8})\.(\d{6})$")
SS_RE = re.compile(r"^ensOut(\d+)$")
SL_RE = re.compile(r"^ensOut(\d+)_sl(\d+)$")
FIM_THR = 1.0


def cycle_to_t(cycle: str) -> pd.Timestamp:
    m = CYCLE_RE.match(cycle)
    d, t = m.group(1), m.group(2)
    return pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}")


def list_cycles(out_root: Path) -> list[str]:
    return sorted(
        p.name
        for p in out_root.iterdir()
        if p.is_dir() and CYCLE_RE.match(p.name) and (p / "barbados_30m").is_dir()
    )


def raster_domain_max(path: str):
    from osgeo import gdal

    gdal.UseExceptions()
    gdal.SetConfigOption("GDAL_PAM_ENABLED", "NO")
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        return None
    b = ds.GetRasterBand(1)
    nd = b.GetNoDataValue()
    mn, mx = b.ComputeRasterMinMax(False)
    if nd is not None and abs(mx - nd) < 1e-6:
        data = b.ReadAsArray().astype(np.float64)
        data[data == nd] = np.nan
        data[data < 0] = np.nan
        if not np.any(np.isfinite(data)):
            return None
        return float(np.nanmax(data)), path
    return float(mx), path


def raster_max_info(path: str):
    from osgeo import gdal

    gdal.UseExceptions()
    gdal.SetConfigOption("GDAL_PAM_ENABLED", "NO")
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        return None
    b = ds.GetRasterBand(1)
    nd = b.GetNoDataValue()
    data = b.ReadAsArray().astype(np.float64)
    if nd is not None:
        data[data == nd] = np.nan
    data[data < 0] = np.nan
    if not np.any(np.isfinite(data)):
        return None
    idx = int(np.nanargmax(data))
    r, c = np.unravel_index(idx, data.shape)
    val = float(data[r, c])
    gt = ds.GetGeoTransform()
    lon = gt[0] + (c + 0.5) * gt[1] + (r + 0.5) * gt[2]
    lat = gt[3] + (c + 0.5) * gt[4] + (r + 0.5) * gt[5]
    return (val, path, int(r), int(c), float(lon), float(lat))


def collect_jobs(out_root: Path, var: str = "maxunitq"):
    jobs = []
    ss_set = set()
    cycles = list_cycles(out_root)
    for cyc in cycles:
        rkey = out_root / cyc / "barbados_30m"
        ss_dir = rkey / "stream_sat"
        sl_dir = rkey / "stormlab"
        if ss_dir.is_dir():
            for p in ss_dir.iterdir():
                if not SS_RE.match(p.name):
                    continue
                ss_set.add(p.name)
                tif = p / f"{var}.{cyc}.tif"
                if tif.is_file():
                    jobs.append(("stream_sat", p.name, cyc, str(tif)))
        if sl_dir.is_dir():
            for p in sl_dir.iterdir():
                if not SL_RE.match(p.name):
                    continue
                tif = p / f"{var}.{cyc}.tif"
                if tif.is_file():
                    jobs.append(("stormlab", p.name, cyc, str(tif)))
    ss_list = sorted(ss_set, key=lambda n: int(SS_RE.match(n).group(1)))
    return cycles, ss_list, jobs


def scan(out_root: Path, var: str = "maxunitq", workers: int = 16) -> dict:
    cycles, ss_list, jobs = collect_jobs(out_root, var)
    print(f"scan var={var} cycles={len(cycles)} SS={len(ss_list)} files={len(jobs)}", flush=True)
    series: dict[tuple[str, str], dict[str, float]] = {}
    best = None
    top = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(raster_domain_max, j[3]): j for j in jobs}
        done = 0
        for fut in as_completed(futs):
            done += 1
            src, ens, cyc, path = futs[fut]
            res = fut.result()
            if res is None:
                continue
            val, _ = res
            series.setdefault((src, ens), {})[cyc] = val
            top.append((val, src, ens, cyc, path))
            if best is None or val > best[0]:
                best = (val, src, ens, cyc, path)
                print(f"  [{done}/{len(jobs)}] BEST {val:.4g} {src} {ens} {cyc}", flush=True)
            elif done % 400 == 0:
                print(f"  [{done}/{len(jobs)}] best={best[0]:.4f}", flush=True)
    peak = None
    if best is not None:
        info = raster_max_info(best[4])
        if info:
            val, path, r, c, lon, lat = info
            peak = {
                "value": val,
                "source": best[1],
                "ensemble": best[2],
                "timestep": best[3],
                "row": r,
                "col": c,
                "lon": lon,
                "lat": lat,
                "file": path,
                "var": var,
            }
    top.sort(key=lambda x: -x[0])
    return {
        "cycles": cycles,
        "ss_list": ss_list,
        "series": series,
        "peak": peak,
        "top10": [
            {"value": v, "source": s, "ensemble": e, "timestep": c, "file": p}
            for v, s, e, c, p in top[:10]
        ],
        "n_files": len(jobs),
    }


def _colors(n: int):
    cmap = plt.get_cmap("tab10")
    return [cmap(i % 10) for i in range(n)]


def plot_spaghetti(scan_d: dict, fim_cycles: list[str], out_path: Path) -> Path:
    cycles = scan_d["cycles"]
    ss_list = scan_d["ss_list"]
    series = scan_d["series"]
    colors = _colors(len(ss_list))
    t_axis = [cycle_to_t(c) for c in cycles]
    fig, ax = plt.subplots(figsize=(13, 6.5))
    n_ss = n_sl = 0
    for i, parent in enumerate(ss_list):
        c = colors[i]
        key = ("stream_sat", parent)
        if key in series:
            ys = [series[key].get(cyc, np.nan) for cyc in cycles]
            ax.plot(t_axis, ys, color=c, lw=2.2, alpha=0.95, zorder=3, label=parent)
            n_ss += 1
        for (src, ens), d in series.items():
            if src != "stormlab":
                continue
            m = SL_RE.match(ens)
            if not m or f"ensOut{m.group(1)}" != parent:
                continue
            ys = [d.get(cyc, np.nan) for cyc in cycles]
            ax.plot(t_axis, ys, color=c, lw=1.0, alpha=0.40, zorder=2)
            n_sl += 1
    ax.axhline(FIM_THR, color="crimson", ls="--", lw=1.2, label=f"FIM trigger {FIM_THR}")
    for fc in fim_cycles:
        ax.axvline(cycle_to_t(fc), color="crimson", ls=":", lw=1.0, alpha=0.7, zorder=4)
    peak = scan_d.get("peak")
    if peak:
        ax.plot(
            [cycle_to_t(peak["timestep"])],
            [peak["value"]],
            "k*",
            ms=14,
            zorder=5,
            label=f'peak {peak["value"]:.2f} ({peak["ensemble"]})',
        )
    ax.set_ylabel(r"domain-max unit streamflow (m$^2$ s$^{-1}$)")
    ax.set_xlabel("Cycle time T (UTC)")
    ax.set_title(
        "Barbados 16–17 Aug 2026  ·  domain-max maxunitq\n"
        f"{n_ss} Stream-Sat + {n_sl} StormLab  "
        f"(thick=SS, thin=SL; red dashed=FIM UQ≥{FIM_THR}; red dotted=triggered cycles)"
    )
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=10))
    for lab in ax.get_xticklabels():
        lab.set_rotation(25)
        lab.set_ha("right")
    ax.legend(ncol=4, fontsize=8, loc="upper left", framealpha=0.92)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _read_tif(path: Path):
    from osgeo import gdal

    ds = gdal.Open(str(path))
    b = ds.GetRasterBand(1)
    nd = b.GetNoDataValue()
    data = b.ReadAsArray().astype(np.float64)
    if nd is not None:
        data[data == nd] = np.nan
    data[data < 0] = np.nan
    gt = ds.GetGeoTransform()
    ny, nx = data.shape
    xs = gt[0] + (np.arange(nx) + 0.5) * gt[1]
    ys = gt[3] + (np.arange(ny) + 0.5) * gt[5]
    extent = [xs[0] - gt[1] / 2, xs[-1] + gt[1] / 2, ys[-1] + gt[5] / 2, ys[0] - gt[5] / 2]
    return data, extent, gt


def plot_peak_map(peak: dict, out_path: Path) -> Path | None:
    if not peak:
        return None
    data, extent, _ = _read_tif(Path(peak["file"]))
    fig, ax = plt.subplots(figsize=(8.5, 8))
    vmax = np.nanmax(data)
    finite = data[np.isfinite(data) & (data > 0)]
    vmin = max(np.nanpercentile(finite, 5), 1e-3) if finite.size else 1e-3
    im = ax.imshow(
        data,
        extent=extent,
        origin="upper",
        cmap="turbo",
        norm=LogNorm(vmin=max(vmin, 1e-3), vmax=max(vmax, 1e-2)),
        interpolation="nearest",
    )
    ax.plot(peak["lon"], peak["lat"], "k*", ms=16, markeredgecolor="white", markeredgewidth=0.8)
    ax.annotate(
        f'{peak["value"]:.2f}\n{peak["ensemble"]}\n{peak["timestep"]}',
        xy=(peak["lon"], peak["lat"]),
        xytext=(12, 12),
        textcoords="offset points",
        fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.85),
    )
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("maxunitq")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        f'Barbados peak maxunitq = {peak["value"]:.4g}\n'
        f'{peak["source"]}/{peak["ensemble"]}  {peak["timestep"]}  '
        f'lon={peak["lon"]:.5f} lat={peak["lat"]:.5f}'
    )
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_bars_at_cycle(scan_d: dict, cyc: str, out_path: Path, title: str) -> Path:
    ss_list = scan_d["ss_list"]
    series = scan_d["series"]
    colors = _colors(len(ss_list))
    labels, vals, cols = [], [], []
    for i, parent in enumerate(ss_list):
        labels.append(parent)
        vals.append(series.get(("stream_sat", parent), {}).get(cyc, np.nan))
        cols.append(colors[i])
        for (src, ens), d in sorted(series.items()):
            if src != "stormlab":
                continue
            m = SL_RE.match(ens)
            if not m or f"ensOut{m.group(1)}" != parent:
                continue
            labels.append(ens)
            vals.append(d.get(cyc, np.nan))
            cols.append(colors[i])
    fig, ax = plt.subplots(figsize=(14, 5.5))
    x = np.arange(len(labels))
    ax.bar(x, vals, color=cols, width=0.85, edgecolor="none")
    ax.axhline(FIM_THR, color="crimson", ls="--", lw=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=90, fontsize=6)
    ax.set_ylabel(r"domain-max maxunitq (m$^2$ s$^{-1}$)")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_fim_and_unitq(out_root: Path, scan_d: dict, cyc: str, out_path: Path) -> Path | None:
    """Left: FIM P(depth≥10cm). Right: maxunitq of the peak member at this cycle."""
    series = scan_d["series"]
    best_v, best_src, best_ens, best_path = -1, None, None, None
    for (src, ens), d in series.items():
        v = d.get(cyc)
        if v is None:
            continue
        if v > best_v:
            best_v = v
            best_src = src
            best_ens = ens
            folder = "stream_sat" if src == "stream_sat" else "stormlab"
            best_path = out_root / cyc / "barbados_30m" / folder / ens / f"maxunitq.{cyc}.tif"
    fim_tif = (
        out_root
        / cyc
        / "barbados_30m"
        / "fim"
        / "stream_sat_stormlab"
        / "pluvial"
        / f"prob_depth_ge_10cm.{cyc}.tif"
    )
    if best_path is None or not best_path.is_file() or not fim_tif.is_file():
        print("skip FIM panel: missing", best_path, fim_tif)
        return None
    fim, ext_f, _ = _read_tif(fim_tif)
    uq, ext_u, _ = _read_tif(best_path)
    info = raster_max_info(str(best_path))
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(14, 6.4))
    im0 = ax0.imshow(
        fim,
        extent=ext_f,
        origin="upper",
        cmap="YlOrRd",
        vmin=0,
        vmax=1,
        interpolation="nearest",
    )
    ax0.set_title("FIM  P(depth ≥ 10 cm)")
    cb0 = fig.colorbar(im0, ax=ax0, shrink=0.82)
    cb0.set_label("probability")
    finite = uq[np.isfinite(uq) & (uq > 0)]
    vmax = np.nanmax(uq) if np.any(np.isfinite(uq)) else 1
    vmin = max(np.nanpercentile(finite, 5), 1e-3) if finite.size else 1e-3
    im1 = ax1.imshow(
        uq,
        extent=ext_u,
        origin="upper",
        cmap="turbo",
        norm=LogNorm(vmin=max(vmin, 1e-3), vmax=max(vmax, 1e-2)),
        interpolation="nearest",
    )
    if info:
        _, _, _, _, lon, lat = info
        ax1.plot(lon, lat, "k*", ms=14, markeredgecolor="white", markeredgewidth=0.7)
        ax1.annotate(
            f"{best_v:.2f}",
            xy=(lon, lat),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", alpha=0.85),
        )
    ax1.set_title(f"maxunitq  {best_src}/{best_ens}\ndomain-max = {best_v:.3g}")
    cb1 = fig.colorbar(im1, ax=ax1, shrink=0.82)
    cb1.set_label(r"maxunitq (m$^2$ s$^{-1}$)")
    for ax in (ax0, ax1):
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.25)
    fig.suptitle(
        f"Barbados FIM triggered  ·  cycle {cyc}\n"
        f"left = inundation probability  ·  right = unit streamflow that passed UQ≥{FIM_THR}",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def fim_triggers(out_root: Path) -> list[dict]:
    rows = []
    for cyc in list_cycles(out_root):
        p = out_root / cyc / "barbados_30m" / "fim" / "stream_sat_stormlab" / "pf_summary.json"
        if not p.is_file():
            continue
        d = json.loads(p.read_text())
        t = d.get("trigger") or {}
        if d.get("status") == "triggered" or t.get("triggered"):
            rows.append(
                {
                    "cycle": cyc,
                    "region": d.get("region"),
                    "max_uq": t.get("max_uq"),
                    "threshold": t.get("threshold"),
                }
            )
    return rows


def main():
    out_root = OUT_ROOT
    vis = out_root / "ts_visualization"
    vis.mkdir(parents=True, exist_ok=True)
    trig = fim_triggers(out_root)
    fim_cycles = [r["cycle"] for r in trig]
    print("FIM triggered:", trig)
    scan_d = scan(out_root, var="maxunitq", workers=16)
    p1 = plot_spaghetti(scan_d, fim_cycles, vis / "domain_max_maxunitq_spaghetti.png")
    print("wrote", p1)
    p2 = plot_peak_map(scan_d["peak"], vis / "peak_maxunitq_map.png")
    print("wrote", p2)
    peak = scan_d.get("peak")
    if peak:
        p3 = plot_bars_at_cycle(
            scan_d,
            peak["timestep"],
            vis / "domain_max_maxunitq_at_peak_cycle.png",
            f'Barbados  ·  domain-max maxunitq at peak cycle {peak["timestep"]}\n'
            f'peak={peak["value"]:.4g} from {peak["ensemble"]}',
        )
        print("wrote", p3)
    peak_fim = max(trig, key=lambda r: r["max_uq"] or 0) if trig else None
    if peak_fim:
        p4 = plot_fim_and_unitq(
            out_root,
            scan_d,
            peak_fim["cycle"],
            vis / f"fim_trigger_and_maxunitq_{peak_fim['cycle']}.png",
        )
        print("wrote", p4)
        p5 = plot_bars_at_cycle(
            scan_d,
            peak_fim["cycle"],
            vis / f"domain_max_maxunitq_at_fim_cycle_{peak_fim['cycle']}.png",
            f"Barbados  ·  domain-max maxunitq at FIM-trigger cycle {peak_fim['cycle']}\n"
            f"FIM max_uq={peak_fim['max_uq']} site={peak_fim['region']}",
        )
        print("wrote", p5)
    summary = {
        "fim_triggered": trig,
        "peak_maxunitq": scan_d.get("peak"),
        "top10": scan_d.get("top10"),
        "n_files": scan_d.get("n_files"),
    }
    (vis / "max_unitq_summary.json").write_text(json.dumps(summary, indent=2))
    print("wrote", vis / "max_unitq_summary.json")
    if peak:
        print("\n===== MAX UNIT STREAMFLOW =====")
        print(json.dumps(peak, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
