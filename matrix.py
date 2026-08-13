"""
Batch differential runner — the divergence matrix (D3).

Walks a corpus directory, runs every applicable extractor on every file, and
writes a timestamped run under results/ with:
    per_file.jsonl   one serialized differ report per file (written incrementally)
    summary.json     aggregate divergence-rate statistics (the D3 result)
    pairs.csv        pairwise divergence table

The corpus "group" for each file is its immediate parent directory name
(e.g. mutated/ vs baseline/), so divergence rates break down per mutation
vector automatically.

Scale knobs (added for the thousand-document corpus):
    --jobs N     run N files in parallel (multiprocessing). Tika should be in
                 warm-server mode (TIKA_SERVER_URL) so concurrent workers share
                 one JVM; PDFBox uses per-call temp files and is process-safe;
                 the pure-Python extractors are CPU-bound and parallelize well.
                 Set OCR_DISABLE=1 for a pure extractor-vs-extractor (D3) run.
    --resume DIR resume into an existing run dir, skipping files already present
                 in its per_file.jsonl. The JSONL is flushed per file, so an
                 interrupted multi-hour run restarts where it left off.

Usage:
    source env.sh
    python matrix.py corpus/                              # whole corpus, serial
    OCR_DISABLE=1 python matrix.py corpus/real --jobs 8   # bulk D3 run
    python matrix.py corpus/real --jobs 8 --resume results/runs/20260813-101500
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


# module-level worker so it is picklable for multiprocessing.Pool
def _worker(args):
    path, root, threshold = args
    try:
        rep = run_file(path, threshold=threshold)
        rec = serialize_report(rep, group=_group_of(path, root))
        line = (f"  ran {path}  [{rep['format']}]  "
                f"divergences={len(rep['divergences'])}  errored={rep['errored']}")
        return path, rec, line
    except Exception as e:  # defensive: one bad file must not kill the pool
        return path, {"file": os.path.abspath(path), "error": repr(e)}, \
            f"  ERR {path}: {e!r}"


def _already_done(jsonl_path: str) -> set:
    """Absolute paths already recorded in an existing per_file.jsonl (for resume)."""
    done = set()
    if not os.path.exists(jsonl_path):
        return done
    with open(jsonl_path, "r", encoding="utf-8") as jf:
        for line in jf:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a torn last line from an interrupted run
            f = rec.get("file")
            if f:
                done.add(os.path.abspath(f))
    return done


def _load_records(jsonl_path: str) -> list:
    records = []
    with open(jsonl_path, "r", encoding="utf-8") as jf:
        for line in jf:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def run_corpus(root: str, threshold: float, out_root: str,
               jobs: int = 1, resume_dir: str | None = None) -> dict:
    if resume_dir:
        out_dir = resume_dir
        os.makedirs(out_dir, exist_ok=True)
        stamp = os.path.basename(out_dir.rstrip("/"))
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_dir = os.path.join(out_root, "runs", stamp)
        os.makedirs(out_dir, exist_ok=True)

    jsonl_path = os.path.join(out_dir, "per_file.jsonl")
    done = _already_done(jsonl_path) if resume_dir else set()
    worklist = [(p, root, threshold) for p in _iter_files(root)
                if os.path.abspath(p) not in done]

    if done:
        print(f"resume: {len(done)} files already done, {len(worklist)} remaining")

    n_new = 0
    # append on resume, write fresh otherwise
    mode = "a" if resume_dir else "w"
    with open(jsonl_path, mode, encoding="utf-8") as jf:
        if jobs and jobs > 1 and len(worklist) > 1:
            import multiprocessing as mp
            with mp.Pool(processes=jobs) as pool:
                for _path, rec, line in pool.imap_unordered(_worker, worklist):
                    jf.write(json.dumps(rec) + "\n")
                    jf.flush()
                    n_new += 1
                    print(line)
        else:
            for args in worklist:
                _path, rec, line = _worker(args)
                jf.write(json.dumps(rec) + "\n")
                jf.flush()
                n_new += 1
                print(line)

    # aggregate over ALL records in the JSONL (resumed + new), skipping error rows
    records = [r for r in _load_records(jsonl_path) if "results" in r]
    summary = aggregate(records, threshold=threshold)
    summary["run"] = stamp
    summary["corpus_root"] = os.path.abspath(root)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)
    with open(os.path.join(out_dir, "pairs.csv"), "w", encoding="utf-8") as cf:
        cf.write(pairs_csv(summary))

    _print_summary(summary, out_dir, len(records), n_new)
    return summary


def _print_summary(summary: dict, out_dir: str, n: int, n_new: int = 0) -> None:
    tag = f"{n} files" + (f", {n_new} this pass" if n_new != n else "")
    print(f"\n=== run summary  ({tag}) ===")
    print(f"overall divergence rate: {summary['overall_divergence_rate']:.2%}"
          f"  [95% CI {summary.get('overall_ci_low', 0):.2%}"
          f"-{summary.get('overall_ci_high', 0):.2%}]"
          f"  ({summary['total_divergent_comparisons']}/"
          f"{summary['total_pair_comparisons']} pair comparisons)")

    print("\npairwise divergence rate  [95% CI]:")
    for p in summary["pairs"]:
        print(f"  {p['pair']:24} {p['divergence_rate']:6.2%}"
              f"  [{p.get('ci_low', 0):.2%}-{p.get('ci_high', 0):.2%}]"
              f"  ({p['divergent']}/{p['comparable']})")

    print("\nextractor blind-spot rate (empty/error while another recovered text):")
    for e in summary["extractors"]:
        print(f"  {e['extractor']:11} blind {e['blind_rate']:6.2%}"
              f"  (ok={e['ok']} err={e['error']} empty={e['empty']} /{e['applicable']})")

    print("\nby format (files with any divergence)  [95% CI]:")
    for f in summary.get("by_format", []):
        print(f"  {f['format']:6} files={f['files']:4}"
              f"  with-divergence {f['rate']:6.2%}"
              f"  [{f.get('ci_low', 0):.2%}-{f.get('ci_high', 0):.2%}]")

    print("\nby format x pair (pair-comparison divergence rate)  [95% CI]:")
    for fp in summary.get("by_format_pair", []):
        print(f"  {fp['format']:5} {fp['pair']:22} {fp['divergence_rate']:6.2%}"
              f"  [{fp.get('ci_low', 0):.2%}-{fp.get('ci_high', 0):.2%}]"
              f"  ({fp['divergent']}/{fp['comparable']})")

    print("\nby corpus group:")
    for g in summary["by_group"]:
        print(f"  {g['group']:18} files={g['files']:3}"
              f"  with-divergence {g['rate']:6.2%}")

    print(f"\nwrote: {out_dir}/  (per_file.jsonl, summary.json, pairs.csv)")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python matrix.py <corpus-dir> "
              "[--threshold F] [--out DIR] [--jobs N] [--resume RUN_DIR]")
        return 1
    root = argv[0]
    threshold = 0.95
    out_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    jobs = 1
    resume_dir = None
    if "--threshold" in argv:
        threshold = float(argv[argv.index("--threshold") + 1])
    if "--out" in argv:
        out_root = argv[argv.index("--out") + 1]
    if "--jobs" in argv:
        jobs = int(argv[argv.index("--jobs") + 1])
    if "--resume" in argv:
        resume_dir = argv[argv.index("--resume") + 1]
    if not os.path.exists(root):
        print(f"no such path: {root}")
        return 1
    run_corpus(root, threshold, out_root, jobs=jobs, resume_dir=resume_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
