"""
Differential runner — the core measurement loop.

For one file: run every applicable extractor, then compute pairwise divergence
between them AND against the OCR ground-truth oracle. The whole thesis lives in
the output of this function: where do extractors disagree, and does any one of
them silently return content that differs from what the human sees?

Usage (once adapters are implemented):
    python differ.py corpus/sample.pdf
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from itertools import combinations
from difflib import SequenceMatcher

from extractors.adapters import ALL_EXTRACTORS
from extractors.base import ExtractionResult


def similarity(a: str, b: str) -> float:
    """1.0 = identical, 0.0 = nothing in common. Cheap first-pass metric;
    swap for token-set / embedding distance in Week 5-6 if needed."""
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class Divergence:
    left: str
    right: str
    score: float          # similarity 0..1
    kind: str             # "extractor-vs-extractor" | "extractor-vs-render"


def detect_format(path: str) -> str:
    p = path.lower()
    for ext in ("pdf", "docx", "xlsx", "pptx", "doc", "xls", "ppt"):
        if p.endswith("." + ext):
            return ext
    return "unknown"


def run_file(path: str, threshold: float = 0.95) -> dict:
    fmt = detect_format(path)
    results: list[ExtractionResult] = [
        e.extract(path) for e in ALL_EXTRACTORS if e.handles(fmt)
    ]
    ok = [r for r in results if r.ok]

    # separate the render/OCR oracle from the parsers
    oracle = next((r for r in ok if r.extractor == "ocr_render"), None)
    parsers = [r for r in ok if r.extractor != "ocr_render"]

    divergences: list[Divergence] = []

    # extractor vs extractor
    for a, b in combinations(parsers, 2):
        s = similarity(a.text, b.text)
        if s < threshold:
            divergences.append(Divergence(a.extractor, b.extractor, s,
                                          "extractor-vs-extractor"))

    # each extractor vs the human-render oracle (the interesting axis)
    if oracle:
        for p in parsers:
            s = similarity(p.text, oracle.text)
            if s < threshold:
                divergences.append(Divergence(p.extractor, oracle.extractor, s,
                                              "extractor-vs-render"))

    return {
        "file": path,
        "format": fmt,
        "results": results,
        "divergences": sorted(divergences, key=lambda d: d.score),
        "errored": [r.extractor for r in results if not r.ok],
    }


def _print_report(rep: dict) -> None:
    print(f"=== {rep['file']}  [{rep['format']}] ===")
    for r in rep["results"]:
        status = "ok " if r.ok else "ERR"
        preview = (r.text[:80] if r.ok else r.error) or ""
        print(f"  [{status}] {r.extractor:12} {preview}")
    if rep["divergences"]:
        print("  -- divergences (lower score = wider gap) --")
        for d in rep["divergences"]:
            print(f"     {d.score:.2f}  {d.left} vs {d.right}  ({d.kind})")
    else:
        print("  -- no divergence above threshold --")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python differ.py <file>")
        sys.exit(1)
    _print_report(run_file(sys.argv[1]))
