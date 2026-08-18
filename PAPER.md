# One File, Many Readings: Cross-Extractor Content Divergence as an Evasion Primitive in Email Attachment Pipelines

**Draft — arXiv preprint (cs.CR).** Author: Ankitha Kundhuru, Independent
Researcher (akundhuru@cs.stonybrook.edu). Status: working
draft; numbers are from the reference harness in this repository and are
reproducible via the commands noted per section. The core divergence measurement
(§6) is at n=5,788 real documents; remaining small-sample results (detector
impact, per-vector) are marked *preliminary*.

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
On a real public document corpus of **5,788 GovDocs1 documents**, extractors
diverge on **43.3%** (95% CI 42.6–44.0%) of attachment-pair comparisons under a
deterministic, OCR-free configuration, and two independent content detectors (a
deterministic heuristic and Claude) both flip malicious→benign on 31.6% of
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
   per-extractor blind-spot rates, and per-format/vector breakdowns. On 5,788
   real documents it measures a 43.3% pairwise divergence rate (§6).
2. **Attack.** A vector taxonomy (§5) and a detector-impact study (§7) showing
   which divergences flip a modern content detector's verdict — including
   Claude.
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

**Shadow Attacks (Mainka et al., NDSS 2021).** Hide/replace content in *signed*
PDFs so a viewer renders content the signature-validation logic does not see —
i.e. a *renderer-vs-signature* gap in a document-integrity threat model. Ours is
orthogonal: an *extractor-vs-extractor* (and extractor-vs-render) gap in a
content-detection threat model, with no signature or single privileged view.

These works form an explicit lineage: Shadow Attacks itself extends PDF Mirage's
object-level *extracted ≠ rendered* insight into the signature-validation model;
we extend the same insight into the *extraction* model, across multiple
extractors.

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
| 3 | image+invisible decoy | text-as-image | lure as image, benign invisible decoy; parsers read benign |
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
loader. From the Apache SpamAssassin public corpus we process all four spam
archives (`20021010`/`20030228`/`20030228_2`/`20050311_2`; 2,400 messages, not
deduplicated across the superseded 2002 release), recovering 31 attachments — of
which only one is an Office document (25 are images, 4 HTML). Document
attachments are rare here, itself a finding about where document-parser evasion
lives. For a document-rich sample we use
**GovDocs1** (Digital Corpora), ~1M redistributable real `.gov` documents. We run
the harness over **5,928 GovDocs1 documents** (PDF/DOC/XLS/PPT) in the
deterministic **`no_ocr`** configuration (Tika `X-Tika-PDFOcrStrategy=no_ocr`, so
every extractor performs pure text extraction and the comparison is not confounded
by Tika's built-in image OCR — see the OCR-confound note below). Of the 5,928
files, 5,788 completed under all extractors; 140 induced parser timeouts or a
native crash and are analyzed separately in §9.

| metric (`no_ocr`, N=5,788) | value |
|---|---|
| overall pairwise divergence | **43.3%** — 95% CI [42.6%, 44.0%] (7,935/18,336 comparisons) |
| files with ≥1 divergence | **60.6%** |
| by format (files w/ ≥1 divergence) | PPT **80.0%** · XLS **78.9%** · PDF **61.9%** · DOC **32.3%** |
| pdfminer vs pypdf | **68.0%** (vs **0%** on the synthetic baseline) |
| selected pairs | pdfminer vs tika 67.2% · pdfbox vs pdfminer 65.2% · oletools vs tika 73.9% (PPT 99.6% / XLS 99.8%) · pdfbox vs tika 7.4% |

All rates carry Wilson 95% confidence intervals (full table in `RESULTS.md`);
intervals are ≤±1.8 points at this sample size.

**OCR confound (why `no_ocr` is primary).** Tika silently OCRs embedded images,
which inflates apparent divergence against the pure-text extractors on identical
bytes. On our 42-document pilot the same corpus measures **37.3%** divergence
under `no_ocr` but **46.5%** with Tika's OCR-on strategy; we therefore adopt the
deterministic `no_ocr` configuration as our primary measurement. Scaling `no_ocr`
from the pilot (37.3%, n=42) to 5,788 documents *raises* the rate to 43.3%,
because the larger corpus is richer in the PPT/XLS formats that diverge most
(≈80%) — the phenomenon is robust and, if anything, stronger at scale.

**Worked example (`000816.pdf`, a US Census NAICS report).** The same special-dash
glyph is extracted four incompatible ways on identical bytes (pypdf vs pdfminer
similarity 0.25):

| extractor | output for the glyph | chars |
|---|---|---|
| pypdf | `/thrqtrEMdash` (internal glyph name leaked) | 31,614 |
| pdfminer | `(cid:1)` (unmapped CID) | 25,270 |
| tika | `�` (U+FFFD) | 24,619 |
| pdfbox | `\x01` (raw control byte) | 12,519 |

(For pdfbox, these raw control bytes make up ~40% of its extracted text.) This is
a *naturally occurring* font/encoding divergence in the wild — the same class
§5's vector 6 weaponizes deliberately.

## 7. Detector Impact (D4)

Divergence matters iff it changes a detector's decision. D4's scope is the five
non-font content-masking vectors (the font vector is evaluated separately as the
subject of the §8 defense-gap experiment). For each such masking vector we
classify every extractor's output and the OCR ground truth with two detectors
— a deterministic phishing heuristic (offline, zero-cost, reproducible) and
Claude (Haiku 4.5), producing a structured-output verdict. An **evasion** is a
(file, extractor) pair where the OCR truth scores malicious but the extractor's
text scores benign.

| detector | files w/ malicious truth | files evaded | extractor evasions |
|---|---|---|---|
| heuristic | 5 | 2 | **6/19 (31.6%)** |
| Claude (Haiku 4.5) | 5 | 2 | **6/19 (31.6%)** |

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
CVE), reproduces on the current release (olefile v0.47), and is addressed by a
one-line complement to the #103 fix. We report it, if at all, as an incomplete-fix hardening PR citing
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

