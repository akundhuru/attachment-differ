"""
PDF divergence vectors.

Each class builds a PDF that reads one way to a human (rendered pixels, the OCR
oracle) and another way to a text-layer parser (pypdf/pdfminer/tika/pdfbox).
The gap is the evasion primitive: a detector that scores parser output is blind
to what the victim actually reads.

Vectors here use only reportlab + PyMuPDF (fitz) + PIL — no external binaries.
"""
from __future__ import annotations
import os

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from .base import Mutation, MutationResult

ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
PAGE_W, PAGE_H = letter


# --------------------------------------------------------------------------
class InvisibleText(Mutation):
    """invisible-layer: decoy drawn with text render mode 3 (invisible) sits on
    top of the visible content. Parsers extract text regardless of render mode,
    so they read visible+decoy; the human/OCR sees only the visible layer.
    Classic 'parser reads what the human can't'."""
    name = "invisible_text"
    category = "invisible-layer"

    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        c = canvas.Canvas(out_path, pagesize=letter)
        # visible layer (render mode 0)
        t = c.beginText(72, PAGE_H - 96)
        t.setFont("Helvetica", 14)
        t.setTextRenderMode(0)
        for line in visible.splitlines():
            t.textLine(line)
        c.drawText(t)
        # invisible decoy (render mode 3)
        t2 = c.beginText(72, PAGE_H - 300)
        t2.setFont("Helvetica", 14)
        t2.setTextRenderMode(3)
        for line in decoy.splitlines():
            t2.textLine(line)
        c.drawText(t2)
        c.showPage()
        c.save()
        return MutationResult(
            out_path, self.name, self.category, "pdf",
            visible_text=visible,
            parser_text=_norm(visible + " " + decoy),
            expect_axis="extractor-vs-render",
            note="parsers read visible+decoy; OCR reads visible only")


# --------------------------------------------------------------------------
class TextAsImage(Mutation):
    """text-as-image: the entire visible message is rasterized to a PNG and
    embedded; there is NO text layer. Every text-layer parser comes back blank;
    only the OCR oracle recovers the content. Parsers are fully blind."""
    name = "text_as_image"
    category = "text-as-image"

    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        png = out_path + ".png"
        _render_text_png(visible, png)
        c = canvas.Canvas(out_path, pagesize=letter)
        c.drawImage(png, 36, 36, width=PAGE_W - 72, height=PAGE_H - 72,
                    preserveAspectRatio=True, anchor="n")
        c.showPage()
        c.save()
        os.remove(png)
        return MutationResult(
            out_path, self.name, self.category, "pdf",
            visible_text=visible,
            parser_text="",
            expect_axis="extractor-vs-render",
            note="no text layer; parsers blank, OCR recovers full text")


# --------------------------------------------------------------------------
class ImageWithDecoy(Mutation):
    """text-as-image + invisible-layer combined — the full evasion showcase.
    The phishing lure is an image (human/OCR sees it); a benign decoy paragraph
    is an invisible text layer (parsers read ONLY the benign decoy). A detector
    scoring parser output sees benign text and passes the malicious lure."""
    name = "image_with_decoy"
    category = "text-as-image"

    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        png = out_path + ".png"
        _render_text_png(visible, png)
        c = canvas.Canvas(out_path, pagesize=letter)
        c.drawImage(png, 36, 36, width=PAGE_W - 72, height=PAGE_H - 72,
                    preserveAspectRatio=True, anchor="n")
        t = c.beginText(72, PAGE_H - 120)
        t.setFont("Helvetica", 12)
        t.setTextRenderMode(3)  # invisible
        for line in decoy.splitlines():
            t.textLine(line)
        c.drawText(t)
        c.showPage()
        c.save()
        os.remove(png)
        return MutationResult(
            out_path, self.name, self.category, "pdf",
            visible_text=visible,
            parser_text=_norm(decoy),
            expect_axis="extractor-vs-render",
            note="parsers read benign decoy; OCR reads the malicious lure")


# --------------------------------------------------------------------------
class OptionalContentHidden(Mutation):
    """optional-content: decoy text placed in an Optional Content Group (OCG /
    PDF layer) whose default state is OFF. Renderers honor the layer state and
    omit it; text-layer parsers ignore OCG semantics and extract it anyway.
    Tests visibility-awareness rather than render mode."""
    name = "ocg_hidden"
    category = "optional-content"

    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_text((72, 96), visible, fontsize=14)
        ocg = doc.add_ocg("decoy-layer", on=False)   # hidden by default
        page.insert_text((72, 300), decoy, fontsize=14, oc=ocg)
        doc.save(out_path)
        doc.close()
        return MutationResult(
            out_path, self.name, self.category, "pdf",
            visible_text=visible,
            parser_text=None,   # depends on whether a parser honors OCG state
            expect_axis="extractor-vs-render",
            note="decoy in OFF layer; renderers hide it, parsers may extract it")


# --------------------------------------------------------------------------
class MalformedXref(Mutation):
    """malformed-recoverable: a structurally valid page, then the cross-
    reference offset (startxref) is corrupted. Lenient parsers rebuild the xref
    by scanning and recover the text; strict parsers error. Divergence surfaces
    as some extractors ok and others errored on the same bytes."""
    name = "malformed_xref"
    category = "malformed-recoverable"

    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        # 1. write a clean PDF
        c = canvas.Canvas(out_path, pagesize=letter)
        t = c.beginText(72, PAGE_H - 96)
        t.setFont("Helvetica", 14)
        for line in visible.splitlines():
            t.textLine(line)
        c.drawText(t)
        c.showPage()
        c.save()
        # 2. corrupt the startxref offset so the xref table can't be trusted
        with open(out_path, "rb") as fh:
            data = fh.read()
        marker = b"startxref"
        idx = data.rfind(marker)
        if idx != -1:
            nl = data.find(b"\n", idx + len(marker))
            if nl != -1:
                data = data[:idx + len(marker)] + b"\n9999999999" + data[nl:]
        with open(out_path, "wb") as fh:
            fh.write(data)
        return MutationResult(
            out_path, self.name, self.category, "pdf",
            visible_text=visible,
            parser_text=None,
            expect_axis="errored",
            note="corrupt startxref; lenient parsers recover, strict ones error")


# --------------------------------------------------------------------------
# helpers

def _norm(s: str) -> str:
    return " ".join(s.split()).strip()


def _render_text_png(text: str, out_png: str, width: int = 1200, pad: int = 60) -> None:
    """Rasterize `text` to a white PNG at a size tesseract reads reliably."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(ARIAL, 34)
    except Exception:
        font = ImageFont.load_default()
    lines = text.splitlines() or [""]
    line_h = 46
    height = pad * 2 + line_h * len(lines)
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        d.text((pad, y), line, fill="black", font=font)
        y += line_h
    img.save(out_png)


ALL_VECTORS = [
    InvisibleText(),
    TextAsImage(),
    ImageWithDecoy(),
    OptionalContentHidden(),
    MalformedXref(),
]
