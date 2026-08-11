"""
LLM content detector — Claude scores extracted text for phishing/malice.

Represents the "modern/LLM content detector" arm of D4. Uses the Anthropic
Messages API with structured outputs (output_config.format) so every verdict is
a validated JSON object, no free-text parsing.

Cost/credentials:
  - Default model is claude-opus-4-8. Set DETECTOR_MODEL=claude-haiku-4-5 to cut
    cost ~5x for this simple classification (a few hundred tokens per call).
  - Needs Anthropic credentials: ANTHROPIC_API_KEY, or an `ant auth login`
    profile. With none present, classify() returns ok=False and the pipeline
    proceeds on the heuristic detector alone (no spend, no crash).
  - Verdicts are cached per text hash for the life of the object to avoid paying
    twice for identical extractions.
"""
from __future__ import annotations
import hashlib
import json
import os

from .base import Detector, Verdict

SYSTEM = (
    "You are an email-attachment content detector in a security pipeline. "
    "Given text extracted from an attachment, decide whether the content is a "
    "phishing / social-engineering / brand-impersonation lure (malicious) or "
    "ordinary benign content. Judge only the text provided."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["malicious", "benign"]},
        "score": {"type": "number"},   # 0..1 confidence of malicious
        "rationale": {"type": "string"},
    },
    "required": ["label", "score", "rationale"],
    "additionalProperties": False,
}


class LLMDetector(Detector):
    name = "llm"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("DETECTOR_MODEL", "claude-opus-4-8")
        self._client = None
        self._cache: dict[str, Verdict] = {}

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()  # resolves env key or ant profile
        return self._client

    def classify(self, text: str) -> Verdict:
        if not text:
            return Verdict(self.name, "benign", 0.0, "empty text", ok=True)
        key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
        if key in self._cache:
            return self._cache[key]

        try:
            client = self._get_client()
        except Exception as e:
            return Verdict(self.name, "benign", 0.0, "", ok=False,
                           error=f"anthropic SDK unavailable: {e!r}")
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=256,
                system=SYSTEM,
                messages=[{"role": "user",
                           "content": f"Extracted attachment text:\n\n{text[:6000]}"}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            )
            raw = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(raw)
            v = Verdict(self.name, data["label"], float(data["score"]),
                        data.get("rationale", ""), ok=True)
            self._cache[key] = v
            return v
        except Exception as e:
            # includes auth errors (no key), rate limits, refusals
            return Verdict(self.name, "benign", 0.0, "", ok=False, error=repr(e))
