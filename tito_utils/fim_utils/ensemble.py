"""Global (layout-driven) ensemble handling.

TITO ensemble outputs can be nested any way (products, QPE members, QPF
members). Instead of hard-coding a tree, the config describes it with
path templates containing named placeholders:

  members:
    template: "stormlab/ensOut{ens}_sl{sl}/guatemala/tmp_output_crest_stormlab"
  components:            # rainfall pieces summed into the member total
    - {name: qpe_streamsat, template: "stream_sat/ensOut{ens}/guatemala/tmp_output_crest_streamsat", grid: qpe_accum}
    - {name: qpe_scampr,    template: "scampr/ensOut{ens}/guatemala/tmp_output_crest_gap_scampr",    grid: qpe_accum}
    - {name: rain_stormlab, template: "stormlab/ensOut{ens}_sl{sl}/guatemala/tmp_output_crest_stormlab", grid: qpe_accum}
  trigger_sources:       # every run whose maxunitq can fire the trigger
    - {template: "stream_sat/ensOut{ens}/guatemala/tmp_output_crest_streamsat"}
    - {template: "scampr/ensOut{ens}/guatemala/tmp_output_crest_gap_scampr"}
    - {template: "stormlab/ensOut{ens}_sl{sl}/guatemala/tmp_output_crest_stormlab"}

Placeholders match any value on disk; whatever matched in the member
template is substituted into the component templates, so member
(ens=3, sl=2) picks stream_sat/ensOut3 + scampr/ensOut3 +
stormlab/ensOut3_sl2. Add members or whole new products on disk and they
are discovered with zero code changes.
"""

import glob
import os
import re
from dataclasses import dataclass, field

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _template_to_regex(template: str):
    """'a/ensOut{ens}_sl{sl}/b' -> compiled regex with named groups."""
    out, pos = [], 0
    for m in _PLACEHOLDER.finditer(template):
        out.append(re.escape(template[pos:m.start()]))
        out.append(f"(?P<{m.group(1)}>[^/]+?)")
        pos = m.end()
    out.append(re.escape(template[pos:]))
    return re.compile("^" + "".join(out) + "$")


def _template_to_glob(template: str) -> str:
    return _PLACEHOLDER.sub("*", template)


@dataclass
class EnsembleMember:
    member_id: str                 # e.g. "ens03_sl2"
    keys: dict                     # {"ens": "3", "sl": "2"}
    run_dir: str                   # resolved member run dir (absolute)
    cycle: str


def discover_ensemble_members(outputs_root: str, member_template: str,
                              cycle: str = None,
                              cycle_format: str = "%Y%m%d.%H%M%S") -> list:
    """Find members by expanding the member template against the disk."""
    from datetime import datetime
    rx = _template_to_regex(member_template.strip("/"))
    hits = []
    for path in sorted(glob.glob(os.path.join(outputs_root, _template_to_glob(member_template)))):
        rel = os.path.relpath(path, outputs_root).replace(os.sep, "/")
        m = rx.match(rel)
        if not m or not os.path.isdir(path):
            continue
        hits.append((m.groupdict(), path))

    # cycle discovery
    if cycle is None or cycle == "":
        latest = ""
        for _, path in hits:
            for name in os.listdir(path):
                if os.path.isdir(os.path.join(path, name)):
                    try:
                        datetime.strptime(name, cycle_format)
                    except ValueError:
                        continue
                    latest = max(latest, name)
        cycle = latest
    if not cycle:
        return []

    members = []
    for keys, path in hits:
        cdir = os.path.join(path, cycle)
        if not os.path.isdir(cdir):
            continue
        member_id = "_".join(f"{k}{_pad(v)}" for k, v in sorted(keys.items()))
        members.append(EnsembleMember(member_id=member_id, keys=keys,
                                      run_dir=cdir, cycle=cycle))
    return members


def _pad(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits and digits == value.strip():
        return f"{int(digits):02d}"
    # values like "ensOut3" keep their tail digits padded
    m = re.match(r"^(.*?)(\d+)$", value)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}"
    return value


def resolve_component_dir(outputs_root: str, template: str, keys: dict, cycle: str) -> str:
    """Fill a component template with the member's keys (unused keys ok)."""
    try:
        rel = template.format(**keys)
    except KeyError as exc:
        raise KeyError(f"Component template '{template}' needs key {exc} "
                       f"not present in member keys {sorted(keys)}") from exc
    return os.path.join(outputs_root, rel, cycle)


def grid_path(run_dir: str, role: str, cycle: str, file_templates: dict) -> str:
    template = file_templates.get(role)
    if not template:
        return ""
    path = os.path.join(run_dir, template.format(cycle=cycle))
    return path if os.path.isfile(path) else ""


# ---------------------------------------------------------------------------
# Sampling zone: AOC stats with expand-on-nodata fallback.
# EF5 outputs can be masked to gauged basins; if the Area of Concern falls
# in the masked (nodata) region, the sampling window widens step by step
# until enough valid cells are found, and the expansion is flagged.
# ---------------------------------------------------------------------------

@dataclass
class ZoneStat:
    value: float
    n_valid: int
    expand_km: float
    flags: list = field(default_factory=list)


def zone_stat(raster_path: str, bounds, stat: str = "mean",
              expand_steps_km=(0, 2, 5, 10, 15), min_valid_cells: int = 50) -> ZoneStat:
    """Statistic over a lon/lat bounds box with widening fallback."""
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds, Window

    with rasterio.open(raster_path) as src:
        for exp_km in expand_steps_km:
            dd = exp_km / 111.0
            bb = (bounds[0] - dd, bounds[1] - dd, bounds[2] + dd, bounds[3] + dd)
            win = from_bounds(*bb, transform=src.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, src.width, src.height))
            if win.width <= 0 or win.height <= 0:
                continue
            data = src.read(1, window=win)
            valid = data != src.nodata if src.nodata is not None else np.isfinite(data)
            n = int(valid.sum())
            if n >= min_valid_cells:
                vals = data[valid]
                value = float(vals.max()) if stat == "max" else float(vals.mean())
                flags = [] if exp_km == 0 else [f"sampling_expanded_{exp_km}km"]
                return ZoneStat(value=value, n_valid=n, expand_km=float(exp_km), flags=flags)
    return ZoneStat(value=float("nan"), n_valid=0, expand_km=float(expand_steps_km[-1]),
                    flags=["no_valid_cells"])
