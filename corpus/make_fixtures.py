"""
Generate small, license-clean PDF fixtures so the harness has something to run
before the public corpora are wired in. These are *baseline* fixtures — plain
documents where every extractor should agree. They prove the pipeline runs and
establish the "agreement" floor against which Week 3-4 mutation vectors (which
deliberately induce divergence) are measured.

    python corpus/make_fixtures.py

Writes into the same directory as this file.
"""
from __future__ import annotations
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(HERE, "baseline")

PLAIN_BODY = [
    "Invoice 4471 — ACME Supply Co.",
    "Amount due: $1,240.00",
    "Please remit payment within 30 days to accounts@acme.example.",
    "Wire transfer details are attached on page two.",
]


def _plain_pdf(path: str, lines: list[str]) -> None:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    c = canvas.Canvas(path, pagesize=letter)
    y = 720
    for line in lines:
        c.drawString(72, y, line)
        y -= 24
    c.showPage()
    c.save()


def main() -> None:
    os.makedirs(BASELINE, exist_ok=True)
    fixtures = {
        "invoice_plain.pdf": PLAIN_BODY,
        "hello.pdf": ["Hello world.", "This is a single-line baseline fixture."],
    }
    for name, lines in fixtures.items():
        out = os.path.join(BASELINE, name)
        _plain_pdf(out, lines)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