**Robustness at scale (a real-world instance of the same caution).** The 5,928-document
`no_ocr` extraction run (§6), executed 8-way concurrently under a 120 s per-file
wall-clock cap, flagged **139 files** as exceeding the cap. Taken at face value
this looks like a 2.3% parser-hang rate — but the caution above predicts most are
CPU-contention artifacts, not hangs. We tested this directly: the 80 flagged files
under 1 MB (where a genuine algorithmic-complexity hang would concentrate), plus the
one file that deadlocked a worker, were re-run in **isolation** (single parser,
idle CPU, one-at-a-time, 60 s cap) through the fuzz harness's corpus-pass mode.
Only **6 of the 81** reproduce as genuine hangs — and **all six are Apache Tika**,
on unmutated real documents (345 KB–2.1 MB); the pure-Python parsers
(pypdf/pdfminer/oletools) that saturated CPU under contention all completed
normally (308 clean extractions, 91 ordinary parse exceptions, 0 crashes, 0 OOM).
This is a genuine *differential robustness* observation — Tika hangs on inputs
that PDFBox, pypdf, and pdfminer parse without incident — and a cautionary data
point: the raw concurrent-run timeout count overstated genuine hangs by ~13× on
the verified subset. We make **no CVE claim** (Tika has prior DoS history; these
inputs require triage against known issues before any disclosure) and report the
count only as a robustness signal consistent with the divergence thesis.

## 10. Limitations and Ethics

- **Sample size.** The core divergence measurement (D3, §6) is now at n=5,788
  real documents with Wilson confidence intervals. The detector-impact study (D4,
  §7) and per-vector mutation numbers remain at smaller samples and are the
  natural next scaling step; they report the phenomenon and the method.
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
directly (43.3% across 5,788 real documents), showed it flips modern content detectors
including Claude (31.6% of extractor pairs on image-masking vectors), and showed the
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
- Mainka, C., Mladenov, V., Rohlmann, S. *Shadow Attacks: Hiding and Replacing
  Content in Signed PDFs.* NDSS 2021.
- Dalmiere, A., Zhou, Z., Auriol, G., Nicomette, V., Marchand, P. *Measuring
  Modern Phishing Tactics: A Quantitative Study of Body Obfuscation Prevalence,
  Co-occurrence, and Filter Impact.* Security and Trust Management (STM) 2025,
  Springer LNCS. arXiv:2506.20228.
- Garfinkel, S., Farrell, P., Roussev, V., Dinolt, G. *Bringing Science to
  Digital Forensics with Standardized Forensic Corpora.* Digital Investigation
  6(S1):S2–S11, DFRWS 2009. doi:10.1016/j.diin.2009.06.016. *(GovDocs1)*
- Albertini, A. *Corkami / file-format tricks.* https://github.com/corkami/pocs
