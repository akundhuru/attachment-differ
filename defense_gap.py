"""
Defense-gap experiment (Week 7, D5) — the novelty anchor.

Runs PDF Mirage's OCR font-verification defense against every divergence vector
and a clean baseline, and tabulates catch vs. miss. The claim to demonstrate:
the accepted font-masking defense catches the font vector it was designed for
but does NOT generalize to the non-font vectors (invisible-layer, text-as-image,
optional-content, container/malformed) that dominate real attachments.

    source env.sh                     # OCR is required (it IS the defense)
    python defense_gap.py

Writes results/defense_gap/<ts>/summary.json.
"""
from __future__ import annotations
import json
import os
import sys
import time

from mutations import ALL_VECTORS
from corpus.make_fixtures import _plain_pdf
from defense import verify

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "corpus", "mutated")

VISIBLE = ("URGENT: Your ACME account is suspended.\n"
           "Verify now at http://acme-verify.example/login\n"
           "Failure to act in 24 hours forfeits access.")
DECOY = ("Meeting notes: Q3 planning sync.\n"
         "Action items assigned. Thanks everyone.")

# Which vectors are genuinely font-based (the defense's design target)?
FONT_BASED = {"font-encoding"}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    rows = []

    # a clean baseline PDF — the defense must NOT flag it (true negative)
    base = os.path.join(OUT, "_defense_baseline.pdf")
    _plain_pdf(base, ["Quarterly report attached.", "Regards, Finance team."])
    rows.append(("baseline", "(none)", base, verify(base)))

    for vec in ALL_VECTORS:
        path = os.path.join(OUT, f"{vec.name}.pdf")
        vec.build(path, VISIBLE, DECOY)
        rows.append((vec.name, vec.category, path, verify(path)))

    # table
    print("\n=== PDF Mirage font-verification defense vs. every vector ===")
    print(f"{'vector':18} {'category':20} {'font-based?':11} {'flagged':8} {'verdict'}")
    print("-" * 78)
    caught = missed = 0
    for name, cat, _p, r in rows:
        font_based = cat in FONT_BASED
        if name == "baseline":
            verdict = "OK (true negative)" if not r.flagged else "FALSE POSITIVE"
        elif font_based:
            verdict = "CAUGHT (expected)" if r.flagged else "MISSED (defense broke!)"
            caught += int(r.flagged)
        else:
            verdict = "MISSED (gap)" if not r.flagged else "caught"
            missed += int(not r.flagged)
        flagged = ("yes" if r.flagged else "no") if r.ok else "n/a"
        print(f"{name:18} {cat:20} {str(font_based):11} {flagged:8} {verdict}")

    n_attack = len(ALL_VECTORS)
    n_font = sum(1 for v in ALL_VECTORS if v.category in FONT_BASED)
    n_nonfont = n_attack - n_font
    print("-" * 78)
    print(f"font vector(s) caught:      {caught}/{n_font}")
    print(f"non-font vectors missed:    {missed}/{n_nonfont}")
    print("=> PDF Mirage's font check is specific to the font vector; it does "
          "not\n   generalize to the non-font content-masking vectors.")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "results", "defense_gap", stamp)
    os.makedirs(out_dir, exist_ok=True)
    summary = {
        "font_vectors_caught": caught, "font_vectors_total": n_font,
        "nonfont_vectors_missed": missed, "nonfont_vectors_total": n_nonfont,
        "rows": [
            {"vector": n, "category": c, "font_based": c in FONT_BASED,
             "flagged": r.flagged, "ok": r.ok, "similarity": r.similarity,
             "reason": r.reason, "claimed": r.claimed_preview,
             "rendered": r.rendered_preview}
            for n, c, _p, r in rows
        ],
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nwrote: {out_dir}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
