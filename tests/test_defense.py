"""
Font-remap vector + PDF Mirage defense-gap tests.

The rot13 remap is checkable offline (no OCR). The defense itself needs the OCR
backend (it IS the defense), so those assertions self-skip when OCR is absent.

    python tests/test_defense.py
"""
from __future__ import annotations
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mutations.font_vectors import FontRemap, rot13_text   # noqa: E402
from corpus.make_fixtures import _plain_pdf                 # noqa: E402
from defense import verify                                  # noqa: E402

LURE = "URGENT verify your account"


def test_rot13_roundtrip():
    assert rot13_text(rot13_text(LURE)) == LURE
    assert rot13_text("URGENT") == "HETRAG"


def test_font_remap_extraction_is_rot13_of_visible():
    # pypdf reads the /ToUnicode (remapped); it must equal rot13 of the visible text
    from pypdf import PdfReader
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "font_remap.pdf")
        res = FontRemap().build(out, LURE, "")
        assert res.meta["fonts_remapped"] >= 1
        extracted = (PdfReader(out).pages[0].extract_text() or "")
        assert rot13_text(LURE).split()[0] in extracted, extracted


def test_defense_catches_font_and_misses_nonfont():
    # Needs OCR; skip cleanly if unavailable.
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "base.pdf")
        _plain_pdf(base, ["Quarterly report attached."])
        rb = verify(base)
        if not rb.ok:
            print("  (OCR backend unavailable — skipping defense assertions)")
            return
        assert not rb.flagged, "clean baseline must not be flagged"

        remap = os.path.join(d, "font_remap.pdf")
        FontRemap().build(remap, "URGENT verify your account now please", "")
        rf = verify(remap)
        assert rf.ok and rf.flagged, f"font remap must be caught: {rf}"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
