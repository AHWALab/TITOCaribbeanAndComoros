"""Generate one fim_config/ibf/<Site>_ibf.yaml per island FIM site.

Reads the island FIM site YAMLs (Antigua_*.yaml, Barbados_*.yaml,
Comoros_*.yaml), reuses their region and products_root, and writes the
paired IBF YAML pointing at the country's static data under
ibf_data/<Country>/.

Run:  python fim_dev/gen_island_ibf_yamls.py fim_config fim_config/ibf [Country ...]
"""

import glob
import os
import sys

import yaml

FIM_DIR = sys.argv[1] if len(sys.argv) > 1 else "fim_config"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "out_ibf_yamls"
ONLY = sys.argv[3:]

ISLAND_ADMIN = """  admin:
    source: ibf_data/{country}/{country}_adm1_population.gpkg
    layer: adm1
    id_field: ADM1_PCODE
    name_field: ADM1_EN
    population_field: population"""

ISLAND_DATA = """# Static data lives IN the repo under ibf_data/{country}/: Overture Maps
# buildings and roads, admin units with census population, and the GHS
# BUILT-C functional class raster for the dasymetric weights. Nothing to
# download before running."""

META = {
    "Antigua": {"slug": "antigua", "work_crs": "EPSG:32620", "label": "Antigua and Barbuda"},
    "Barbados": {"slug": "barbados", "work_crs": "EPSG:32621", "label": "Barbados"},
    "Comoros": {
        "slug": "comoros",
        "work_crs": "EPSG:32738",
        "label": "Comoros",
        "data": """# Static data: ibf_data/Comoros/, built by fim_dev/build_comoros_ibf_preload.py
# from the IBF team's package (IBF_v1_Comoros_20240427_updated.zip; see
# manifest_ibf_Comoros.json): Overture Maps buildings, roads and places,
# the 55 communes of COM_communes.shp (the FIM site units) with the WorldPop
# 2025 population recomputed per commune, and the GHS BUILT-C functional
# class raster. The team's IBFv1.0 Comoros run used a 0.40 likelihood
# cutoff; TITO keeps the 0.50 user default (ibf_regions).""",
        "admin": """  admin:
    source: ibf_data/{country}/{country}_admin_population.gpkg
    layer: admin
    id_field: ADM_ID          # com_admin3 pcode (KMxxx)
    name_field: ADM_NAME
    population_field: population   # WorldPop 2025 sum per municipality""",
        # IBF_v1_Comoros road classes (no unclassified)
        "keep_classes": "[motorway, trunk, primary, secondary, tertiary, residential]",
        "places": True,
        # the IBF team's Comoros run read the overbank probabilities
        # (baseline channel water removed): pluvial_overbank products
        "mode": "pluvial_overbank",
        "prefer_overbank": "true",
    },
}

TEMPLATE = """# IBF receptor product: {label}, {unit_label} (paired with the FIM site
# {site}.yaml; same stem plus _ibf).
#
{data}
#
# In orchestrated runs tito_hook overrides fim_products with the cycle
# first path, and the ibf_regions block in Caribbean_Comoros_config.py
# OVERRIDES severity_thresholds_m, hazard_flag_cutoff and
# reporting_threshold, so operators normally edit them there.
region: {site}

receptors:
  buildings:
    source: ibf_data/{country}/{slug}_overture_bld_rds.gpkg
    layer: buildings
    id_field: id
    subtype_field: subtype
  roads:
    source: ibf_data/{country}/{slug}_overture_bld_rds.gpkg
    layer: roads
    id_field: id
    class_field: class
    keep_classes: {keep_classes}
{places}{admin}
  land_use:
    source: ibf_data/{country}/{country}_GHS_BUILT_C_FUN_E2018_R2023A_54009_10.tif
  work_crs: "{work_crs}"
  domain_buffer_m: 250
  cache_dir: outputs/ibf_cache

fim_products:
  # manual pipeline_pf runs write {products_root}/<cycle>/<mode>
  root: {products_root}/{{cycle}}/{{mode}}
  mode: {mode}
  prefer_overbank: {prefer_overbank}

classification:
  # User defaults for the islands: likelihood cutoff 50 percent, severity
  # depths equal to the FIM depth thresholds of these sites (10, 30, 70 cm).
  reporting_threshold: 0.05
  severity_thresholds_m:
    minor: 0.10
    significant: 0.30
    severe: 0.70
  hazard_flag_cutoff: 0.50

outputs:
  # Orchestrated runs override to outputs/<cycle>/<rkey>/ibf/<Site>/
  root: outputs
  append_cycle: false
"""

PLACES = """  places:
    source: ibf_data/{country}/{slug}_overture_bld_rds.gpkg
    layer: places
    id_field: id
    name_field: name
    category_field: category
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    n = 0
    for country, meta in META.items():
        if ONLY and country not in ONLY:
            continue
        fmt = {"country": country, "slug": meta["slug"]}
        for path in sorted(glob.glob(os.path.join(FIM_DIR, f"{country}_*.yaml"))):
            with open(path) as fh:
                fim = yaml.safe_load(fh)
            site = fim["region"]
            unit_label = site.split("_", 1)[1]
            out = os.path.join(OUT_DIR, f"{site}_ibf.yaml")
            with open(out, "w") as fh:
                fh.write(
                    TEMPLATE.format(
                        label=meta["label"],
                        unit_label=unit_label,
                        site=site,
                        country=country,
                        slug=meta["slug"],
                        work_crs=meta["work_crs"],
                        products_root=fim["products_root"],
                        data=meta.get("data", ISLAND_DATA).format(**fmt),
                        admin=meta.get("admin", ISLAND_ADMIN).format(**fmt),
                        keep_classes=meta.get(
                            "keep_classes",
                            "[motorway, trunk, primary, secondary, tertiary, residential, "
                            "unclassified]",
                        ),
                        places=PLACES.format(**fmt) if meta.get("places") else "",
                        mode=meta.get("mode", "pluvial"),
                        prefer_overbank=meta.get("prefer_overbank", "false"),
                    )
                )
            n += 1
            print("wrote", out)
    print(f"{n} IBF yamls")


if __name__ == "__main__":
    main()
