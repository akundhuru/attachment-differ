# attachment-differ

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21894923.svg)](https://doi.org/10.5281/zenodo.21894923)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A differential-testing harness for content extraction in email-attachment
security pipelines. It measures where multiple production extractors (Apache
Tika, PDFBox, pypdf, pdfminer, oletools) **diverge on the same attachment**, and
where their output diverges from what a human actually sees (render + OCR).

**Thesis.** A detector does not score an attachment's bytes — it scores the text
an *extractor* pulled out of it. Different extractors make different, individually
spec-compliant choices, so "the content of this attachment" is a function of which
extractor you ask. An attacker who knows (or probes) the pipeline picks the
extractor that reads benign while the victim reads a lure.

## Contributions

- **Measurement (D3)** — cross-extractor divergence rates across formats and
  vectors, plus an OCR "what the human sees" oracle. On real documents,
  extractors diverge on **46%** of attachment-pair comparisons.
- **Attack (D4)** — which divergences flip a modern content detector. Two
  independent detectors (a deterministic heuristic and Claude) both flip
  malicious→benign on **32%** of extractor pairs for image-masking vectors.
- **Defense-gap (D5)** — a faithful re-implementation of *PDF Mirage*'s
  (USENIX '17) OCR font-verification defense, shown to catch only the font vector
  it was designed for and **miss all five** non-font vectors.

See **[RESULTS.md](RESULTS.md)** for the numbers and **[PAPER.md](PAPER.md)** for
the write-up.

## Quickstart

```bash
bash reproduce.sh        # venv + tests + D3/D4/D5 end-to-end
```

Or step by step:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # pure-Python extractor stack

python differ.py corpus/<file>.pdf     # one file, all available extractors
```

**Optional native backends** (the harness self-disables what's missing):
- OCR oracle → the `tesseract` binary (`brew install tesseract`).
- Tika / PDFBox → a JRE + the app jars; set `TIKA_JAR` / `PDFBOX_JAR` (see
  `env.sh`), then `source env.sh` before a run.
- LLM detector → `export ANTHROPIC_API_KEY=...` (`DETECTOR_MODEL=claude-haiku-4-5`
  for a ~5× cheaper run); otherwise the offline heuristic detector runs alone.

Common runs:
```bash
source env.sh && python -m mutations.validate     # build + validate the 6 vectors
source env.sh && python matrix.py corpus/          # divergence matrix -> results/runs/
source env.sh && bash reproduce.sh                 # D4 evasion (step 4, non-font vectors)
source env.sh && python defense_gap.py             # D5 defense gap
python corpus/loader.py inbox.mbox corpus/real/    # normalize a public corpus
OCR_DISABLE=1 python matrix.py corpus/real         # real-corpus matrix (fast)
```

## Layout

```
extractors/     Extractor interface + adapters (pypdf, pdfminer, oletools,
                ocr_render; tika/pdfbox Java bridge)
mutations/      Divergence vectors: invisible-layer, text-as-image,
                optional-content, malformed-recoverable, font-encoding (PDF Mirage)
detectors/      Content detectors: heuristic (offline) + llm (Claude)
defense/        Re-implemented PDF Mirage OCR font-verification defense
fuzz/           Mutation-fuzzing / robustness harness (DoS hunting)
differ.py       Core loop: run extractors on one file, compute divergence
matrix.py       Batch runner over a corpus -> results/
report.py       Aggregation math (pairwise + blind-spot rates)
detector_impact.py   D4: does divergence flip a detector's verdict?
defense_gap.py       D5: PDF Mirage defense vs. every vector
corpus/         make_fixtures.py (baseline) + loader.py (.eml/.mbox normalizer)
tests/          bare-env smoke + builder + aggregation tests
results/        run outputs (gitignored)
```

## Documentation

| doc | what |
|---|---|
| [RESULTS.md](RESULTS.md) | headline numbers (D3/D4/D5) at a glance |
| [PAPER.md](PAPER.md) | the write-up (arXiv cs.CR draft) |
| [TAXONOMY.md](TAXONOMY.md) | the six divergence vectors |
| [DEFENSE_GAP.md](DEFENSE_GAP.md) | PDF Mirage defense-gap experiment |
| [REAL_CORPUS.md](corpus/REAL_CORPUS.md) | normalizing SpamAssassin / GovDocs1 |
| [FUZZING.md](FUZZING.md) | robustness harness + methodology |

## Corpora (public)

SpamAssassin and Nazario (email), GovDocs1 (documents; Digital Corpora), plus the
generated baseline/mutation fixtures. `corpus/` generated content and `results/`
are gitignored; keep any malware sample sets sandboxed and out of git.

## Scope, ethics, license

- **Scope guardrail (non-negotiable):** open-source components and public data
  only. No proprietary detection-engine internals, signatures, or architecture.
- **Ethics:** divergence vectors are demonstrated on synthetic and public
  documents; any parser bug found via fuzzing is handled by coordinated
  disclosure before publication. Pre-disclosure material is kept out of the tree.
- **License:** [MIT](LICENSE).
