"""
Aggregation-math tests (bare environment) — the divergence-rate statistics are
the core paper result, so their arithmetic is pinned with synthetic records
rather than trusted to a live run.

    python tests/test_report.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from report import aggregate, serialize_report, pairs_csv   # noqa: E402


def _rec(group, fmt, results, divergences):
    """results: list of (extractor, ok, text_len). divergences: list of (a,b,kind)."""
    return {
        "file": f"{group}/f", "group": group, "format": fmt,
        "results": [{"extractor": e, "ok": ok, "error": None if ok else "x",
                     "text_len": n, "text_sha1": "h" if n else "", "preview": "",
                     "meta": {}} for (e, ok, n) in results],
        "errored": [e for (e, ok, _n) in results if not ok],
        "divergences": [{"left": a, "right": b, "score": 0.1, "kind": k}
                        for (a, b, k) in divergences],
    }


def test_pairwise_and_overall_rates():
    records = [
        # file1: pypdf & pdfminer both ok, agree (no divergence)
        _rec("baseline", "pdf",
             [("pypdf", True, 100), ("pdfminer", True, 100)], []),
        # file2: pypdf & pdfminer both ok, diverge
        _rec("mutated", "pdf",
             [("pypdf", True, 100), ("pdfminer", True, 50)],
             [("pypdf", "pdfminer", "extractor-vs-extractor")]),
    ]
    s = aggregate(records, threshold=0.95)
    assert s["total_pair_comparisons"] == 2
    assert s["total_divergent_comparisons"] == 1
    assert s["overall_divergence_rate"] == 0.5
    pair = next(p for p in s["pairs"] if p["pair"] == "pdfminer|pypdf")
    assert pair["comparable"] == 2 and pair["divergent"] == 1
    assert pair["divergence_rate"] == 0.5


def test_blind_spot_counts_error_and_empty():
    records = [
        # pypdf errored while pdfminer recovered text -> pypdf blind
        _rec("mutated", "pdf",
             [("pypdf", False, 0), ("pdfminer", True, 80)], []),
        # pdfbox ok-but-empty while ocr recovered text -> pdfbox blind
        _rec("mutated", "pdf",
             [("pdfbox", True, 0), ("ocr_render", True, 80)], []),
    ]
    s = aggregate(records)
    by = {e["extractor"]: e for e in s["extractors"]}
    assert by["pypdf"]["blind"] == 1 and by["pypdf"]["error"] == 1
    assert by["pdfbox"]["blind"] == 1 and by["pdfbox"]["empty"] == 1
    assert by["ocr_render"]["blind"] == 0
    assert by["pdfminer"]["blind"] == 0


def test_no_divergence_when_only_one_extractor_ok():
    # a lone ok extractor forms no comparable pair
    records = [_rec("mutated", "pdf",
                    [("pypdf", True, 100), ("pdfminer", False, 0)], [])]
    s = aggregate(records)
    assert s["total_pair_comparisons"] == 0
    assert s["overall_divergence_rate"] == 0.0


def test_group_breakdown_and_csv():
    records = [
        _rec("baseline", "pdf", [("a", True, 10), ("b", True, 10)], []),
        _rec("mutated", "pdf", [("a", True, 10), ("b", True, 10)],
             [("a", "b", "extractor-vs-render")]),
    ]
    s = aggregate(records)
    groups = {g["group"]: g for g in s["by_group"]}
    assert groups["baseline"]["rate"] == 0.0
    assert groups["mutated"]["rate"] == 1.0
    csv = pairs_csv(s)
    assert csv.startswith("pair,comparable,divergent,divergence_rate")
    assert "a|b" in csv


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
