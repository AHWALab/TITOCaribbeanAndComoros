"""Cycle timing, warmup decisions, and phase windows for TITO."""

from tito_utils.cycle.region_plan import build_region_configs
from tito_utils.cycle.timeline import (
    IMERG_LATENCY,
    STATE_LOOKBACK,
    WARMUP_STATE_OFFSET,
    CyclePlan,
    PhaseWindow,
    build_cycle_plan,
    expected_state_for_next_cycle,
    round_cycle_time,
)
from tito_utils.cycle.warmup import decide_warmup, warmup_window

__all__ = [
    "IMERG_LATENCY",
    "WARMUP_STATE_OFFSET",
    "STATE_LOOKBACK",
    "CyclePlan",
    "PhaseWindow",
    "build_cycle_plan",
    "round_cycle_time",
    "expected_state_for_next_cycle",
    "decide_warmup",
    "warmup_window",
    "build_region_configs",
]
