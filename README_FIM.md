# FIM and IBF in TITO (main)

Scenario library flood inundation mapping (FIM) turns each forecast cycle's
rainfall into pre-simulated flood maps: the cycle's rain total is matched to
the closest simulated storm in a per-site zarr store, and that storm's depth
and extent become the cycle's probabilistic products. The IBF receptor layer
can then turn those probabilities into building, road and admin-unit warning
products. Both run inside orchestrator STEP 8, after EF5, and both are
non-fatal: they can never block EF5.

## Layout

| Path | Role |
|------|------|
| `tito_utils/fim_utils/` | FIM package (pipelines, store, matching, the STEP 8 hook) |
| `tito_utils/ibf_utils/` | IBF receptor package (see its own README) |
| `fim_config/` | One YAML per FIM site (`<Region>*.yaml`) |
| `fim_config/ibf/` | One YAML per IBF site (`<Site>_ibf.yaml`) |
| `fim_config/aoc/` | Area of concern polygons |
| `fim_store/<Region>/` | Scenario stores, one zip per site (plain files, no LFS) |
| `fim_dev/` | Store builders (Guatemala basins, island admin units) |
| `outputs/<cycle>/<rkey>/fim/<chain>/` | Runtime FIM products (gitignored) |
| `outputs/ibf/` | Runtime IBF products (gitignored) |

## Switching things on and off

Everything operators touch lives in `Caribbean_Comoros_config.py`:

```python
fim_enabled = True                 # global FIM switch
fim_default_thresholds_m = [0.10, 0.30, 0.70, 1.00]
fim_regions = {                    # per country switch + USER thresholds
    "Guatemala": {"enabled": True, "thresholds_m": fim_default_thresholds_m},
    "Antigua":   {"enabled": True, "thresholds_m": fim_default_thresholds_m},
    ...
}

ibf_enabled = True                 # global IBF switch
ibf_regions = {                    # per country switch + threshold overrides
    "Guatemala": {"enabled": True,
                  "severity_thresholds_m": {"minor": 0.10,
                                            "significant": 0.30,
                                            "severe": 0.76},
                  "hazard_flag_cutoff": 0.30,
                  "reporting_threshold": 0.05},
    ...
}
```

Rules of the two blocks: one country key switches every site of that country
(Antigua has 7 unit sites, Barbados 11). Values set here OVERRIDE the site
YAMLs, so thresholds can be changed without opening any YAML. A region
missing from a block simply follows its YAMLs. `thresholds_m` accepts any
number of positive depths in meters; each value produces its own probability
raster and likelihood raster.

## When FIM runs

| Rule | Behaviour |
|------|-----------|
| When | After the forecast EF5 phase only (`run_LR` / Phase C). Never after IMERG or STREAM-Sat alone. |
| Resolution | 90m regions only; others are skipped and logged. |
| Rain total | Sum of qpeaccum components (never qpfaccum or long range). |
| IMERG+GFS chain | IMERG + optional SCaMPR gap + GFS forecast QPE accums |
| STREAM-Sat+StormLab chain | STREAM-Sat + StormLab QPE accums per ensemble member |

Site discovery: `fim_config/<Region>*.yaml`, where `<Region>` is the exact
name in `regions_to_run`. Park a single site with a top level
`enabled: false` line in its YAML.

## Current sites

| Country | Sites | Status |
|---------|-------|--------|
| Guatemala | Santa Ines Petapa (pluvial + fluvial + combined) | READY |
| Guatemala | Morales (prepared, `enabled: false`) | waiting for its flood map library |
| Antigua and Barbuda | 7 ADM1 units, one store each (pluvial) | READY |
| Barbados | 11 parishes, one store each (pluvial) | READY |
| Comoros, Haiti | placeholders under `fim_store/` | waiting for analog maps |

Island unit stores hold the 200 hydrodynamic samples clipped to the unit
window, max depth from the dmax product (uint8 centimeters, saturated at
2.55 m) and real pluvial magnitudes (289 band storm totals in mm averaged
over the unit polygon), so matching is local to every unit.
`fim_store/<Country>/manifest_*.csv` lists every unit and its store.

## One time setup after clone or pull

Store zips are plain git files (no LFS involved). Extract them once:

```bash
python fim_store/unzip_stores.py
```

The helper extracts every zip that is not yet unzipped and skips the rest,
so it is always safe to rerun. Requires: pyyaml, numpy, rasterio, zarr (all
in `tito_env.yml`).

## Products

FIM writes cycle first, tagged by the forcing chain so IMERG+GFS and
STREAM-Sat+StormLab never mix:

```text
outputs/<cycle>/<rkey>/fim/<chain>/
  pluvial/   prob_depth_ge_10cm.<cycle>.tif ... likelihood + extent rasters
  fluvial/   (Guatemala sites)
  combined/  (Guatemala sites)
```

with `<chain>` one of `stream_sat_stormlab`, `imerg_gfs`, `imerg_stormlab`,
`stream_sat_gfs`.

## IBF chained after FIM

For each site that just produced FIM products, STEP 8 also runs the IBF
receptor layer when `fim_config/ibf/<Site>_ibf.yaml` exists and the region
is enabled in `ibf_regions`. IBF samples the probability rasters onto
buildings and roads, classifies them with the flood risk matrix (Speight et
al. 2018), rolls exposure up to admin units and writes per cycle GeoPackage,
CSV and JSON summaries under `outputs/ibf/`.

Coverage: all 18 island unit sites (Antigua and Barbuda, Barbados) plus
Guatemala Santa Ines Petapa. The island receptor data ships IN the repo
under `ibf_data/<Country>/` (Overture buildings and roads, admin units with
census population, GHS BUILT-C classes), so the islands need nothing
downloaded. Guatemala still uses the external `IBFv10_Guatemala/input_data/`
package next to the repo (too large for git). The environment needs
geopandas plus pyogrio (declared in `tito_env.yml`); without them IBF logs
one line and skips.

The user thresholds live in `ibf_regions` in the main config: the
likelihood cutoff that flags a receptor (default 0.50, that is 50 percent)
and the severity depths, set equal to the FIM depth thresholds of each
region. The first cycle over a domain builds a clipped receptor cache under
`outputs/ibf_cache/`; later cycles reuse it (seconds for small units, about
two minutes for the densest ones such as Saint John's or Saint Michael).
Details and the flood risk matrix semantics:
`tito_utils/ibf_utils/README.md`.

## Manual tests

```bash
# one FIM site, one cycle
python -m tito_utils.fim_utils.pipeline_pf \
  --config fim_config/Guatemala_SantaInesPetapa.yaml --cycle 20230621.070000

# one IBF site on an existing FIM products folder
python -m tito_utils.ibf_utils.pipeline_ibf \
  --config fim_config/ibf/Guatemala_SantaInesPetapa_ibf.yaml \
  --cycle 20230621.070000 \
  --products-dir outputs/20230621.070000/guatemala_90m/fim/imerg_gfs/combined
```

## Building or extending stores

- Guatemala basins: `fim_dev/build_store_guatemala.py` plus
  `fim_dev/attach_real_magnitudes_santaines.py` (worked example for real
  magnitudes and the fluvial index).
- Island admin units: `fim_dev/build_admin_stores.py` rebuilds all Antigua
  and Barbuda plus Barbados stores from the ADM1 shapefile and the dmax and
  pcpout rasters; see the notes at the top of the script and
  `fim_store/<Country>/README_<Country>.md`.
