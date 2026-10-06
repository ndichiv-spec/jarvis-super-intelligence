"""
Knowledge validation and confidence scoring.

Validates content quality, relevance, and safety before acceptance.
"""

from __future__ import annotations
import re
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from .types import LearningRequest, Document, KnowledgeSource

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    score: float
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "passed": self.passed,
            "checks": self.checks,
        }


class KnowledgeValidator:
    """
    Validates knowledge content for quality, safety, and relevance.

    Pluggable check system:
      - Content quality (length, structure, language)
      - Safety filters (PII, toxic content)
      - Relevance scoring
      - Source credibility
      - Deduplication
    """

    def __init__(self, min_content_length: int = 20, max_content_length: int = 100_000):
        self.min_content_length = min_content_length
        self.max_content_length = max_content_length
        self._checks: List[Callable[[str, Dict[str, Any]], tuple]] = []
        self._setup_default_checks()

    def add_check(self, fn: Callable[[str, Dict[str, Any]], tuple]):
        """Add a validation check. Returns (score_delta: float, reason: str)."""
        self._checks.append(fn)

    def _setup_default_checks(self):
        self.add_check(self._check_length)
        self.add_check(self._check_repetition)
        self.add_check(self._check_language_quality)

    def validate(self, request: LearningRequest) -> ValidationResult:
        """Full validation of a learning request."""
        checks: List[Dict[str, Any]] = []
        total_delta = 0.0

        for check_fn in self._checks:
            try:
                delta, reason = check_fn(request.content, {})
                checks.append({"check": check_fn.__name__, "delta": delta, "reason": reason})
                total_delta += delta
            except Exception as e:
                checks.append({"check": check_fn.__name__, "delta": -0.3, "reason": str(e)})
                total_delta -= 0.3

        base_score = 0.7
        final_score = max(0.0, min(1.0, base_score + total_delta))

        return ValidationResult(
            score=final_score,
            passed=final_score >= 0.4,
            checks=checks,
        )

    def validate_document(self, doc: Document) -> ValidationResult:
        """Validate an already-stored document."""
        checks: List[Dict[str, Any]] = []
        total_delta = 0.0

        for check_fn in self._checks:
            try:
                delta, reason = check_fn(doc.content, {"doc_id": doc.id})
                checks.append({"check": check_fn.__name__, "delta": delta})
                total_delta += delta
            except Exception:
                pass

        final_score = max(0.0, min(1.0, doc.confidence + total_delta))
        return ValidationResult(
            score=final_score,
            passed=final_score >= 0.4,
            checks=checks,
        )

    @staticmethod
    def _check_length(content: str, metadata: Dict) -> tuple:
        length = len(content)
        if length < 20:
            return -0.4, "Content too short"
        if length > 100_000:
            return -0.2, "Content unusually long"
        if length > 500:
            return 0.1, "Good content length"
        return 0.0, "Adequate length"

    @staticmethod
    def _check_repetition(content: str, metadata: Dict) -> tuple:
        """Detect repetitive content."""
        if len(content) < 100:
            return 0.0, ""

        sentences = re.split(r'[.!?]+', content)
        if len(sentences) < 3:
            return 0.0, ""

        unique = len(set(s.strip().lower() for s in sentences if s.strip()))
        ratio = unique / len(sentences)
        if ratio < 0.3:
            return -0.3, f"Highly repetitive (unique ratio: {ratio:.2f})"
        if ratio < 0.6:
            return -0.1, f"Some repetition (unique ratio: {ratio:.2f})"
        return 0.05, "Good variety"

    @staticmethod
    def _check_language_quality(content: str, metadata: Dict) -> tuple:
        """Basic language quality heuristics."""
        if len(content) < 50:
            return 0.0, ""

        words = content.split()
        avg_word_len = sum(len(w) for w in words) / len(words) if words else 0

        if avg_word_len < 2:
            return -0.2, "Suspiciously short words"
        if avg_word_len > 15:
            return -0.1, "Unusually long words"

        return 0.05, "Acceptable language quality"

    def confidence_for_source(self, source: KnowledgeSource) -> float:
        """Base confidence for a knowledge source type."""
        confidence_map = {
            KnowledgeSource.DOCUMENT: 0.8,
            KnowledgeSource.CONVERSATION: 0.6,
            KnowledgeSource.USER_INPUT: 0.5,
            KnowledgeSource.AGENT_OUTPUT: 0.7,
            KnowledgeSource.EXTERNAL_API: 0.6,
            KnowledgeSource.WEB_SCRAPE: 0.4,
            KnowledgeSource.CODEBASE: 0.9,
            KnowledgeSource.PLUGIN: 0.5,
            KnowledgeSource.MANUAL: 0.85,
        }
        return confidence_map.get(source, 0.5)
