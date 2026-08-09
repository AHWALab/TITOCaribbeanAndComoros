"""Pluvial (P) hazard: analog matching on rainfall magnitude.

Thin, named wrapper around the existing magnitude machinery so the three
hazard routines (pluvial, fluvial, combined) read the same way in code
and in configs. The matching itself is the banded round-up rule of
store.match(); the member magnitude is the zone mean of the accumulation
grid over the area of concern (ensemble.zone_stat).
"""

from .ensemble import zone_stat, grid_path


def member_rain_total(run_dir: str, cycle: str, bounds, files: dict,
                      grid_role: str = "qpe_accum",
                      expand_steps_km=(0, 2, 5, 10, 15), min_valid_cells: int = 50):
    """Zone-mean rainfall total of one run over the AOC. Returns (mm, flags)."""
    gpath = grid_path(run_dir, grid_role, cycle, files)
    if not gpath:
        return float("nan"), [f"missing_{grid_role}"]
    zs = zone_stat(gpath, bounds, "mean", expand_steps_km, min_valid_cells)
    return zs.value, list(zs.flags)


def match_pluvial(store, total_mm: float, band=(0.9, 1.2), band_wide=(0.8, 1.3)) -> dict:
    """Banded round-up analog match on rainfall magnitude (existing rule)."""
    decision = store.match(total_mm, band=tuple(band), band_wide=tuple(band_wide))
    decision["rule_applied"] = "pluvial_" + decision["rule_applied"]
    return decision
