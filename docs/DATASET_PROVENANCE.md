# JARVIS Dataset Provenance

## Overview

The JARVIS Laboratory treats datasets as **first-class, versioned, validated
artifacts** with full provenance tracking.  Datasets are never assumed —
they are created, validated through a deterministic pipeline, versioned,
and registered in the `DatasetRegistry`.

Dataset provenance ensures that every experiment can be traced back to the
exact dataset version, hash, and validation status used for its results.

---

## Dataset Data Model

Located in `jarvis_backend/dataset.py`.

### Dataset

```python
@dataclass
class Dataset:
    dataset_id: str              # unique identifier (e.g. "ds_math_qa_2024")
    name: str                    # human-readable name
    version: str = "1"           # semantic version
    source: str = ""             # source system (e.g. "local", "kaggle", "huggingface")
    location: str = ""           # filesystem path or URL
    schema: dict = {}            # column definitions, types, constraints
    license: str = ""            # license string
    provenance: list[str] = []   # audit trail of creation/modification
    hash: str = ""               # SHA-256 hash of content
    created_at: str = ""         # ISO timestamp
    updated_at: str = ""         # ISO timestamp
    validation_stage: str = "generated"
    blocked: bool = False       # True if validation/security failed
    blocked_reason: str = ""     # reason if blocked
    format: str = ""             # data format (e.g. "csv", "json", "parquet")
    row_count: int = 0           # number of data rows
    metadata: dict = {}          # additional metadata
```

- `versioned_id` property: `f"{dataset_id}:v{version}"` (e.g.,
  `ds_math_qa_2024:v1`)
- `to_dict()` / `from_dict()` for serialization
- Persistence via `get_store("datasets")` (SQLite-backed key-value store)
- `Dataset.create(...)` factory method with auto-generated ID and hash

### DatasetRegistry

Persists datasets via `get_store("datasets")`.

| Method | Description |
|--------|-------------|
| `register(dataset)` | Register a dataset (by `versioned_id`) |
| `get_versioned(versioned_id)` | Load a dataset by versioned ID |
| `get(dataset_id, version=None)` | Load best matching version |
| `list_datasets(registered_only=False)` | List all (or only registered) datasets |
| `list_by_source(source)` | List datasets from a specific source |
| `delete(versioned_id)` | Remove a dataset |

**Important:** `list_datasets(registered_only=False)` defaults to `False`,
meaning it lists ALL datasets (including unregistered ones) — not just
registered ones.

---

## Validation Pipeline

The `DatasetValidator` implements a deterministic 7-stage pipeline:

```
GENERATE → VALIDATE → DEDUPLICATE → QUALITY CHECK → SECURITY CHECK → VERSION → REGISTER
```

### Validation Stages

| Stage | Description | Key Checks |
|-------|-------------|------------|
| `generated` | Initial creation | Dataset created with basic metadata |
| `validating` | Format validation | `validate_format()` — checks file exists, format is supported, schema is valid |
| `deduplicating` | Duplicate detection | `deduplicate()` — finds and removes duplicate rows |
| `quality_checking` | Quality assessment | `quality_check()` — checks row count, minimum quality thresholds |
| `security_checking` | Security scan | `security_check()` — scans for secret-shaped strings |
| `versioned` | Version assignment | `version_dataset()` — computes hash, assigns version |
| `registered` | Registry enrollment | `register_dataset()` — persists in DatasetRegistry |

The `validation_stage` field is updated at **each** step and the dataset is
saved between stages.

### DatasetValidator Static Methods

All 6 methods return `ValidationResult` objects:

| Method | Returns | Description |
|--------|---------|-------------|
| `validate_format(dataset)` | `ValidationResult` | Format and schema validation |
| `deduplicate(dataset)` | `ValidationResult` | Duplicate row detection and removal |
| `quality_check(dataset)` | `ValidationResult` | Data quality thresholds |
| `security_check(dataset)` | `ValidationResult` | Secret-shaped string scanning |
| `version_dataset(dataset)` | `ValidationResult` | Hash computation and versioning |
| `register_dataset(dataset)` | `ValidationResult` | Registry enrollment |
| `run_pipeline(dataset)` | `list[ValidationResult]` | Runs all stages in sequence |

### ValidationResult

```python
@dataclass
class ValidationResult:
    stage: str              # e.g. "validating", "registered"
    passed: bool            # True if this stage passed
    error: str = ""         # error message if failed
    details: dict = {}      # additional stage details
```

**Important:** `ValidationResult` uses `passed` (not `success`) as the
boolean field name.

### Pipeline Behavior

`run_pipeline(dataset)` sequences all stages:

1. Calls each validator in order: `validate_format → deduplicate →
   quality_check → security_check → version_dataset → register_dataset`
