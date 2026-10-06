# JARVIS Experiment Security

## Overview

The JARVIS Laboratory enforces a **strict security model** that protects
provider credentials, API keys, and sensitive configuration from ever reaching
the Brain or being embedded in experiment data, datasets, or metrics.

Security is enforced at **four layers**:

1. **Design-time secret scrubbing** — Every experiment design is scanned
   for secret-shaped keys before creation.
2. **Runtime secret scrubbing** — Baseline and candidate metrics are
   scanned for secrets before storage.
3. **Dataset security validation** — All dataset content is scanned for
   secret-shaped strings before registration.
4. **Brain isolation** — The Brain never receives credentials, tokens, or
   provider secrets.  All provider interactions are mediated by
   `ProviderGateway` and `cloud_fabric`.

---

## Brain Isolation Boundary

The Brain **must NEVER** receive:

- API keys
- OAuth tokens
- Provider credentials
- Database passwords
- Filesystem credentials
- SSH keys
- Cloud credentials
- Raw secret configuration
- Unrestricted shell authority

### How Isolation Is Enforced

| Boundary | Mechanism |
|----------|-----------|
| Design scrubbing | `brain_fabric.assert_no_secrets()` called in `design_experiment()` |
| Metric scrubbing | `brain_fabric.assert_no_secrets()` called in `establish_baseline()` and `add_candidate()` |
| Dataset scrubbing | `DatasetValidator.security_check()` scans all content |
| Compute selection | `cloud_fabric.select_compute()` only returns resource IDs, never credentials |
| Job submission | `JobRegistry.create_job()` receives only resource metadata, not secrets |
| Evaluation | `SuiteWrapper` only receives checkpoint paths, not credentials |
| Promotion | `PromotionGate` only receives model evaluation results, not credentials |

---

## Secret Detection

### `_SECRET_KEYS`

Located in `jarvis_backend/brain_fabric.py`:

```python
_SECRET_KEYS = (
    "api_key", "apikey", "token", "secret", "password", "passwd",
    "credential", "authorization", "bearer", "private_key",
)
```

These keys are matched **case-insensitively** against all dict keys at any
depth in the payload.

### `assert_no_secrets(payload, _path="") → list[str]`

Recursively traverses the payload (dict, list, str) and returns a list of
**secret path strings** (e.g., `["parameters.api_key", "configs[0].token"]`).

**Important behavior:**
- Returns a **list** of found secret paths — does NOT raise.
- The caller decides what to do: `ExperimentOrchestrator` raises
  `ValueError` and blocks the experiment.
- Only flags string values that are non-empty, non-boolean, non-None
  (a boolean "configured" flag is metadata, not a secret).
- Does NOT match on value content — only on key names.

### `re_search_secret(text) → bool`

Used by `DatasetValidator.security_check()` to scan text content for
`key=value` patterns that resemble secrets:

```python
import re
_SECRET_PATTERN_RE = re.compile(
    r'(?i)(api[_-]?key|apikey|secret|password|passwd|token|credential|'
    r'authorization|bearer|private[_-]?key)\s*[=:]\s*["\']?[^"\']{4,}'
)
```

- Matches `key=value` or `key: value` patterns
- Requires at least 4 characters after the separator
- **Does NOT** flag CSV column headers like `"question,answer"` — only
  matches key=value pattern strings within cell content

---

## Experiment Pipeline Secret Scrubbing

### 1. Design

In `ExperimentOrchestrator.design_experiment()`:

```python
from jarvis_backend.brain_fabric import assert_no_secrets
leaks = assert_no_secrets(design.to_dict())
if leaks:
    exp.blocked_reason = f"secrets_detected: {leaks}"
    exp.status = ExperimentStatus.BLOCKED.value
    exp.save()
    raise ValueError(f"Secrets detected in experiment design: {leaks}")
```

If any secret-shaped keys are found in the design's serialized dict, the
experiment is:
1. Blocked (status set to `BLOCKED`)
2. The blocked reason is recorded
3. The experiment is saved for audit
4. A `ValueError` is raised listing the leaked paths

### 2. Baseline

In `ExperimentOrchestrator.establish_baseline()`:

```python
leaks = assert_no_secrets(metrics_dicts)
if leaks:
    raise ValueError(f"Secrets detected in baseline metrics: {leaks}")
```

Baseline metrics are scrubbed before the baseline is stored on the
experiment.  This prevents provider API response data (which may contain
tokens) from leaking into experiment provenance.

### 3. Candidate

In `ExperimentOrchestrator.add_candidate()`:

```python
leaks = assert_no_secrets(metrics_dicts)
if leaks:
    raise ValueError(f"Secrets detected in candidate metrics: {leaks}")
```

Same as baseline — all candidate metrics are scrubbed before storage.

