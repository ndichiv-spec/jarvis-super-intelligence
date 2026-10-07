"""System knowledge store for the Teacher Node (spec §17, §18).

A structured, append-only knowledge base that accumulates machine observations,
repo patterns, and lesson-derived heuristics.  Unlike a model context, this
store is:

  * **Indexed** — by category, timestamp, and confidence score.
  * **Versioned** — each entry has a unique ID for lineage (spec §17.5).
  * **Privacy-filtered** — only sanitized data is stored; the sanitizer is
    wired into every write path.
  * **Queryable** — supports tag-based lookup and similarity ranking.

The store is pluggable (in-memory dict by default; production may use SQLite
or a document DB).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class KnowledgeEntry:
    """A single unit of system knowledge."""

    id: str
    category: str           # e.g. "resource", "repo", "pattern", "lesson"
    key: str                # human-readable key (e.g. "cpu_spike_during_training")
    value: dict[str, Any]   # the structured payload
    confidence: float       # 0.0 — 1.0
    tags: list[str]         # searchable tags
    source_ref: str         # where this came from (e.g. "machine_observer:t0")
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None  # None = never expires

    def is_expired(self) -> bool:
        return self.expires_at is not None and time.time() > self.expires_at


class SystemKnowledge:
    """Append-only, indexed knowledge store for the Teacher Node.

    All writes are sanitized through the provided :class:`Sanitizer` before
    being stored (spec §23).
    """

    def __init__(self, sanitizer: Any = None) -> None:
        self._store: dict[str, KnowledgeEntry] = {}
        self._sanitizer = sanitizer

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def add(
        self,
        category: str,
        key: str,
        value: dict[str, Any],
        *,
        confidence: float = 0.5,
        tags: list[str] = None,
        source_ref: str = "unknown",
        ttl: Optional[float] = None,
    ) -> KnowledgeEntry:
        """Add a knowledge entry.  Values are sanitized before storage."""
        entry_id = str(uuid.uuid4())
        # Deep-sanitize all string values in the payload.
        sanitized_value = self._sanitize_value(value) if self._sanitizer else value
        tags = tags or []
        entry = KnowledgeEntry(
            id=entry_id,
            category=category,
            key=key,
            value=sanitized_value,
            confidence=confidence,
            tags=tags,
            source_ref=source_ref,
            expires_at=(time.time() + ttl) if ttl else None,
        )
        self._store[entry_id] = entry
        return entry

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively sanitize all string values in a dict/list structure."""
        if isinstance(value, str):
            return self._sanitizer.sanitize(value)
        if isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize_value(v) for v in value]
        return value

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        entry = self._store.get(entry_id)
        if entry and entry.is_expired():
            del self._store[entry_id]
            return None
        return entry

    def find_by_key(self, key: str) -> list[KnowledgeEntry]:
        """Find all entries with a matching key."""
        return [
            e for e in self._store.values()
            if e.key == key and not e.is_expired()
        ]

    def find_by_tag(self, tag: str) -> list[KnowledgeEntry]:
        """Find all entries tagged with ``tag``."""
        return [
            e for e in self._store.values()
            if tag in e.tags and not e.is_expired()
        ]

    def find_by_category(self, category: str) -> list[KnowledgeEntry]:
        """Find all entries in a category, sorted by recency."""
        entries = [
            e for e in self._store.values()
            if e.category == category and not e.is_expired()
        ]
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def search(self, query: str) -> list[KnowledgeEntry]:
        """Simple keyword search across key + tags + string values."""
        matches = []
        q_lower = query.lower()
        for e in self._store.values():
            if e.is_expired():
                continue
            haystack = " ".join(
                [e.key] + e.tags + [str(v) for v in _flatten_values(e.value)]
            ).lower()
            if q_lower in haystack:
                matches.append(e)
        return sorted(matches, key=lambda e: e.created_at, reverse=True)

    # ------------------------------------------------------------------ #
    # Maintenance
    # ------------------------------------------------------------------ #
    def cleanup(self) -> int:
        """Remove expired entries.  Returns count removed."""
        expired = [eid for eid, e in self._store.items() if e.is_expired()]
        for eid in expired:
            del self._store[eid]
        return len(expired)

    def all(self) -> list[KnowledgeEntry]:
        return list(self._store.values())

    def clear(self) -> None:
        self._store.clear()


def _flatten_values(d: Any) -> list[Any]:
    """Extract all leaf values from a nested dict/list structure."""
    result = []
    if isinstance(d, dict):
        for v in d.values():
            result.extend(_flatten_values(v))
    elif isinstance(d, list):
        for v in d:
            result.extend(_flatten_values(v))
    else:
        result.append(d)
    return result
