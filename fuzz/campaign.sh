#!/usr/bin/env bash
# Refined CVE campaign — runs each parser SEQUENTIALLY (no CPU contention) with a
# small input-size cap (so a HANG means small-input/disproportionate-time, the
# real DoS signature) and a large per-run timeout (separates "slow" from
# "infinite"). Format-matched seeds per target.
#
#   source env.sh && nohup bash fuzz/campaign.sh > results/fuzz/campaign.log 2>&1 &
#
set -u
cd "$(dirname "$0")/.."
source env.sh

CAP=256          # KB — small enough that >timeout is clearly disproportionate
PY_TO=45         # seconds per python run
JV_TO=60         # seconds per java run (JVM startup + parse)

run() { # target seeds iters timeout seed
  echo ">>> $(date +%H:%M:%S) target=$1 iters=$3 cap=${CAP}KB timeout=$4s"
  python -m fuzz.fuzz --seeds "$2" --targets "$1" --iters "$3" \
    --timeout "$4" --max-input-kb "$CAP" --seed "$5"
}

# native MuPDF first — cheapest to iterate, best memory-safety candidate
run pymupdf  corpus/real/pdfseeds 15000 "$PY_TO" 101
run pdfminer corpus/real/pdfseeds  6000 "$PY_TO" 102
run pypdf    corpus/real/pdfseeds  6000 "$PY_TO" 103
run oletools corpus/real/oleseeds  4000 "$PY_TO" 104
run tika     corpus/real/pdfseeds  1500 "$JV_TO" 105
run pdfbox   corpus/real/pdfseeds  1500 "$JV_TO" 106

echo ">>> $(date +%H:%M:%S) campaign done"
echo "=== bug-class findings across all runs ==="
find results/fuzz -path '*/findings/*' -type f 2>/dev/null | sed 's|.*/findings/||' | sort
