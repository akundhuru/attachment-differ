# Fuzzing / Robustness Harness (`fuzz/`)

The divergence harness measures *disagreement*; this one hunts *crashes* — the
DoS-class and memory-safety bugs that become responsible-disclosure / CVE
candidates. Separate tool, separate goal.

## Design
- **Seeds:** real documents (GovDocs1). Real files carry structural diversity
  that reaches deep parser code; mutating them beats synthetic junk.
- **Mutators** (`mutate.py`): bitflip, byteset, truncate, chunk-duplicate,
  repeat-insert, 0xFF int-field. Header bytes preserved so input still sniffs as
  the format and reaches real parsing. Deterministic per RNG seed (reproducible).
  Uses `radamsa` automatically if installed.
- **Isolation** (`worker.py`): each extraction runs in a subprocess calling the
  parser library **directly** (not via `extractors/adapters.py`, which swallows
  exceptions), under a wall-clock timeout + best-effort memory/CPU rlimits.
- **Classifier** (`fuzz.py`): distinguishes *bugs* from expected noise —
  | outcome | meaning | bug? |
  |---|---|---|
  | CRASH | process died by signal (segfault/abort) | ✅ memory-safety |
  | HANG | exceeded timeout | ✅ DoS (infinite loop / pathological) |
  | MEMORY | MemoryError / Java OOM / stack overflow | ✅ DoS (allocation) |
  | RECURSION | RecursionError | ✅ DoS (unbounded recursion) |
  | exception | ordinary parse error on corrupt input | ❌ expected |
  | ok | parsed fine | ❌ |
  Bug-class inputs are saved to `results/fuzz/<ts>/findings/` for repro.

Targets: `pypdf`, `pdfminer`, `pymupdf` (native MuPDF — best memory-safety
candidate), `oletools`, and `tika`/`pdfbox` (Java; run under `-Xmx`, real DoS/XXE
CVE history).

## Usage
```bash
source env.sh
python -m fuzz.fuzz --seeds corpus/real/govdocs --corpus-pass          # raw valid files
python -m fuzz.fuzz --seeds corpus/real/govdocs --iters 500            # mutation fuzz (python)
python -m fuzz.fuzz --seeds corpus/real/govdocs --targets pymupdf,tika,pdfbox --iters 5000
```

## Results so far (honest)

Short builtin-mutator runs — **0 bug-class findings**:

| run | runs | exceptions (expected) | ok | bugs |
|---|---|---|---|---|
| corpus-pass (raw, 4 targets) | 168 | 85 | 83 | 0 |
| mutation ×120 (4 targets) | 480 | 284 | 196 | 0 |
| pymupdf ×500 | 500 | 293 | 207 | 0 |

Longer radamsa campaigns (pymupdf/pypdf/pdfminer/oletools ×5000; Tika/PDFBox
×600, run concurrently) flagged **7 "HANG" candidates** (1 pdfminer, 6 Tika).
**On triage all were false positives:** re-run on idle CPU, the pdfminer input
completes in ~15 s and the Tika input in ~34 s (293 KB extracted from a
radamsa-bloated 1.4 MB file). They crossed the timeout only because (a) radamsa's
size-inflating strategies made large documents and (b) both campaigns were
saturating the CPU. Slow-but-*proportionate* — **not** a DoS bug. **Confirmed
CVEs: 0.**

**Methodology lesson (for the paper).** A naive timeout hang-detector yields
false positives from size-inflating mutators + CPU contention. Real DoS bugs show
the opposite signature — *small input, disproportionate time*. A production
campaign should: cap mutated file size (isolate algorithmic complexity from mere
bloat), run one campaign at a time (no contention), use a large per-run timeout to
separate "slow" from "infinite," and record wall-time per run so triage is
automatic. `fuzz.py` now records per-run wall-time and supports `--max-input-kb`.

**Refined campaign (per-target, 256 KB cap, no contention) — 1 strong finding.**
15k MuPDF / 6k pdfminer / 6k pypdf / 4k oletools / 1.5k Tika / 1.5k PDFBox:
- **olefile 0.47 `OleFileIO._list()` unbounded recursion** — 3 independent
  ~71–80 KB PoCs, all the same frame; confirmed infinite (still recurses at a
  20k-frame limit; no guard in latest release). Stack-exhaustion DoS; genuine
  responsible-disclosure candidate. See `DISCLOSURE.md`.
- **pdfminer.six super-linear parse** — 73 KB → ~55 CPU-s (completes). Weaker.
- MuPDF, pypdf, Tika, PDFBox: 0 findings at this depth.

The size cap worked: it converted the earlier false-positive "hangs" into a real
signal (small input, disproportionate cost). Going further still needs a longer
campaign:
- tens of thousands to millions of iterations (run overnight / in CI);
- `radamsa` or coverage-guided mutation (AFL++ via a harness);
- long runs against the native/Java targets specifically;
- then triage + minimize any crashing input and open a 30–90 day disclosure
  thread (per the project plan).

The harness is the missing piece that makes that campaign possible; the campaign
itself is future work, and CVEs remain the plan's *stretch* goal, not a
dependency of the paper's core contributions.