2. Each stage updates `dataset.validation_stage` and saves
3. If any stage fails (returns `passed=False`), the pipeline stops and the
   dataset is set to `blocked=True` with the error reason
4. If all stages pass, the dataset ends at `validation_stage="registered"`
5. Returns a list of all `ValidationResult` objects (one per stage that ran)

---

## Security Validation

### Secret Scanning

`DatasetValidator.security_check()` uses pattern matching to detect
secret-shaped strings in dataset content:

- Scans all text content (CSV cells, JSON values, etc.) for patterns
  resembling secrets
- Uses `re_search_secret` from `brain_fabric` (the same function used for
  experiment design secret detection)
- Matches key=value patterns like `api_key=sk-something`,
  `password=secret123`, `token=abc123`, etc.
- **Does NOT** flag CSV column headers like `"question,answer"` — only
  matches key=value pattern strings

If secrets are found:
- Dataset is set to `blocked=True`
- `blocked_reason` is set to a description of the findings
- The pipeline stops and does not register the dataset

### Brain Fabric Reuse

The dataset validator reuses `brain_fabric._SECRET_KEYS` and the same
secret-detection logic as the experiment engine, ensuring consistent
security boundaries across all data ingestion paths.

---

## Hash and Integrity

Each dataset is assigned a SHA-256 hash (`dataset.hash`) computed during
the `version_dataset` stage.  The hash covers:
- File content
- Schema definition
- Row count

This hash is stored in the dataset's provenance and used to verify
integrity during experiments.

### Versioned Identity

Datasets use `versioned_id` = `f"{dataset_id}:v{version}"` for unique
identification.  This ensures experiments always reference the exact
dataset version that was used, even if the dataset is later updated.

---

## Experiment Integration

### Dataset Attachment

Experiments store dataset IDs in `exp.datasets: list[str]`.  These are
dataset names (not versioned IDs) — the experiment engine resolves them
to the latest registered version at runtime.

### Dataset Validation Experiments

The experiment engine includes a **Dataset Validation Experiment** that:
1. Creates a CSV dataset with math QA pairs
2. Runs the full validation pipeline via `DatasetValidator.run_pipeline()`
3. Verifies all stages pass (`all(r.passed for r in results)`)
4. Checks `results[0].stage == "validating"` (first pipeline step)
5. Reloads the dataset and confirms `validation_stage == "registered"`

### Provenance Chain

```
Dataset created
  → Hash computed (version_dataset)
  → Registered in DatasetRegistry
  → Dataset ID added to Experiment.datasets
  → Experiment provenance records dataset version
  → ReproducibilityManifest includes dataset_versions with hash + version
  → Experiment result is traceable to exact dataset version
```

---

## Dataset Sources

Datasets can originate from multiple sources, all flowing through the same
validation pipeline:

| Source | Description |
|--------|-------------|
| `local` | Created or placed on the local filesystem |
| `kaggle` | Downloaded from Kaggle (requires auth) |
| `huggingface` | Downloaded from Hugging Face Hub |
| `synthetic` | Generated programmatically |
| `manual` | Manually created by a researcher |

The `source` field records the origin for audit purposes.

---

## Test Coverage

| Test File | Tests | Description |
|-----------|-------|-------------|
| `tests/test_dataset_provenance.py` | 19 | Dataset creation, versioning, validation pipeline, security checks, registry operations, provenance tracking |

**Last run: 19/19 passed (0.82s).**

### Key Test Scenarios

1. `test_dataset_create_and_register` — Full create → validate → register cycle
2. `test_dataset_versioning` — Versioned IDs (`ds_id:v1`, `ds_id:v2`)
3. `test_dataset_hash_integrity` — SHA-256 hash computation and verification
4. `test_dataset_validation_pipeline` — All 7 stages execute in order
5. `test_dataset_security_check_secrets` — Secret-shaped strings are blocked
6. `test_dataset_security_check_no_false_positives` — Normal CSV headers pass
7. `test_dataset_registry_persistence` — Round-trip save/load
8. `test_dataset_provenance_chain` — Full audit trail from creation to experiment

---

## Usage Example

```python
from jarvis_backend.dataset import Dataset, DatasetRegistry, DatasetValidator

# Create a dataset
ds = Dataset.create(
    name="math_qa_v1",
    source="local",
    location="/path/to/math_qa.csv",
    schema={"columns": ["question", "answer"], "types": ["str", "str"]},
    format="csv",
    license="CC-BY-4.0",
)

# Run the validation pipeline
validator = DatasetValidator()
results = validator.run_pipeline(ds)

# Check results
assert all(r.passed for r in results)
assert results[0].stage == "validating"
assert ds.validation_stage == "registered"

# Look up by versioned ID
loaded = DatasetRegistry.get_versioned(ds.versioned_id)
assert loaded.hash == ds.hash  # integrity verified
```
