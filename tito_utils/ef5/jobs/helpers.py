"""Shared helpers for EF5 job builders."""

from __future__ import annotations

import glob
import os
import re
import shutil
from collections.abc import Sequence
from datetime import datetime, timedelta


def with_sep(path: str) -> str:
    return os.path.join(path, "")


def as_source_list(val: str | Sequence[str] | None) -> list[str]:
    """Normalize qpe_source / qpf_source which may be a string or a list."""
    if val is None or val == "":
        return []
    if isinstance(val, (list, tuple)):
        return [str(x).strip().upper() for x in val if str(x).strip()]
    s = str(val).strip().upper()
    return [s] if s else []


def has_source(val: str | Sequence[str] | None, name: str) -> bool:
    return str(name).strip().upper() in as_source_list(val)


def copy_tifs_from_shared(shared_folder: str, dest_folder: str) -> None:
    from tito_utils.file_utils.file_handling import mkdir_p

    mkdir_p(dest_folder)
    for src in glob.glob(os.path.join(shared_folder, "*.tif")):
        try:
            shutil.copy2(src, dest_folder)
        except Exception as exc:
            print(f"    Warning: copy {os.path.basename(src)}: {exc}")


def resolve_cold_start_window(config, sim_end: datetime) -> tuple[datetime, datetime]:
    """Return ``(cold_start_begin, cold_start_warm_end)`` for IMERG-only EF5."""
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


def parse_streamsat_tif_window(
    ens_p1_dir: str,
    tif_pattern: str = "streamsat",
) -> tuple[datetime, datetime, list[datetime]] | None:
    """
    Parse STREAM-Sat GeoTIFF timestamps from ``ensP1``.

    Returns ``(ss_start, ss_end, all_timestamps)`` or ``None`` if none found.
    """
    tif_files = sorted(glob.glob(os.path.join(ens_p1_dir, f"{tif_pattern}.qpe.*.mmhInst.tif")))
    if not tif_files:
        return None

    timestamps: list[datetime] = []
    for tf in tif_files:
        m = re.search(r"qpe\.(\d{12})\.", os.path.basename(tf))
        if m:
            try:
                timestamps.append(datetime.strptime(m.group(1), "%Y%m%d%H%M"))
            except ValueError:
                pass
    if not timestamps:
        return None
    return min(timestamps), max(timestamps), timestamps


def resolve_region_resolution(
    region_name: str,
    model_resolution: str,
    region_resolution_map,
) -> str:
    if isinstance(region_resolution_map, dict):
        val = region_resolution_map.get(region_name, model_resolution)
        # A region may list several resolutions; singular callers use the first.
        if isinstance(val, (list, tuple)):
            val = val[0] if val else model_resolution
        return val
    return model_resolution


def resolve_region_resolutions(
    region_name: str,
    model_resolution: str,
    region_resolution_map,
) -> list[str]:
    """All resolutions for a region (string or list value), deduped in order."""
    default = [str(model_resolution).strip()]
    if not isinstance(region_resolution_map, dict):
        return default
    val = region_resolution_map.get(region_name, model_resolution)
    if isinstance(val, (list, tuple)):
        out: list[str] = []
        for x in val:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out or default
    s = str(val).strip()
    return [s] if s else default


def region_path_key(region_name: str, model_resolution: str) -> str:
    """Folder segment for states/outputs: ``guatemala_900m``."""
    return f"{str(region_name).lower()}_{str(model_resolution).strip()}"


def resolve_control_template(
    template_path: str,
    region_name: str,
    model_resolution: str,
    region_template_map=None,
    default_template: str = "ef5_Antigua_control_template.txt",
) -> str:
    """
    Pick EF5 control template for a region + resolution.

    Priority:
      1. ``region_template_map[region]`` if set and the file exists
      2. ``ef5_{Region}_{resolution}_control_template.txt`` if present
      3. ``ef5_{Region}_control_template.txt`` if present
      4. ``default_template``
    """
    if isinstance(region_template_map, dict):
        override = region_template_map.get(region_name)
        if override:
            override_path = os.path.join(template_path, override)
            if os.path.isfile(override_path):
                return override

    res = str(model_resolution or "").strip()
    candidates = []
    if res:
        candidates.append(f"ef5_{region_name}_{res}_control_template.txt")
    candidates.append(f"ef5_{region_name}_control_template.txt")

    for name in candidates:
        if os.path.isfile(os.path.join(template_path, name)):
            return name

    return default_template
