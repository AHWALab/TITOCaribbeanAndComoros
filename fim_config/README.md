# fim_config: this folder decides where FIM runs

One YAML file in this folder = one FIM site. The orchestrator (Phase 3, after
the EF5 runs) looks for files named `<Region>*.yaml`, where `<Region>` is the
exact region name from `Caribbean_Comoros_config.py` `regions_to_run`. No
matching YAML means no FIM for that region, and the pipeline is unchanged.
The `examples/` subfolder is never picked up.

Above the site files sits one master control: the `fim_regions` block in
`Caribbean_Comoros_config.py`. It switches each region on or off and sets
the depth thresholds for all of that region's sites. Operators normally
only touch that block.

## Current sites

| file | site | hazards | status |
| --- | --- | --- | --- |
| `Guatemala_SantaInesPetapa.yaml` | Santa Ines Petapa, cuenca Villalobos | pluvial + fluvial + combined | READY (unzip the store once, see below) |
| `Guatemala_Morales.yaml` | Morales, Rio Motagua | pluvial + fluvial + combined | prepared, `enabled: false`, waiting for the flood map library |

Guatemala carries two basins, so it has two YAML files. Any country can hold
any number of sites the same way: `Haiti_SiteA.yaml`, `Haiti_SiteB.yaml`, and
so on.

## Declaring the hazards of a site

The `hazards:` block inside each YAML is the switch:

    hazards:
      pluvial:
        enabled: true          # rainfall analog matching (all sites)
      fluvial:
        enabled: true          # discharge analog matching (Guatemala sites)
        boundary_series:
          - "ts.cuenca_villalobos_1.crest.{cycle}.csv"
          - "ts.cuenca_villalobos_2.crest.{cycle}.csv"

Guatemala sites run both hazards plus the combined PF product (per pixel
maximum across the two matched maps, member by member). Sites in other
countries are pluvial only for now: set `fluvial: {enabled: false}` and the
site produces pluvial products alone. Start new pluvial only sites from
`examples/PluvialOnly_country_template.yaml`.

A YAML with a `hazards:` block uses the pluvial + fluvial runner
(`pipeline_pf`). A YAML without one is treated as a classic v0.2 config and
uses the original ensemble runner, so older configs keep working.

## Switching a site off and on

Add a top level line `enabled: false` to skip a site without deleting its
file (`Guatemala_Morales.yaml` ships that way until its store is built).
Remove the line to activate it.

## Depth thresholds are a user input

Since v0.5 the thresholds live in `Caribbean_Comoros_config.py`:

    fim_regions = {
        "Guatemala": {"enabled": True, "thresholds_m": [0.10, 0.30, 0.70, 1.00]},
        ...
    }

Edit that list and rerun; every value produces its own probability raster
and likelihood class raster in every enabled routine, and it overrides the
`thresholds_m` line of the site YAMLs (which still applies to standalone
runs outside the orchestrator).

## Before a site can run

Each site needs, once: its scenario store under `fim_store/<Region>/`
(run `python fim_store/unzip_stores.py` after pulling a new store zip),
real storm magnitudes attached to that store, and its area of concern
polygon under `fim_config/aoc/`. Every country folder under `fim_store/`
carries a README_ADD_STORE.md with the five step drop-in checklist; the
full version with commands is in `README_FIM.md`. For the Santa Ines
Petapa site only the unzip step remains; everything else ships done.

## Testing a site by hand

    python -m tito_utils.fim_utils.pipeline_pf \
        --config fim_config/Guatemala_SantaInesPetapa.yaml --cycle <cycle>

Use `--hazard P`, `--hazard F` or `--hazard PF` to run one routine alone.
