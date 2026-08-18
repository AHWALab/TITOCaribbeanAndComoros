"""Unzip every scenario store shipped in this folder tree, once.

Stores travel through git as <name>.zarr.zip inside their country folder
(fim_store/<Region>/). This script walks the tree and extracts every zip
whose matching <name>.zarr folder does not exist yet. Already extracted
stores are skipped, so the script is safe to run any number of times.

Usage, from the repository root or from fim_store/:

    python fim_store/unzip_stores.py
"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    done = skipped = 0
    for dirpath, _dirnames, filenames in os.walk(HERE):
        for fn in sorted(filenames):
            if not fn.endswith(".zarr.zip"):
                continue
            zip_path = os.path.join(dirpath, fn)
            out_dir = os.path.join(dirpath, fn[: -len(".zip")])
            rel = os.path.relpath(out_dir, HERE)
            if os.path.isdir(out_dir) and os.listdir(out_dir):
                print(f"already extracted: {rel}")
                skipped += 1
                continue
            print(f"extracting: {rel}")
            with zipfile.ZipFile(zip_path) as z:
                for member in z.namelist():
                    # refuse entries that would land outside the target dir
                    target = os.path.realpath(os.path.join(out_dir, member))
                    if not target.startswith(os.path.realpath(out_dir) + os.sep) \
                            and target != os.path.realpath(out_dir):
                        raise RuntimeError(
                            f"unsafe path inside {fn}: {member}")
                # extract to a partial folder first, then rename, so an
                # interrupted run never leaves a half store that later runs
                # would skip as "already extracted"
                partial = out_dir + ".partial"
                if os.path.isdir(partial):
                    import shutil
                    shutil.rmtree(partial)
                z.extractall(partial)
                os.rename(partial, out_dir)
            done += 1
    if done == 0 and skipped == 0:
        print("no .zarr.zip stores found under fim_store/; nothing to do")
    else:
        print(f"done: {done} extracted, {skipped} already in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
