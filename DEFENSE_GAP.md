# Defense-Gap Result (Week 7 deliverable, D5)

The novelty anchor: PDF Mirage's accepted OCR font-verification defense catches
the font vector it was designed for and **does not generalize** to the non-font
content-masking vectors that dominate real attachments.

## What was re-implemented
`defense/font_verify.py` re-implements the defense from *PDF Mirage: Content
Masking Attack* (Markwood et al., USENIX Security 2017). It is a **font-integrity
check**: OCR the rendered page and compare it against what the *visible* text
layer claims (via `/ToUnicode`). A mismatch means the shown glyphs don't match
their character mapping — font tampering.

"Visible" is load-bearing and faithful to the paper: the check inspects glyphs
that are actually rendered. We build the claimed side from `get_texttrace()`,
dropping render-mode-3 (invisible) spans; OCG-hidden text is already absent from
the trace. A pure-image page has no visible fonts to verify. This scoping is
precisely why the defense is specific to the font vector — and why it misses the
others.

## The attack it targets
`mutations/font_vectors.py::FontRemap` is the PDF Mirage primitive: render the
lure with an embedded TrueType subset, then rewrite only the `/ToUnicode`
destinations (rot13). Glyphs render the lure; every text-layer parser extracts
gibberish.

```
font_remap.pdf:
  pypdf/pdfminer/tika/pdfbox -> "HETRAG irevsl lbhe nppbhag abj"   (rot13)
  ocr_render (human/OCR)     -> "URGENT verify your account now"
```

## Result — defense vs. every vector
`source env.sh && python defense_gap.py`

| vector | category | font-based | defense flags? | verdict |
|---|---|:---:|:---:|---|
| baseline (clean) | (none) | no | no | OK — true negative |
| **font_remap** | **font-encoding** | **yes** | **yes** | **CAUGHT (as designed)** |
| invisible_text | invisible-layer | no | no | MISSED — gap |
| text_as_image | text-as-image | no | no | MISSED — gap |
| image_with_decoy | text-as-image | no | no | MISSED — gap |
| ocg_hidden | optional-content | no | no | MISSED — gap |
| malformed_xref | malformed-recoverable | no | no | MISSED — gap |

**Font vectors caught: 1/1. Non-font vectors missed: 5/5.**

## Why each non-font vector slips past
- **invisible_text** — the invisible decoy renders no glyphs (render mode 3), so
  the font check can't inspect it; the visible glyphs match their `/ToUnicode`.
- **text_as_image / image_with_decoy** — the malicious content is pixels, not a
  font. There is no text layer (or only an invisible decoy) to verify.
- **ocg_hidden** — the decoy lives in an OFF optional-content layer; it isn't
  rendered, so its glyphs are never checked.
- **malformed_xref** — a structural/availability attack, not content masking; the
  visible glyphs match their mapping.

## Significance
1. The defense is a single-extractor, font-specific check. It says nothing about
   **extractor-vs-extractor** divergence — the core primitive this project
   measures (e.g. the real-world `000816.pdf`, where four extractors disagree
   four ways; see `corpus/REAL_CORPUS.md`).
2. In the mutation corpus the non-font vectors are 5 of 6, and in real
   attachments image/invisible/optional-content masking is common — exactly the
   space the accepted defense leaves open.
