"""
Concrete extractor adapters.

PURE-PYTHON (run anywhere): pypdf, pdfminer, oletools, ocr_render (needs the
                            tesseract binary + a render backend).
JAVA BRIDGE (need a JRE)  : tika, pdfbox.

Every adapter honors the base contract: extract() MUST NOT raise. When a
dependency is missing (no JRE, no tesseract, package not installed) the adapter
returns ExtractionResult(ok=False, error=...) so the differ records a clean
"this extractor was blind here" rather than crashing the run. A missing
extractor is itself signal — a pipeline that silently drops an extractor is
exactly the blind spot this study measures.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import warnings

from .base import Extractor, ExtractionResult, normalize

warnings.filterwarnings("ignore")


# ----------------------------- WORKING (pure-python) -----------------------------

class PyPDFExtractor(Extractor):
    name = "pypdf"
    formats = {"pdf"}

    def extract(self, path: str) -> ExtractionResult:
        try:
            from pypdf import PdfReader
            pages = PdfReader(path).pages
            text = "\n".join((p.extract_text() or "") for p in pages)
            return ExtractionResult(self.name, normalize(text), ok=True,
                                    meta={"pages": len(pages)})
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False, error=repr(e))


class PDFMinerExtractor(Extractor):
    name = "pdfminer"
    formats = {"pdf"}

    def extract(self, path: str) -> ExtractionResult:
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(path) or ""
            return ExtractionResult(self.name, normalize(text), ok=True)
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False, error=repr(e))


class OletoolsExtractor(Extractor):
    """oletools/olefile for OLE + legacy/macro-bearing Office docs. Pure Python.

    Content of interest here is not just body prose — for the threat-pipeline
    question, the security-relevant "content" a detector must see includes VBA
    macro source. We pull, in order of signal:
      1. VBA macro source (olevba)   — the payload a detector should score
      2. printable strings from OLE streams (WordDocument, Workbook, etc.)
    and concatenate them. Divergence between this and what a PDF/render channel
    sees for the *same logical document* is the OLE arm of the study.
    """
    name = "oletools"
    formats = {"ole", "doc", "xls", "ppt", "docx", "xlsm", "msg"}

    def extract(self, path: str) -> ExtractionResult:
        try:
            import olefile  # noqa: F401  (presence check)
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False,
                                    error=f"oletools not installed: {e!r}")

        chunks: list[str] = []
        meta: dict = {}

        # 1. VBA macros — the detector-relevant payload
        try:
            from oletools.olevba import VBA_Parser
            vp = VBA_Parser(path)
            if vp.detect_vba_macros():
                macros = [code for (_f, _s, _n, code) in vp.extract_macros() if code]
                if macros:
                    chunks.append("\n".join(macros))
                    meta["vba_macros"] = len(macros)
            vp.close()
        except Exception as e:
            meta["vba_error"] = repr(e)

        # 2. printable text from OLE streams (legacy binary formats)
        try:
            import olefile
            if olefile.isOleFile(path):
                ole = olefile.OleFileIO(path)
                for stream in ole.listdir():
                    name = "/".join(stream)
                    if any(k in name for k in ("WordDocument", "Workbook",
                                               "Book", "PowerPoint", "Text")):
                        raw = ole.openstream(stream).read()
                        chunks.append(_printable(raw))
                meta["ole"] = True
                ole.close()
        except Exception as e:
            meta["ole_error"] = repr(e)

        text = normalize("\n".join(c for c in chunks if c))
        # Only report failure if we recovered nothing AND every path errored.
        if not text and "vba_macros" not in meta and not meta.get("ole") \
                and ("vba_error" in meta or "ole_error" in meta):
            err = meta.get("vba_error") or meta.get("ole_error")
            return ExtractionResult(self.name, "", ok=False, error=err, meta=meta)
        return ExtractionResult(self.name, text, ok=True, meta=meta)


class OCRGroundTruth(Extractor):
    """NOT a parser — the 'what the human sees' oracle. Render each page to a
    raster image (PyMuPDF), then OCR (pytesseract). This is the reference the
    parser extractors are diffed AGAINST: if a parser's text diverges from the
    OCR of the rendered page, the parser is reading something the human isn't.

    Needs the tesseract binary on PATH. Absent it, returns ok=False so the run
    proceeds with extractor-vs-extractor divergence only.
    """
    name = "ocr_render"
    formats = {"pdf", "docx", "xlsx", "pptx"}  # via render-to-image
    dpi = 200

    def extract(self, path: str) -> ExtractionResult:
        # OCR_DISABLE=1 skips the render oracle entirely — useful for bulk
        # extractor-vs-extractor runs over large real corpora where the slow
        # render channel isn't the axis under study.
        if os.environ.get("OCR_DISABLE"):
            return ExtractionResult(self.name, "", ok=False, error="OCR disabled (OCR_DISABLE)")
        if not shutil.which("tesseract"):
            return ExtractionResult(self.name, "", ok=False,
                                    error="tesseract binary not on PATH "
                                          "(install: brew install tesseract)")
        try:
            import io
            import fitz  # PyMuPDF
            import pytesseract
            from PIL import Image
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False,
                                    error=f"OCR deps missing: {e!r}")

        # Optional page cap for large real-world docs (OCR is the slow channel).
        # OCR_MAX_PAGES=N renders only the first N pages; unset = all pages.
        try:
            max_pages = int(os.environ.get("OCR_MAX_PAGES", "0")) or None
        except ValueError:
            max_pages = None

        try:
            doc = fitz.open(path)
            zoom = self.dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            page_texts = []
            for i, page in enumerate(doc):
                if max_pages and i >= max_pages:
                    break
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                page_texts.append(pytesseract.image_to_string(img) or "")
            n_total = doc.page_count
            doc.close()
            text = normalize("\n".join(page_texts))
            return ExtractionResult(self.name, text, ok=True,
                                    meta={"pages_ocred": len(page_texts),
                                          "pages_total": n_total, "dpi": self.dpi})
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False, error=repr(e))


# ------------------------------ JAVA BRIDGE ------------------------------

class TikaExtractor(Extractor):
    """Apache Tika. Two backends, tried in order:
      A. TIKA_JAR env var → `java -jar $TIKA_JAR --text <file>` (pinned, preferred)
      B. the `tika` python package (auto-downloads a server jar; needs a JRE)
    Multi-format: PDF, OOXML, OLE — Tika uses PDFBox under the hood for PDFs, so
    tika-vs-pdfbox divergence is itself a finding worth logging.
    """
    name = "tika"
    formats = {"pdf", "docx", "xlsx", "pptx", "ole", "doc", "xls", "ppt"}

    def extract(self, path: str) -> ExtractionResult:
        jar = os.environ.get("TIKA_JAR")
        java = shutil.which("java")
        # backend A: pinned jar via subprocess
        if jar and java:
            try:
                out = subprocess.run(
                    [java, "-jar", jar, "--text", path],
                    capture_output=True, text=True, timeout=120,
                )
                if out.returncode != 0:
                    return ExtractionResult(self.name, "", ok=False,
                                            error=f"tika jar rc={out.returncode}: "
                                                  f"{out.stderr[:200]}")
                return ExtractionResult(self.name, normalize(out.stdout), ok=True,
                                        meta={"backend": "jar"})
            except Exception as e:
                return ExtractionResult(self.name, "", ok=False, error=repr(e))
        # backend B: tika-python package
        try:
            from tika import parser as tika_parser
        except Exception:
            return ExtractionResult(
                self.name, "", ok=False,
                error="no Tika backend: set TIKA_JAR (+JRE) or `pip install tika`")
        try:
            parsed = tika_parser.from_file(path)
            return ExtractionResult(self.name, normalize(parsed.get("content") or ""),
                                    ok=True, meta={"backend": "tika-python"})
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False, error=repr(e))


class PDFBoxExtractor(Extractor):
    """Apache PDFBox via subprocess: `java -jar $PDFBOX_JAR export:text -i in -o out`.
    PDF-only; the contrast partner to Tika (Tika embeds PDFBox for PDFs, so a
    tika-vs-pdfbox gap points at Tika's configuration, not the parser).

    We route text to a temp file with `-o`, NOT `-console`: console mode emits a
    banner line ("The encoding parameter is ignored...") into stdout that would
    contaminate the extracted text and register as a false divergence.
    """
    name = "pdfbox"
    formats = {"pdf"}

    def extract(self, path: str) -> ExtractionResult:
        jar = os.environ.get("PDFBOX_JAR")
        java = shutil.which("java")
        if not (jar and java):
            return ExtractionResult(
                self.name, "", ok=False,
                error="no PDFBox backend: set PDFBOX_JAR and install a JRE")
        import tempfile
        outfd, outpath = tempfile.mkstemp(suffix=".txt")
        os.close(outfd)
        try:
            out = subprocess.run(
                [java, "-jar", jar, "export:text", "-i", path, "-o", outpath],
                capture_output=True, text=True, timeout=120,
            )
            if out.returncode != 0:
                return ExtractionResult(self.name, "", ok=False,
                                        error=f"pdfbox rc={out.returncode}: "
                                              f"{out.stderr[:200]}")
            with open(outpath, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            return ExtractionResult(self.name, normalize(text), ok=True)
        except Exception as e:
            return ExtractionResult(self.name, "", ok=False, error=repr(e))
        finally:
            try:
                os.remove(outpath)
            except OSError:
                pass


# ------------------------------ helpers ------------------------------

def _printable(raw: bytes, min_run: int = 4) -> str:
    """Pull runs of printable text out of a raw OLE stream. Legacy .doc/.xls
    interleave text with binary formatting records; this recovers the readable
    spans without a full format parser. Deliberately crude — a detector fed the
    same stream sees roughly this."""
    out, cur = [], []
    for byte in raw:
        if 32 <= byte < 127 or byte in (9, 10, 13):
            cur.append(chr(byte))
        else:
            if len(cur) >= min_run:
                out.append("".join(cur))
            cur = []
    if len(cur) >= min_run:
        out.append("".join(cur))
    return " ".join(out)


# Registry the runner imports. Adapters self-report ok=False when their backend
# is unavailable, so it is safe to enable all of them: unavailable ones show up
# as "errored" in the report instead of crashing the run.
ALL_EXTRACTORS = [
    PyPDFExtractor(),
    PDFMinerExtractor(),
    OletoolsExtractor(),
    OCRGroundTruth(),
    TikaExtractor(),
    PDFBoxExtractor(),
]
