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
| **real (GovDocs1, n=42)** *(prelim)* | **46.5%** (66/142 pairs) | **55%** | pdfminer-vs-tika 70%, oletools-vs-tika 68% |

Worked real example — `000816.pdf` (US Census NAICS), one glyph read four ways
(pypdf `/thrqtrEMdash`, pdfminer `(cid:1)`, tika `�`, pdfbox `\x01`; pdfbox got
~40% of the text). See `REAL_CORPUS.md`.
`OCR_DISABLE=1 python matrix.py corpus/real`

## D4 — Detector impact (attack / evasion)
Does divergence flip a content detector? Evasion = OCR-truth malicious, but an
extractor's text scored benign. Scope: the five non-font content-masking vectors
(the font vector is evaluated separately in D5).

| detector | extractor evasions | files evaded |
|---|---|---|
| heuristic (offline) | **6/19 (31.6%)** | image_with_decoy, text_as_image |
| LLM (live) | **6/19 (31.6%)** | same |

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

## Vectors
Six programmatic divergence vectors, each validated end-to-end (`TAXONOMY.md`):
invisible-layer · text-as-image · image+invisible-decoy · optional-content ·
malformed-recoverable · font-encoding (PDF Mirage).

## Tests
`test_smoke · test_mutations · test_report · test_detectors · test_defense ·
test_fuzz` — all green (`bash reproduce.sh` runs them first).
