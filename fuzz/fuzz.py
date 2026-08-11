"""
Fuzzing / robustness harness — hunts DoS-class and native-crash bugs in the
document parsers, the input this project needs to turn "CVE upside" into real
responsible-disclosure candidates.

Two modes:
  --corpus-pass   run every target on the RAW seed files (catches parsers that
                  choke on valid real-world documents — rare but cheap to check)
  (default)       mutation fuzz: pick a seed, mutate it, run every target under
                  a wall-clock timeout + best-effort memory/CPU cap, classify.

Outcomes that are BUGS (saved to results/fuzz/<ts>/findings/):
  CRASH   parser process died by signal (segfault/abort) — memory-safety class
  HANG    exceeded the timeout — denial-of-service (infinite loop / pathological)
  MEMORY  MemoryError / OOM — denial-of-service (allocation blowup)
  RECURSION  RecursionError — unbounded recursion (stack DoS)
Ordinary parse exceptions (ValueError, PdfError, ...) on corrupted input are
EXPECTED and just counted, not saved.

    source env.sh
    python -m fuzz.fuzz --seeds corpus/real/govdocs --iters 500
    python -m fuzz.fuzz --seeds corpus/real/govdocs --corpus-pass

Java targets (tika, pdfbox) run under -Xmx and the same timeout when their jars
are configured (TIKA_JAR / PDFBOX_JAR).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fuzz.mutate import mutate, radamsa_available, radamsa_mutate  # noqa: E402

PY_TARGETS = ["pypdf", "pdfminer", "pymupdf", "oletools"]
BUG_STATUSES = {"CRASH", "HANG", "MEMORY", "RECURSION"}


def _run_python_target(target: str, path: str, timeout: int,
                       mem_mb: int, cpu_sec: int) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "fuzz.worker", target, path, str(mem_mb), str(cpu_sec)],
            capture_output=True, text=True, timeout=timeout, cwd=ROOT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "HANG"}
    if proc.returncode < 0:
        return {"status": "CRASH", "signal": -proc.returncode}
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        return {"status": "CRASH", "signal": proc.returncode,
                "stderr": proc.stderr[-200:]}
    st = out.get("status")
    if st == "memory":
        return {"status": "MEMORY", "exc": out.get("exc")}
    if st == "recursion":
        return {"status": "RECURSION", "exc": out.get("exc")}
    if st == "exception":
        return {"status": "exception", "exc": out.get("exc")}   # expected noise
    return {"status": "ok", "text_len": out.get("text_len", 0)}


def _run_java_target(target: str, path: str, timeout: int, mem_mb: int) -> dict:
    jar = os.environ.get("TIKA_JAR" if target == "tika" else "PDFBOX_JAR")
    java = shutil.which("java")
    if not (jar and java):
        return {"status": "skip"}
    if target == "tika":
        cmd = [java, f"-Xmx{mem_mb}m", "-jar", jar, "--text", path]
    else:
        out = path + ".out.txt"
        cmd = [java, f"-Xmx{mem_mb}m", "-jar", jar, "export:text", "-i", path, "-o", out]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "HANG"}
    finally:
        if target == "pdfbox":
            try:
                os.remove(path + ".out.txt")
            except OSError:
                pass
    err = (proc.stderr or "")
    if "OutOfMemoryError" in err or "StackOverflowError" in err:
        return {"status": "MEMORY", "exc": err[-160:]}
    if proc.returncode not in (0, 1):   # 1 = ordinary parse failure for these tools
        return {"status": "CRASH", "signal": proc.returncode, "stderr": err[-200:]}
    return {"status": "ok"}


def run_target(target: str, path: str, timeout: int, mem_mb: int, cpu_sec: int) -> dict:
    if target in ("tika", "pdfbox"):
        return _run_java_target(target, path, timeout, mem_mb)
    return _run_python_target(target, path, timeout, mem_mb, cpu_sec)


def _seed_files(seeds: str) -> list[str]:
    if os.path.isfile(seeds):
        return [seeds]
    out = []
    for dp, _d, fs in os.walk(seeds):
        for f in fs:
            out.append(os.path.join(dp, f))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--targets", default=",".join(PY_TARGETS))
    ap.add_argument("--timeout", type=int, default=15, help="wall-clock seconds/run")
    ap.add_argument("--mem-mb", type=int, default=1024)
    ap.add_argument("--cpu-sec", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1337, help="RNG seed (reproducible)")
    ap.add_argument("--max-input-kb", type=int, default=0,
                    help="truncate mutated inputs to this size (0=off); isolates "
                         "algorithmic-complexity hangs from mere file bloat")
    ap.add_argument("--corpus-pass", action="store_true",
                    help="run raw seed files (no mutation)")
    args = ap.parse_args(argv)

    if os.environ.get("TIKA_JAR"):
        pass  # java targets opt-in via --targets
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    seeds = _seed_files(args.seeds)
    if not seeds:
        print(f"no seed files under {args.seeds}")
        return 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(ROOT, "results", "fuzz", stamp)
    find_dir = os.path.join(out_dir, "findings")
    os.makedirs(find_dir, exist_ok=True)
    rng = random.Random(args.seed)
    use_radamsa = radamsa_available()

    counts: dict[str, int] = {}
    findings = []
    tmp = os.path.join(out_dir, "_cur")

    def record(target, seed_path, strat, res):
        st = res["status"]
        counts[st] = counts.get(st, 0) + 1
        if st in BUG_STATUSES:
            ext = os.path.splitext(seed_path)[1] or ".bin"
            h = hashlib.sha1(open(tmp, "rb").read()).hexdigest()[:12]
            saved = os.path.join(find_dir, f"{target}_{st}_{h}{ext}")
            shutil.copy(tmp, saved)
            rec = {"target": target, "status": st, "strategy": strat,
                   "seed": os.path.basename(seed_path), "input": os.path.basename(saved),
                   **{k: v for k, v in res.items() if k != "status"}}
            findings.append(rec)
            print(f"  !! {st:9} {target:9} strat={strat:9} -> findings/{os.path.basename(saved)}")

    n_runs = 0
    label = "corpus-pass" if args.corpus_pass else f"mutation x{args.iters}"
    print(f"fuzzing: targets={targets} seeds={len(seeds)} mode={label} "
          f"mutator={'radamsa' if use_radamsa else 'builtin'} timeout={args.timeout}s")

    iters = seeds if args.corpus_pass else range(args.iters)
    for it in iters:
        if args.corpus_pass:
            try:
                with open(it, "rb") as s:
                    data = s.read()
            except OSError:
                continue
            with open(tmp, "wb") as d:
                d.write(data)
            seed_path, strat = it, "raw"
        else:
            seed_path = rng.choice(seeds)
            try:
                data = open(seed_path, "rb").read()
            except OSError:
                continue
            if use_radamsa:
                strat = radamsa_mutate(seed_path, tmp, rng)
            else:
                mutated, strat = mutate(data, rng)
                with open(tmp, "wb") as fh:
                    fh.write(mutated)
        # cap input size so a HANG means disproportionate time, not a huge file
        if args.max_input_kb and os.path.getsize(tmp) > args.max_input_kb * 1024:
            with open(tmp, "r+b") as fh:
                fh.truncate(args.max_input_kb * 1024)
        in_kb = os.path.getsize(tmp) // 1024
        for target in targets:
            t0 = time.time()
            res = run_target(target, tmp, args.timeout, args.mem_mb, args.cpu_sec)
            res["elapsed_s"] = round(time.time() - t0, 2)
            res["input_kb"] = in_kb
            if res.get("status") == "skip":
                continue
            n_runs += 1
            record(target, seed_path, strat, res)

    if os.path.exists(tmp):
        os.remove(tmp)

    summary = {"runs": n_runs, "counts": counts, "n_findings": len(findings),
               "findings": findings, "mutator": "radamsa" if use_radamsa else "builtin",
               "targets": targets, "mode": label, "rng_seed": args.seed}
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== fuzz summary ({n_runs} runs) ===")
    for st in sorted(counts):
        tag = "  <-- BUG" if st in BUG_STATUSES else ""
        print(f"  {st:10} {counts[st]}{tag}")
    print(f"bug-class findings: {len(findings)}  (saved inputs in {find_dir}/)")
    if not findings:
        print("no crashes/hangs/OOM this run — expected for mature parsers; "
              "raise --iters or add radamsa for deeper search.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
