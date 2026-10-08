"""Phase 11 — Dataset provenance tests.

Validates the Dataset dataclass, DatasetRegistry, DatasetValidator pipeline
(format validation, deduplication, quality checking, security checking),
hash computation, and secret detection in datasets.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from jarvis_backend.core import get_store  # noqa: E402
from jarvis_backend.dataset import (  # noqa: E402
    Dataset,
    DatasetRegistry,
    DatasetValidationStage,
    DatasetValidator,
    ValidationResult,
)


@pytest.fixture(autouse=True)
def _reset_stores():
    get_store("datasets").reset()
    yield
    get_store("datasets").reset()


@pytest.fixture()
def csv_path():
    tmpdir = tempfile.mkdtemp()
    csv_file = os.path.join(tmpdir, "test_data.csv")
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "answer"])
        writer.writerow(["What is 1+1?", "2"])
        writer.writerow(["What is 2+2?", "4"])
        writer.writerow(["What is 3+3?", "6"])
    return csv_file


@pytest.fixture()
def clean_csv_path():
    tmpdir = tempfile.mkdtemp()
    csv_file = os.path.join(tmpdir, "clean_data.csv")
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        writer.writerow(["hello world", "positive"])
        writer.writerow(["good morning", "positive"])
        writer.writerow(["bad day", "negative"])
    return csv_file


@pytest.fixture()
def secret_csv_path():
    tmpdir = tempfile.mkdtemp()
    csv_file = os.path.join(tmpdir, "secret_data.csv")
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["config"])
        writer.writerow(["api_key=sk-1234567890abcdef"])
        writer.writerow(["password=hunter2"])
    return csv_file


# --------------------------------------------------------------------------- #
# Dataset dataclass
# --------------------------------------------------------------------------- #
def test_dataset_create_basic():
    ds = Dataset.create(
        name="test_ds", source="local", location="/tmp/data.csv", owner="test")
    assert ds.dataset_id.startswith("ds_")
    assert ds.name == "test_ds"
    assert ds.version == "1"
    assert ds.source == "local"
    assert ds.location == "/tmp/data.csv"
    assert ds.owner == "test"
    assert ds.validation_stage == DatasetValidationStage.GENERATED
    assert ds.blocked is False
    assert ds.created_at is not None


def test_dataset_to_from_dict():
    ds = Dataset.create(name="test_ds", source="local", location="/tmp/data.csv",
                        owner="test")
    d = ds.to_dict()
    assert d["name"] == "test_ds"
    assert d["source"] == "local"
    assert d["version"] == "1"
    assert d["validation_stage"] == "generated"

    loaded = Dataset.from_dict(d)
    assert loaded.dataset_id == ds.dataset_id
    assert loaded.name == "test_ds"
    assert loaded.version == "1"


def test_dataset_versioned_id():
    ds = Dataset.create(name="test", source="local", location="x", owner="test")
    assert ds.versioned_id == f"{ds.dataset_id}:v1"


def test_dataset_save_and_load(csv_path):
    ds = Dataset.create(name="csv_ds", source="local", location=csv_path,
                        owner="test")
    ds = DatasetRegistry.register(ds)
    loaded = DatasetRegistry.get(ds.dataset_id)
    assert loaded is not None
    assert loaded.dataset_id == ds.dataset_id


def test_dataset_load_nonexistent():
    assert Dataset.load("nonexistent_id") is None


def test_dataset_is_validated():
    ds = Dataset.create(name="test", source="local", location="x", owner="test")
    assert ds.is_validated is False
    ds.validation_stage = DatasetValidationStage.REGISTERED.value
    assert ds.is_validated is True


# --------------------------------------------------------------------------- #
# DatasetRegistry
# --------------------------------------------------------------------------- #
def test_registry_register_and_get(csv_path):
    ds = Dataset.create(name="registry_ds", source="local", location=csv_path,
                        owner="test")
    ds = DatasetRegistry.register(ds)
    loaded = DatasetRegistry.get(ds.dataset_id)
    assert loaded is not None
    assert loaded.name == "registry_ds"


def test_registry_get_versioned(csv_path):
    ds = Dataset.create(name="versioned_ds", source="local", location=csv_path,
                        owner="test")
    ds = DatasetRegistry.register(ds)
    loaded = DatasetRegistry.get_versioned(ds.versioned_id)
    assert loaded is not None


def test_registry_list_datasets(csv_path):
    ds1 = Dataset.create(name="ds1", source="local", location=csv_path, owner="test")
    DatasetRegistry.register(ds1)
    ds2 = Dataset.create(name="ds2", source="local", location=csv_path, owner="test")
    DatasetRegistry.register(ds2)
    # registered_only=False to get unvalidated datasets too
    all_ds = DatasetRegistry.list_datasets(registered_only=False)
    assert len(all_ds) >= 2


def test_registry_update_validation_stage(csv_path):
    ds = Dataset.create(name="stage_ds", source="local", location=csv_path,
                        owner="test")
    ds = DatasetRegistry.register(ds)
    DatasetRegistry.update_validation_stage(
        ds.dataset_id, DatasetValidationStage.REGISTERED)
    loaded = DatasetRegistry.get(ds.dataset_id)
    assert loaded.validation_stage == DatasetValidationStage.REGISTERED.value


# --------------------------------------------------------------------------- #
# DatasetValidator
# --------------------------------------------------------------------------- #
def test_validator_format(csv_path):
    ds = Dataset.create(name="fmt_ds", source="local", location=csv_path,
                        owner="test")
    validator = DatasetValidator()
    result = validator.validate_format(ds)
    assert result.passed is True
    assert result.stage == DatasetValidationStage.VALIDATING.value


def test_validator_format_bad_file():
    ds = Dataset.create(name="bad_ds", source="local",
                        location="/nonexistent/file.csv", owner="test")
    validator = DatasetValidator()
    result = validator.validate_format(ds)
    assert result.passed is False
    assert result.stage == DatasetValidationStage.VALIDATING.value


def test_validator_deduplicate(csv_path):
    ds = Dataset.create(name="dedup_ds", source="local", location=csv_path,
                        owner="test")
    validator = DatasetValidator()
    result = validator.deduplicate(ds)
    assert result.passed is True


def test_validator_quality_check(csv_path):
    ds = Dataset.create(name="quality_ds", source="local", location=csv_path,
                        owner="test")
    validator = DatasetValidator()
    # Must validate format first to set ds.format
    validator.validate_format(ds)
    result = validator.quality_check(ds)
    assert result.passed is True
    assert result.details.get("record_count", 0) > 0


def test_validator_security_check_no_secrets(clean_csv_path):
    ds = Dataset.create(name="safe_ds", source="local", location=clean_csv_path,
                        owner="test")
    ds.validation_stage = DatasetValidationStage.SECURITY_CHECKING.value
    validator = DatasetValidator()
    result = validator.security_check(ds)
    assert result.passed is True
    assert ds.blocked is False


def test_validator_security_check_detects_secrets(secret_csv_path):
    ds = Dataset.create(name="leak_ds", source="local", location=secret_csv_path,
                        owner="test")
    ds.validation_stage = DatasetValidationStage.SECURITY_CHECKING.value
    validator = DatasetValidator()
    result = validator.security_check(ds)
    assert result.passed is False
    assert ds.blocked is True


def test_validator_full_pipeline_csv(csv_path):
    ds = Dataset.create(name="pipeline_ds", source="local", location=csv_path,
                        owner="test")
    ds = DatasetRegistry.register(ds)
    validator = DatasetValidator()
    results = validator.run_pipeline(ds)
    assert isinstance(results, list)
    assert len(results) > 0
    last = results[-1]
    assert last.passed is True


def test_validator_full_pipeline_bad_file():
    ds = Dataset.create(name="bad_pipeline", source="local",
                        location="/nonexistent/file.csv", owner="test")
    ds = DatasetRegistry.register(ds)
    validator = DatasetValidator()
    results = validator.run_pipeline(ds)
    assert isinstance(results, list)
    # At least one stage should fail
    assert any(not r.passed for r in results)


# --------------------------------------------------------------------------- #
# Validation stage enum
# --------------------------------------------------------------------------- #
def test_validation_stage_values():
    stages = [s.value for s in DatasetValidationStage]
    assert "generated" in stages
    assert "validating" in stages
    assert "deduplicating" in stages
    assert "quality_checking" in stages
    assert "security_checking" in stages
    assert "versioned" in stages
    assert "registered" in stages
