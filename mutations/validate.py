"""
Generate every mutation vector, run it through the live differ, and check the
predicted divergence actually shows up. This is the Week 3-4 evidence: the
mutation module is only worth anything if its claimed divergence is measured.

    source env.sh && python -m mutations.validate

Writes fixtures to corpus/mutated/ and prints a pass/fail table plus, for each
vector, what each extractor actually saw.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mutations import ALL_VECTORS                      # noqa: E402
from differ import run_file                             # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "corpus", "mutated")

VISIBLE = ("URGENT: Your ACME account is suspended.\n"
           "Verify now at http://acme-verify.example/login\n"
           "Failure to act in 24 hours forfeits access.")
DECOY = ("Meeting notes: Q3 planning sync.\n"
         "Action items assigned. Thanks everyone.\n"
         "See the shared calendar for the next date.")


def _has_axis(rep: dict, axis: str) -> bool:
    if axis == "errored":
        return len(rep["errored"]) > 0
    return any(d.kind == axis for d in rep["divergences"])


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    for vec in ALL_VECTORS:
        path = os.path.join(OUT_DIR, f"{vec.name}.pdf")
        pred = vec.build(path, VISIBLE, DECOY)
        rep = run_file(path)
        ok = _has_axis(rep, pred.expect_axis)
        rows.append((vec.name, vec.category, pred.expect_axis, ok, rep, pred))

    # summary table
    print("\n=== mutation validation ===")
    print(f"{'vector':18} {'category':20} {'expect':22} {'detected?'}")
    print("-" * 74)
    npass = 0
    for name, cat, axis, ok, _rep, _pred in rows:
        npass += ok
        print(f"{name:18} {cat:20} {axis:22} {'PASS' if ok else 'FAIL'}")
    print("-" * 74)
    print(f"{npass}/{len(rows)} vectors produced their predicted divergence\n")

    # per-vector detail (what each extractor actually saw)
    for name, _cat, _axis, _ok, rep, pred in rows:
        print(f"--- {name} ---")
        print(f"    note: {pred.note}")
        for r in rep["results"]:
            tag = "ok " if r.ok else "ERR"
            preview = (r.text[:70] if r.ok else r.error) or "(empty)"
            print(f"    [{tag}] {r.extractor:11} {preview}")
        if rep["divergences"]:
            for d in rep["divergences"]:
                print(f"      ~ {d.score:.2f} {d.left} vs {d.right} ({d.kind})")
        print()

    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
