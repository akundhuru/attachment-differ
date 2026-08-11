# One File, Many Readings: Cross-Extractor Content Divergence as an Evasion Primitive in Email Attachment Pipelines

**Draft — arXiv preprint (cs.CR).** Author: Ankitha Kundhuru. Status: working
draft; numbers are from the reference harness in this repository and are
reproducible via the commands noted per section. Small-sample results are marked
*preliminary*; scaling them is a turn of the crank, not new engineering.

---

## Abstract

Production email-security pipelines extract the textual content of attachments
and score that text with downstream detectors (phishing/brand/malware
classifiers, increasingly LLM-based). These pipelines chain **multiple** content
extractors across formats — Apache Tika, PDFBox, pypdf, pdfminer, oletools. We
show that the same attachment yields **different extracted content depending on
which extractor runs**, and that this cross-extractor divergence is an *evasion
primitive*: an attacker who knows (or probes) the pipeline can craft an
attachment whose extracted text scores benign while the rendered document a human
opens is a lure.

We contribute (1) an open-source **differential harness** measuring divergence
across N extractors plus an OCR "what the human sees" oracle; (2) a **vector
taxonomy** beyond font remapping — invisible-layer, text-as-image,
image+invisible-decoy, optional-content, and malformed-recoverable — implemented
as programmatic mutations; and (3) a **defense-gap** result: we re-implement the
OCR font-verification defense proposed by *PDF Mirage* (USENIX '17) and show it
catches only the font vector it was designed for, missing every non-font vector.
On a real public document corpus (GovDocs1), extractors diverge on 46% of
attachment-pair comparisons, and two independent content detectors (a
deterministic heuristic and Claude) both flip malicious→benign on 32% of
extractor pairs for image-based masking vectors.

---

## 1. Introduction

An email-attachment detection pipeline does not score the *bytes* of an
attachment; it scores the *text an extractor pulls out of it*. That extraction
step is where security is quietly decided. Different extractors implement
different — individually spec-compliant — choices about encodings, layer
visibility, render modes, and recovery from malformed structure. The result is
that "the content of this attachment" is not a single string; it is a function of
which extractor you ask.

We frame this as an evasion primitive. If a pipeline's detector reads extractor
*X*'s output, an attacker crafts an attachment where *X* reads benign text while
the rendered page — what the victim actually reads — carries the lure. This is
strictly more general than a single parser bug: it exploits *legitimate
disagreement between compliant parsers*, so there is no single "wrong" parser to
patch.

**Contributions.**
1. **Measurement.** A differential harness (§4) that runs N extractors plus an
   OCR render-oracle over an attachment and quantifies pairwise divergence,
   per-extractor blind-spot rates, and per-format/vector breakdowns. On real
   documents it measures a 46% pairwise divergence rate (§6).
2. **Attack.** A vector taxonomy (§5) and a detector-impact study (§7) showing
   which divergences flip a modern content detector's verdict — including an
   LLM detector (Claude).
3. **Defense-gap.** A faithful re-implementation of PDF Mirage's font-verification
   defense and a demonstration that it does not generalize to the non-font
   vectors that dominate real attachments (§8).

## 2. Background and Related Work

**PDF Mirage: Content Masking Attack (Markwood et al., USENIX Security 2017).**
Weaponizes the *extracted ≠ rendered* gap via font remapping (a glyph renders as
A while `/ToUnicode` claims B) and proposes an OCR-based font-verification
defense. We differ on three axes: we are *extractor-vs-extractor* (not
human-vs-single-parser), *multi-format and multi-vector* (not font-only), and we
show their defense fails on our non-font vectors (§8).

**Extract Me If You Can (Carmony et al., NDSS 2016).** Diffs a reference
JavaScript extractor (Adobe) against open-source extractors over 163k PDFs to
evade malware AV. Ours targets *content* extraction (phishing/brand), uses a
human-render OCR oracle rather than an execute-oracle, and modern/LLM content
detectors rather than AV.

**Body Obfuscation (Dalmiere et al., STM 2025).** Measures email-*body*
obfuscation prevalence (386 phishing emails, ten techniques) and its impact on
SpamAssassin/Rspamd scores. Ours is *attachments*, a controlled automated
differential rather than a prevalence measurement, against modern detectors.

*Positioning:* the intersection — a multi-extractor *content* differential in the
email-attachment threat model, framed as a detector-evasion primitive — is, to
our knowledge, open.

## 3. Threat Model

The attacker can send an attachment and knows (or probes, via bounce/verdict
oracles) which extractor the target pipeline uses for a given format. The
defender runs one or more extractors and scores their output. The victim opens
the attachment in a normal renderer (the OCR oracle stands in for "what the victim
reads"). The attacker's goal: a document scored benign by the pipeline's extractor
but read as a lure by the victim. We assume open-source tools and public data
throughout; no proprietary detection internals are used or required.

## 4. The Differential Harness

For one attachment the harness runs every applicable extractor and computes
pairwise similarity (normalized-text `SequenceMatcher` ratio; §Limitations
discusses stronger metrics), separating two axes:
- **extractor-vs-extractor** — two parsers disagree on the same bytes.
- **extractor-vs-render** — a parser disagrees with the OCR oracle (render →
  pytesseract), i.e. reads something the human does not, or misses what they see.

Extractors: `pypdf`, `pdfminer.six`, Apache `Tika`, Apache `PDFBox` (PDF and
OOXML/OLE), `oletools` (OLE/macros), and `ocr_render` (PyMuPDF render +
pytesseract) as the oracle. Every adapter obeys a no-raise contract: a missing
backend surfaces as a clean "this extractor was blind here," itself signal. A
batch runner aggregates divergence-rate statistics to machine-readable JSON/CSV.

*Reproduce:* `python differ.py <file>`; `python matrix.py <corpus>`.

**A note on Tika.** Tika bundles Tesseract and OCRs embedded images by default,
so it behaves as a hybrid parser+OCR and diverges from pure text extractors on
identical bytes (e.g. on a text-as-image PDF, pypdf/pdfminer/pdfbox return empty
while Tika returns ~0.66 of the OCR text). We treat Tika-OCR as a confound and
recommend measuring both with and without it (`OCR strategy NO_OCR`).

## 5. Divergence Vector Taxonomy

Each vector is a programmatic mutation that makes an attachment read one way to a
human and another to a text-layer parser (`mutations/`, validated end-to-end by
`mutations/validate.py` — all six produce their predicted divergence).

| # | Vector | Class | Mechanism |
|---|---|---|---|
| 1 | invisible-layer | text render mode 3 | decoy drawn invisibly; parsers read it, OCR/human don't |
| 2 | text-as-image | rasterization | content is pixels, no text layer; parsers blind, OCR reads |
| 3 | image+invisible decoy | 1+2 | lure as image, benign invisible decoy; parsers read benign |
| 4 | optional-content | OCG layer OFF | decoy in a hidden PDF layer; renderers hide, parsers extract |
| 5 | malformed-recoverable | corrupt xref | lenient parsers recover, strict ones error (availability divergence) |
| 6 | font-encoding | glyph ≠ `/ToUnicode` | PDF Mirage primitive; parsers extract a scramble, OCR reads the glyphs |

Documented in `TAXONOMY.md`. Container/polyglot and email-multipart vectors are
enumerated as future extensions (the latter needs an `.eml`-level harness).

## 6. Measurement (D3)

**Synthetic control.** On clean baseline PDFs, the pure-text extractors agree
exactly (pypdf vs pdfminer = 0% divergence). On the mutated corpus, 80% of files
diverge — a clean separation confirming the vectors, not the harness, drive
divergence.

**Real corpus.** We normalize public corpora with an `.eml`/`.mbox` attachment
loader. Apache SpamAssassin (2,400 spam emails → 31 attachments) is
overwhelmingly image/HTML; document attachments are rare — itself a finding about
where document-parser evasion lives. For a document-rich sample we use
**GovDocs1** (Digital Corpora), ~1M redistributable real `.gov` documents. On a
42-document sample (20 PDF / 10 DOC / 6 XLS / 6 PPT):

| metric | value |
|---|---|
| overall pairwise divergence | **46.5%** (66/142 comparisons) |
| files with ≥1 divergence | **69%** |
| pdfminer vs pypdf | **55%** (vs **0%** on the synthetic baseline) |
| pdfminer vs tika | 70% · oletools vs tika 68% · pdfbox vs pdfminer 50% |

*Preliminary (n=42); the harness scales to full GovDocs1 threads.*

**Worked example (`000816.pdf`, a US Census NAICS report).** The same special-dash
glyph is extracted four incompatible ways on identical bytes (pypdf vs pdfminer
similarity 0.25):

| extractor | output for the glyph | chars |
|---|---|---|
| pypdf | `/thrqtrEMdash` (internal glyph name leaked) | 31,614 |
| pdfminer | `(cid:1)` (unmapped CID) | 25,270 |
| tika | `�` (U+FFFD) | 24,619 |
| pdfbox | `\x01` (raw control byte) — ~40% of the text | 12,519 |

This is a *naturally occurring* font/encoding divergence in the wild — the same
class §5's vector 6 weaponizes deliberately.

## 7. Detector Impact (D4)

Divergence matters iff it changes a detector's decision. D4's scope is the five
non-font content-masking vectors (the font vector is evaluated separately as the
subject of the §8 defense-gap experiment). For each such masking vector we
classify every extractor's output and the OCR ground truth with two detectors
— a deterministic phishing heuristic (offline, zero-cost, reproducible) and an
LLM detector (Claude, structured-output verdict). An **evasion** is a
(file, extractor) pair where the OCR truth scores malicious but the extractor's
text scores benign.

| detector | files w/ malicious truth | files evaded | extractor evasions |
|---|---|---|---|
| heuristic | 5 | 2 | **6/19 (31.6%)** |
| Claude (haiku) | 5 | 2 | **6/19 (31.6%)** |

The two independent detectors agree exactly — the evasion is a property of the
extraction divergence, not a heuristic artifact. Evasions concentrate on the
image-based vectors (text-as-image, image+decoy), where pypdf/pdfminer/pdfbox
read the benign decoy (or nothing) while the victim sees the lure. Notably Tika
does **not** evade there — its built-in OCR recovers the lure, closing the blind
spot the pure text extractors have (a concrete pipeline-configuration consequence).

## 8. Defense-Gap (D5)

We re-implement PDF Mirage's OCR font-verification (`defense/font_verify.py`) as
a faithful *font-integrity* check: OCR the rendered page and compare it to what
the **visible** text layer claims via `/ToUnicode` (visible = `get_texttrace`
spans excluding render-mode-3; OCG-hidden text is already absent). A page with no
visible text layer has no fonts to verify. Running it against every vector:

| vector | class | font-based | defense flags? | verdict |
|---|---|:---:|:---:|---|
| baseline | — | no | no | true negative |
| **font_remap** | font-encoding | **yes** | **yes** | **CAUGHT (as designed)** |
| invisible_text | invisible-layer | no | no | MISSED |
| text_as_image | text-as-image | no | no | MISSED |
| image_with_decoy | text-as-image | no | no | MISSED |
| ocg_hidden | optional-content | no | no | MISSED |
| malformed_xref | malformed-recoverable | no | no | MISSED |

**Font vectors caught 1/1; non-font vectors missed 5/5.** The defense is
single-extractor and font-specific: it verifies rendered glyphs against their
mapping. It cannot see content that is an image, an invisible/hidden layer, or a
structural-recovery divergence, and it says nothing about extractor-vs-extractor
disagreement — the primitive we measure. Since non-font masking dominates real
attachments, the accepted defense leaves the larger surface open.

## 9. Robustness Testing and Responsible Disclosure

Divergence is (mostly) spec-compliant behavior, not a memory-safety bug. To
probe for disclosable DoS/crash bugs we built a separate mutation-fuzzing harness
(`fuzz/`) that mutates real GovDocs1 seeds (radamsa) and runs each parser in an
isolated subprocess under a timeout + resource caps, classifying crashes (signal
death), hangs (timeout), and OOM/recursion as bugs distinct from ordinary parse
errors. A refined campaign (per target sequentially, 256 KB input cap, no CPU contention;
15k iterations on MuPDF, 6k each on pdfminer/pypdf, 4k on oletools, 1.5k each on
Tika/PDFBox) rediscovered an **unbounded-recursion condition in `olefile`'s
directory handling** (the OLE2 parser under `oletools`): a self-referential root
directory entry drives `OleDirectoryEntry._list()` into infinite recursion during
`listdir()` (minimized to a 1536-byte file). **This is not a novel bug.** olefile
issue #103 (2018) reported infinite recursion while *opening* a malformed file; its
fix moved the "referenced more than once" guard to the top of `append_kids()`,
which stops the build-phase recursion. Our case is a *confirmed residual* of that
fix: the root entry is loaded directly and never passes through `append_kids`, so
it is never marked "used"; a self-referential root therefore slips into its own
`kids` and recurses in `_list()` during `listdir()` — a path the #103 fix does not
cover. It is low-severity (a catchable `RecursionError`; #103 itself received no
CVE), reproduces on the current release, and is addressed by a one-line complement
to the #103 fix. We report it, if at all, as an incomplete-fix hardening PR citing
#103, and make **no CVE claim**. A weaker pdfminer.six super-linear-time
observation (73 KB → ~55 CPU-s) was also recorded. The takeaway is methodological:
the harness surfaced a real, minimizable robustness gap from real seeds; see
`DISCLOSURE.md`.

A methodological note worth reporting: a naive timeout-based hang detector
produces false positives from size-inflating mutators under CPU contention (an
earlier concurrent run flagged seven "hangs" that all completed on idle CPU).
Real DoS shows the opposite signature — *small input, disproportionate cost* —
which the size cap plus per-run wall-time recording isolates. CVEs remain upside,
not a dependency of the contributions above.

## 10. Limitations and Ethics

- **Sample size.** Real-corpus numbers (n=42) and mutation-corpus numbers are
  preliminary; the harness scales to full corpora — this draft reports the
  phenomenon and the method, and larger runs are the natural next step.
- **Similarity metric.** `SequenceMatcher` is a first-pass metric; token-set or
  embedding distance may sharpen results without changing the qualitative story.
- **OCR oracle.** OCR is imperfect and slow on long documents (we expose a page
  cap and an off switch); it is a stand-in for human reading, not ground truth.
- **Ethics.** Open-source tools and public data only. Vectors are demonstrated on
  synthetic and public documents; any parser bug found via fuzzing is disclosed
  responsibly before publication. No proprietary detection internals are used.

## 11. Conclusion

The unit a content detector scores — extracted text — is not a property of the
attachment but of the extractor. We measured that cross-extractor divergence
directly (46% on real documents), showed it flips modern content detectors
including an LLM (32% of extractor pairs on image-masking vectors), and showed the
accepted content-masking defense is font-specific and misses the vectors that
dominate real attachments. The harness, taxonomy, and defense-gap experiment are
released for reproduction and extension.

## Artifact Availability

Open-source harness, mutation vectors, detectors, defense, and fuzzing harness:
https://github.com/akundhuru/attachment-differ (archived at
Zenodo, DOI [10.5281/zenodo.21894923](https://doi.org/10.5281/zenodo.21894923)).
Reproduction commands are inline per section; see `README.md`,
`TAXONOMY.md`, `DEFENSE_GAP.md`, `REAL_CORPUS.md`, and `FUZZING.md`.

## References
- Markwood, Liu, et al. *PDF Mirage: Content Masking Attack Against
  Information-Based Online Services.* USENIX Security 2017.
- Carmony, et al. *Extract Me If You Can: Abusing PDF Parsers in Malware
  Detectors.* NDSS 2016.
- Dalmiere, A., Zhou, Z., Auriol, G., Nicomette, V., Marchand, P. *Measuring
  Modern Phishing Tactics: A Quantitative Study of Body Obfuscation Prevalence,
  Co-occurrence, and Filter Impact.* Security and Trust Management (STM) 2025,
  Springer LNCS. arXiv:2506.20228.
- Albertini, A. *Corkami / file-format tricks.* https://github.com/corkami/pocs
