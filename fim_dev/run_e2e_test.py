"""End-to-end test of fim_utils on fully synthetic data.

Run from the repo root (or from fim_dev/):
    python fim_dev/make_synthetic.py
    python fim_dev/run_e2e_test.py

Checks the whole chain: run discovery, UQ trigger, QPE+QPF totals,
catalog matching (normal, quiet, beyond-catalog) and product export.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from tito_utils.fim_utils.config import load_config
from tito_utils.fim_utils.pipeline import run_fim_cycle

CONFIG = os.path.join(HERE, "configs", "Barbados_synthetic.yaml")
CHECKS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    CHECKS.append((name, condition))
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail else ""))


def main():
    config = load_config(CONFIG, root=ROOT)

    print("== Cycle 20240704.090000 (normal event) ==")
    s = run_fim_cycle(config, cycle="20240704.090000")

    check("status is triggered", s.get("status") == "triggered")
    check("only the QPE-only run was skipped (2 members)",
          len({k.split("|")[1] for k in s["trigger"]["max_uq"]}) == 2,
          str(sorted({k.split("|")[1] for k in s["trigger"]["max_uq"]})))
    check("triggered exactly in AOC_Central",
          s["trigger"]["triggered_aocs"] == ["AOC_Central"],
          str(s["trigger"]["triggered_aocs"]))

    sel = s["selections"]["AOC_Central"]
    best, upper = sel["best"], sel["upper"]
    check("best member total ~121 mm", abs(best["total_mm"] - 121.0) < 1.0,
          str(best["total_mm"]))
    check("upper member total ~158 mm", abs(upper["total_mm"] - 158.0) < 1.0,
          str(upper["total_mm"]))
    check("best matched 130 mm storm (round up from 121)",
          abs(best["storm_magnitude_mm"] - 130.0) < 0.1, best["storm_id"])
    check("upper matched 175 mm storm (round up from 158)",
          abs(upper["storm_magnitude_mm"] - 175.0) < 0.1, upper["storm_id"])
    check("first tier band rule applied",
          best["rule_applied"] == "band" and upper["rule_applied"] == "band")

    out_dir = os.path.join(config.outputs_dir, "20240704.090000")
    expected = [
        f"AOC_Central_best_{best['storm_id']}_depth.tif",
        f"AOC_Central_best_{best['storm_id']}_extent.tif",
        f"AOC_Central_upper_{upper['storm_id']}_depth.tif",
        f"AOC_Central_upper_{upper['storm_id']}_extent.tif",
        "member_totals.csv", "matches.csv", "fim_summary.json",
    ]
    for fname in expected:
        check(f"output exists: {fname}", os.path.isfile(os.path.join(out_dir, fname)))

    with open(os.path.join(out_dir, "fim_summary.json")) as fh:
        js = json.load(fh)
    check("summary json readable with selections", "selections" in js)

    print("== Cycle 20240703.090000 (quiet) ==")
    s2 = run_fim_cycle(config, cycle="20240703.090000")
    check("quiet cycle stays quiet", s2.get("status") == "quiet")
    check("quiet summary written", os.path.isfile(
        os.path.join(config.outputs_dir, "20240703.090000", "fim_summary.json")))

    print("== Cycle 20240704.150000 (beyond catalog) ==")
    s3 = run_fim_cycle(config, cycle="20240704.150000")
    check("extreme cycle triggered", s3.get("status") == "triggered")
    up3 = s3["selections"]["AOC_Central"]["upper"]
    check("beyond_catalog rule fired", up3["rule_applied"] == "beyond_catalog",
          up3["rule_applied"])
    check("largest storm used with an alternate listed",
          abs(up3["storm_magnitude_mm"] - 290.0) < 0.1 and bool(up3["alt_storm_id"]),
          f"{up3['storm_id']} alt={up3['alt_storm_id']}")

    failed = [name for name, ok in CHECKS if not ok]
    print()
    if failed:
        print(f"E2E RESULT: {len(failed)} FAILED of {len(CHECKS)}: {failed}")
        return 1
    print(f"E2E RESULT: all {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