### 4. Evaluation Results

In `ExperimentOrchestrator._compute_metrics()`:

Metrics returned from `SuiteWrapper` are `Metric` dataclass instances with
`provenance` lists.  The `assert_no_secrets()` function is NOT called on
metric values (they're floats), but the provenance strings are checked
indirectly through the Critic's secret leakage check.

---

## Critic Secret Leakage Check

The `Critic` performs a dedicated experiment secret leakage check
(`_check_experiment_secret_leakage`):

```python
def _check_experiment_secret_leakage(self, exp: dict) -> list[CriticFinding]:
    """Check for secret leakage in experiment data."""
    leak_paths = assert_no_secrets(exp)
    if leak_paths:
        return [CriticFinding(
            finding_id=f"find_{_short_uuid()}",
            at=now_iso(),
            severity=FindingSeverity.ERROR.value,
            category=FindingCategory.EXPERIMENT.value,
            description=(
                f"Secret leakage detected in experiment data at: {leak_paths}"
            ),
            recommendation="Remove secrets from experiment data and re-run",
        )]
    return []
```

If any secret-shaped data is found in the experiment dict, the Critic
produces an **ERROR**-severity finding in the `EXPERIMENT` category.

---

## Dataset Security Validation

### `DatasetValidator.security_check(dataset) → ValidationResult`

Scans all dataset content for secret-shaped strings:

1. Iterates over every row in the dataset's data
2. For each cell, calls `re_search_secret()` to detect `key=value` patterns
3. If any secrets found:
   - Sets `dataset.blocked = True`
   - Sets `dataset.blocked_reason` with details of matching patterns
   - Returns `ValidationResult(stage="security_checking", passed=False, error=...)`
4. If no secrets: returns `ValidationResult(stage="security_checking", passed=True)`

### Pipeline Behavior

In `DatasetValidator.run_pipeline()`:
```
GENERATE → VALIDATE → DEDUPLICATE → QUALITY CHECK → SECURITY CHECK → VERSION → REGISTER
```

- The security check runs at the `security_checking` stage (5th of 7)
- If security check fails, the pipeline **stops** — the dataset is NOT
  versioned or registered
- The dataset is saved with `blocked=True` and the error reason

### What Gets Flagged

| Content | Flagged? | Reason |
|---------|----------|--------|
| `api_key=sk-12345678` | ✅ Yes | Matches `api_key=value` pattern |
| `password=secret123` | ✅ Yes | Matches `password=value` pattern |
| `token=abc.def.ghi` | ✅ Yes | Matches `token=value` pattern |
| `question,answer,1+1,2` | ❌ No | No `key=value` pattern |
| Column header `question` | ❌ No | Not a key=value pattern |
| Empty cell | ❌ No | No content to match |
| `The API_KEY is set` (prose) | ❌ No | No `=` or `:` followed by value |

---

## Compute Resource Security

### Resource Selection Never Leaks Credentials

`cloud_fabric.select_compute()` returns a dict with resource selection
results:

```python
{
    "selected": "local:control-node",       # resource ID only
    "eligible": ["local:control-node"],
    "evaluated": [...],
    "infeasible_reason": None,
    "local_viable": True,
    ...
}
```

The returned dict contains **only resource IDs and status** — never API
keys, tokens, or credentials.  The `ExperimentOrchestrator` extracts only
`sel_result.get("selected", "")` and stores it as
`compute_requirements["selected_resource"]`.

### `cloud_resources()` Structure

```python
{
    "local_hardware": {...},
    "resources": [
        {"resource_id": "local:control-node", "type": "cpu", "status": "AVAILABLE", ...},
        {"resource_id": "cloud:nvidia", "type": "gpu_inference", "status": "BLOCKED", ...},
        ...
    ],
    "by_id": {
        "local:control-node": {...},
        "cloud:nvidia": {...},
        ...
    },
    "count": N,
    "note": "..."
}
```

Only `resource_id`, `status`, and `type` fields are accessed by the
orchestrator.  Credentials like `api_key`, `api_token`, `kaggle_username`,
etc. are present in the resource dicts but are **never** accessed, stored,
or propagated to experiments.

### Resource Status Truthfulness

Resources are never reported as `AVAILABLE` merely because credentials
exist.  Status is determined by actual verification:

```
CONFIGURED → AUTHENTICATED → REACHABLE → HEALTHY →
RESOURCE_VERIFIED → JOB_VERIFIED → AVAILABLE
```

If credentials exist but the resource is unreachable, the status is
`UNREACHABLE` or `BLOCKED`, and the experiment is truthfully blocked.

---

## Promotion Gate Security

### `PromotionGate.evaluate_for_promotion(model_id, criteria, evaluator)`

The promotion gate receives only:
- `model_id` — the model to evaluate
- `criteria` — `EvaluationCriteria` with thresholds (accuracy, pass rate,
  latency, etc.)
- `evaluator` — who is making the evaluation

It does **not** receive:
- API keys
- Provider credentials
- Dataset contents
- Secret configuration

The gate checks the model's stored `evaluation_results` against the criteria
and returns `(PromotionOutcome, evidence_dict)`.

### Promotion States

```
EXPERIMENTAL → EVALUATED → CANDIDATE → APPROVED → DEPLOYABLE → DEPLOYED
```

A model must pass through all states in order.  Self-promotion (an
experiment approving its own model without going through the gate) is
flagged by the Critic's `_check_experiment_self_approval()`.

---

## Critic Security Findings

The Critic can produce the following security-related findings during
experiment critique:

| Finding | Category | Severity | Trigger |
|---------|----------|----------|---------|
| Missing baseline | `EXPERIMENT` | `ERROR` | Improvement experiment has no baseline |
| Dataset leakage | `EXPERIMENT` | `ERROR` | Same dataset used for baseline and candidate |
| Invalid comparison | `EXPERIMENT` | `WARNING` | Comparing incompatible metrics |
| Small sample | `EXPERIMENT` | `WARNING` | Metric sample count below threshold (default: 10) |
| Metric mismatch | `EXPERIMENT` | `WARNING` | Metric names differ between baseline and candidate |
| Contamination | `EXPERIMENT` | `ERROR` | Candidate trained on evaluation data |
| Uncontrolled variables | `EXPERIMENT` | `WARNING` | Variables present in candidate but not baseline |
| Missing provenance | `EXPERIMENT` | `ERROR` | No provenance records on experiment results |
| Unsupported conclusion | `EXPERIMENT` | `ERROR` | COMPLETED experiment has no comparisons |
| Regression | `EXPERIMENT` | `ERROR` | Candidate metric worse than baseline |
| Resource mismatch | `EXPERIMENT` | `ERROR` | GPU required but no GPU resource selected |
| Incomplete verification | `EXPERIMENT` | `ERROR` | Marked complete but verification failed |
| Self-approval | `EXPERIMENT` | `ERROR` | Experiment bypassing PromotionGate |
| Secret leakage | `EXPERIMENT` | `ERROR` | Secret-shaped data found in experiment |

---

## Test Coverage

| Test File | Tests | Security Aspect |
|-----------|-------|-----------------|
| `tests/test_experiment_redteam.py` | 8 (+1 deselected) | Security red-team: secret rejection, GPU blocking, Kaggle auth, resource truthfulness |
| `tests/test_experiment_no_fabrication.py` | 9 | No-fabrication: no fake metrics, no placeholder data, truthful blocking |
| `tests/test_dataset_provenance.py` | 19 | Dataset security: secret detection in CSV, no false positives on headers |
| `tests/test_experiment_engine.py` | 33 (incl. 2 security) | Secret rejection in design, resource blocking |
| `tests/test_compute_redteam.py` | ~15 | Compute selection red-team: no credential leakage, truthful availability |

---

## Security Audit Results

### Phase 11 No-Fabrication Audit

A comprehensive search for `mock`, `fake`, `dummy`, `placeholder`,
`simulated`, `hardcoded`, `TODO`, `FIXME`, and `xxx` patterns was performed
on all Phase 11 source files:

```
jarvis_backend/experiment.py:           clean
jarvis_backend/experiment_engine.py:    clean
jarvis_backend/evaluation_suite.py:     clean
jarvis_backend/dataset.py:              1 hit (comment describing anti-fabrication)
jarvis_backend/hypothesis_engine.py:    1 hit (comment about deterministic mapping)
jarvis_backend/critic.py:               10 hits (fabrication *detection*, not creation)
jarvis_backend/evidence_engine.py:      3 hits (fabrication *detection*)
jarvis_backend/cognitive_kernel.py:     1 hit (docstring: "No fabrication")
jarvis_backend/cloud_fabric.py:         clean
jarvis_backend/specialist_roles.py:     clean
jarvis_backend/delegation.py:           clean
jarvis_backend/mission_lifecycle.py:     clean
jarvis_backend/mission.py:             clean
jarvis_backend/routers/experiments.py:  clean
```

All hits are in **fraud-detection contexts** — they reference the concept
of fabrication to detect it, not to create it.  No mock data, fake metrics,
placeholder values, or simulated results exist in the codebase.

### EvidenceEngine.assert_no_fabrication()

The `EvidenceEngine` provides a `assert_no_fabrication()` method that
returns a list of fabrication violations.  A violation occurs when a claim
has zero-value metrics without a corresponding failure provenance entry.
This ensures that if an evaluation fails, the failure is **truthfully
recorded** with provenance, rather than silently producing a fake passing
score.
