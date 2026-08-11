#!/usr/bin/env bash
# One-command reproduction of the harness results (D3 measurement, D4 detector
# impact, D5 defense gap) plus the test suite.
#
#   bash reproduce.sh
#
# Prereqs:
#   - Python 3.10+  (a .venv is created if missing)
#   - Optional native backends for the full extractor set / OCR oracle:
#       * a JRE + Tika/PDFBox jars   -> see requirements.txt / env.sh
#       * the `tesseract` binary     -> brew install tesseract
#     Without them, pure-Python extractors still run and those channels
#     self-disable cleanly.
#   - Optional LLM detector: export ANTHROPIC_API_KEY (else heuristic only).
set -euo pipefail
cd "$(dirname "$0")"

echo "== 0. environment =="
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet -r requirements.txt
fi
# env.sh activates .venv and wires TIKA_JAR/PDFBOX_JAR + .env.local if present
# shellcheck disable=SC1091
source env.sh 2>/dev/null || source .venv/bin/activate

echo "== 1. tests (must be green) =="
for t in test_smoke test_mutations test_report test_detectors test_defense test_fuzz; do
  python "tests/$t.py"
done

echo "== 2. corpora =="
python corpus/make_fixtures.py            # baseline/
python -m mutations.validate              # mutated/ + confirms each vector's divergence

echo "== 3. D3 divergence matrix (synthetic) =="
python matrix.py corpus/

echo "== 4. D4 detector impact (evasion) =="
# D4 scope = the five non-font content-masking vectors. The font vector
# (font_remap) is the subject of D5 (§8), not D4, so it is named out here; the
# benign _defense_baseline.pdf is auto-skipped. This reproduces the paper's
# 6/19 (31.6%) with heuristic and LLM agreeing exactly (§7).
python detector_impact.py \
  corpus/mutated/invisible_text.pdf \
  corpus/mutated/text_as_image.pdf \
  corpus/mutated/image_with_decoy.pdf \
  corpus/mutated/ocg_hidden.pdf \
  corpus/mutated/malformed_xref.pdf

echo "== 5. D5 defense gap (PDF Mirage font check vs. every vector) =="
python defense_gap.py

echo
echo "== done. outputs in results/runs/, results/detector_impact/, results/defense_gap/ =="
echo "For the real-corpus matrix, first normalize a public corpus into corpus/real/"
echo "(see REAL_CORPUS.md), then:  OCR_DISABLE=1 python matrix.py corpus/real"
