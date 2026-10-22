"""Per-cycle IBF runner.

    python -m tito_utils.ibf_utils.pipeline_ibf --config fim_config/ibf/<region>_ibf.yaml \
        [--cycle 20230621.070000] [--products-dir DIR] [--rebuild-cache]

Steps per cycle:
    1. discover the cycle's probability products (new or legacy naming;
       other-cycle files in the folder are reported, never blended)
    2. build or reuse the receptor cache for the product domain
    3. sample every probability grid onto buildings and roads (max)
    4. classify: risk matrix + IBFv1.0-compatible hazard/IWF fields
    5. write {outputs.root}/{cycle}/ibf_receptors.{cycle}.gpkg
             (buildings_ibf / roads_ibf / admin_ibf, plus places_ibf when
             receptors.places is configured),
             ibf_admin_summary.{cycle}.csv, ibf_summary.{cycle}.json
"""

import json
import os
import sys

from .classify import classify_features, match_severity_layers, summarize_admin
from .config import RISK_LEVELS, load_ibf_config, resolve
from .domain import FimDomain
from .receptors import prepare_receptors, write_gpkg_layers
from .sampling import discover_probability_products, sample_probabilities


def _write_web_layers(out_dir, cycle, layers, log) -> list:
    """Web-friendly copies next to the GeoPackage, in WGS84 (EPSG:4326):
    ``ibf_<layer>.<cycle>.parquet`` (GeoParquet, every layer) and
    ``ibf_admin.<cycle>.geojson`` (small admin layer only; the building
    layers are too large for GeoJSON). GeoParquet needs pyarrow; without
    it the Parquet files are skipped with a note, never the cycle.
    """
    files = []
    try:
        import pyarrow  # noqa: F401

        have_arrow = True
    except ImportError:
        have_arrow = False
        log("    IBF: pyarrow not installed, GeoParquet copies skipped")
    for name, gdf in layers:
        short = name.replace("_ibf", "")
        try:
            wgs = gdf.to_crs(4326) if gdf.crs is not None else gdf
            if have_arrow:
                fn = f"ibf_{short}.{cycle}.parquet"
                wgs.to_parquet(os.path.join(out_dir, fn), index=False)
                files.append(fn)
            if short == "admin":
                fn = f"ibf_admin.{cycle}.geojson"
                path = os.path.join(out_dir, fn)
                if os.path.exists(path):
                    os.remove(path)
                wgs.to_file(path, driver="GeoJSON")
                files.append(fn)
        except Exception as exc:  # web copies must never fail the cycle
            log(f"    IBF: web copy of {name} skipped: {exc}")
    return files


