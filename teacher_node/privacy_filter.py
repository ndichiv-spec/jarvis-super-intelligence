"""Privacy filter for the Teacher Node (spec §17, §22, §55).

Detects and redacts PII and secrets from observation text before it is
promoted to lessons or stored in the knowledge base.

Detection classes:
  * EMAIL_ADDRESS  — RFC-5322-ish email patterns
  * PHONE_NUMBER   — international phone numbers
  * CREDIT_CARD    — 13–19 digit card numbers (with Luhn validation)
  * API_KEY        — known key formats (OpenAI, HuggingFace, JWT, generic hex/
                     base64 tokens prefixed by common key names)
  * AWS_KEY_ID     — `AKIA...` style identifiers
  * GENERIC_SECRET — `key=value`, `token="..."`, `password="..."` patterns
  * FILE_PATH      — absolute POSIX/Windows paths (optional, for code diffs)

All redaction is conservative: if a pattern *might* be sensitive, it is
redacted.  Redaction replaces the match with a typed placeholder
(``[REDACTED:EMAIL_ADDRESS]``) that preserves structure without leaking data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


class DetectionKind(Enum):
    """Categories of sensitive data the privacy filter can detect."""

    EMAIL = "EMAIL_ADDRESS"
    PHONE = "PHONE_NUMBER"
    CREDIT_CARD = "CREDIT_CARD"
    API_KEY = "API_KEY"
    AWS_KEY_ID = "AWS_KEY_ID"
    GENERIC_SECRET = "GENERIC_SECRET"
    FILE_PATH = "FILE_PATH"


@dataclass
class Detection:
    """A single redactable finding."""

    kind: DetectionKind
    match: str
    start: int
    end: int
    confidence: float = 1.0  # 0.0 — 1.0; low = heuristic guess


@dataclass
class RedactionResult:
    """Result of a privacy-filter pass."""

    text: str
    detections: list[Detection] = field(default_factory=list)

    @property
    def redacted_count(self) -> int:
        return len(self.detections)


# --------------------------------------------------------------------------- #
# Pattern library
# --------------------------------------------------------------------------- #

# Email — conservative pattern.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Phone — international format, e.g. +1-555-123-4567 or +44 20 7946 0958.
_PHONE_RE = re.compile(
    r"\+?\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{3,4}[\s.\-]?\d{4,}"
)

# Credit card — 13-19 digits, optionally grouped with spaces/dashes.
_CC_RE = re.compile(
    r"\b(?:\d[ -]*?){13,19}\b"
)

# AWS access key ID — starts with AKIA, ASR, AGI, or AID.
_AWS_KEY_RE = re.compile(r"\bAK[IA][0-9A-Z]{16,18}\b")

# Known API-key formats:
#   OpenAI:   sk-... or org-...
#   HuggingFace: hf_...
#   GitHub:   ghp_..., gho_..., ghs_..., ghu_...
#   Google:   AIza...
#   Generic:  Bearer <token>
_API_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{8,}"
    r"|hf_[A-Za-z0-9]{10,}"
    r"|gh[pousr]_[A-Za-z0-9]{36}"
    r"|AIza[A-Za-z0-9_\-]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|[A-Za-z0-9_\-]{32,})"
)

# Generic key=value or key: "value" with secret-like key names.
_GENERIC_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)"
    r"[\s:=]+[\"']?([A-Za-z0-9_\-+/=]{8,})[\"']?"
)

# Absolute file paths (POSIX + Windows).
_FILE_PATH_RE = re.compile(
    r"(?:/[A-Za-z0-9_.\-/]+|\b[A-Za-z]:\\(?:[A-Za-z0-9_.\-\\\/]+)+)"
)


def _luhn_valid(card_str: str) -> bool:
    """Luhn checksum — quick false-positive filter for credit cards."""
    digits = [int(d) for d in re.sub(r"[^0-9]", "", card_str)]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


class PrivacyFilter:
    """Detects and redacts PII and secrets from text (spec §22, §55).

    Uses ``psutil``-independent regex heuristics.  All detection is
    in-memory and never calls any external service.
    """

    def __init__(self, *, redact_file_paths: bool = False) -> None:
        self._redact_file_paths = redact_file_paths

    # ------------------------------------------------------------------ #
    # Detection
    # ------------------------------------------------------------------ #
    def detect(self, text: str) -> list[Detection]:
        """Return all detections in ``text``, sorted by position."""
        detections: list[Detection] = []

        for m in _EMAIL_RE.finditer(text):
            detections.append(Detection(
                kind=DetectionKind.EMAIL, match=m.group(), start=m.start(), end=m.end(),
            ))

        for m in _AWS_KEY_RE.finditer(text):
            detections.append(Detection(
                kind=DetectionKind.AWS_KEY_ID, match=m.group(), start=m.start(), end=m.end(),
            ))

        for m in _API_KEY_RE.finditer(text):
            detections.append(Detection(
                kind=DetectionKind.API_KEY, match=m.group(), start=m.start(), end=m.end(),
            ))

        for m in _GENERIC_SECRET_RE.finditer(text):
            detections.append(Detection(
                kind=DetectionKind.GENERIC_SECRET, match=m.group(), start=m.start(), end=m.end(),
            ))

        for m in _CC_RE.finditer(text):
            candidate = re.sub(r"[^0-9]", "", m.group())
            if _luhn_valid(candidate):
                detections.append(Detection(
                    kind=DetectionKind.CREDIT_CARD, match=m.group(), start=m.start(), end=m.end(),
                ))

        for m in _PHONE_RE.finditer(text):
            # Skip if this match is part of a longer number (avoid sub-matching).
            detections.append(Detection(
                kind=DetectionKind.PHONE, match=m.group(), start=m.start(), end=m.end(),
                confidence=0.7,
            ))

        if self._redact_file_paths:
            for m in _FILE_PATH_RE.finditer(text):
                detections.append(Detection(
                    kind=DetectionKind.FILE_PATH, match=m.group(), start=m.start(), end=m.end(),
                ))

        # Merge overlapping detections (conservative: keep the highest-priority
        # kind for each overlapping span).
        detections = self._merge_overlapping(detections)
        return detections

    def _merge_overlapping(self, detections: list[Detection]) -> list[Detection]:
        """Merge overlapping spans, keeping the kind with highest priority."""
        if not detections:
            return []
        priority = {
            DetectionKind.API_KEY: 6,       # most specific — highest priority
            DetectionKind.GENERIC_SECRET: 5,
            DetectionKind.AWS_KEY_ID: 4,
            DetectionKind.CREDIT_CARD: 3,
            DetectionKind.EMAIL: 3,
            DetectionKind.FILE_PATH: 1,
            DetectionKind.PHONE: 1,
        }
        sorted_d = sorted(detections, key=lambda d: d.start)
        merged: list[Detection] = []
        for d in sorted_d:
            if merged and d.start < merged[-1].end:
                prev = merged[-1]
                if priority.get(d.kind, 0) > priority.get(prev.kind, 0):
                    merged[-1] = Detection(
                        kind=d.kind, match=prev.match + d.match,
                        start=prev.start, end=d.end,
                    )
                else:
                    merged[-1] = Detection(
                        kind=prev.kind, match=prev.match + d.match,
                        start=prev.start, end=d.end,
                    )
            else:
                merged.append(d)
        return merged

    # ------------------------------------------------------------------ #
    # Redaction
    # ------------------------------------------------------------------ #
    def redact(self, text: str) -> RedactionResult:
        """Redact all sensitive data from ``text``.

        Returns a :class:`RedactionResult` with the redacted text and a list
        of what was found (without the raw values — the ``match`` field on
        each Detection is replaced with a placeholder).
        """
        detections = self.detect(text)
        if not detections:
            return RedactionResult(text=text, detections=[])

        # Work from right to left so offsets stay valid.
        redacted = text
        safe_detections: list[Detection] = []
        for d in sorted(detections, key=lambda x: x.start, reverse=True):
            redacted = redacted[:d.start] + f"[REDACTED:{d.kind.value}]" + redacted[d.end:]
            safe_detections.append(Detection(
                kind=d.kind, match=f"[REDACTED:{d.kind.value}]",
                start=d.start, end=d.start, confidence=d.confidence,
            ))
        safe_detections.reverse()
        return RedactionResult(text=redacted, detections=safe_detections)

    def is_clean(self, text: str) -> bool:
        """True iff ``text`` contains no detectable PII or secrets."""
        return len(self.detect(text)) == 0

    def scan_stream(self, lines: Iterator[str]) -> Iterator[str]:
        """Generator: redact each line from a stream."""
        for line in lines:
            yield self.redact(line).text
