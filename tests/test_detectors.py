"""
Heuristic-detector tests (offline, no API). The LLM detector needs credentials
and is exercised by detector_impact.py when a key is present.

    python tests/test_detectors.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detectors.heuristic import HeuristicDetector   # noqa: E402
from detectors.base import Verdict                   # noqa: E402
from detectors.llm import LLMDetector                # noqa: E402

LURE = ("URGENT: Your ACME account is suspended. Verify your account now at "
        "http://acme-verify.example/login within 24 hours or access is forfeited.")
BENIGN = ("Meeting notes: Q3 planning sync. Action items assigned. "
          "Thanks everyone. See the shared calendar for the next date.")


def test_heuristic_flags_lure_and_passes_benign():
    d = HeuristicDetector()
    lure = d.classify(LURE)
    benign = d.classify(BENIGN)
    assert lure.label == "malicious" and lure.score >= 0.5, lure
    assert benign.label == "benign" and benign.score < 0.5, benign
    # this gap is exactly the evasion the study demonstrates
    assert lure.score > benign.score


def test_heuristic_empty_is_benign_and_ok():
    v = HeuristicDetector().classify("")
    assert v.ok and v.label == "benign" and v.score == 0.0


def test_heuristic_is_deterministic():
    d = HeuristicDetector()
    assert d.classify(LURE).score == d.classify(LURE).score


def test_llm_detector_degrades_without_credentials():
    # No API key in the test env -> must return ok=False, never raise.
    v = LLMDetector().classify(LURE)
    assert isinstance(v, Verdict)
    if not v.ok:
        assert v.error


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
