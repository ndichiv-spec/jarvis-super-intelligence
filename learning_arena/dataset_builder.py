"""Governed curriculum dataset builder (spec §28).

Turns *verified curriculum lessons* into structured training examples with
full provenance.  Every example carries:

* the problem (question, context, constraints, expected format),
* the verified/resolved solution,
* the verification outcome and method,
* the 1-6 difficulty scale and label,
* provenance — exact ``lesson_id``, ``evidence_ids``, ``research_ids`` and
  ``experiment_ids`` (the lineage ``source -> research -> evidence -> lesson
  -> dataset``).

Immutable revisions: publishing a dataset is versioned, and a revision is
**never mutated** — a changed dataset is a new ``version`` with a new content
hash, so model training can be pinned to exact bytes.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .lesson_gate import CurriculumLesson, LessonClass, content_hash as _lesson_hash


class DatasetQuality(str):
    QUALIFIED = "QUALIFIED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DatasetExample:
    """One immutable training example distilled from a verified lesson."""

    example_id: str
    problem: str
    context: str
    constraints: tuple[str, ...]
    expected_format: str
    resolved_solution: str
    verification_status: str
    verification_method: str
    domain: str
    difficulty: int
    difficulty_label: str
    provenance: dict = field(default_factory=dict)
    source: str = "lesson_gate"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["constraints"] = list(self.constraints)
        return data


@dataclass
class DatasetRevision:
    """One immutable version of a curriculum dataset."""

    dataset_id: str
    name: str
    version: int
    created_at: float = field(default_factory=time.time)
    uri: str = ""
    examples: list[DatasetExample] = field(default_factory=list)
    source_lessons: list[str] = field(default_factory=list)
    research_ids: list[str] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    lesson_experiment_ids: list[str] = field(default_factory=list)
    filtering_policy: dict = field(default_factory=dict)
    dedup: dict = field(default_factory=dict)
    quality_status: str = DatasetQuality.PENDING
    content_hash: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def example_count(self) -> int:
        return len(self.examples)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["examples"] = [e.to_dict() for e in self.examples]
        return data

    def content_payload(self) -> str:
        return json.dumps(
            [e.to_dict() for e in self.examples],
            sort_keys=True,
            separators=(",", ":"),
        )


def compute_content_hash(examples: list[DatasetExample]) -> str:
    """Real content hash: SHA-256 of the serialized example payload.  A
    changed example changes the hash — the dataset id never lies."""
    payload = json.dumps(
        [e.to_dict() for e in examples], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CurriculumDatasetBuilder:
    """Builds immutable, provenance-rich dataset revisions from the lesson gate."""

    def __init__(
        self,
        gate: Any,
        *,
        store_path: Optional[Path] = None,
        base_uri: str = "jarvis://curriculum/datasets",
    ) -> None:
        self.gate = gate
        self.base_uri = base_uri
        self._store_path = store_path
        self._datasets: dict[str, dict[int, DatasetRevision]] = {}
        self._by_hash: dict[str, str] = {}  # content hash -> dataset_id:version
        if store_path is not None:
            self._load(store_path)

    # ------------------------------------------------------------------
    # Persistence (optional, JSONL)
    # ------------------------------------------------------------------
    def _load(self, store_path: Path) -> None:
        if not store_path.exists():
            return
        for line in store_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                ver = int(data["version"])
                data["examples"] = [DatasetExample(**e) for e in data.get("examples", [])]
                revision = DatasetRevision(**data)
            except (KeyError, TypeError, ValueError):
                continue
            self._datasets.setdefault(revision.dataset_id, {})[ver] = revision
            self._by_hash[revision.content_hash] = f"{revision.dataset_id}:{ver}"

    def _persist(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for datasets in self._datasets.values():
            for revision in datasets.values():
                rows.append(json.dumps(revision.to_dict()))
        self._store_path.write_text("\n".join(rows), encoding="utf-8")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(
        self,
        *,
        name: str,
        min_quality_score: float = 0.5,
        include_statuses: Optional[list[str]] = None,
        experiment_ids: Optional[list[str]] = None,
        policy_notes: str = "",
        actor: str = "dataset_builder",
    ) -> DatasetRevision:
        """Publish a new dataset revision from verified lessons.

        Filtering is explicit and recorded in ``filtering_policy``:
        lesson status, minimum quality score, dedup strategy.  Uniqueness is
        enforced per content hash; duplicates are counted and dropped with a
        report (``dedup``).
        """
        allow = [s.value if hasattr(s, "value") else str(s) for s in
                 (include_statuses or [LessonClass.VERIFIED])]
        candidates = [l for l in self.gate.lessons() if l.status.value in allow]

        policy = {
            "min_quality_score": float(min_quality_score),
            "include_statuses": allow,
            "dedup_strategy": "content_hash",
            "notes": policy_notes,
        }

        selected: list[CurriculumLesson] = []
        seen_hashes: set[str] = set()
        duplicates = 0
        for lesson in sorted(candidates, key=lambda l: l.difficulty):
            key = lesson.content_hash
            if key in seen_hashes:
                duplicates += 1
                continue
            if lesson.quality_score < min_quality_score:
                continue
            selected.append(lesson)
            seen_hashes.add(key)

        examples: list[DatasetExample] = []
        for lesson in selected:
            # Deterministic example id: the same source lesson always yields the
            # same bytes, so republishing the same lessons is a new *version* of
            # the same immutable dataset (not a new dataset). The id still
            # changes the moment any lesson content changes.
            example_id = "ex-{}".format(
                hashlib.sha256(
                    f"{lesson.lesson_id}|{lesson.content_hash}".encode("utf-8")
                ).hexdigest()[:12]
            )
            examples.append(
                DatasetExample(
                    example_id=example_id,
                    problem=lesson.problem,
                    context=lesson.context,
                    constraints=tuple(lesson.constraints),
                    expected_format=lesson.expected_format,
                    resolved_solution=lesson.verified_solution,
                    verification_status=lesson.verification.get("outcome", "VERIFIED"),
                    verification_method=lesson.verification.get("method", "lesson_gate"),
                    domain=lesson.domain,
                    difficulty=lesson.difficulty,
                    difficulty_label=lesson.difficulty_label,
                    provenance={
                        "lesson_id": lesson.lesson_id,
                        "problem_id": lesson.problem_id,
                        "teacher_keys": list(lesson.teacher_keys),
                        "evidence_ids": list(lesson.evidence_ids),
                        "research_ids": list(lesson.research_ids),
                        "dataset_builder": "curriculum",
                    },
                )
            )

        # Content hash over the ACTUAL payload (spec §28 real hash).
        payload = json.dumps(
            [e.to_dict() for e in examples], sort_keys=True, separators=(",", ":")
        )
        dataset_id = "ds-{}".format(
            hashlib.sha256(f"{name}|{payload}".encode("utf-8")).hexdigest()[:16]
        )
        existing = self._datasets.get(dataset_id)
        version = (max(existing) + 1) if existing else 1

        revision = DatasetRevision(
            dataset_id=dataset_id,
            name=name,
            version=version,
            uri=f"{self.base_uri}/{name}/v{version}",
            examples=examples,
            source_lessons=[l.lesson_id for l in selected],
            research_ids=sorted({rid for l in selected for rid in _flatten(l.research_ids)}),
            experiment_ids=sorted(set(experiment_ids or [])),
            filtering_policy=policy,
            dedup={
                "candidates": len(candidates),
                "selected": len(selected),
                "duplicates_removed": duplicates,
                "strategy": "content_hash",
            },
            quality_status=DatasetQuality.QUALIFIED
            if selected and all(e.verification_status == "VERIFIED" for e in examples)
            else DatasetQuality.PENDING,
            content_hash=compute_content_hash(examples),
            metadata={"actor": actor, "lessons_considered": len(candidates)},
        )

        self._datasets.setdefault(dataset_id, {})[version] = revision
        self._by_hash[revision.content_hash] = f"{dataset_id}:{version}"
        self._persist()
        return revision

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def revisions(self, dataset_id: str) -> list[DatasetRevision]:
        return sorted(
            (self._datasets.get(dataset_id) or {}).values(), key=lambda r: r.version
        )

    def get(self, dataset_id: str, version: int) -> Optional[DatasetRevision]:
        return (self._datasets.get(dataset_id) or {}).get(version)

    def latest(self, dataset_id: str) -> Optional[DatasetRevision]:
        versions = self.revisions(dataset_id)
        return versions[-1] if versions else None

    def all_datasets(self) -> list[DatasetRevision]:
        result: list[DatasetRevision] = []
        for datasets in self._datasets.values():
            for revision in datasets.values():
                result.append(revision)
        result.sort(key=lambda r: -r.created_at)
        return result

    def find_by_hash(self, content_hash: str) -> Optional[str]:
        return self._by_hash.get(content_hash)

    def snapshot(self) -> dict:
        latest = [self.latest(did) for did in self._datasets]
        latest = [l for l in latest if l is not None]
        return {
            "datasets": len(self._datasets),
            "revisions": sum(len(v) for v in self._datasets.values()),
            "examples_total": sum(r.example_count for r in latest),
            "latest": [r.to_dict() for r in latest],
        }


def _flatten(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    out: list[str] = []
    for v in values:
        if isinstance(v, list):
            out.extend(_flatten(v))
        elif v:
            out.append(str(v))
    return out