def run_ibf_cycle(
    cfg,
    cycle: str = None,
    products_dir: str = None,
    rebuild_cache: bool = False,
    verbose: bool = True,
) -> dict:
    if isinstance(cfg, str):
        cfg = load_ibf_config(cfg)
    log = print if verbose else (lambda *a, **k: None)

    fp = cfg["fim_products"]
    directory = products_dir or resolve(
        cfg,
        fp["root"].format(cycle=cycle or "", mode=fp["mode"], region=cfg["region"]).rstrip("/\\"),
    )
    layers, skipped, cycle = discover_probability_products(
        directory, cycle=cycle, prefer_overbank=fp["prefer_overbank"]
    )
    if not layers:
        log(f"  IBF {cfg['region']}: no probability products in {directory}")
        return {"region": cfg["region"], "cycle": cycle, "status": "no_products"}
    log(
        f"  IBF {cfg['region']} {cycle}: {len(layers)} probability grids "
        f"({', '.join(lyr.tag for lyr in layers)})"
    )
    for s in skipped:
        log(f"    skipped other-cycle file: {os.path.basename(s.path)} ({s.cycle})")

    domain = FimDomain.from_raster(layers[0].path)
    receptors, manifest_path = prepare_receptors(
        cfg, domain, rebuild=rebuild_cache, verbose=verbose
    )

    sev_layers = match_severity_layers(layers, cfg["classification"], log=log)
    if not sev_layers:
        return {"region": cfg["region"], "cycle": cycle, "status": "no_severity_match"}

    bldgs = sample_probabilities(receptors["buildings"], layers)
    roads = sample_probabilities(receptors["roads"], layers)
    bldgs = classify_features(bldgs, sev_layers, cfg["classification"], layers)
    roads = classify_features(roads, sev_layers, cfg["classification"], layers)
    places = receptors.get("places")
    if places is not None:
        places = sample_probabilities(places, layers)
        places = classify_features(places, sev_layers, cfg["classification"], layers)
    admin = summarize_admin(receptors["admin"], bldgs, roads, cfg, sev_layers, places=places)

    out_root = resolve(cfg, cfg["outputs"]["root"].format(region=cfg["region"]))
    out_dir = os.path.join(out_root, cycle) if cfg["outputs"]["append_cycle"] else out_root
    os.makedirs(out_dir, exist_ok=True)
    gpkg = os.path.join(out_dir, f"ibf_receptors.{cycle}.gpkg")
    out_layers = [("buildings_ibf", bldgs), ("roads_ibf", roads), ("admin_ibf", admin)]
    if places is not None:
        out_layers.append(("places_ibf", places))
    write_gpkg_layers(gpkg, out_layers)
    web_files = _write_web_layers(out_dir, cycle, out_layers, log)
    admin.drop(columns="geometry").to_csv(
        os.path.join(out_dir, f"ibf_admin_summary.{cycle}.csv"), index=False
    )

    def by_risk(df, col="risk_class"):
        return {RISK_LEVELS[r]: int((df[col] == r).sum()) for r in range(4)}

    summary = {
        "region": cfg["region"],
        "cycle": cycle,
        "status": "ok",
        "products_dir": directory,
        "layers": [
            {
                "tag": lyr.tag,
                "threshold_m": lyr.threshold_m,
                "file": os.path.basename(lyr.path),
                "cycle": lyr.cycle,
                "overbank": lyr.overbank,
            }
            for lyr in layers
        ],
        "skipped_other_cycle": [os.path.basename(s.path) for s in skipped],
        "severity_axis": {
            name: {
                "target_m": cfg["classification"]["severity_thresholds_m"][name],
                "layer_tag": lyr.tag,
                "layer_threshold_m": lyr.threshold_m,
            }
            for name, lyr in sev_layers.items()
        },
        "receptor_manifest": manifest_path,
        "buildings_by_risk": by_risk(bldgs),
        "roads_by_risk": by_risk(roads),
        **({"places_by_risk": by_risk(places)} if places is not None else {}),
        "admin_by_risk": by_risk(admin),
        "population_at_yellow_or_worse": float(
            bldgs.loc[bldgs["risk_class"] >= 1, "population_per_building"].sum()
        ),
        "config_echo": {k: cfg[k] for k in ("classification", "fim_products", "outputs")},
        "files": [os.path.basename(gpkg), f"ibf_admin_summary.{cycle}.csv"] + web_files,
    }
    with open(os.path.join(out_dir, f"ibf_summary.{cycle}.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    log(f"    IBF products -> {out_dir}")
    log(f"    buildings by risk: {summary['buildings_by_risk']}")
    return summary


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Run one IBF receptor cycle")
    ap.add_argument("--config", required=True)
    ap.add_argument("--cycle", default=None)
    ap.add_argument("--root", default=None)
    ap.add_argument(
        "--products-dir", default=None, help="explicit folder with the cycle's probability rasters"
    )
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_ibf_config(a.config, root=a.root)
    s = run_ibf_cycle(
        cfg,
        cycle=a.cycle,
        products_dir=a.products_dir,
        rebuild_cache=a.rebuild_cache,
        verbose=not a.quiet,
    )
    return 0 if s.get("status") == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
