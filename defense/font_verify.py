"""
Re-implementation of PDF Mirage's OCR font-verification defense
(Markwood et al., "PDF Mirage: Content Masking Attack", USENIX Security 2017).

Their defense targets the font-remapping attack: a glyph renders as one
character while the font's /ToUnicode claims another, so extracted text diverges
from what a human reads. The check OCRs the rendered page and compares it to the
text the font layer *claims*; a mismatch means the shown glyphs don't match
their character mapping — i.e. font tampering.

Crucially this is a FONT-INTEGRITY check, not a blanket extracted-vs-OCR diff.
It verifies the characters that are actually rendered (visible glyphs) against
their mapping. So the "claimed" side is the *visible* text layer only:
`get_texttrace()` gives per-span render mode — we drop render-mode-3 (invisible)
spans, and OCG-hidden text is already absent from the trace. A document with no
visible text layer (pure image) has no fonts to verify.

This scoping is exactly what makes the defense specific to the font vector — and
exactly why it misses the invisible-layer / image / optional-content / container
vectors (Week 7 defense-gap result).
"""
from __future__ import annotations
from dataclasses import dataclass, field

from differ import similarity
from extractors.base import normalize
from extractors.adapters import OCRGroundTruth


@dataclass
class DefenseResult:
    path: str
    flagged: bool                 # True = font tampering detected
    ok: bool                      # False = could not run (no OCR backend)
    reason: str = ""
    similarity: float = 1.0       # visible-text-layer vs OCR
    claimed_preview: str = ""     # what the visible glyphs' /ToUnicode claims
    rendered_preview: str = ""    # what OCR reads off the page
    meta: dict = field(default_factory=dict)


def _visible_text_layer(path: str) -> str:
    """Concatenate the /ToUnicode text of glyphs that are actually rendered:
    drop render-mode-3 (invisible) spans; OCG-hidden text is already excluded
    by get_texttrace."""
    import fitz
    parts = []
    doc = fitz.open(path)
    try:
        for page in doc:
            for span in page.get_texttrace():
                if span.get("type") == 3:      # invisible render mode
                    continue
                parts.append("".join(chr(c[0]) for c in span.get("chars", [])))
    finally:
        doc.close()
    return normalize(" ".join(parts))


def verify(path: str, threshold: float = 0.6) -> DefenseResult:
    """PDF Mirage font check. Flags when the *visible* text layer disagrees with
    OCR of the rendering (glyph shapes don't match their /ToUnicode)."""
    claimed = _visible_text_layer(path)

    ocr = OCRGroundTruth().extract(path)
    if not ocr.ok:
        return DefenseResult(path, flagged=False, ok=False,
                             reason=f"cannot verify (no OCR: {ocr.error})")
    rendered = ocr.text

    if not claimed:
        # no visible fonts to verify — the attack, if any, isn't font-based
        return DefenseResult(path, flagged=False, ok=True,
                             reason="no visible text layer to verify",
                             similarity=1.0, rendered_preview=rendered[:120])

    sim = similarity(claimed, rendered)
    flagged = sim < threshold
    return DefenseResult(
        path, flagged=flagged, ok=True,
        reason=("visible glyphs disagree with /ToUnicode (font tampering)"
                if flagged else "visible glyphs match their mapping"),
        similarity=round(sim, 4),
        claimed_preview=claimed[:120],
        rendered_preview=rendered[:120])
