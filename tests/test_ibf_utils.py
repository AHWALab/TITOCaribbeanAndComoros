"""Tests for tito_utils.ibf_utils (receptor IBF layer).

Geo deps (geopandas/pyogrio) are optional in some CI environments, so
every test that needs them importorskips.
"""

import os

import numpy as np
import pytest

from tito_utils.ibf_utils.classify import likelihood_index
from tito_utils.ibf_utils.config import DEFAULT_MATRIX
from tito_utils.ibf_utils.sampling import _tag_from_meters, parse_probability_filename

BANDS = {"very_low": [0.0, 0.2], "low": [0.2, 0.4], "medium": [0.4, 0.6], "high": [0.6, 1.01]}


# ---------------------------------------------------------------- filenames
def test_parse_new_naming():
    lyr = parse_probability_filename("prob_depth_ge_30cm.20230621.070000.tif")
    assert lyr.threshold_m == pytest.approx(0.30)
    assert lyr.tag == "30cm"
    assert lyr.cycle == "20230621.070000"
    assert not lyr.overbank


def test_parse_new_naming_overbank_and_p_tag():
    lyr = parse_probability_filename("prob_depth_ge_7p62cm_overbank.20230620.000000.tif")
    assert lyr.threshold_m == pytest.approx(0.0762)
    assert lyr.overbank


def test_parse_legacy_qpeprob_units_not_mislabelled():
    """Regression for the IBFv1.0 defect: the 0.1524 m (6 in) grid was
    treated as the 7.62 cm layer. The parser must label it 15.24 cm."""
    lyr = parse_probability_filename("qpeprob.20230621.070000.0.1524 meters.tif")
    assert lyr.threshold_m == pytest.approx(0.1524)
    assert lyr.tag == "15p24cm"
    assert lyr.tag != "7p62cm"
    assert parse_probability_filename("qpeprob.20230621.070000.0.3048 meters.tif").tag == "30p48cm"


def test_parse_rejects_other_files():
    assert parse_probability_filename("maxunitq.20230621.070000.tif") is None


def test_tag_roundtrip():
    assert _tag_from_meters(0.10) == "10cm"
    assert _tag_from_meters(0.76) == "76cm"
    assert _tag_from_meters(0.6096) == "60p96cm"


def test_discovery_reports_mixed_cycles(tmp_path):
    from tito_utils.ibf_utils.sampling import discover_probability_products

    for name in [
        "prob_depth_ge_10cm.20230621.070000.tif",
        "prob_depth_ge_30cm.20230621.070000.tif",
        "prob_depth_ge_76cm.20230620.000000.tif",
    ]:
        (tmp_path / name).write_bytes(b"")
    layers, skipped, cycle = discover_probability_products(str(tmp_path))
    assert cycle == "20230621.070000"
    assert [lyr.tag for lyr in layers] == ["10cm", "30cm"]
    assert [s.cycle for s in skipped] == ["20230620.000000"]


# ---------------------------------------------------------------- matrix
def test_likelihood_bands_edges():
    assert likelihood_index(0.0, BANDS, 0.05) == -1  # no signal
    assert likelihood_index(0.04, BANDS, 0.05) == -1  # below reporting
    assert likelihood_index(0.1, BANDS, 0.05) == 0  # very low
    assert likelihood_index(0.2, BANDS, 0.05) == 1  # boundary -> upper
    assert likelihood_index(0.5, BANDS, 0.05) == 2
    assert likelihood_index(1.0, BANDS, 0.05) == 3


def test_matrix_invariants():
    for row in DEFAULT_MATRIX:
        assert row[0] == 0  # minimal is green
    assert DEFAULT_MATRIX[3][3] == 3  # High x Severe = red
    assert DEFAULT_MATRIX[0][3] == 1  # VL x Severe = yellow
    assert DEFAULT_MATRIX[1][3] == 2  # Low x Severe = amber


