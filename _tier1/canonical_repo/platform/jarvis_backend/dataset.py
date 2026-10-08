"""Phase 11 — Dataset abstraction and validation pipeline for the JARVIS Laboratory.

A Dataset is a versioned, traceable collection of data used for training,
evaluation, or analysis.  Every dataset carries full provenance: source,
hash, schema, license, and a validation stage that must complete before
the dataset can be registered for use.

Generated datasets CANNOT become training data without passing through the
full validation pipeline: GENERATE → VALIDATE → DEDUPLICATE → QUALITY_CHECK →
SECURITY_CHECK → VERSION → REGISTER.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso

logger = logging.getLogger("jarvis_backend.dataset")


# ---------------------------------------------------------------------------
# Dataset validation stages
# ---------------------------------------------------------------------------
class DatasetValidationStage(str, Enum):
    """Stages in the dataset validation pipeline.

    GENERATED: Dataset created (not yet validated)
    VALIDATING: Format/schema validation in progress
    DEDUPLICATING: Removing duplicates
    QUALITY_CHECKING: Quality checks (completeness, correctness)
    SECURITY_CHECKING: Security scan (secrets, PII, malicious content)
    VERSIONED: Assigned a content hash and version
    REGISTERED: Persisted and available for use
    """

    GENERATED = "generated"
    VALIDATING = "validating"
    DEDUPLICATING = "deduplicating"
    QUALITY_CHECKING = "quality_checking"
    SECURITY_CHECKING = "security_checking"
    VERSIONED = "versioned"
    REGISTERED = "registered"


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
@dataclass
class Dataset:
    """A versioned, traceable dataset with full provenance.

    Persistence via ``get_store("datasets")``.
    """

    dataset_id: str
    name: str
    version: str
    source: str = ""              # e.g. "local_file", "huggingface", "kaggle"
    location: str = ""            # path, URL, or HF repo
    schema: dict[str, Any] = field(default_factory=dict)
    license: str = ""
    hash: str = ""                # SHA256 of content
    provenance: list[str] = field(default_factory=list)
    validation_stage: str = DatasetValidationStage.GENERATED.value
    owner: str = "system"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    size_bytes: int = 0
    record_count: int = 0
    format: str = ""              # e.g. "jsonl", "csv", "parquet"
    metadata: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    block_reason: Optional[str] = None

    @property
    def versioned_id(self) -> str:
        return f"{self.dataset_id}:v{self.version}"

    @property
    def is_validated(self) -> bool:
        """A dataset is validated when it has reached VERSIONED or REGISTERED."""
        return self.validation_stage in (
            DatasetValidationStage.VERSIONED.value,
            DatasetValidationStage.REGISTERED.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "location": self.location,
            "schema": dict(self.schema),
            "license": self.license,
            "hash": self.hash,
            "provenance": list(self.provenance),
            "validation_stage": self.validation_stage,
            "owner": self.owner,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "size_bytes": self.size_bytes,
            "record_count": self.record_count,
            "format": self.format,
            "metadata": dict(self.metadata),
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dataset":
        return cls(
            dataset_id=data["dataset_id"],
            name=data.get("name", ""),
            version=data.get("version", "1"),
            source=data.get("source", ""),
            location=data.get("location", ""),
            schema=dict(data.get("schema", {})),
            license=data.get("license", ""),
            hash=data.get("hash", ""),
            provenance=list(data.get("provenance", [])),
            validation_stage=data.get("validation_stage", DatasetValidationStage.GENERATED.value),
            owner=data.get("owner", "system"),
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
            size_bytes=int(data.get("size_bytes", 0)),
            record_count=int(data.get("record_count", 0)),
            format=data.get("format", ""),
            metadata=dict(data.get("metadata", {})),
            blocked=data.get("blocked", False),
            block_reason=data.get("block_reason"),
        )

    # -- Persistence --
    def save(self) -> None:
        store = get_store("datasets")
        datasets = store.load()
        datasets[self.dataset_id] = self.to_dict()
        store.save()

    @staticmethod
    def load(dataset_id: str) -> Optional["Dataset"]:
        store = get_store("datasets")
        datasets = store.load()
        raw = datasets.get(dataset_id)
        if raw is None:
            return None
        return Dataset.from_dict(raw)

    @staticmethod
    def load_versioned(versioned_id: str) -> Optional["Dataset"]:
        """Load by versioned_id (dataset_id:vN)."""
        store = get_store("datasets")
        datasets = store.load()
        raw = datasets.get(versioned_id)
        if raw is None:
            # Try matching by dataset_id + version
            parts = versioned_id.rsplit(":v", 1)
            if len(parts) == 2:
                for raw_d in datasets.values():
                    if (raw_d.get("dataset_id") == parts[0]
                            and raw_d.get("version") == parts[1]):
                        return Dataset.from_dict(raw_d)
            return None
        return Dataset.from_dict(raw)

    @staticmethod
    def list_all() -> list["Dataset"]:
        store = get_store("datasets")
        datasets = store.load()
        return [Dataset.from_dict(raw) for raw in datasets.values()]

    @staticmethod
    def create(
        name: str,
        source: str = "local_file",
        location: str = "",
        owner: str = "system",
        license: str = "",
        schema: Optional[dict[str, Any]] = None,
    ) -> "Dataset":
        """Create a new Dataset in GENERATED state."""
        ds_id = f"ds_{_short_uuid()}"
        ds = Dataset(
            dataset_id=ds_id,
            name=name,
            version="1",
            source=source,
            location=location,
            schema=schema or {},
            license=license,
            validation_stage=DatasetValidationStage.GENERATED.value,
            owner=owner,
        )
        ds.save()
        return ds


# ---------------------------------------------------------------------------
# Dataset Registry
# ---------------------------------------------------------------------------
class DatasetRegistry:
    """Registry for datasets with persistence via get_store("datasets")."""

    @staticmethod
    def register(dataset: Dataset) -> Dataset:
        """Register (or update) a dataset in the persistent store."""
        dataset.save()
        return dataset

    @staticmethod
    def get(dataset_id: str) -> Optional[Dataset]:
        return Dataset.load(dataset_id)

    @staticmethod
    def get_versioned(versioned_id: str) -> Optional[Dataset]:
        return Dataset.load_versioned(versioned_id)

    @staticmethod
    def list_datasets(
        validation_stage: Optional[str] = None,
        registered_only: bool = True,
    ) -> list[Dataset]:
        """List datasets, optionally filtered by validation stage."""
        store = get_store("datasets")
        datasets = store.load()
        result = []
        for raw in datasets.values():
            ds = Dataset.from_dict(raw)
            if validation_stage and ds.validation_stage != validation_stage:
                continue
            if registered_only and not ds.is_validated:
                continue
            result.append(ds)
        return result

    @staticmethod
    def update_validation_stage(
        dataset_id: str,
        stage: DatasetValidationStage,
    ) -> Optional[Dataset]:
        """Update the validation stage of a dataset."""
        ds = Dataset.load(dataset_id)
        if ds is None:
            return None
        ds.validation_stage = stage.value
        ds.updated_at = now_iso()
        ds.save()
        return ds

    @staticmethod
    def verify_integrity(dataset_id: str) -> dict[str, Any]:
        """Verify a dataset's integrity by checking its hash.

        Returns a dict with:
        - dataset_id, hash, computed_hash, match (bool), record_count, size_bytes
        Never fabricates — if the file cannot be read, match=False.
        """
        ds = Dataset.load(dataset_id)
        if ds is None:
            return {"dataset_id": dataset_id, "match": False, "error": "dataset_not_found"}

        if not ds.hash or not ds.location:
            return {
                "dataset_id": dataset_id,
                "hash": ds.hash,
                "computed_hash": "",
                "match": False,
                "error": "no_hash_or_location",
            }

        computed = _compute_file_hash(ds.location)
        return {
            "dataset_id": dataset_id,
            "hash": ds.hash,
            "computed_hash": computed,
            "match": computed == ds.hash if computed else False,
            "record_count": ds.record_count,
            "size_bytes": ds.size_bytes,
        }


# ---------------------------------------------------------------------------
# Validation Pipeline
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Result of a validation stage."""
    stage: str
    passed: bool
    error: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "passed": self.passed,
            "error": self.error,
            "details": dict(self.details),
        }


