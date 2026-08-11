"""
Detector-impact pass (D4) — does cross-extractor divergence flip a content
detector's verdict?

For each attachment:
  1. run every extractor (differ) → each yields its own text
  2. treat the OCR-render text as the human-visible ground truth
  3. classify each extractor's text AND the ground-truth text with each detector
  4. an EVASION occurs when the ground truth is scored malicious but a parser's
     text is scored benign — the detector, reading that parser's output, passes
     an attachment the victim experiences as a lure.

This is the significance test for the whole study: divergence matters iff it
changes what a detector decides.

    source env.sh                      # extractors (OCR + Tika/PDFBox)
    export ANTHROPIC_API_KEY=...       # optional: enables the LLM detector
    python detector_impact.py corpus/mutated

Writes results/detector_impact/<ts>/{per_file.jsonl, summary.json}.
"""
from __future__ import annotations
import json
import os
import sys
import time

from differ import run_file
from detectors import ALL_DETECTORS

EXTS = (".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls")
ORACLE = "ocr_render"


def _iter_files(root: str):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, _d, files in os.walk(root):
        for f in sorted(files):
            # skip internal helpers (e.g. _defense_baseline.pdf, a benign
            # baseline used by the D5 defense module — not a D4 attack subject)
            if f.startswith("_"):
                continue
            if f.lower().endswith(EXTS):
                yield os.path.join(dirpath, f)


def analyze_file(path: str, detectors) -> dict:
    rep = run_file(path)
    texts = {r.extractor: r.text for r in rep["results"] if r.ok}
    oracle_text = texts.get(ORACLE)

    file_rec = {"file": path, "format": rep["format"],
                "has_oracle": oracle_text is not None, "detectors": {}}

    for det in detectors:
        truth = det.classify(oracle_text) if oracle_text is not None else None
        per_extractor = {}
        evasions = []
        for name, text in texts.items():
            if name == ORACLE:
                continue
            v = det.classify(text)
            per_extractor[name] = {"label": v.label, "score": v.score, "ok": v.ok}
            # evasion: human sees malicious, this extractor reads benign
            if truth and truth.ok and v.ok \
                    and truth.label == "malicious" and v.label == "benign":
                evasions.append(name)
        file_rec["detectors"][det.name] = {
            "backend_ok": all(d["ok"] for d in per_extractor.values()) if per_extractor else True,
            "ground_truth": ({"label": truth.label, "score": truth.score, "ok": truth.ok}
                             if truth else None),
            "per_extractor": per_extractor,
            "evasions": evasions,
        }
    return file_rec


def aggregate(records: list[dict], detectors) -> dict:
    out = {"n_files": len(records), "detectors": {}}
    for det in detectors:
        malicious_truth_files = 0
        evasion_pairs = 0
        comparable_pairs = 0
        evaded_files = 0
        backend_ok = True
        for rec in records:
            d = rec["detectors"].get(det.name)
            if not d:
                continue
            gt = d["ground_truth"]
            if gt and not gt["ok"]:
                backend_ok = False
            n_ext = len(d["per_extractor"])
            comparable_pairs += n_ext
            if gt and gt["ok"] and gt["label"] == "malicious":
                malicious_truth_files += 1
                evasion_pairs += len(d["evasions"])
                if d["evasions"]:
                    evaded_files += 1
        out["detectors"][det.name] = {
            "backend_ok": backend_ok,
            "files_malicious_ground_truth": malicious_truth_files,
            "files_with_successful_evasion": evaded_files,
            "extractor_evasions": evasion_pairs,
            "comparable_extractor_pairs": comparable_pairs,
            "evasion_rate_over_extractor_pairs":
                round(evasion_pairs / comparable_pairs, 4) if comparable_pairs else 0.0,
        }
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python detector_impact.py <corpus-dir-or-file> [more ...]")
        return 1
    roots = argv
    detectors = ALL_DETECTORS
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "results", "detector_impact", stamp)
    os.makedirs(out_dir, exist_ok=True)

    def _iter_all(paths):
        for p in paths:
            yield from _iter_files(p)

    records = []
    with open(os.path.join(out_dir, "per_file.jsonl"), "w") as jf:
        for path in _iter_all(roots):
            rec = analyze_file(path, detectors)
            records.append(rec)
            jf.write(json.dumps(rec) + "\n")
            marks = " ".join(
                f"{dn}:{'/'.join(d['evasions']) or '-'}"
                for dn, d in rec["detectors"].items())
            print(f"  {os.path.basename(path):22} evasions[{marks}]")

    summary = aggregate(records, detectors)
    with open(os.path.join(out_dir, "summary.json"), "w") as sf:
        json.dump(summary, sf, indent=2)

    print("\n=== detector-impact summary ===")
    for name, d in summary["detectors"].items():
        status = "" if d["backend_ok"] else "  (backend unavailable — skipped)"
        print(f"{name}:{status}")
        print(f"  malicious ground-truth files: {d['files_malicious_ground_truth']}")
        print(f"  files evaded:                 {d['files_with_successful_evasion']}")
        print(f"  extractor evasions:           {d['extractor_evasions']}"
              f"/{d['comparable_extractor_pairs']}"
              f"  ({d['evasion_rate_over_extractor_pairs']:.2%})")
    print(f"\nwrote: {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
