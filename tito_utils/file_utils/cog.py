"""Cloud Optimized GeoTIFF (COG) output.

Every published raster (FIM probability / likelihood grids, country
mosaics, ensemble summaries) is written as a COG: internally tiled,
DEFLATE compressed, with overviews, so web maps and tools such as QGIS or
kepler.gl can read it straight from its URL (HTTP range requests). A COG
is still a normal GeoTIFF for rasterio / GDAL readers.

COG files cannot be written incrementally, so rasters are either built in
memory and copied (``write_cog``) or written as plain GeoTIFF first and
converted in place (``to_cog``). If a conversion ever fails, the plain
GeoTIFF is kept and a warning printed: a product is never lost over format.
Set TITO_COG=0 to write plain GeoTIFFs.
"""

import os

COG_OPTIONS = {
    "COMPRESS": "DEFLATE",
    "BLOCKSIZE": "512",
    "OVERVIEW_RESAMPLING": "NEAREST",
    "BIGTIFF": "IF_SAFER",
}


def cog_enabled() -> bool:
    return os.environ.get("TITO_COG", "1").strip().lower() not in ("0", "false", "no", "off")


def to_cog(path: str) -> str:
    """Convert an existing GeoTIFF to COG in place (atomic replace)."""
    if not cog_enabled() or not os.path.isfile(path):
        return path
    import rasterio.shutil

    tmp = f"{path}.cog.tmp"
    try:
        rasterio.shutil.copy(path, tmp, driver="COG", **COG_OPTIONS)
        os.replace(tmp, path)
    except Exception as exc:  # keep the plain GeoTIFF rather than lose the product
        print(f"    WARNING: COG conversion failed for {os.path.basename(path)}: {exc}")
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def write_cog(path: str, data, profile: dict) -> str:
    """Write ``data`` (2-D, or 3-D bands-first) with ``profile`` as a COG."""
    import rasterio

    arr = data if data.ndim == 3 else data[None, ...]
    prof = dict(profile)
    prof.update(driver="GTiff", count=arr.shape[0], height=arr.shape[1], width=arr.shape[2])
    for key in ("blockxsize", "blockysize", "tiled", "interleave"):
        prof.pop(key, None)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr)
    return to_cog(path)
