"""
Content-detector interface.

A detector scores a piece of *extracted* text for maliciousness — it stands in
for the phishing/brand/content classifier a real email pipeline runs on
whatever its extractor pulled out of an attachment. The evasion claim is: feed
the same attachment's differing extractions to the detector and the verdict
flips, so a pipeline-aware attacker picks the extractor whose text scores benign.

Detectors never raise — a missing backend (no API key) returns ok=False, same
contract as the extractors.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Verdict:
    detector: str
    label: str                 # "malicious" | "benign"
    score: float               # 0..1 confidence that the text is malicious
    rationale: str = ""
    ok: bool = True
    error: Optional[str] = None


class Detector(ABC):
    name: str = "base"

    @abstractmethod
    def classify(self, text: str) -> Verdict:
        """Score `text`. MUST NOT raise; on backend failure return ok=False."""
        ...
