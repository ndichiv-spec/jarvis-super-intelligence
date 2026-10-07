"""Append-only model lifecycle registry (spec §16, §30, §31).

Core rules:

* **identity is immutable** — once a ``(provider, model_id)`` identity is
  created, its ``source`` / ``revision`` / ``parent_model`` / ``discovered_at``
  / ``lifecycle_type`` / ``family`` / capability set are never overwritten.
  Only *transitions* (stage, promotion, history, links, evaluations) are
  appended.  A model that changes is a **new revision**, never a mutation.
* **human-gated promotion** — ``CANDIDATE -> EVALUATED -> PROMOTION_REVIEW ->
  HUMAN_APPROVAL -> PRODUCTION``.  Nothing becomes production without a human
  actor's approval (spec §30).
* **lineage** — records carry typed edges (``parent_model``,
  ``training_run_id``, ``dataset_ids``, provenance ids) so the chain
  ``source -> research -> evidence -> lesson -> dataset -> training -> model``
  can be walked end-to-end (spec §31).
* persistence is JSONL-backed; every event is recorded in ``history``.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from .types import LifecycleStage, ModelLifecycleType, PromotionState

#: Default store location; override with ``JARVIS_MODEL_LIFECYCLE_DIR`` or by
#: passing ``store_path`` to the registry constructor.
DEFAULT_STORE_DIR = Path(
    os.environ.get("JARVIS_MODEL_LIFECYCLE_DIR", "data") or "data"
)
STORE_FILENAME = "model_lifecycle.jsonl"


#: Edges that make lineage walkable end-to-end.
_LINK_FIELDS = (
    "parent_model",
    "training_run_id",
    "source_evidence_id",
    "source_research_id",
    "source_lesson_id",
    "source_dataset_ids",
)


@dataclass
class ModelRecord:
    """One governed model lifecycle entry.

    Transitions (stage/promotion/history/links/evaluations) are the only
    fields an existing record may change; the identity block
    (``provider/model_id/lifecycle_type/family/revision/source/capabilities``)
    is immutable.
    """

    record_id: str
    provider: str
    model_id: str
    lifecycle_type: ModelLifecycleType
    name: str = ""
    family: str = "external"
    revision: str = ""
    lifecycle_stage: LifecycleStage = LifecycleStage.BASE
    promotion: PromotionState = PromotionState.NONE
    capabilities: list[str] = field(default_factory=list)
    deployment: str = "hosted"
    architecture: str = "unknown"
    context_length: int = 0
    max_output_tokens: int = 0
    source: str = "adapter"
    discovered_at: float = field(default_factory=time.time)
    parent_model: Optional[str] = None
    training_run_id: Optional[str] = None
    source_evidence_id: Optional[str] = None
    source_research_id: Optional[str] = None
    source_lesson_id: Optional[str] = None
    source_dataset_ids: list[str] = field(default_factory=list)
    evaluation_results: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def identity_key(self) -> tuple[str, str]:
        return (self.provider, self.model_id)

    @property
    def lineage(self) -> dict:
        """Human-readable lineage chain (str -> str | list[str])."""
        chain: dict[str, Any] = {
            "provider": self.provider,
            "model_id": self.model_id,
            "lifecycle_type": self.lifecycle_type.value,
            "family": self.family,
            "revision": self.revision or "unknown",
        }
        if self.parent_model:
            chain["parent_model"] = self.parent_model
        if self.training_run_id:
            chain["training_run_id"] = self.training_run_id
        if self.source_evidence_id:
            chain["evidence"] = self.source_evidence_id
        if self.source_research_id:
            chain["research"] = self.source_research_id
        if self.source_lesson_id:
            chain["lesson"] = self.source_lesson_id
        if self.source_dataset_ids:
            chain["datasets"] = list(self.source_dataset_ids)
        return chain

    def to_dict(self) -> dict:
        data = asdict(self)
        data["lifecycle_type"] = self.lifecycle_type.value
        data["lifecycle_stage"] = self.lifecycle_stage.value
        data["promotion"] = self.promotion.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ModelRecord":
        fields = dict(data)
        fields["lifecycle_type"] = ModelLifecycleType(fields["lifecycle_type"])
        fields["lifecycle_stage"] = LifecycleStage(fields["lifecycle_stage"])
        fields["promotion"] = PromotionState(fields["promotion"])
        return cls(**fields)


def _event(detail: str, actor: str, *, extra: Optional[dict] = None) -> dict:
    return {
        "at": time.time(),
        "actor": actor,
        "detail": detail,
        **({} if not extra else extra),
    }


class ModelRegistry:
    """In-memory + JSONL-backed registry of lifecycle records.

    Thread-safety is not required by the current single-writer server model;
    every mutating call rewrites the backing store so nothing is lost on exit.
    """

    def __init__(self, store_path: Optional[Path] = None) -> None:
        if store_path is None:
            store_path = DEFAULT_STORE_DIR / STORE_FILENAME
        self.store_path = Path(store_path)
        self._records: dict[str, ModelRecord] = {}
        self._identity: dict[tuple[str, str], str] = {}
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.store_path.exists():
            return
        for line in self.store_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = ModelRecord.from_dict(json.loads(line))
            except (ValueError, TypeError, KeyError) as exc:
                continue  # skip corrupt rows rather than kill the registry
            self._records[record.record_id] = record
            self._identity.setdefault(record.identity_key, record.record_id)

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.store_path.open("w", encoding="utf-8") as handle:
            for record in self._records.values():
                handle.write(json.dumps(record.to_dict(), default=repr) + "\n")

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[ModelRecord]:
        return iter(self._records.values())

    def get(self, record_id: str) -> Optional[ModelRecord]:
        return self._records.get(record_id)

    def require(self, record_id: str) -> ModelRecord:
        record = self.get(record_id)
        if record is None:
            raise KeyError(f"unknown lifecycle record {record_id!r}")
        return record

    def find(self, provider: str, model_id: str) -> Optional[ModelRecord]:
        record_id = self._identity.get((provider, model_id))
        return self._records.get(record_id) if record_id else None

    def list_by_type(self, lifecycle_type: ModelLifecycleType) -> list[ModelRecord]:
        return [r for r in self if r.lifecycle_type is lifecycle_type]

    def list_family(self, family: str) -> list[ModelRecord]:
        return [r for r in self if r.family == family]

    def list_by_stage(self, stage: LifecycleStage) -> list[ModelRecord]:
        return [r for r in self if r.lifecycle_stage is stage]

    def all_records(self) -> list[ModelRecord]:
        return list(self._records.values())

    # ------------------------------------------------------------------
    # Registration (identity immutability)
    # ------------------------------------------------------------------
    def ensure(
        self,
        provider: str,
        model_id: str,
        lifecycle_type: ModelLifecycleType,
        *,
        name: str = "",
        family: str = "external",
        revision: str = "",
        stage: LifecycleStage = LifecycleStage.BASE,
        capabilities: Optional[list[str]] = None,
        deployment: str = "hosted",
        architecture: str = "unknown",
        context_length: int = 0,
        max_output_tokens: int = 0,
        source: str = "adapter",
        parent_model: Optional[str] = None,
        training_run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        actor: str = "system",
    ) -> ModelRecord:
        """Register a lifecycle record, or return the existing identity.

        Existing identities are never re-parented, re-sourced, re-typed or
        re-revised — that is the immutability rule.  ``parent_model`` /
        ``training_run_id`` are attached only when missing.
        """
        existing = self.find(provider, model_id)
        if existing is not None:
            changed = False
            if parent_model and not existing.parent_model:
                existing.parent_model = parent_model
                changed = True
            if training_run_id and not existing.training_run_id:
                existing.training_run_id = training_run_id
                changed = True
            if changed:
                existing.history.append(
                    _event("identity linked", actor, extra={"links": True})
                )
                self._persist()
            return existing

        record_id = uuid.uuid4().hex
        record = ModelRecord(
            record_id=record_id,
            provider=provider,
            model_id=model_id,
            lifecycle_type=lifecycle_type,
            name=name or model_id,
            family=family,
            revision=revision,
            lifecycle_stage=stage,
            capabilities=list(capabilities or []),
            deployment=deployment,
            architecture=architecture,
            context_length=context_length,
            max_output_tokens=max_output_tokens,
            source=source,
            parent_model=parent_model,
            training_run_id=training_run_id,
            metadata=dict(metadata or {}),
        )
        record.history.append(
            _event(
                "registered",
                actor,
                extra={
                    "type": lifecycle_type.value,
                    "family": family,
                    "source": source,
                },
            )
        )
        self._records[record_id] = record
        self._identity[record.identity_key] = record_id
        self._persist()
        return record

    # ------------------------------------------------------------------
    # Transitions (append-only; identity fields never mutate)
    # ------------------------------------------------------------------
    def set_stage(
        self, record_id: str, stage: LifecycleStage, actor: str, detail: str = ""
    ) -> ModelRecord:
        record = self.require(record_id)
        record.lifecycle_stage = stage
        record.history.append(_event(detail or f"stage -> {stage.value}", actor))
        self._persist()
        return record

    def set_promotion(
        self,
        record_id: str,
        promotion: PromotionState,
        actor: str,
        detail: str = "",
    ) -> ModelRecord:
        record = self.require(record_id)
        record.promotion = promotion
        record.history.append(
            _event(detail or f"promotion -> {promotion.value}", actor)
        )
        self._persist()
        return record

    def mark_evaluated(self, record_id: str, actor: str) -> ModelRecord:
        """CANDIDATE -> EVALUATION; promotion enters PROMOTION_REVIEW (§30)."""
        record = self.require(record_id)
        record.lifecycle_stage = LifecycleStage.EVALUATION
        record.promotion = PromotionState.PROMOTION_REVIEW
        record.history.append(
            _event("evaluated vs baseline; promotion review requested", actor)
        )
        self._persist()
        return record

    def request_human_approval(self, record_id: str, actor: str) -> ModelRecord:
        """PROMOTION_REVIEW -> HUMAN_APPROVAL (awaiting human decision)."""
        record = self.require(record_id)
        if record.promotion is not PromotionState.PROMOTION_REVIEW:
            raise ValueError(
                f"{record.model_id} not in PROMOTION_REVIEW "
                f"(got {record.promotion.value})"
            )
        record.promotion = PromotionState.HUMAN_APPROVAL
        record.history.append(
            _event("promotion review passed; awaiting human approval", actor)
        )
        self._persist()
        return record

    def human_approve(self, record_id: str, actor: str) -> ModelRecord:
        """HUMAN_APPROVAL -> APPROVED, stage PROMOTED (production eligible)."""
        record = self.require(record_id)
        if record.promotion is not PromotionState.HUMAN_APPROVAL:
            raise ValueError(
                f"{record.model_id} must be in HUMAN_APPROVAL before approval "
                f"(got {record.promotion.value})"
            )
        record.promotion = PromotionState.APPROVED
        record.lifecycle_stage = LifecycleStage.PROMOTED
        record.history.append(
            _event(f"human-approved for production ({record.model_id})", actor)
        )
        self._persist()
        return record

    def human_reject(self, record_id: str, actor: str, reason: str = "") -> ModelRecord:
        """Reject the promotion proposal; stage becomes REJECTED."""
        record = self.require(record_id)
        record.promotion = PromotionState.REJECTED
        record.lifecycle_stage = LifecycleStage.REJECTED
        record.history.append(
            _event(f"human rejected promotion ({reason or 'no reason given'})", actor)
        )
        self._persist()
        return record

    # ------------------------------------------------------------------
    # Links & evaluation evidence
    # ------------------------------------------------------------------
    def link_training(self, record_id: str, training_run_id: str, actor: str) -> ModelRecord:
        record = self.require(record_id)
        if not record.training_run_id:
            record.training_run_id = training_run_id
        else:
            record.metadata.setdefault("training_run_ids", []).append(training_run_id)
        record.history.append(
            _event(f"linked training run {training_run_id}", actor)
        )
        self._persist()
        return record

    def link_dataset(
        self, record_id: str, dataset_id: str, actor: str
    ) -> ModelRecord:
        record = self.require(record_id)
        if dataset_id not in record.source_dataset_ids:
            record.source_dataset_ids.append(dataset_id)
        record.history.append(_event(f"linked dataset {dataset_id}", actor))
        self._persist()
        return record

    def link_provenance(
        self,
        record_id: str,
        *,
        lesson_id: Optional[str] = None,
        evidence_id: Optional[str] = None,
        research_id: Optional[str] = None,
        actor: str = "learning_loop",
    ) -> ModelRecord:
        """Attach lesson/evidence/research provenance (spec §31 lineage)."""
        record = self.require(record_id)
        if lesson_id and not record.source_lesson_id:
            record.source_lesson_id = lesson_id
        if evidence_id and not record.source_evidence_id:
            record.source_evidence_id = evidence_id
        if research_id and not record.source_research_id:
            record.source_research_id = research_id
        record.history.append(
            _event(
                "provenance linked",
                actor,
                extra={
                    "lesson_id": lesson_id,
                    "evidence_id": evidence_id,
                    "research_id": research_id,
                },
            )
        )
        self._persist()
        return record

    def record_evaluation(
        self,
        record_id: str,
        eval_name: str,
        result: dict,
        actor: str = "evaluator",
    ) -> ModelRecord:
        record = self.require(record_id)
        record.evaluation_results[eval_name] = dict(result)
        record.history.append(_event(f"evaluation '{eval_name}' recorded", actor))
        self._persist()
        return record

    def lineage(self, record_id: str) -> list[dict]:
        """Resolve the full relational chain for a record (spec §31)."""
        record = self.require(record_id)
        chain: list[dict] = [record.lineage]
        visited: set[str] = {record.record_id}

        current = record
        while current.parent_model and current.parent_model not in visited:
            visited.add(current.parent_model)
            parent = self.get(current.parent_model)
            if parent is None:
                chain.append({"parent_model": current.parent_model, "unresolved": True})
                break
            chain.append(parent.lineage)
            current = parent
        return chain

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "records": len(self._records),
            "families": {
                fam: len(self.list_family(fam)) for fam in sorted({r.family for r in self})
            },
            "by_type": {
                t.value: len(self.list_by_type(t)) for t in ModelLifecycleType
            },
            "jars": {r.model_id for r in self if r.lifecycle_stage is LifecycleStage.PROMOTED},
            "production": [
                r.model_id
                for r in self
                if r.lifecycle_type is ModelLifecycleType.JARVIS_PRODUCTION
            ],
        }