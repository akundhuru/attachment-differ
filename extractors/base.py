"""
Extractor adapter interface.

Every content extractor (Tika, PDFBox, pypdf, pdfminer, oletools) and the
OCR ground-truth channel implement the same contract, so the differential
runner can treat them uniformly. Add a new extractor = add one subclass.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionResult:
    extractor: str                 # adapter name, e.g. "pypdf"
    text: str                      # normalized extracted text ("" if none)
    ok: bool                       # True if extraction ran without error
    error: Optional[str] = None    # error string if ok is False
    meta: dict = field(default_factory=dict)  # optional: page count, fonts, etc.


class Extractor(ABC):
    """One content extractor under test."""

    name: str = "base"
    # formats this adapter claims to handle, e.g. {"pdf"} or {"docx","xlsx"}
    formats: set[str] = set()

    @abstractmethod
    def extract(self, path: str) -> ExtractionResult:
        """Return normalized text for the file at `path`.

        MUST NOT raise: on failure, return ExtractionResult(ok=False, error=...).
        A silent-but-wrong extraction (ok=True, wrong text) is the interesting
        case — do not paper over it here; let the differ catch it.
        """
        ...

    def handles(self, fmt: str) -> bool:
        return fmt in self.formats


def normalize(text: str) -> str:
    """Shared normalization so divergences reflect real content differences,
    not whitespace noise. Keep this deliberately light — over-normalizing
    hides real divergences (that is the whole subject of the study).
    """
    if not text:
        return ""
    # collapse runs of whitespace, strip, lowercase-fold is NOT applied
    # (case can matter for brand impersonation). Tune consciously.
    return " ".join(text.split()).strip()
