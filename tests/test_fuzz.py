"""
Fuzz-harness unit tests: the mutators and the outcome classifier are the
load-bearing parts, so pin their behavior. Actual bug-hunting is a long
campaign, not a unit test.

    python tests/test_fuzz.py
"""
from __future__ import annotations
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fuzz.mutate import mutate, STRATEGIES              # noqa: E402
from corpus.make_fixtures import _plain_pdf             # noqa: E402


def test_mutate_preserves_header_and_changes_body():
    data = b"%PDF-1.4\n" + bytes(range(256)) * 20
    rng = random.Random(0)
    changed = 0
    for _ in range(50):
        out, strat = mutate(data, rng, keep_header=8)
        assert strat in STRATEGIES or strat == "noop"
        assert out[:8] == data[:8], "header must be preserved"
        if out != data:
            changed += 1
    assert changed > 0, "mutation never changed the input"


def test_mutate_is_deterministic_per_seed():
    data = b"%PDF-1.4\n" + os.urandom(4000)
    a = [mutate(data, random.Random(42))[0] for _ in range(5)]
    b = [mutate(data, random.Random(42))[0] for _ in range(5)]
    assert a == b, "same RNG seed must reproduce the same mutations"


def test_worker_classifies_valid_pdf_ok():
    with tempfile.TemporaryDirectory() as d:
        pdf = os.path.join(d, "ok.pdf")
        _plain_pdf(pdf, ["hello world", "second line"])
        proc = subprocess.run(
            [sys.executable, "-m", "fuzz.worker", "pypdf", pdf, "1024", "20"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert '"status": "ok"' in proc.stdout, proc.stdout


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
