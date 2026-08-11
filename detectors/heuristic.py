"""
Deterministic keyword/URL phishing heuristic — the zero-cost offline detector.

Not a state-of-the-art model; a transparent, reproducible stand-in that scores
the signals a content classifier keys on (urgency, credential/action lures,
threats, money movement, links). Because it is deterministic it makes the
detector-impact experiment reproducible with no API spend, and it is a fair
baseline: if divergence flips even this simple detector, it will flip a real one.
"""
from __future__ import annotations
import re

from .base import Detector, Verdict

# weighted signal groups (weight, pattern)
SIGNALS = [
    (0.30, r"\b(urgent|immediately|act now|final notice|expires?|within \d+ hours?|24 hours?)\b"),
    (0.30, r"\b(verify|confirm|validate|re-?activate|update) (your )?(account|password|identity|details)\b"),
    (0.25, r"\b(suspend|suspended|locked|disabled|terminated|forfeit|restricted)\b"),
    (0.20, r"\b(login|log in|sign in|click (here|below)|follow (this|the) link)\b"),
    (0.20, r"\b(wire|remit|payment|invoice|transfer|bank|routing|beneficiary)\b"),
    (0.25, r"https?://[^\s]+"),
    (0.20, r"\b(password|credentials?|ssn|social security|one-?time (code|password)|otp)\b"),
]

# a link to a raw IP or a lookalike/newly-registered-looking host is a stronger signal
SUSPICIOUS_URL = re.compile(
    r"https?://(\d{1,3}(\.\d{1,3}){3}|[^\s/]*\b(verify|secure|account|login|update)\b[^\s/]*)",
    re.IGNORECASE)


class HeuristicDetector(Detector):
    name = "heuristic"
    threshold = 0.5

    def classify(self, text: str) -> Verdict:
        if not text:
            return Verdict(self.name, "benign", 0.0, "empty text", ok=True)
        low = text.lower()
        score = 0.0
        hits = []
        for weight, pat in SIGNALS:
            if re.search(pat, low):
                score += weight
                hits.append(pat.split("\\b")[1][:18] if "\\b" in pat else "url")
        if SUSPICIOUS_URL.search(text):
            score += 0.25
            hits.append("suspicious-url")
        score = min(score, 1.0)
        label = "malicious" if score >= self.threshold else "benign"
        rationale = f"matched: {', '.join(hits)}" if hits else "no phishing signals"
        return Verdict(self.name, label, round(score, 3), rationale, ok=True)
