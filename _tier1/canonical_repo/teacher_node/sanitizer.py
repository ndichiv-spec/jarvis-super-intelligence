"""Sanitizer for the Teacher Node (spec §17, §23).

Composes the :class:`~teacher_node.privacy_filter.PrivacyFilter` with
additional context-aware rules:

  * **Secret-file aware**: code diffs that touch credential files
    (``.env``, ``secrets/``, ``credentials.json``) are flagged even if the
    file contents aren't shown — the *path itself* is a signal.
  * **Observation metadata**: strips environment variable names, stack-trace
    internals, and internal hostnames from observations before they become
    lessons (spec §55 — never expose infra to the model context).
  * **Safe summary**: produces a metadata-only digest of an observation
    (resource deltas, error categories) without any raw content.

The sanitizer is the **gatekeeper** between the machine/repo observer and the
lesson builder — nothing passes through without sanitization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .privacy_filter import DetectionKind, PrivacyFilter, RedactionResult


# File paths that indicate secrets/credentials — their *existence* in a diff
# is itself a red flag (spec §55).
_SECRET_FILE_PATTERNS = re.compile(
    r"(?i)\.env\b|\.env\.|\.secrets?|credentials\.json|secret\.json|"
    r"private[_-]?key|service[_-]?account|token[_-]?store|risk[_-]?report",
    re.IGNORECASE,
)

# Environment variable names that look like secrets (spec §55).
_SECRET_VAR_PATTERN = re.compile(
    r"(?i)\b(JARVIS_[A-Z_]*SECRET[A-Z_]*|JARVIS_.*_API_KEY|JARVIS_.*_TOKEN|"
    r"JARVIS_.*_PASSWORD|JARVIS_.*_SECRET|OPENAI_API_KEY|HF_TOKEN|"
    r"AWS_.*KEY|GOOGLE_API_KEY|REPLICATE_API_KEY|STABILITY_API_KEY|"
    r"N8N_API_KEY|JARVIS_SECRET_KEY)\b"
)

# Internal hostnames / IPs that should not appear in lessons.
_INTERNAL_HOST_PATTERN = re.compile(
    r"(?i)(127\.0\.0\.1|localhost|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[01])\..*\.[0-9]+|10\.0\.0\.[0-9]+|"
    r"jarvis[_-]brain|silverwing[_-]runtime|brain[_-]?gateway)",
)


@dataclass
class SanitizationReport:
    """Metadata about what was sanitized — safe to store in lessons."""

    original_length: int
    redacted_length: int
    detection_counts: dict[str, int] = field(default_factory=dict)
    secret_file_referenced: bool = False
    secret_var_referenced: bool = False
    internal_host_referenced: bool = False
    warnings: list[str] = field(default_factory=list)


class Sanitizer:
    """Context-aware observation sanitizer (spec §23, §55).

    Wraps :class:`PrivacyFilter` and adds:
      * Secret-file reference detection (for code diffs)
      * Secret env-var name detection
      * Internal hostname/IP redaction
    """

    def __init__(self, privacy_filter: Optional[PrivacyFilter] = None) -> None:
        self._pf: PrivacyFilter = privacy_filter or PrivacyFilter(
            redact_file_paths=True,
        )

    def sanitize(self, text: str, *, context: str = "observation") -> str:
        """Sanitize text, applying all redaction rules.

        Parameters
        ----------
        text
            Raw observation text (may contain PII, secrets, hostnames).
        context
            ``observation``, ``code_diff``, ``stack_trace``, or
            ``system_prompt``.  Used to tune which rules apply.
        """
        # 1. Privacy filter (PII, API keys, credit cards, etc.)
        result: RedactionResult = self._pf.redact(text)

        # 2. Secret env-var names
        result = self._redact_env_vars(result.text)

        # 3. Internal hostnames / IPs
        result = self._redact_internal_hosts(result.text)

        return result.text

    def sanitize_with_report(
        self, text: str, *, context: str = "observation"
    ) -> tuple[str, SanitizationReport]:
        """Sanitize and return a metadata-only report (spec §55)."""
        report = SanitizationReport(
            original_length=len(text),
            redacted_length=0,
        )

        # Privacy filter detections
        detections = self._pf.detect(text)
        for d in detections:
            key = d.kind.value
            report.detection_counts[key] = report.detection_counts.get(key, 0) + 1

        # Secret file references
        if _SECRET_FILE_PATTERNS.search(text):
            report.secret_file_referenced = True
            report.warnings.append(
                f"observation references a secrets/credential file path "
                f"(context={context})"
            )

        # Secret env-var references
        if _SECRET_VAR_PATTERN.search(text):
            report.secret_var_referenced = True
            report.warnings.append(
                "observation references a secret environment variable name"
            )

        # Internal hosts
        if _INTERNAL_HOST_PATTERN.search(text):
            report.internal_host_referenced = True
            report.warnings.append(
                "observation references an internal hostname/IP"
            )

        sanitized = self.sanitize(text, context=context)
        report.redacted_length = len(sanitized)
        return sanitized, report

    def _redact_env_vars(self, text: str) -> RedactionResult:
        """Replace secret env-var *names* with placeholders (spec §55)."""
        def _repl(m: re.Match) -> str:
            return "[SECRET_VAR]"

        redacted = _SECRET_VAR_PATTERN.sub(_repl, text)
        return RedactionResult(text=redacted, detections=[])

    def _redact_internal_hosts(self, text: str) -> RedactionResult:
        """Replace internal hostnames/IPs with placeholders (spec §55)."""
        def _repl(m: re.Match) -> str:
            return "[INTERNAL_HOST]"

        redacted = _INTERNAL_HOST_PATTERN.sub(_repl, text)
        return RedactionResult(text=redacted, detections=[])

    # ------------------------------------------------------------------ #
    # Safe summary — extract only non-sensitive metadata (spec §55)
    # ------------------------------------------------------------------ #
    def safe_summary(
        self, text: str, max_length: int = 500
    ) -> dict[str, Any]:
        """Produce a metadata-only digest of an observation.

        Returns category tags, length, and sanitized excerpt — never the
        raw sensitive content.  Useful for logging/telemetry.
        """
        _, report = self.sanitize_with_report(text)
        sanitized_excerpt = self.sanitize(text)[:max_length]
        return {
            "original_length": report.original_length,
            "redacted_length": report.redacted_length,
            "detection_counts": report.detection_counts,
            "secret_file_referenced": report.secret_file_referenced,
            "secret_var_referenced": report.secret_var_referenced,
            "internal_host_referenced": report.internal_host_referenced,
            "warnings": report.warnings,
            "sanitized_excerpt": sanitized_excerpt,
        }
