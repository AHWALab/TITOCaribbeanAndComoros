# fim_dev : development sandbox for the FIM lookup framework

This folder is the workbench; `tito_utils/fim_utils/` is the deliverable
that goes to GitHub. Nothing here is needed at runtime.

## Contents

- `SAMPLES_NEEDED.md`  the exact sample files needed to finish the
  framework against real data, and the open decisions.
- `ARCHITECTURE.md`    data flow, folder plan, orchestrator integration.
- `configs/`           region config templates (Barbados admin units,
  Haiti pilot basin) plus the synthetic test config.
- `make_synthetic.py`  builds a complete fake setup: AOCs, a 12-storm
  catalog, EF5 outputs for a normal, a quiet and an extreme cycle.
- `run_e2e_test.py`    runs the whole chain with 21 checks.
- `sample_data/`       synthetic data lands in `synthetic/`; put real
  samples under `real/` (kept out of git).

## Quick start

```bash
cd <repo root>
python fim_dev/make_synthetic.py
python fim_dev/run_e2e_test.py        # expect: all 21 checks passed
```

Then try the CLI the way TITO will call it:

```bash
python -m tito_utils.fim_utils.pipeline \
    --config fim_dev/configs/Barbados_synthetic.yaml \
    --cycle 20240704.090000
```

## Status (28 July 2026)

Working end to end on synthetic data: run discovery (members = run
folders, QPE-only runs skipped), any-pixel UQ trigger per Area of Concern,
QPE + QPF totals from the EF5 accumulation grids, widening-band round-up
matching with beyond-catalog fallback, best/upper member selection, product
export with a full decision log, quiet-cycle records.

Waiting on real samples (see SAMPLES_NEEDED.md) to: adapt the RainyDay
metadata reader, build the first real catalog, run against a real EF5
cycle, and wire the call into orchestrator.py.
