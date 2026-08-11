from .base import Detector, Verdict
from .heuristic import HeuristicDetector
from .llm import LLMDetector

# Heuristic first (always available, zero cost); LLM runs when credentials exist.
ALL_DETECTORS = [HeuristicDetector(), LLMDetector()]

__all__ = ["Detector", "Verdict", "HeuristicDetector", "LLMDetector", "ALL_DETECTORS"]
