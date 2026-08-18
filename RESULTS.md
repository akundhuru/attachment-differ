# Results at a glance

Headline numbers from the harness. Small-sample figures are marked *preliminary*
— the harness scales to full corpora (that's a run, not new code). Reproduce
everything with `bash reproduce.sh`.

## D3 — Cross-extractor divergence (measurement)
Same attachment, different extracted content depending on the extractor.

| corpus | overall pairwise divergence | pypdf vs pdfminer | note |
|---|---|---|---|
| synthetic baseline (clean) | 0% | **0%** | pure-text extractors agree |
| synthetic mutated | 80% of files | — | vectors, not the harness, drive divergence |
| **real (GovDocs1, N=5,788, `no_ocr`)** | **43.3%** — 95% CI [42.6, 44.0] (7,935/18,336 pairs) | **68.0%** | see stratification below |

Per-format (files with ≥1 divergence): PPT **80.0%** · XLS **78.9%** · PDF
**61.9%** · DOC **32.3%**. Selected pairs: pdfminer-vs-tika 67.2%, pdfbox-vs-pdfminer
65.2%, oletools-vs-tika 73.9% (PPT 99.6% / XLS 99.8%), pdfbox-vs-tika 7.4%.
Of 5,928 files, 5,788 completed under all extractors; 140 hit parser
timeouts/crash (see Robustness below).

**OCR confound:** `no_ocr` (Tika pure-text) is the primary, deterministic
configuration. On the 42-doc pilot the same corpus is 37.3% under `no_ocr` vs
46.5% with Tika OCR-on; scaling `no_ocr` to 5,788 docs *raises* the rate to 43.3%
(the larger corpus is richer in the high-divergence PPT/XLS formats).

Worked real example — `000816.pdf` (US Census NAICS), one glyph read four ways
(pypdf `/thrqtrEMdash`, pdfminer `(cid:1)`, tika `�`, pdfbox `\x01`; pdfbox got
~40% of the text). See `REAL_CORPUS.md`.
`OCR_DISABLE=1 TIKA_SERVER_URL=http://localhost:9998 python matrix.py corpus/real --jobs 8`

## D4 — Detector impact (attack / evasion)
Does divergence flip a content detector? Evasion = OCR-truth malicious, but an
extractor's text scored benign. Scope: the five non-font content-masking vectors
(the font vector is evaluated separately in D5).

| detector | extractor evasions | files evaded |
|---|---|---|
| heuristic (offline) | **6/19 (31.6%)** | image_with_decoy, text_as_image |
| Claude (Haiku 4.5, live) | **6/19 (31.6%)** | same |

Two independent detectors agree exactly — not a heuristic artifact. Pure text
extractors (pypdf/pdfminer/pdfbox) read the benign decoy; Tika's built-in OCR
recovers the lure and does *not* evade. Reproduce via `bash reproduce.sh` (step 4
names the five non-font vectors explicitly).

## D5 — Defense gap (novelty anchor)
PDF Mirage's OCR font-verification defense, re-implemented, vs. every vector.

| | result |
|---|---|
| font vector (font_remap) | **CAUGHT 1/1** (validates the re-implementation) |
| non-font vectors | **MISSED 5/5** (invisible-layer, text-as-image, image+decoy, optional-content, malformed) |
| clean baseline | not flagged (true negative) |

The accepted content-masking defense is font-specific and does not generalize.
See `DEFENSE_GAP.md`. `python defense_gap.py`

## Robustness / disclosure (stretch)
Fuzzing harness (`fuzz/`) over real GovDocs1 seeds surfaced one reproducible
robustness gap: unbounded recursion in `olefile`'s `listdir()`/`_list()` on a
self-referential-root OLE (minimized to 1536 bytes). **Not a novel bug** — a
confirmed *residual* of the fix for olefile issue #103 (2018); low severity, no
CVE claim. Reported, if at all, as an incomplete-fix hardening PR citing #103.
See `FUZZING.md`. (Pre-disclosure material is kept out of the public tree.)

**Robustness at scale.** The 5,928-doc `no_ocr` run (8-way concurrent, 120 s cap)
flagged 139 files as over-cap. Isolated re-verification (single parser, idle CPU,
60 s) of the 81 strongest candidates confirmed only **6 genuine hangs — all Apache
Tika**, on unmutated real documents (345 KB–2.1 MB); the pure-Python parsers all
completed normally. The concurrent count overstated hangs ~13× — a differential-
robustness signal (Tika hangs where PDFBox/pypdf/pdfminer succeed), **no CVE claim**.

## Vectors
Six programmatic divergence vectors, each validated end-to-end (`TAXONOMY.md`):
invisible-layer · text-as-image · image+invisible-decoy · optional-content ·
malformed-recoverable · font-encoding (PDF Mirage).

## Tests
`test_smoke · test_mutations · test_report · test_detectors · test_defense ·
test_fuzz` — all green (`bash reproduce.sh` runs them first).
