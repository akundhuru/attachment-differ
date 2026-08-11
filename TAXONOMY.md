# Divergence Vector Taxonomy (Week 3-4 deliverable)

A *divergence vector* is a construction that makes one attachment yield
different content depending on which extractor reads it — or different content
to a parser than to the human who renders it. Each vector is implemented as a
programmatic mutation in `mutations/pdf_vectors.py` and validated end-to-end by
`mutations/validate.py`, which builds the fixture and confirms the live harness
detects the predicted divergence.

Two divergence axes matter:

- **extractor-vs-render** — a parser reads content the human does not see (or
  misses content the human does). A content detector scoring parser output is
  blind to the victim's actual experience.
- **extractor-vs-extractor** — two parsers disagree on the same bytes. A
  pipeline-aware attacker selects whichever extractor is blind to the payload.

Similarity is `difflib.SequenceMatcher` ratio on normalized text (1.0 =
identical). The `results/` numbers below are from the seed fixtures generated
by `validate.py` on this repo's extractor set (pypdf, pdfminer, tika, pdfbox,
ocr_render).

---

## Implemented vectors

### 1. Invisible layer — `InvisibleText` · `invisible-layer`
Decoy text drawn with PDF text render mode 3 (invisible). Text extraction
ignores render mode, so every parser reads *visible + decoy*; the human and the
OCR oracle see only the visible layer.
- **Axis:** extractor-vs-render (all parsers ~0.69 vs OCR).
- **Attacker use:** inject detector-poisoning keywords the victim never sees, or
  hide a benign smokescreen around a visible lure.

### 2. Text as image — `TextAsImage` · `text-as-image`
The whole visible message is rasterized to a PNG and embedded with **no text
layer**. Pure text extractors return empty; only OCR recovers the content.
- **Axis:** extractor-vs-render **and** extractor-vs-extractor.
- **Measured finding:** pypdf / pdfminer / pdfbox return blank (0.00 vs OCR),
  but **Tika returns text (~0.66 vs OCR)** — Tika bundles Tesseract and OCRs
  embedded images by default, so it behaves as a hybrid parser+OCR and diverges
  from the pure text extractors on identical bytes (tika-vs-pdfbox = 0.00).
  This is a concrete cross-extractor divergence, not a designed one.

### 3. Image + invisible decoy — `ImageWithDecoy` · `text-as-image`
The full evasion showcase: the phishing lure is an image (human/OCR sees it); a
benign paragraph is an invisible text layer. Text parsers read **only** the
benign decoy, so a detector scoring parser output passes the lure untouched.
- **Axis:** extractor-vs-render (parsers ~0.29 vs the OCR'd lure).
- **Attacker use:** the canonical "detector sees benign, victim sees phish."

### 4. Optional content group — `OptionalContentHidden` · `optional-content`
Decoy text placed in an OCG (PDF layer) whose default state is OFF. Renderers
honor the layer state and hide it; parsers ignore OCG semantics and extract it.
- **Axis:** extractor-vs-render (~0.69 vs OCR).
- **Distinct from invisible-layer:** exercises *visibility metadata* handling,
  not render mode — a different code path in every parser, and a candidate for
  parser-specific divergence as more extractors are added.

### 5. Malformed but recoverable — `MalformedXref` · `malformed-recoverable`
A structurally valid page whose `startxref` offset is corrupted. Lenient
parsers rebuild the cross-reference table by scanning and recover the text;
strict parsers refuse.
- **Axis:** errored (extractor availability divergence).
- **Measured finding:** pypdf errors (`startxref not found`); pdfminer, tika,
  and pdfbox all recover. A pipeline that routes to pypdf sees nothing.

---

## Font vector (implemented — Week 7 anchor)

### 6. Font / encoding remap — `FontRemap` · `font-encoding`
A glyph renders as one character while the font's `/ToUnicode` CMap maps its code
to another. Parsers that trust `/ToUnicode` extract the scrambled text; the human
and OCR see the real glyphs. This is **PDF Mirage's** vector (Markwood et al.,
USENIX '17). Implemented in `mutations/font_vectors.py`: render the lure with an
embedded TrueType subset (reportlab), then rewrite only the `/ToUnicode`
destinations (rot13) with pypdf — the glyph program is untouched, so rendering is
unchanged and only extraction moves.
- **Axis:** extractor-vs-render (all parsers ~0.27 vs OCR; parsers agree with
  each other since they all trust `/ToUnicode`).
- **Defense-gap anchor:** this is the one vector PDF Mirage's OCR
  font-verification defense catches; it misses vectors 1–5. See `DEFENSE_GAP.md`.

## Planned / documented vectors (not yet implemented)

### 7. Container / polyglot — `container-polyglot`
A file valid as two formats at once (e.g. PDF+ZIP, or a PDF with a mismatched
magic/extension). Content-sniffing extractors (Tika) may dispatch to a
different parser than extension-driven ones (pypdf), yielding different content.
Depends on format-detection divergence rather than in-format tricks.

### 8. Multipart / container abuse — `multipart`  *(email-level)*
An email whose MIME parts carry conflicting content, or an attachment whose
"real" content sits in an alternative/nested part that some pipeline stages skip.
Operates above the single-file differ; needs an `.eml`-level harness extension.

---

## How to reproduce

```bash
source env.sh                 # enables OCR + Tika/PDFBox
python -m mutations.validate  # builds corpus/mutated/*.pdf, prints the table
```

Every implemented vector must show `PASS` (predicted divergence detected). A
`FAIL` means either the mutation stopped working or an extractor changed
behavior — both are signal worth investigating, not just test noise.