# ---------------------------------------------------------------- end to end
@pytest.fixture()
def synthetic_region(tmp_path):
    gpd = pytest.importorskip("geopandas")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import LineString, box

    crs = "EPSG:32615"
    try:
        rasterio.crs.CRS.from_user_input(crs)
    except Exception:  # pragma: no cover - GDAL/PROJ data missing in this env
        pytest.skip("rasterio/GDAL cannot parse EPSG:32615 (PROJ data issue)")
    transform = from_origin(500000, 1600100, 5, 5)  # 20x20 at 5 m

    def write(name, arr):
        path = tmp_path / name
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=20,
            width=20,
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(arr.astype("float32"), 1)
        return str(path)

    p10 = np.zeros((20, 20))
    p10[5:15, 5:15] = 0.7  # High for minor
    p30 = np.zeros((20, 20))
    p30[8:12, 8:12] = 0.5  # Medium for signif
    p76 = np.zeros((20, 20))
    p76[9:11, 9:11] = 0.3  # Low for severe
    write("prob_depth_ge_10cm.20230621.070000.tif", p10)
    write("prob_depth_ge_30cm.20230621.070000.tif", p30)
    write("prob_depth_ge_76cm.20230621.070000.tif", p76)

    lu = np.ones((20, 20)) * 1  # all residential
    write("landuse.tif", lu)

    # receptors: one building in the deep core, one on the fringe, one dry
    b = gpd.GeoDataFrame(
        {"id": ["core", "fringe", "dry"], "subtype": ["residential", None, "medical"]},
        geometry=[
            box(500047, 1600047, 500053, 1600053),  # rows ~9-10
            box(500030, 1600030, 500036, 1600036),
            box(500002, 1600002, 500008, 1600008),
        ],
        crs=crs,
    )
    r = gpd.GeoDataFrame(
        {"id": ["r1"], "class": ["primary"], "subtype": ["road"]},
        geometry=[LineString([(500000, 1600050), (500100, 1600050)])],
        crs=crs,
    )
    a = gpd.GeoDataFrame(
        {"CODIGO": [1], "MUNICIPIO": ["Test"], "POB": [1000.0]},
        geometry=[box(499900, 1599900, 500200, 1600200)],
        crs=crs,
    )

    nat = tmp_path / "national.gpkg"
    b.to_file(nat, layer="buildings", driver="GPKG")
    r.to_file(nat, layer="roads", driver="GPKG")
    adm = tmp_path / "admin.gpkg"
    a.to_file(adm, layer="admin", driver="GPKG")

    cfg = {
        "_root": str(tmp_path),
        "region": "TestRegion",
        "receptors": {
            "buildings": {
                "source": str(nat),
                "layer": "buildings",
                "id_field": "id",
                "subtype_field": "subtype",
            },
            "roads": {
                "source": str(nat),
                "layer": "roads",
                "id_field": "id",
                "class_field": "class",
                "keep_classes": [],
            },
            "admin": {
                "source": str(adm),
                "layer": "admin",
                "id_field": "CODIGO",
                "name_field": "MUNICIPIO",
                "population_field": "POB",
            },
            "land_use": {"source": str(tmp_path / "landuse.tif")},
            "land_class_weights": {0: 0.1, 1: 0.9, 2: 0.0},
            "subtype_weights": {"residential": 1.0},
            "critical_subtypes": ["medical"],
            "domain_buffer_m": 20.0,
            "cache_dir": str(tmp_path / "cache"),
            "work_crs": crs,
        },
        "fim_products": {
            "root": str(tmp_path),
            "mode": "combined",
            "prefer_overbank": False,
            "patterns": [],
        },
        "classification": {
            "likelihood_bands": {k: list(v) for k, v in BANDS.items()},
            "reporting_threshold": 0.05,
            "severity_thresholds_m": {"minor": 0.10, "significant": 0.30, "severe": 0.76},
            "severity_match_tolerance": 0.6,
            "matrix": [list(r_) for r_ in DEFAULT_MATRIX],
            "hazard_flag_cutoff": 0.3,
            "iwf": {
                "IWF_Pop": {
                    "suffix": "total_pop",
                    "severe": {"absolute": 10, "percentage": 0.05},
                    "lmh": {"absolute": 100, "percentage": 0.10},
                }
            },
        },
        "outputs": {"root": str(tmp_path / "out"), "append_cycle": True},
        "cycle_format": "%Y%m%d.%H%M%S",
    }
    return cfg


