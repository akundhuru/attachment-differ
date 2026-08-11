from .base import Mutation, MutationResult
from .pdf_vectors import ALL_VECTORS as _PDF_VECTORS
from .font_vectors import ALL_FONT_VECTORS

# font-encoding (PDF Mirage) vector is the Week 7 anchor; include it in the full set
ALL_VECTORS = _PDF_VECTORS + ALL_FONT_VECTORS

__all__ = ["Mutation", "MutationResult", "ALL_VECTORS"]
