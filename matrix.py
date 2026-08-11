"""
Batch differential runner — the Week 5-6 divergence matrix.

Walks a corpus directory, runs every applicable extractor on every file, and
writes a timestamped run under results/ with:
    per_file.jsonl   one serialized differ report per file
    summary.json     aggregate divergence-rate statistics (the D3 result)
    pairs.csv        pairwise divergence table

The corpus "group" for each file is its immediate parent directory name
(e.g. mutated/ vs baseline/), so divergence rates break down per mutation
vector automatically.

Usage:
    source env.sh
    python matrix.py corpus/            # whole corpus
    python matrix.py corpus/mutated --threshold 0.9
"""
from __future__ import annotations
import json
import os
import sys
import time

from differ import run_file
from report import serialize_report, aggregate, pairs_csv

EXTS = (".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".ole", ".msg")


def _iter_files(root: str):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.lower().endswith(EXTS):
                yield os.path.join(dirpath, f)


def _group_of(path: str, root: str) -> str:
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    root_base = os.path.basename(os.path.abspath(root.rstrip("/")))
    return "" if parent == root_base else parent


def run_corpus(root: str, threshold: float, out_root: str) -> dict:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(out_root, "runs", stamp)
    os.makedirs(out_dir, exist_ok=True)

    records = []
    jsonl_path = os.path.join(out_dir, "per_file.jsonl")
    n = 0
    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for path in _iter_files(root):
            rep = run_file(path, threshold=threshold)
            rec = serialize_report(rep, group=_group_of(path, root))
            records.append(rec)
            jf.write(json.dumps(rec) + "\n")
            n += 1
            print(f"  ran {path}  "
                  f"[{rep['format']}]  divergences={len(rep['divergences'])}"
                  f"  errored={rep['errored']}")

    summary = aggregate(records, threshold=threshold)
    summary["run"] = stamp
    summary["corpus_root"] = os.path.abspath(root)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)
    with open(os.path.join(out_dir, "pairs.csv"), "w", encoding="utf-8") as cf:
        cf.write(pairs_csv(summary))

    _print_summary(summary, out_dir, n)
    return summary


def _print_summary(summary: dict, out_dir: str, n: int) -> None:
    print(f"\n=== run summary  ({n} files) ===")
    print(f"overall divergence rate: {summary['overall_divergence_rate']:.2%}"
          f"  ({summary['total_divergent_comparisons']}/"
          f"{summary['total_pair_comparisons']} pair comparisons)")

    print("\npairwise divergence rate:")
    for p in summary["pairs"]:
        print(f"  {p['pair']:24} {p['divergence_rate']:6.2%}"
              f"  ({p['divergent']}/{p['comparable']})")

    print("\nextractor blind-spot rate (empty/error while another recovered text):")
    for e in summary["extractors"]:
        print(f"  {e['extractor']:11} blind {e['blind_rate']:6.2%}"
              f"  (ok={e['ok']} err={e['error']} empty={e['empty']} /{e['applicable']})")

    print("\nby corpus group:")
    for g in summary["by_group"]:
        print(f"  {g['group']:18} files={g['files']:3}"
              f"  with-divergence {g['rate']:6.2%}")

    print(f"\nwrote: {out_dir}/  (per_file.jsonl, summary.json, pairs.csv)")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python matrix.py <corpus-dir> [--threshold F] [--out DIR]")
        return 1
    root = argv[0]
    threshold = 0.95
    out_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    if "--threshold" in argv:
        threshold = float(argv[argv.index("--threshold") + 1])
    if "--out" in argv:
        out_root = argv[argv.index("--out") + 1]
    if not os.path.exists(root):
        print(f"no such path: {root}")
        return 1
    run_corpus(root, threshold, out_root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
