# FIM lookup architecture in TITO

## Data flow (one cycle, one region)

```
EF5 runs (existing TITO output; every run folder = one ensemble member)
outputs/<Region>/tmp_output_crest_scampr_gfs/<cycle>/
outputs/<Region>/tmp_output_crest_scampr_arome/<cycle>/
    maxunitq.<cycle>.tif  qpeaccum.<cycle>.tif  qpfaccum.<cycle>.tif
        |
        v
[1] trigger.py      any pixel of maxunitq >= 1.0 inside an Area of Concern?
        | yes (per AOC)
        v
[2] rainfall.py     T(member, AOC) = mean(qpeaccum) + mean(qpfaccum) over AOC
        |
        v
[3] matching.py     candidates: magnitude in [0.9T, 1.2T]  (direction optional)
                    none -> [0.8T, 1.3T] -> drop direction
                    none and T > largest -> two largest, flag beyond_catalog
                    pick the candidate closest to T from above (round up)
        |
        v
[4] select          best  = match of the median member
                    upper = match of the 90th percentile member
        |
        v
[5] products.py     outputs/<Region>/fim/<cycle>/
                        <AOC>_best_<storm>_depth.tif / _extent.tif
                        <AOC>_upper_<storm>_depth.tif / _extent.tif
                        member_totals.csv  matches.csv  fim_summary.json
```

Quiet cycles still write `fim_summary.json` with status "quiet", so every
cycle leaves a record.

## Folder plan

```
TITOCaribbeanAndComoros/
  tito_utils/fim_utils/        the package (push to GitHub)
  fim_config/                  one YAML per region (push; create from
                               fim_dev/configs templates)
  fim_catalog/<Region>/v1/     lookup tables (large rasters; keep OUT of
                               git or use LFS)
      index.csv  magnitudes_by_aoc.csv  meta.json  maps/  extents/
  aoc/                         Area of Concern polygons per region (small,
                               can be pushed)
  fim_dev/                     development sandbox (synthetic data, tests,
                               docs; push or keep local, either works;
                               fim_dev/sample_data/ should stay out of git)
  outputs/<Region>/fim/<cycle>/   runtime products (never pushed)
```

Suggested .gitignore additions:
```
fim_catalog/
fim_dev/sample_data/
outputs/*/fim/
```

## TITO integration point

`orchestrator.py`, after the LR EF5 simulations of a cycle complete
(end of Phase 2b), per region:

```python
from tito_utils.fim_utils import load_config, run_fim_cycle
fim_cfg = f"fim_config/{region}.yaml"
if os.path.isfile(fim_cfg):
    try:
        run_fim_cycle(load_config(fim_cfg), cycle=output_timestamp_str)
    except Exception as exc:
        print(f"    FIM step failed for {region}: {exc}")  # never blocks EF5
```

The step is read-only with respect to EF5 outputs, file-based, idempotent
(re-running a cycle overwrites the same fim/<cycle> folder), and safe to
skip when no config exists for a region.

## Ensembles and future changes

- More QPF members (ensemble GFS/AROME): each lands as another run folder
  or, if TITO later encodes members inside one folder, extend
  `ef5_runs.discover_runs` only; the rest of the chain is member-agnostic.
- 3 cycles per day, different warm-up: no code change, cycles and windows
  come from the EF5 outputs themselves.
- Selector percentiles (50/90), thresholds, bands: YAML only.
- Direction matching: set `matching.use_direction: true` and pass a
  member -> degrees mapping into `match_members` once storm motion is
  extracted from the QPF grids (catalog directions are already stored).
```
