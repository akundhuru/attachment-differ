#!/usr/bin/env bash
# Warm Apache Tika server for bulk corpus runs (matrix.py --jobs).
#
# One JVM handles every file over HTTP instead of one JVM per file
# (~7 s/file cold-start -> ~ms/file), which is what makes a multi-thousand
# document corpus tractable. Text is byte-identical to `tika-app.jar --text`
# for a given OCR strategy.
#
#   ./tika_server.sh start     # launch on port 9998 (background)
#   ./tika_server.sh stop
#   ./tika_server.sh status
#
# Then point the harness at it:
#   export TIKA_SERVER_URL=http://localhost:9998
#   OCR_DISABLE=1 python matrix.py corpus/real --jobs 8
#
# OCR CONFIG (the confound the paper flags — Tika silently OCRs embedded images):
#   Default here launches WITHOUT tesseract on the server's PATH, and the adapter
#   sends X-Tika-PDFOcrStrategy=no_ocr, so Tika does pure text extraction:
#   deterministic, reproducible, comparable to pypdf/pdfminer/pdfbox. This is the
#   paper's recommended NO_OCR measurement.
#
#   To measure the OCR-on (hybrid parser+OCR) regime instead, launch with
#   tesseract on PATH (TIKA_WITH_OCR=1 ./tika_server.sh start) and run the
#   harness with TIKA_OCR_STRATEGY=ocr_and_text_extraction.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${TIKA_PORT:-9998}"
JAR="$PWD/jars/tika-server-standard.jar"
JAVA_BIN_DIR="${JAVA_BIN_DIR:-/opt/homebrew/opt/openjdk/bin}"
PIDFILE="/tmp/tika_server_${PORT}.pid"
LOG="/tmp/tika_server_${PORT}.log"

start() {
  if [ ! -f "$JAR" ]; then
    echo "missing $JAR — download the matching version:"
    echo "  curl -fsSL https://repo1.maven.org/maven2/org/apache/tika/tika-server-standard/<VER>/tika-server-standard-<VER>.jar -o $JAR"
    echo "  (<VER> must match jars/tika-app.jar; check: java -jar jars/tika-app.jar --version)"
    exit 1
  fi
  if curl -fsS "http://localhost:$PORT/version" >/dev/null 2>&1; then
    echo "already running on :$PORT"; return
  fi
  # PATH: java always; tesseract only when explicitly measuring the OCR-on regime
  if [ "${TIKA_WITH_OCR:-0}" = "1" ]; then
    RUNPATH="$JAVA_BIN_DIR:/opt/homebrew/bin:$PATH"
    echo "launching WITH tesseract (OCR-on regime possible via TIKA_OCR_STRATEGY)"
  else
    RUNPATH="$JAVA_BIN_DIR:/usr/bin:/bin"
    echo "launching WITHOUT tesseract (deterministic NO_OCR pure-text extraction)"
  fi
  PATH="$RUNPATH" nohup java -jar "$JAR" --port "$PORT" >"$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 60); do
    curl -fsS "http://localhost:$PORT/version" >/dev/null 2>&1 && { echo "ready on :$PORT ($(curl -fsS http://localhost:$PORT/version))"; return; }
    sleep 0.5
  done
  echo "server did not become ready — see $LOG"; exit 1
}

stop() {
  pkill -f "tika-server-standard.jar --port $PORT" 2>/dev/null && echo "stopped :$PORT" || echo "not running"
  rm -f "$PIDFILE"
}

status() {
  if curl -fsS "http://localhost:$PORT/version" >/dev/null 2>&1; then
    echo "up on :$PORT ($(curl -fsS http://localhost:$PORT/version))"
  else
    echo "down"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  restart) stop; start ;;
  *) echo "usage: $0 {start|stop|status|restart}"; exit 1 ;;
esac
