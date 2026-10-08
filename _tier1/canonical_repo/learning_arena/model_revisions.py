"""Model revision tracking for the Learning Arena (spec §19, §31).

Tracks model versions, their lineage, and provenance.  Each revision records:
  * The base model it was derived from
  * Training datasets used
  * Evaluation results
  * Resource cost of training
  * The lesson that inspired the training (if any)

Revisions form a DAG — a revision can have multiple parents (merge) or
multiple children (specialization).  The arena provides a registry for
querying by tag, base model, or evaluation score.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class RevisionStatus(Enum):
    """Model revision status."""

    DRAFT = "draft"
    TRAINING = "training"
    READY = "ready"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class ModelRevision:
    """A versioned model in the arena's registry."""

    id: str
    name: str
    base_model: str
    version: str    # semantic: "1.0.0"
    status: RevisionStatus = RevisionStatus.DRAFT
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"
    created_from_lesson: Optional[str] = None
    dataset_ids: list[str] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)  # lineage
    eval_scores: dict[str, float] = field(default_factory=dict)  # benchmark → score
    training_cost_hours: float = 0.0
    tags: list[str] = field(default_factory=list)
    checkpoint_uri: str = ""
    sha256: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.name}:{self.version}"

    @property
    def best_eval(self) -> Optional[tuple[str, float]]:
        if not self.eval_scores:
            return None
        best = max(self.eval_scores.items(), key=lambda x: x[1])
        return best


@dataclass
class RevisionEvent:
    """An event in a revision's lifecycle (for audit trail)."""

    event_type: str    # "created", "trained", "evaluated", "promoted", "deprecated"
    revision_id: str
    actor: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ModelRevisionArena:
    """Registry of model revisions with lineage tracking (spec §31)."""

    def __init__(self) -> None:
        self._revisions: dict[str, ModelRevision] = {}
        self._events: list[RevisionEvent] = []
        self._by_name: dict[str, list[str]] = {}  # name → list of revision IDs

    def register(
        self,
        name: str,
        base_model: str,
        *,
        version: str = "1.0.0",
        created_by: str = "system",
        created_from_lesson: Optional[str] = None,
        dataset_ids: list[str] = None,
        parent_ids: list[str] = None,
        tags: list[str] = None,
        checkpoint_uri: str = "",
    ) -> ModelRevision:
        """Register a new model revision."""
        rev = ModelRevision(
            id=str(uuid.uuid4()),
            name=name,
            base_model=base_model,
            version=version,
            created_by=created_by,
            created_from_lesson=created_from_lesson,
            dataset_ids=dataset_ids or [],
            parent_ids=parent_ids or [],
            tags=tags or [],
            checkpoint_uri=checkpoint_uri,
        )
        self._revisions[rev.id] = rev
        self._by_name.setdefault(name, []).append(rev.id)
        self._events.append(RevisionEvent(
            event_type="created", revision_id=rev.id,
            actor=created_by,
            metadata={"base_model": base_model, "version": version},
        ))
        return rev

    def get(self, revision_id: str) -> Optional[ModelRevision]:
        return self._revisions.get(revision_id)

    def find_by_name(self, name: str, version: Optional[str] = None) -> list[ModelRevision]:
        ids = self._by_name.get(name, [])
        revs = [self._revisions[r] for r in ids if r in self._revisions]
        if version:
            revs = [r for r in revs if r.version == version]
        return sorted(revs, key=lambda r: r.created_at, reverse=True)

    def best(self, name: str, metric: str = "accuracy") -> Optional[ModelRevision]:
        """Find the best-scoring revision by a given metric."""
        revs = self.find_by_name(name)
        candidates = [r for r in revs if metric in r.eval_scores]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.eval_scores[metric])

    def lineage(self, revision_id: str) -> list[ModelRevision]:
        """Return the full ancestor chain for a revision."""
        chain: list[ModelRevision] = []
        visited: set[str] = set()
        stack = [revision_id]
        while stack:
            rid = stack.pop()
            if rid in visited:
                continue
            visited.add(rid)
            rev = self._revisions.get(rid)
            if rev is None:
                continue
            chain.append(rev)
            stack.extend(rev.parent_ids)
        return list(reversed(chain))

    def record_eval(
        self, revision_id: str, benchmark: str, score: float,
        *, evaluator: str = "system",
    ) -> ModelRevision:
        """Record an evaluation score for a revision."""
        rev = self._revisions.get(revision_id)
        if rev is None:
            raise KeyError(f"unknown revision: {revision_id}")
        rev.eval_scores[benchmark] = score
        self._events.append(RevisionEvent(
            event_type="evaluated", revision_id=revision_id,
            actor=evaluator, metadata={"benchmark": benchmark, "score": score},
        ))
        return rev

    def promote(self, revision_id: str, *, actor: str = "system") -> ModelRevision:
        """Mark a revision as READY (production)."""
        rev = self._revisions.get(revision_id)
        if rev is None:
            raise KeyError(f"unknown revision: {revision_id}")
        rev.status = RevisionStatus.READY
        self._events.append(RevisionEvent(
            event_type="promoted", revision_id=revision_id, actor=actor,
        ))
        return rev

    def deprecate(self, revision_id: str, *, reason: str = "", actor: str = "system") -> ModelRevision:
        """Mark a revision as DEPRECATED."""
        rev = self._revisions.get(revision_id)
        if rev is None:
            raise KeyError(f"unknown revision: {revision_id}")
        rev.status = RevisionStatus.DEPRECATED
        self._events.append(RevisionEvent(
            event_type="deprecated", revision_id=revision_id,
            actor=actor, metadata={"reason": reason},
        ))
        return rev

    def events(self, revision_id: Optional[str] = None) -> list[RevisionEvent]:
        if revision_id:
            return [e for e in self._events if e.revision_id == revision_id]
        return list(self._events)

    def by_tag(self, tag: str) -> list[ModelRevision]:
        return [r for r in self._revisions.values() if tag in r.tags]

    def ready_revisions(self) -> list[ModelRevision]:
        return [r for r in self._revisions.values() if r.status == RevisionStatus.READY]

    def all(self) -> list[ModelRevision]:
        return list(self._revisions.values())

    def clear(self) -> None:
        self._revisions.clear()
        self._by_name.clear()
        self._events.clear()
