"""
Mutation interface — programmatic divergence vectors.

A Mutation takes a *visible* message (what a human reading the rendered page
sees) and a *decoy* message (what an attacker wants the text-layer parsers to
read instead) and emits an attachment that induces a specific, predicted
divergence. Each build returns a MutationResult carrying that prediction, so
the validation harness can check the harness actually detects what the vector
was designed to do — the mutation module is only trustworthy if its claimed
divergence is measured, not assumed.

Taxonomy categories (see TAXONOMY.md):
    invisible-layer · text-as-image · optional-content · font-encoding ·
    container-polyglot · malformed-recoverable
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MutationResult:
    path: str                       # generated file
    vector: str                     # mutation name, e.g. "invisible_text"
    category: str                   # taxonomy class
    fmt: str                        # "pdf" | "docx" | ...
    visible_text: str               # what the render/OCR oracle should see
    parser_text: Optional[str]      # expected text-layer extraction; None = varies, "" = blank
    expect_axis: str                # "extractor-vs-render" | "extractor-vs-extractor" | "errored"
    note: str = ""
    meta: dict = field(default_factory=dict)


class Mutation(ABC):
    name: str = "base"
    category: str = "base"
    fmt: str = "pdf"

    @abstractmethod
    def build(self, out_path: str, visible: str, decoy: str) -> MutationResult:
        """Write a mutated attachment to out_path and return its prediction.

        `visible` is the human-facing content; `decoy` is what the attacker
        wants parsers to read. Not every vector uses both (text-as-image has no
        decoy layer); unused args are ignored by that vector.
        """
        ...
