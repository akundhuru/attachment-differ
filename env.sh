# Source this to enable the Java-bridge extractors (Tika, PDFBox) for a run:
#   source env.sh && python differ.py corpus/<file>.pdf
#
# The pure-Python extractors (pypdf, pdfminer, oletools) need none of this.
# The OCR channel additionally needs the tesseract binary (brew install tesseract).

REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# OpenJDK (keg-only Homebrew install); adjust if your JRE lives elsewhere.
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

export TIKA_JAR="$REPO/jars/tika-app.jar"
export PDFBOX_JAR="$REPO/jars/pdfbox-app.jar"

# Local secrets (gitignored) — e.g. `export ANTHROPIC_API_KEY=sk-ant-...` for
# the LLM detector. Never commit this file.
[ -f "$REPO/.env.local" ] && source "$REPO/.env.local"

# Activate the project venv if present.
[ -f "$REPO/.venv/bin/activate" ] && source "$REPO/.venv/bin/activate"
