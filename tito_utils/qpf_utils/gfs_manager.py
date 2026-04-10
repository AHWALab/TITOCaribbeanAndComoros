import os
import shutil
from datetime import datetime as dt
from datetime import timedelta
from .gfs_downloader import download_GFS
import glob


def _expected_gfs_filenames(start_time, end_time):
    """Return the set of GFS tif basenames expected to cover start_time..end_time.

    GFS files are named gfs.YYYYMMDDHH00.tif (valid hour, one per hour).
    """
    names = set()
    t = start_time.replace(minute=0, second=0, microsecond=0)
    while t <= end_time:
        names.add(f"gfs.{t.strftime('%Y%m%d%H')}00.tif")
        t += timedelta(hours=1)
    return names


def _clear_gfs_data_folder(download_folder):
    """Remove all tif files from the EF5 working gfs_data folder."""
    for f in glob.glob(os.path.join(download_folder, "*.tif")):
        try:
            os.remove(f)
        except Exception:
            pass


def GFS_searcher(path_gfs, qpf_store_path, start_time, end_time, xmin, xmax, ymin, ymax):
    """Populate qpf_store_path/gfs_data/ with GFS tifs covering start_time..end_time.

    Architecture
    ------------
    The background gfs_downloader daemon continuously writes the latest GFS cycle
    files into the shared folder *path_gfs* (e.g. ``qpf_store/GFS/``).
    GFS_searcher is a *read-only consumer* of that folder — it never writes back to it.

    Strategy
    --------
    1. Always clear qpf_store_path/gfs_data/ (stale files from the previous run).
    2. Check path_gfs for all expected hourly tifs (gfs.YYYYMMDDHH00.tif):
       - **All present** → copy to gfs_data/ and return.  No network access.
       - **Any missing** → trigger a one-shot download_GFS directly into gfs_data/.
         The result is NOT archived back to path_gfs; the daemon owns that folder.

    Parameters
    ----------
    path_gfs : str
        Shared folder maintained by the background gfs_downloader daemon.
    qpf_store_path : str
        Per-region EF5 working folder; tifs land in qpf_store_path/gfs_data/.
    start_time, end_time : datetime
        Forecast window to cover.
    xmin, xmax, ymin, ymax : float
        Spatial clipping bbox.
    """
    download_folder = os.path.join(qpf_store_path, "gfs_data/")
    os.makedirs(download_folder, exist_ok=True)
    os.makedirs(path_gfs, exist_ok=True)

    # Step 1: always clear the EF5 working folder before populating it.
    _clear_gfs_data_folder(download_folder)

    # Step 2: check the daemon-maintained shared folder.
    expected = _expected_gfs_filenames(start_time, end_time)
    daemon_files = {os.path.basename(f) for f in glob.glob(os.path.join(path_gfs, "*.tif"))}
    missing = expected - daemon_files

    if not missing:
        print(f"    GFS: all {len(expected)} file(s) found in shared folder — copying to region store.")
        for name in sorted(expected):
            src = os.path.join(path_gfs, name)
            dst = os.path.join(download_folder, name)
            try:
                shutil.copy2(src, dst)
            except Exception as e:
                print(f"    Warning: could not copy GFS file {name}: {e}")
        return

    # Step 3: daemon folder is incomplete — fallback one-shot download.
    print(f"    GFS: {len(missing)} of {len(expected)} file(s) missing from shared folder "
          f"(daemon may not have run yet) — downloading directly.")
    result = download_GFS(start_time, end_time, xmin, xmax, ymin, ymax, download_folder)
    num_written = len(result) if result else 0
    print(f"    GFS: fallback download complete — {num_written} file(s) written.")

    if num_written == 0:
        raise RuntimeError("No GFS data available after downloader fallback attempts.")
        