def test_end_to_end_cycle(synthetic_region):
    pytest.importorskip("geopandas")
    from tito_utils.ibf_utils.pipeline_ibf import run_ibf_cycle

    s = run_ibf_cycle(synthetic_region, products_dir=synthetic_region["_root"], verbose=False)
    assert s["status"] == "ok"
    assert s["cycle"] == "20230621.070000"
    assert [lyr["tag"] for lyr in s["layers"]] == ["10cm", "30cm", "76cm"]

    import geopandas as gpd

    out = os.path.join(
        synthetic_region["outputs"]["root"], "20230621.070000", "ibf_receptors.20230621.070000.gpkg"
    )
    b = gpd.read_file(out, layer="buildings_ibf")
    core = b.set_index("feature_id").loc["core"]
    fringe = b.set_index("feature_id").loc["fringe"]
    dry = b.set_index("feature_id").loc["dry"]

    # core: minor@High=yellow, significant@Medium=amber, severe@Low=amber
    assert core["risk_level"] == "MEDIUM"
    assert core["hazard_flag"] == 3  # p76 = 0.3 >= cutoff
    # fringe: only minor axis (p10=0.7 High) -> yellow
    assert fringe["risk_level"] == "LOW"
    # dry building: green, critical tag preserved
    assert dry["risk_level"] == "VERY LOW"
    assert bool(dry["critical"]) is True

    # population conserved (single admin unit holds all of it)
    assert b["population_per_building"].sum() == pytest.approx(1000.0)
    # dasymetric weights: fringe has no subtype -> land-class weight path
    assert 0 < fringe["population_per_building"] < 1000

    a = gpd.read_file(out, layer="admin_ibf")
    assert a.iloc[0]["risk_class"] == 2  # worst feature cell
    assert a.iloc[0]["IWF_Pop"] >= 1
    r = gpd.read_file(out, layer="roads_ibf")
    assert r.iloc[0]["risk_class"] >= 1  # road crosses the core


def test_receptor_cache_reused(synthetic_region):
    pytest.importorskip("geopandas")
    from tito_utils.ibf_utils import receptors as rmod
    from tito_utils.ibf_utils.pipeline_ibf import run_ibf_cycle

    run_ibf_cycle(synthetic_region, products_dir=synthetic_region["_root"], verbose=False)
    calls = {"n": 0}
    original = rmod._read_clip

    def counting(*a, **k):
        calls["n"] += 1
        return original(*a, **k)

    rmod._read_clip = counting
    try:
        s = run_ibf_cycle(synthetic_region, products_dir=synthetic_region["_root"], verbose=False)
    finally:
        rmod._read_clip = original
    assert s["status"] == "ok"
    assert calls["n"] == 0  # cache hit, no re-read


def test_places_optional_layer(synthetic_region, tmp_path):
    """IBFv1.0 v10 places: sampled and classified like the other receptors,
    counted per admin unit (baseline + per hazard class)."""
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    from tito_utils.ibf_utils.pipeline_ibf import run_ibf_cycle

    crs = synthetic_region["receptors"]["work_crs"]
    p = gpd.GeoDataFrame(
        {"id": ["clinic", "shop"], "name": ["Clinic", "Shop"], "category": ["health", "retail"]},
        geometry=[Point(500050, 1600050), Point(500005, 1600005)],  # core, dry
        crs=crs,
    )
    src = tmp_path / "places.gpkg"
    p.to_file(src, layer="places", driver="GPKG")
    synthetic_region["receptors"]["places"] = {
        "source": str(src),
        "layer": "places",
        "id_field": "id",
        "name_field": "name",
        "category_field": "category",
    }

    s = run_ibf_cycle(synthetic_region, products_dir=synthetic_region["_root"], verbose=False)
    assert s["status"] == "ok"
    assert sum(s["places_by_risk"].values()) == 2

    out = os.path.join(
        synthetic_region["outputs"]["root"], "20230621.070000", "ibf_receptors.20230621.070000.gpkg"
    )
    pl = gpd.read_file(out, layer="places_ibf").set_index("feature_id")
    assert pl.loc["clinic", "risk_level"] == "MEDIUM"
    assert pl.loc["clinic", "place_category"] == "health"
    assert pl.loc["shop", "risk_level"] == "VERY LOW"
    a = gpd.read_file(out, layer="admin_ibf").iloc[0]
    assert a["places_count"] == 2
    assert a["hzrd_3_places_count"] == 1  # clinic: p76 = 0.3 >= cutoff


