"""Failure catalog for the Learning Arena (spec §28, §55).

Tracks and categorizes task failures for root-cause analysis.  Each failure
is tagged with:
  * An error category (OOM, Timeout, Network, Auth, Validation, etc.)
  * The resource snapshot at failure time
  * The model revision and task that produced it
  * A sanitized error message (no PII/secrets — spec §23)

Failures feed back into:
  * The Teacher Node's experience recorder (for lesson extraction).
  * The resource governor (adjusting thresholds based on observed patterns).
  * The task arena (avoiding task types that repeatedly fail).
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from teacher_node.privacy_filter import PrivacyFilter


class FailureCategory(Enum):
    """Structured failure categories (spec §28)."""

    OUT_OF_MEMORY = "out_of_memory"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMIT = "rate_limit"
    DISK_FULL = "disk_full"
    GPU_ERROR = "gpu_error"
    DEPENDENCY_MISSING = "dependency_missing"
    UNKNOWN = "unknown"


@dataclass
class FailureRecord:
    """A single failure in the catalog."""

    id: str
    task_id: str
    category: FailureCategory
    model_revision: Optional[str]
    error_message: str  # already sanitized
    error_category_detail: str
    resource_at_failure: dict[str, Any]
    tags: list[str]
    created_at: float
    source: str = "arena"


class FailureArena:
    """Catalogs and analyzes task failures (spec §28, §55).

    Parameters
    ----------
    sanitizer
        Optional :class:`~teacher_node.sanitizer.Sanitizer` for error
        message redaction.  If not provided, a default PrivacyFilter is used.
    """

    def __init__(self, sanitizer: Any = None) -> None:
        self._sanitizer = sanitizer or PrivacyFilter()
        self._failures: dict[str, FailureRecord] = {}

    def record(
        self,
        task_id: str,
        error_message: str,
        *,
        model_revision: Optional[str] = None,
        resource_at_failure: dict[str, Any] = None,
        tags: list[str] = None,
        source: str = "arena",
    ) -> FailureRecord:
        """Record a failure, auto-categorizing and sanitizing the message."""
        category, detail = self._categorize(error_message)
        sanitized = self._sanitizer.redact(error_message).text if hasattr(
            self._sanitizer, "redact"
        ) else error_message

        record = FailureRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            category=category,
            model_revision=model_revision,
            error_message=sanitized,
            error_category_detail=detail,
            resource_at_failure=resource_at_failure or {},
            tags=tags or [],
            created_at=time.time(),
            source=source,
        )
        self._failures[record.id] = record
        return record

    @staticmethod
    def _categorize(error: str) -> tuple[FailureCategory, str]:
        """Heuristic failure categorization (spec §28 — no PII in result)."""
        e = error.lower()
        if any(w in e for w in ("oom", "out of memory", "allocate", "cuda", "cuda runtime")):
            return FailureCategory.OUT_OF_MEMORY, "out_of_memory"
        if any(w in e for w in ("timeout", "timed out", "deadline", "timedout")):
            return FailureCategory.TIMEOUT, "timeout"
        if any(w in e for w in ("connection", "network", "refused", "unreachable", "socket")):
            return FailureCategory.NETWORK_ERROR, "network_error"
        if any(w in e for w in ("auth", "unauthorized", "401", "403", "forbidden", "credentials")):
            return FailureCategory.AUTH_ERROR, "auth_error"
        if any(w in e for w in ("rate limit", "429", "too many requests", "quota")):
            return FailureCategory.RATE_LIMIT, "rate_limit"
        if any(w in e for w in ("no space", "disk full", "enospc", "storage")):
            return FailureCategory.DISK_FULL, "disk_full"
        if any(w in e for w in ("gpu", "cuda", "driver", "device")):
            return FailureCategory.GPU_ERROR, "gpu_error"
        if any(w in e for w in ("module", "import", "not found", "dependency", "package")):
            return FailureCategory.DEPENDENCY_MISSING, "dependency_missing"
        return FailureCategory.UNKNOWN, "unknown"

    def get(self, failure_id: str) -> Optional[FailureRecord]:
        return self._failures.get(failure_id)

    def for_task(self, task_id: str) -> list[FailureRecord]:
        return [f for f in self._failures.values() if f.task_id == task_id]

    def by_category(self, category: FailureCategory) -> list[FailureRecord]:
        return [f for f in self._failures.values() if f.category == category]

    def by_model(self, model_revision: str) -> list[FailureRecord]:
        return [f for f in self._failures.values() if f.model_revision == model_revision]

    def summary(self) -> dict[str, Any]:
        """Aggregate failure statistics by category."""
        cats = Counter(f.category.value for f in self._failures.values())
        return {
            "total": len(self._failures),
            "by_category": dict(cats),
            "by_model": dict(Counter(
                f.model_revision or "unknown" for f in self._failures.values()
            )),
        }

    def top_patterns(self, n: int = 5) -> list[dict[str, Any]]:
        """Return the top-N failure categories by frequency."""
        cats = Counter(f.category.value for f in self._failures.values())
        return [
            {"category": cat, "count": count}
            for cat, count in cats.most_common(n)
        ]

    def clear(self) -> None:
        self._failures.clear()