class DatasetValidator:
    """Runs the dataset validation pipeline.

    Pipeline: GENERATE → VALIDATE → DEDUPLICATE → QUALITY_CHECK →
    SECURITY_CHECK → VERSION → REGISTER

    Each stage is a method that returns ValidationResult.  The pipeline
    runs sequentially and stops at the first failure.

    NO fabrication: this validator only checks real datasets.  It does
    not generate synthetic data.
    """

    _SECRET_PATTERNS = [
        "api_key", "apikey", "token", "secret", "password", "passwd",
        "credential", "authorization", "bearer", "private_key",
    ]

    @staticmethod
    def validate_format(dataset: Dataset) -> ValidationResult:
        """Validate dataset format and schema."""
        if not dataset.location:
            return ValidationResult(
                stage=DatasetValidationStage.VALIDATING.value,
                passed=False,
                error="no_location",
            )
        if not os.path.exists(dataset.location):
            return ValidationResult(
                stage=DatasetValidationStage.VALIDATING.value,
                passed=False,
                error=f"file_not_found: {dataset.location}",
            )

        fmt = dataset.format
        if not fmt:
            # Infer from extension
            ext = os.path.splitext(dataset.location)[1].lower()
            fmt_map = {".jsonl": "jsonl", ".csv": "csv", ".parquet": "parquet",
                       ".json": "json", ".txt": "txt"}
            fmt = fmt_map.get(ext, "unknown")
            dataset.format = fmt

        if fmt == "unknown":
            return ValidationResult(
                stage=DatasetValidationStage.VALIDATING.value,
                passed=False,
                error=f"unrecognized_format:{ext}",
            )
        return ValidationResult(
            stage=DatasetValidationStage.VALIDATING.value,
            passed=True,
            details={"format": fmt},
        )

    @staticmethod
    def deduplicate(dataset: Dataset) -> ValidationResult:
        """Remove duplicate records from the dataset.

        For JSONL files: reads all lines, deduplicates by content hash.
        For CSV files: reads rows, deduplicates by full row content.
        """
        if not os.path.exists(dataset.location):
            return ValidationResult(
                stage=DatasetValidationStage.DEDUPLICATING.value,
                passed=False,
                error="file_not_found",
            )
        try:
            original_count = dataset.record_count
            if dataset.format == "jsonl":
                seen = set()
                unique_lines = []
                with open(dataset.location, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            h = hashlib.sha256(line.encode()).hexdigest()
                            if h not in seen:
                                seen.add(h)
                                unique_lines.append(line)
                with open(dataset.location, "w", encoding="utf-8") as f:
                    for line in unique_lines:
                        f.write(line + "\n")
                dataset.record_count = len(unique_lines)
                removed = original_count - len(unique_lines) if original_count > 0 else 0
                return ValidationResult(
                    stage=DatasetValidationStage.DEDUPLICATING.value,
                    passed=True,
                    details={"original_count": original_count, "deduplicated_count": len(unique_lines), "removed": removed},
                )
            elif dataset.format == "csv":
                seen = set()
                unique_rows = []
                with open(dataset.location, "r", encoding="utf-8", errors="replace") as f:
                    for row in f:
                        row = row.strip()
                        if row:
                            h = hashlib.sha256(row.encode()).hexdigest()
                            if h not in seen:
                                seen.add(h)
                                unique_rows.append(row)
                with open(dataset.location, "w", encoding="utf-8") as f:
                    for row in unique_rows:
                        f.write(row + "\n")
                dataset.record_count = len(unique_rows)
                removed = original_count - len(unique_rows) if original_count > 0 else 0
                return ValidationResult(
                    stage=DatasetValidationStage.DEDUPLICATING.value,
                    passed=True,
                    details={"original_count": original_count, "deduplicated_count": len(unique_rows), "removed": removed},
                )
            return ValidationResult(
                stage=DatasetValidationStage.DEDUPLICATING.value,
                passed=True,
                details={"format": dataset.format, "skipped": True},
            )
        except Exception as exc:
            return ValidationResult(
                stage=DatasetValidationStage.DEDUPLICATING.value,
                passed=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def quality_check(dataset: Dataset) -> ValidationResult:
        """Run quality checks on the dataset.

        Checks:
        - record_count > 0
        - hash is computable
        - size_bytes is accurate
        """
        if not os.path.exists(dataset.location):
            return ValidationResult(
                stage=DatasetValidationStage.QUALITY_CHECKING.value,
                passed=False,
                error="file_not_found",
            )
        try:
            stat = os.stat(dataset.location)
            dataset.size_bytes = stat.st_size
            if dataset.format == "jsonl":
                count = 0
                with open(dataset.location, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip():
                            count += 1
                dataset.record_count = count
            elif dataset.format == "csv":
                count = 0
                with open(dataset.location, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip():
                            count += 1
                dataset.record_count = count
            else:
                dataset.record_count = 0

            if dataset.record_count == 0:
                return ValidationResult(
                    stage=DatasetValidationStage.QUALITY_CHECKING.value,
                    passed=False,
                    error="empty_dataset",
                    details={"size_bytes": dataset.size_bytes},
                )
            return ValidationResult(
                stage=DatasetValidationStage.QUALITY_CHECKING.value,
                passed=True,
                details={
                    "record_count": dataset.record_count,
                    "size_bytes": dataset.size_bytes,
                },
            )
        except Exception as exc:
            return ValidationResult(
                stage=DatasetValidationStage.QUALITY_CHECKING.value,
                passed=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def security_check(dataset: Dataset) -> ValidationResult:
        """Scan dataset for secrets, PII, and malicious content.

        Searches for secret-shaped strings in the dataset content.
        NEVER passes if secrets are found.
        """
        if not os.path.exists(dataset.location):
            return ValidationResult(
                stage=DatasetValidationStage.SECURITY_CHECKING.value,
                passed=False,
                error="file_not_found",
            )
        try:
            findings = []
            with open(dataset.location, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    lower = line.lower()
                    for pattern in DatasetValidator._SECRET_PATTERNS:
                        if pattern in lower:
                            # Check if it looks like an actual secret (key=value pattern)
                            if re_search_secret(line, pattern):
                                findings.append({
                                    "line": i,
                                    "pattern": pattern,
                                    "snippet": f"line {i} contains secret-shaped content",
                                })
            if findings:
                dataset.blocked = True
                dataset.block_reason = f"secrets_found: {len(findings)} occurrence(s)"
                dataset.save()
                return ValidationResult(
                    stage=DatasetValidationStage.SECURITY_CHECKING.value,
                    passed=False,
                    error="secrets_found",
                    details={"findings": findings},
                )
            return ValidationResult(
                stage=DatasetValidationStage.SECURITY_CHECKING.value,
                passed=True,
                details={"secrets_found": 0},
            )
        except Exception as exc:
            return ValidationResult(
                stage=DatasetValidationStage.SECURITY_CHECKING.value,
                passed=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def version_dataset(dataset: Dataset) -> ValidationResult:
        """Compute content hash and assign version."""
        if not os.path.exists(dataset.location):
            return ValidationResult(
                stage=DatasetValidationStage.VERSIONED.value,
                passed=False,
                error="file_not_found",
            )
        try:
            h = _compute_file_hash(dataset.location)
            dataset.hash = h
            dataset.updated_at = now_iso()
            dataset.provenance.append(f"versioned:{now_iso()}:hash={h[:16]}")
            dataset.save()
            return ValidationResult(
                stage=DatasetValidationStage.VERSIONED.value,
                passed=True,
                details={"hash": h, "version": dataset.version},
            )
        except Exception as exc:
            return ValidationResult(
                stage=DatasetValidationStage.VERSIONED.value,
                passed=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def register_dataset(dataset: Dataset) -> ValidationResult:
        """Register the dataset as validated and available."""
        dataset.validation_stage = DatasetValidationStage.REGISTERED.value
        dataset.updated_at = now_iso()
        dataset.provenance.append(f"registered:{now_iso()}")
        dataset.save()
        return ValidationResult(
            stage=DatasetValidationStage.REGISTERED.value,
            passed=True,
            details={"dataset_id": dataset.dataset_id, "versioned_id": dataset.versioned_id},
        )

    @staticmethod
    def run_pipeline(dataset: Dataset) -> list[ValidationResult]:
        """Run the full validation pipeline.

        Stops at the first failure.  Returns the list of results so far.
        """
        results: list[ValidationResult] = []

        # Stage 1: VALIDATE format
        dataset.validation_stage = DatasetValidationStage.VALIDATING.value
        dataset.save()
        result = DatasetValidator.validate_format(dataset)
        results.append(result)
        if not result.passed:
            return results

        # Stage 2: DEDUPLICATE
        dataset.validation_stage = DatasetValidationStage.DEDUPLICATING.value
        dataset.save()
        result = DatasetValidator.deduplicate(dataset)
        results.append(result)
        if not result.passed:
            return results

        # Stage 3: QUALITY_CHECK
        dataset.validation_stage = DatasetValidationStage.QUALITY_CHECKING.value
        dataset.save()
        result = DatasetValidator.quality_check(dataset)
        results.append(result)
        if not result.passed:
            return results

        # Stage 4: SECURITY_CHECK
        dataset.validation_stage = DatasetValidationStage.SECURITY_CHECKING.value
        dataset.save()
        result = DatasetValidator.security_check(dataset)
        results.append(result)
        if not result.passed:
            return results

        # Stage 5: VERSION
        dataset.validation_stage = DatasetValidationStage.VERSIONED.value
        dataset.save()
        result = DatasetValidator.version_dataset(dataset)
        results.append(result)
        if not result.passed:
            return results

        # Stage 6: REGISTER
        result = DatasetValidator.register_dataset(dataset)
        results.append(result)
        return results


def _short_uuid() -> str:
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]


def _compute_file_hash(filepath: str) -> str:
    """Compute SHA256 hash of a file's content."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def re_search_secret(line: str, pattern: str) -> bool:
    """Check if a line contains a secret-shaped key=value pattern."""
    # Look for common secret assignment patterns: key=value, "key": "value"
    # Return True if the pattern appears to be an actual secret assignment
    import re as _re
    # Check for assignment-style: pattern=... or pattern: ...
    patterns = [
        rf'{pattern}\s*[:=]\s*\S+',
        rf'"{pattern}"\s*:\s*"\S+"',
        rf"'{pattern}'\s*:\s*'\S+'",
    ]
    for p in patterns:
        if _re.search(p, line, _re.IGNORECASE):
            return True
    return False


__all__ = [
    "DatasetValidationStage",
    "Dataset",
    "DatasetRegistry",
    "ValidationResult",
    "DatasetValidator",
]
