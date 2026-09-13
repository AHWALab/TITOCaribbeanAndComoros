"""Unzip every scenario store shipped in this folder tree, once.

Stores travel through git as <name>.zarr.zip inside their country folder
(fim_store/<Region>/). Stores bigger than GitHub's per file comfort zone
are shipped as split parts named <name>.zarr.zip.part01, .part02, ...;
this script joins the parts into the single zip first (once), then
extracts every zip whose matching <name>.zarr folder does not exist yet.

Walks never descend into extracted .zarr trees (those are tens of thousands
of chunk files and stall on NFS). Extraction writes to local temp then
moves into place, which is much faster than unzipping onto /Dedicated.

Usage, from the repository root or from fim_store/:

    python fim_store/unzip_stores.py
    python fim_store/unzip_stores.py Haiti
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _walk_zips(root):
    """Walk zip/part files only; never descend into extracted .zarr trees."""
    skip_sfx = (".zarr", ".partial", ".joining", ".partial.root")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.endswith(skip_sfx)]
        yield dirpath, dirnames, filenames


def _already_extracted(out_dir):
    return os.path.isfile(os.path.join(out_dir, "zarr.json")) or os.path.isfile(
        os.path.join(out_dir, ".zgroup"))


def join_parts(root):
    """<name>.zarr.zip.partNN -> <name>.zarr.zip (kept; parts left in place)."""
    groups = {}
    for dirpath, _dirnames, filenames in _walk_zips(root):
        for fn in filenames:
            m = re.match(r"^(.+\.zarr\.zip)\.part(\d+)$", fn)
            if m:
                groups.setdefault(os.path.join(dirpath, m.group(1)), []).append(
                    (int(m.group(2)), os.path.join(dirpath, fn)))
    for target, parts in sorted(groups.items()):
        parts.sort()
        total = sum(os.path.getsize(p) for _, p in parts)
        if os.path.exists(target) and os.path.getsize(target) == total:
            continue
        nums = [n for n, _ in parts]
        if nums != list(range(1, len(nums) + 1)):
            raise RuntimeError(
                f"missing part for {os.path.basename(target)}: have {nums}")
        print(f"joining {len(parts)} parts -> {os.path.relpath(target, HERE)}",
              flush=True)
        tmp = target + ".joining"
        with open(tmp, "wb") as out:
            for _, p in parts:
                with open(p, "rb") as f:
                    while True:
                        b = f.read(1 << 22)
                        if not b:
                            break
                        out.write(b)
        os.replace(tmp, target)


def extract_zip(zip_path, out_dir):
    print(f"extracting: {os.path.relpath(out_dir, HERE)}", flush=True)
    tmp = tempfile.mkdtemp(prefix="tito_fim_")
    src_is_tmp = False
    try:
        unzip = shutil.which("unzip")
        if unzip:
            subprocess.check_call(
                [unzip, "-qo", zip_path, "-d", tmp],
                stdout=subprocess.DEVNULL)
        else:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(tmp)
        names = [n for n in os.listdir(tmp) if n not in (".", "..")]
        wrapped = (
            len(names) == 1
            and os.path.isdir(os.path.join(tmp, names[0]))
            and names[0] == os.path.basename(out_dir)
        )
        if wrapped:
            src = os.path.join(tmp, names[0])
        else:
            src = tmp
            src_is_tmp = True
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        shutil.move(src, out_dir)
        if src_is_tmp:
            tmp = None
    finally:
        if tmp and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = HERE
    if argv:
        country = argv[0]
        cand = os.path.join(HERE, country)
        if not os.path.isdir(cand):
            raise SystemExit(f"no country folder: {cand}")
        root = cand
        print(f"only: {country}", flush=True)

    join_parts(root)
    done = skipped = 0
    for dirpath, _dirnames, filenames in _walk_zips(root):
        for fn in sorted(filenames):
            if not fn.endswith(".zarr.zip"):
                continue
            zip_path = os.path.join(dirpath, fn)
            out_dir = os.path.join(dirpath, fn[: -len(".zip")])
            rel = os.path.relpath(out_dir, HERE)
            if _already_extracted(out_dir):
                print(f"already extracted: {rel}", flush=True)
                skipped += 1
                continue
            extract_zip(zip_path, out_dir)
            done += 1
    if done == 0 and skipped == 0:
        print("no .zarr.zip stores found under fim_store/; nothing to do")
    else:
        print(f"done: {done} extracted, {skipped} already in place", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
