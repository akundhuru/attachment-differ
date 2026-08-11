"""
Mutation-builder tests that run in a bare environment (no JRE, no tesseract):
every vector must produce a non-trivial PDF and a well-formed prediction. The
*divergence* claims are validated separately by `mutations/validate.py`, which
needs the full extractor set live.

    python tests/test_mutations.py
"""
from __future__ import annotations
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mutations import ALL_VECTORS                      # noqa: E402
from mutations.base import MutationResult              # noqa: E402

VISIBLE = "Visible line one.\nVisible line two."
DECOY = "Decoy line one.\nDecoy line two."
VALID_AXES = {"extractor-vs-render", "extractor-vs-extractor", "errored"}


def test_every_vector_builds_a_pdf():
    with tempfile.TemporaryDirectory() as d:
        for vec in ALL_VECTORS:
            out = os.path.join(d, f"{vec.name}.pdf")
            res = vec.build(out, VISIBLE, DECOY)
            assert isinstance(res, MutationResult)
            assert os.path.exists(out), f"{vec.name} wrote no file"
            with open(out, "rb") as fh:
                head = fh.read(5)
            assert head == b"%PDF-", f"{vec.name} output is not a PDF"
            assert os.path.getsize(out) > 400, f"{vec.name} output is trivially small"


def test_predictions_are_well_formed():
    with tempfile.TemporaryDirectory() as d:
        for vec in ALL_VECTORS:
            res = vec.build(os.path.join(d, f"{vec.name}.pdf"), VISIBLE, DECOY)
            assert res.vector == vec.name
            assert res.category == vec.category
            assert res.expect_axis in VALID_AXES
            assert res.visible_text, f"{vec.name} has no visible_text prediction"


def test_no_png_sidecar_left_behind():
    with tempfile.TemporaryDirectory() as d:
        for vec in ALL_VECTORS:
            vec.build(os.path.join(d, f"{vec.name}.pdf"), VISIBLE, DECOY)
        leftovers = [f for f in os.listdir(d) if f.endswith(".png")]
        assert leftovers == [], f"image vectors leaked sidecars: {leftovers}"


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
