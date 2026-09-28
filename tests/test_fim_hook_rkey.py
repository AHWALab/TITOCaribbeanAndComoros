"""FIM member discovery must stay inside the resolution being processed.

Guatemala and Haiti run 900m and 90m into the same cycle folder; with
{rkey} left as a wildcard the 90m FIM ensemble also picked up the 900m
members (same member ids, no gauge discharge).
"""

from tito_utils.fim_utils.ensemble import discover_ensemble_members
from tito_utils.fim_utils.tito_hook import _apply_chain_templates, _pin_rkey


def test_pin_rkey_keeps_members_in_their_resolution(tmp_path):
    cycle = "20260928.190000"
    for rkey in ("haiti_900m", "haiti_90m"):
        for ens in (1, 2):
            (tmp_path / cycle / rkey / "stormlab" / f"ensOut{ens}_sl1").mkdir(parents=True)

    cfg = {}
    _apply_chain_templates(cfg, "stream_sat_stormlab")
    loose = discover_ensemble_members(str(tmp_path), cfg["member"]["template"], cycle=cycle)
    assert len(loose) == 4  # the defect: both resolutions

    _pin_rkey(cfg, "haiti_90m")
    members = discover_ensemble_members(str(tmp_path), cfg["member"]["template"], cycle=cycle)
    assert len(members) == 2
    assert all("/haiti_90m/" in m.run_dir for m in members)
    assert all("{rkey}" not in c["template"] for c in cfg["rain_components"])
    assert all("{rkey}" not in s["template"] for s in cfg["trigger"]["sources"])