def test_vectorized_sampler_matches_reference_loop(tmp_path):
    """_reduce_many must pick exactly the cells of the per-geometry
    rasterize loop, including GDAL's boundary rules for lines lying on cell
    edges and for edge-aligned and sub-cell polygons.

    Known, accepted difference: a line passing EXACTLY through a cell corner,
    or a segment ending EXACTLY on a cell edge, is walked by GDAL's own
    line algorithm with special cases not reproduced here. Real receptor
    coordinates (reprojected floats) never land on grid lines; 2,000 real
    Haiti roads on the 2 m grid agreed 100 %."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import LineString, MultiLineString, Point, box

    from tito_utils.ibf_utils.sampling import _InMemoryRaster, _reduce_many

    rng = np.random.default_rng(0)
    data = rng.integers(0, 4, (20, 20)).astype("float32")
    data[3, 3] = np.nan
    path = tmp_path / "grid.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=20, width=20, count=1, dtype="float32",
        crs="EPSG:32615", transform=from_origin(0, 100, 5, 5), nodata=np.nan,
    ) as dst:  # fmt: skip
        dst.write(data, 1)
    ras = _InMemoryRaster(str(path))
    geoms = [
        LineString([(0, 50), (100, 50)]),  # on a horizontal cell edge
        LineString([(50, 0), (50, 100)]),  # on a vertical cell edge
        LineString([(0.3, 0.7), (99.1, 98.2)]),
        LineString([(3, 97), (61, 12), (88, 40)]),
        MultiLineString([[(10.2, 10.1), (30.4, 11.3)], [(60.3, 60.6), (61.2, 90.4)]]),
        box(20, 20, 40, 40),  # edge aligned
        box(21, 21, 22, 22),  # sub-cell, no centre: retry
        box(-10, -10, 7, 7),  # partly outside
        box(200, 200, 210, 210),  # fully outside
        box(12, 12, 18.9, 18.9),
        Point(12.5, 87.5),
        Point(15, 85),  # on a cell corner
    ]
    for op in ("max", "mode"):
        for touched in (True, False):
            t = np.full(len(geoms), touched)
            ref = np.array([ras.reduce(g, op, touched) for g in geoms])
            got = _reduce_many(ras, np.array(geoms, dtype=object), op, t)
            np.testing.assert_array_equal(np.isnan(ref), np.isnan(got), err_msg=f"{op} {touched}")
            ok = ~np.isnan(ref)
            np.testing.assert_allclose(got[ok], ref[ok], err_msg=f"{op} touched={touched}")


def test_web_copies_geojson_and_geoparquet(synthetic_region):
    """Next to the GeoPackage: admin GeoJSON always, GeoParquet per layer when
    pyarrow is installed; both in WGS84 for web tools."""
    gpd = pytest.importorskip("geopandas")
    from tito_utils.ibf_utils.pipeline_ibf import run_ibf_cycle

    s = run_ibf_cycle(synthetic_region, products_dir=synthetic_region["_root"], verbose=False)
    out = os.path.join(synthetic_region["outputs"]["root"], "20230621.070000")
    gj = os.path.join(out, "ibf_admin.20230621.070000.geojson")
    assert os.path.basename(gj) in s["files"]
    admin = gpd.read_file(gj)
    assert admin.crs.to_epsg() == 4326 and len(admin) == 1 and "risk_class" in admin.columns
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow not installed: GeoParquet copies are skipped by design")
    for layer in ("buildings", "roads", "admin"):
        pq = os.path.join(out, f"ibf_{layer}.20230621.070000.parquet")
        assert os.path.basename(pq) in s["files"]
        df = gpd.read_parquet(pq)
        assert df.crs.to_epsg() == 4326 and len(df) > 0
