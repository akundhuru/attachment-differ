"""
Reproducible GovDocs1 corpus fetch + sample (for the scaled NDSS study).

GovDocs1 (Garfinkel et al., DFRWS'09) ships as 1000 "thread" zips named
000.zip .. 999.zip, each ~1000 real U.S. government documents in exactly the
formats the extractors handle. This script downloads the first N threads and
copies every pdf/doc/xls/ppt under a size bound into corpus/real/govdocs/,
so the sampled corpus is a deterministic function of (n_threads, max_mb) —
no hand-picking, fully reproducible from the public source.

    source env.sh
    python corpus/fetch_govdocs.py --threads 12 --max-mb 3

Idempotent / resumable: a thread whose .zip is already present is not
re-downloaded, and files already copied are skipped. corpus/real/govdocs/ is
gitignored; regenerate from this script + the public S3 bucket.

Source bucket (redistributable):
    https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/NNN.zip
"""
from __future__ import annotations
import argparse
import os
import shutil
import sys
import urllib.request
import zipfile

BUCKET = ("https://digitalcorpora.s3.amazonaws.com/corpora/files/"
          "govdocs1/zipfiles/{:03d}.zip")
KEEP_EXTS = (".pdf", ".doc", ".xls", ".ppt")  # the four extractor-relevant formats

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _download(url: str, dest: str) -> None:
    """Stream a zip to dest.part then atomically rename (so an interrupted
    download never looks complete on the next resume)."""
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "govdocs-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    os.replace(tmp, dest)


def fetch(threads: int, max_mb: float, zips_dir: str, out_dir: str,
          start: int = 0) -> tuple[int, int]:
    os.makedirs(zips_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    max_bytes = int(max_mb * 1024 * 1024)
    n_copied = 0
    n_docs_total = 0

    for t in range(start, start + threads):
        url = BUCKET.format(t)
        zpath = os.path.join(zips_dir, f"{t:03d}.zip")
        if not os.path.exists(zpath):
            print(f"[thread {t:03d}] downloading {url}")
            try:
                _download(url, zpath)
            except Exception as e:
                print(f"[thread {t:03d}] download FAILED: {e!r} — skipping")
                continue
        else:
            print(f"[thread {t:03d}] zip already present")

        try:
            zf = zipfile.ZipFile(zpath)
        except zipfile.BadZipFile:
            print(f"[thread {t:03d}] corrupt zip — removing so a rerun refetches")
            os.remove(zpath)
            continue

        copied_here = 0
        with zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = os.path.basename(info.filename)
                if not base.lower().endswith(KEEP_EXTS):
                    continue
                n_docs_total += 1
                if info.file_size > max_bytes:
                    continue
                dest = os.path.join(out_dir, base)
                if os.path.exists(dest):
                    continue
                with zf.open(info) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                copied_here += 1
        n_copied += copied_here
        print(f"[thread {t:03d}] copied {copied_here} docs "
              f"(<= {max_mb} MB) into {os.path.relpath(out_dir, REPO)}")

    return n_copied, n_docs_total


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threads", type=int, default=12,
                    help="number of GovDocs1 thread zips to fetch (default 12)")
    ap.add_argument("--start", type=int, default=0,
                    help="first thread index (default 0)")
    ap.add_argument("--max-mb", type=float, default=3.0,
                    help="size bound per doc, MB (default 3.0)")
    ap.add_argument("--zips-dir", default=os.path.join(HERE, "govdocs_zips"),
                    help="where thread zips are cached (gitignored)")
    ap.add_argument("--out-dir", default=os.path.join(HERE, "real", "govdocs"),
                    help="sampled-corpus output dir")
    args = ap.parse_args(argv)

    copied, total = fetch(args.threads, args.max_mb, args.zips_dir, args.out_dir,
                          start=args.start)
    n_have = sum(1 for f in os.listdir(args.out_dir)
                 if f.lower().endswith(KEEP_EXTS))
    print(f"\n=== fetch complete ===")
    print(f"threads {args.start:03d}..{args.start + args.threads - 1:03d}  "
          f"max {args.max_mb} MB")
    print(f"docs seen: {total}   copied this run: {copied}   "
          f"corpus now holds: {n_have}")
    print(f"next: source env.sh && ./tika_server.sh start && "
          f"OCR_DISABLE=1 python matrix.py {os.path.relpath(args.out_dir, REPO)} --jobs 8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
