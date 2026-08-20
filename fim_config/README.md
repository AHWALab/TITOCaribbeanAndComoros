# fim_config: this folder decides where FIM runs

One YAML file in this folder = one FIM site. After each cycle’s EF5 runs,
`orchestrator.py` STEP 8 calls `tito_utils.fim_utils.tito_hook` when
`fim_enabled = True` in `Caribbean_Comoros_config.py`. It picks up files named
`<Region>*.yaml`, where `<Region>` is the exact name from `regions_to_run`.
No matching YAML means no FIM for that region. The `examples/` subfolder is
never auto-picked.

Toggles, coarse to fine: `fim_enabled = False` skips FIM entirely (EF5
unchanged); the `fim_regions` block in `Caribbean_Comoros_config.py`
switches whole countries and carries the USER depth thresholds (they
OVERRIDE the `thresholds_m` inside the YAMLs here); a top level
`enabled: false` line inside a YAML parks that single site.

## Current sites

| file | site | hazards | status |
| --- | --- | --- | --- |
| `Guatemala_SantaInesPetapa.yaml` | Santa Ines Petapa, cuenca Villalobos | pluvial + fluvial + combined | READY (unzip the store once, see below) |
| `Guatemala_Morales.yaml` | Morales, Rio Motagua | pluvial + fluvial + combined | prepared, `enabled: false`, waiting for the flood map library |
| `Antigua_*.yaml` (7 files) | one per ADM1 unit of Antigua and Barbuda | pluvial | READY |
| `Barbados_*.yaml` (11 files) | one per parish | pluvial | READY |

Guatemala carries two basins, so it has two YAML files. The islands carry
one YAML per administrative unit, so one country switch in `fim_regions`
covers 7 sites for Antigua and 11 for Barbados. Any country can hold any
number of sites the same way: `Haiti_SiteA.yaml`, `Haiti_SiteB.yaml`, and
so on.

## The ibf/ subfolder

`ibf/<Site>_ibf.yaml` files describe the IBF receptor product that is
chained after a site's FIM run (buildings, roads, admin exposure). They are
picked up by name: `<Site>_ibf.yaml` pairs with the FIM site `<Site>.yaml`.
Switches and threshold overrides live in `ibf_enabled` / `ibf_regions` in
the main config. Sites without an ibf YAML simply run FIM alone.

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

    thresholds_m: [0.10, 0.30, 0.70, 1.00]

Edit the list and rerun; every value produces its own probability raster and
likelihood class raster in every enabled routine. The values above are the
current default set (10 cm, 30 cm, 70 cm, 1 m). In orchestrated runs the
`thresholds_m` of the region's entry in `fim_regions`
(`Caribbean_Comoros_config.py`) takes precedence, so operators normally
change thresholds there, once per country, without opening any YAML.

## Before a site can run

Each site needs, once: its scenario store under `fim_store/` (unzipped from
the shipped zip, or built new with `fim_dev/build_store_guatemala.py` for
basin sites and `fim_dev/build_admin_stores.py` for island admin units),
real storm magnitudes attached to that store, and its area of concern
polygon under `fim_config/aoc/`. The full checklist with commands is in
`README_FIM.md`, section "Manual steps before a region can run". For the
Santa Ines Petapa site only the unzip step remains; everything else ships
done.

## Testing a site by hand

    python -m tito_utils.fim_utils.pipeline_pf \
        --config fim_config/Guatemala_SantaInesPetapa.yaml --cycle <cycle>

Use `--hazard P`, `--hazard F` or `--hazard PF` to run one routine alone.
