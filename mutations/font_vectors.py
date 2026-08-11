"""
Font/encoding divergence vector — the PDF Mirage primitive (Markwood et al.,
USENIX '17), deferred from Week 3-4 as the Week 7 anchor.

A glyph renders as one character but the font's /ToUnicode CMap maps its code to
a *different* character. The rendered page (what the human and OCR see) is the
real message; every text-layer parser that trusts /ToUnicode extracts a
scrambled one. Here the scramble is rot13: extraction yields gibberish while the
page reads the lure — a text detector scoring the extraction sees no phishing
keywords.

Implementation: render the visible text with an embedded TrueType subset
(reportlab keeps an identity code->glyph and code->ToUnicode map), then rewrite
only the /ToUnicode destinations. The glyph program is untouched, so rendering
is unchanged; only extraction moves.
"""
from __future__ import annotations
import io
import re

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

from .base import Mutation, MutationResult

ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
PAGE_W, PAGE_H = letter
_BFCHAR = re.compile(r"<([0-9A-Fa-f]{2,4})>\s*<([0-9A-Fa-f]{4})>")

_registered = False


def _rot13_cp(cp: int) -> int:
    c = chr(cp)
    if "a" <= c <= "z":
        return ord("a") + (cp - ord("a") + 13) % 26
    if "A" <= c <= "Z":
        return ord("A") + (cp - ord("A") + 13) % 26
    return cp


def rot13_text(s: str) -> str:
    return "".join(chr(_rot13_cp(ord(ch))) for ch in s)


def _remap_cmap(cmap_text: str) -> str:
    def repl(m):
        code, dst = m.group(1), m.group(2)
        return f"<{code}> <{_rot13_cp(int(dst, 16)):04X}>"
    return _BFCHAR.sub(repl, cmap_text)


class FontRemap(Mutation):
    name = "font_remap"
    category = "font-encoding"

    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        global _registered
        if not _registered:
            pdfmetrics.registerFont(TTFont("RemapFont", ARIAL))
            _registered = True

        # 1. render the visible message with the embedded subset font
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.setFont("RemapFont", 15)
        y = PAGE_H - 96
        for line in visible.splitlines():
            c.drawString(72, y, line)
            y -= 24
        c.showPage()
        c.save()
        buf.seek(0)

        # 2. rewrite only /ToUnicode destinations (rot13); leave glyphs alone
        reader = PdfReader(buf)
        writer = PdfWriter()
        writer.append(reader)
        remapped = 0
        for page in writer.pages:
            fonts = page.get("/Resources", {}).get("/Font", {})
            for _k, ref in fonts.items():
                f = ref.get_object()
                tu = f.get("/ToUnicode")
                if tu is None:
                    continue
                obj = tu.get_object()
                data = obj.get_data().decode("latin-1")
                obj.set_data(_remap_cmap(data).encode("latin-1"))
                remapped += 1
        with open(out_path, "wb") as fh:
            writer.write(fh)

        return MutationResult(
            out_path, self.name, self.category, "pdf",
            visible_text=visible,
            parser_text=rot13_text(visible),
            expect_axis="extractor-vs-render",
            note="glyphs render the lure; /ToUnicode rot13 -> parsers extract gibberish",
            meta={"fonts_remapped": remapped})


ALL_FONT_VECTORS = [FontRemap()]
