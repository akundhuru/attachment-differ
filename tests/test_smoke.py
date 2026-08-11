"""
Smoke tests: the base contract is that no adapter EVER raises from extract() —
missing backends must surface as ok=False, not exceptions. These tests hold
even in a bare environment (no JRE, no tesseract), which is the point.

    python -m pytest tests/ -q      (or)      python tests/test_smoke.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractors.adapters import ALL_EXTRACTORS, _printable  # noqa: E402
from extractors.base import ExtractionResult, normalize      # noqa: E402
from differ import run_file                                   # noqa: E402

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus")
FIXTURE = os.path.join(CORPUS, "baseline", "hello.pdf")


def _ensure_fixture() -> None:
    if not os.path.exists(FIXTURE):
        from corpus.make_fixtures import main as make
        make()


def test_no_adapter_raises():
    _ensure_fixture()
    for ext in ALL_EXTRACTORS:
        r = ext.extract(FIXTURE)                 # must not raise for any adapter
        assert isinstance(r, ExtractionResult)
        assert r.ok in (True, False)
        if not r.ok:
            assert r.error, f"{ext.name} failed without an error string"


def test_pure_python_pdf_extractors_agree_on_baseline():
    _ensure_fixture()
    rep = run_file(FIXTURE)
    ok = {r.extractor: r.text for r in rep["results"] if r.ok}
    assert "pypdf" in ok and "pdfminer" in ok, "pure-python PDF path must run"
    # baseline fixture: the two pure-python extractors must not diverge
    e2e = [d for d in rep["divergences"] if d.kind == "extractor-vs-extractor"]
    assert e2e == [], f"unexpected baseline divergence: {e2e}"


def test_normalize_collapses_whitespace():
    assert normalize("  a\n\n b\t c ") == "a b c"
    assert normalize("") == ""


def test_printable_recovers_runs_across_binary():
    raw = b"\x00\x01Hello\x00\xffWorld\x00"
    out = _printable(raw)
    assert "Hello" in out and "World" in out


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
