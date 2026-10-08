"""Dataset pipeline for the Learning Arena (spec §25.5, §31).

Manages the dataset lifecycle for learning tasks:
  * **Validation** — schema/type checks before a dataset is usable.
  * **Versioning** — each dataset has a unique version ID (SHA256 of content).
  * **Lineage** — tracks which dataset produced which model revision.
  * **Storage** — metadata-only; actual data is referenced by path/URI.

Datasets are never loaded into memory by this module — only metadata is
tracked.  This keeps the arena lightweight and avoids loading large data
into the model context (spec §16/§69).
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DatasetStatus(Enum):
    """Dataset lifecycle status."""

    REGISTERED = "registered"
    VALIDATED = "validated"
    READY = "ready"
    ARCHIVED = "archived"
    ERROR = "error"


@dataclass
class DatasetValidation:
    """Result of a dataset validation pass."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    size_bytes: int = 0


@dataclass
class Dataset:
    """Metadata for a learning dataset (spec §25.5)."""

    id: str
    name: str
    version: str    # semantic version, e.g. "1.0.0"
    uri: str        # path or URI to the actual data
    status: DatasetStatus = DatasetStatus.REGISTERED
    format: str = "jsonl"  # jsonl, parquet, csv, ...
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"
    tags: list[str] = field(default_factory=list)
    validation: Optional[DatasetValidation] = None
    lineage: list[str] = field(default_factory=list)  # parent dataset IDs
    used_by: list[str] = field(default_factory=list)  # model revision IDs that used this

    @property
    def content_hash(self) -> str:
        """Content hash derived from name + version + uri (spec §31)."""
        raw = f"{self.name}:{self.version}:{self.uri}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_ready(self) -> bool:
        return self.status == DatasetStatus.READY


class DatasetArena:
    """Manages dataset registration, validation, and lineage (spec §31).

    All validation is in-memory — the arena checks metadata, not the full
    dataset content.  For detailed validation, a ``validator`` callback can
    be injected.
    """

    def __init__(self, validator: Any = None) -> None:
        self._datasets: dict[str, Dataset] = {}
        self._validator = validator

    def register(
        self,
        name: str,
        uri: str,
        *,
        version: str = "1.0.0",
        format: str = "jsonl",
        created_by: str = "system",
        tags: list[str] = None,
        lineage: list[str] = None,
    ) -> Dataset:
        """Register a new dataset.  Validation must be run separately."""
        dataset = Dataset(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
            uri=uri,
            format=format,
            created_by=created_by,
            tags=tags or [],
            lineage=lineage or [],
        )
        self._datasets[dataset.id] = dataset
        return dataset

    def validate(self, dataset_id: str) -> DatasetValidation:
        """Validate a dataset's metadata (and optionally content via injected validator)."""
        ds = self._datasets.get(dataset_id)
        if ds is None:
            raise KeyError(f"unknown dataset: {dataset_id}")

        errors: list[str] = []
        warnings: list[str] = []

        # Basic metadata checks.
        if not ds.name:
            errors.append("dataset name is empty")
        if not ds.uri:
            errors.append("dataset URI is empty")

        # File exists check (if local path).
        if ds.uri.startswith("/") or ds.uri.startswith("~/"):
            expanded = os.path.expanduser(ds.uri)
            if not os.path.exists(expanded):
                errors.append(f"dataset file not found: {ds.uri}")

        # Content validation via injected validator.
        if self._validator is not None:
            try:
                val = self._validator(ds)
                if isinstance(val, DatasetValidation):
                    ds.validation = val
                    ds.status = (
                        DatasetStatus.VALIDATED if val.valid else DatasetStatus.ERROR
                    )
                    return val
            except Exception as exc:  # noqa: BLE001
                errors.append(f"validator raised: {exc}")
        else:
            # Minimal validation: set status to VALIDATED if metadata checks pass.
            pass

        val = DatasetValidation(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
        ds.validation = val
        ds.status = DatasetStatus.VALIDATED if val.valid else DatasetStatus.ERROR
        return val

    def mark_ready(self, dataset_id: str) -> Dataset:
        ds = self._datasets.get(dataset_id)
        if ds is None:
            raise KeyError(f"unknown dataset: {dataset_id}")
        if ds.status != DatasetStatus.VALIDATED:
            raise ValueError(f"dataset not validated: status={ds.status}")
        ds.status = DatasetStatus.READY
        return ds

    def get(self, dataset_id: str) -> Optional[Dataset]:
        return self._datasets.get(dataset_id)

    def find_by_name(self, name: str, version: Optional[str] = None) -> list[Dataset]:
        result = [d for d in self._datasets.values() if d.name == name]
        if version:
            result = [d for d in result if d.version == version]
        return sorted(result, key=lambda d: d.created_at, reverse=True)

    def record_usage(self, dataset_id: str, model_revision: str) -> None:
        """Record that a model revision was trained on this dataset (lineage)."""
        ds = self._datasets.get(dataset_id)
        if ds is None:
            return
        if model_revision not in ds.used_by:
            ds.used_by.append(model_revision)

    def lineage_chain(self, dataset_id: str) -> list[Dataset]:
        """Return the full lineage chain (parents -> this dataset)."""
        chain: list[Dataset] = []
        seen: set[str] = set()
        stack = [dataset_id]
        while stack:
            rid = stack.pop()
            if rid in seen:
                continue
            seen.add(rid)
            ds = self._datasets.get(rid)
            if ds is None:
                continue
            chain.append(ds)
            stack.extend(ds.lineage)
        return list(reversed(chain))

    def all(self) -> list[Dataset]:
        return list(self._datasets.values())

    def clear(self) -> None:
        self._datasets.clear()
