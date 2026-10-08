# JARVIS Experiment Engine

## Overview

The **Experiment Engine** (`jarvis_backend/experiment_engine.py`) is the
orchestration layer for the JARVIS Laboratory.  It drives experiments through
the complete scientific method lifecycle, integrating with the existing
compute, job, artifact, evaluation, and promotion infrastructure.

The `ExperimentOrchestrator` class is the single entry point for all
experiment operations.

---

## Core Abstraction: Experiment ≠ JobRegistry

This is a critical architectural distinction:

- **Experiment** represents a *scientific/engineering investigation* — the
  design, hypothesis, baseline, candidate, metrics, comparison, and
  conclusion.
- **JobRegistry** represents *execution* — tracking jobs on compute resources.

The Experiment Engine bridges these two layers: it designs experiments,
selects real compute resources, submits jobs via JobRegistry, runs
evaluations, and verifies results — all while maintaining truthful
provenance and never fabricating metrics.

---

## ExperimentOrchestrator

Located at `jarvis_backend.experiment_engine.ExperimentOrchestrator`.

### Methods

#### `design_experiment(mission_id, name, design, owner)`

Creates a new `Experiment` in the `DESIGNED` state from an
`ExperimentDesign`.

**Secret rejection:** Calls `brain_fabric.assert_no_secrets()` on the
serialized design.  If any secret-shaped keys are found
(`api_key`, `token`, `password`, `secret`, `credential`, etc.), the
experiment is:
1. Set to `BLOCKED` status with `blocked_reason` set
2. Saved to the store
3. A `ValueError` is raised listing the leaked paths

**Never fabricates:** The experiment is only created from a real, validated
design.  No mock or placeholder data is generated.

#### `select_resources(exp_id) → ResourceSelectionResult`

Selects compute resources using `cloud_fabric.select_compute()` based on the
experiment's `compute_requirements`.

**Truthful availability:** Resources are selected based on actual
verification from `cloud_fabric.cloud_resources()`, which performs real
health checks.  Availability is NEVER reported merely because credentials
exist.

Returns a `ResourceSelectionResult` with:
- `selected: bool` — whether a resource was selected
- `resource_id: str` — the selected resource ID
- `reason: str` — selection or blocking reason
- `details: dict` — full selection details
- `available_resources: list[dict]` — all available resources with status

If no resource is selected, the reason comes from
`sel_result.get("infeasible_reason")` or `"no_resources_available"`.

**Resource states** (from `cloud_fabric`):
`CONFIGURED → AUTHENTICATED → REACHABLE → HEALTHY →
RESOURCE_VERIFIED → JOB_VERIFIED → AVAILABLE` / `UNAVAILABLE` / `DEGRADED`
/ `BLOCKED`

#### `prepare_experiment(exp_id) → Experiment`

Prepares an experiment by:
1. Loading the experiment from the store
2. Selecting resources via `select_resources()`
3. If no resource: transitions to `BLOCKED`, appends provenance, returns
4. Validating the resource meets compute bounds via `_validate_resource()`
5. If resource doesn't meet requirements: transitions to `BLOCKED`
6. Updates `compute_requirements["selected_resource"]`
7. Appends `resource_selected:<id>` to provenance
8. Transitions to `READY`

#### `run_experiment(exp_id) → ExperimentRunResult`

Runs an experiment end-to-end:
1. Loads experiment (404 if not found)
2. If `READY`: transitions to `RUNNING`
3. If `DESIGNED`: calls `prepare_experiment()`, then transitions to `RUNNING`
4. If `DESIGNED` + prepare blocks: returns `BLOCKED` result
5. If any other status: raises `ExperimentTransitionError`
6. Submits evaluation job via `_submit_evaluation_job()`
7. If job submission fails: transitions to `FAILED`, returns failure result
8. Calls `analyze_results()` to compute metrics
9. Returns `ExperimentRunResult` with success, job IDs, metrics, and
   selected resource

#### `analyze_results(exp_id) → Experiment`

Analyzes experiment results by computing metrics via
`EvaluationSuiteRegistry`:
1. Loads experiment
2. If `RUNNING`: transitions to `ANALYZING`
3. If not `ANALYZING`: raises `ExperimentTransitionError`
4. Calls `_compute_metrics()` to get typed `Metric` objects
5. Stores `exp.results["metrics"]` as metric dicts
6. Saves and returns

#### `verify_experiment(exp_id) → Experiment`

Verifies an experiment's results:
1. Loads experiment
2. If `ANALYZING`: attempts transition to `VERIFYING`
   - If transition fails (e.g., missing baseline): collects issues, saves
     `verification_issues`, transitions to `FAILED`, returns
3. If not `ANALYZING` or `VERIFYING`: raises `ExperimentTransitionError`
4. Performs verification checks:
   - Metric schema validation (name, value, unit present)
   - Provenance checks (each metric has non-empty provenance)
   - Comparison integrity (comparisons have required fields)
   - Baseline presence check
   - Job status verification
   - Artifact existence checks
5. Stores `exp.results["verification_issues"]` with any issues found
6. Returns the experiment

**Key fix:** The `VERIFYING` transition is wrapped in a try/except for
`ExperimentTransitionError` so that missing baseline (required for `VERIFYING`
in the state machine) is handled gracefully rather than crashing.

#### `complete_experiment(exp_id) → Experiment`

Finalizes a verified experiment:
1. Loads experiment
2. If not `VERIFYING`:
   - If already `COMPLETED`: builds manifest if missing, records hypothesis
     outcome, returns
   - Else: raises `ExperimentTransitionError`
3. Builds `ReproducibilityManifest` via `_build_reproducibility_manifest()`
4. Sets `exp.reproducibility_metadata = manifest`
5. Saves and transitions to `COMPLETED`
6. Records hypothesis outcome via `_record_hypothesis_outcome()`
7. Returns

**Key fix:** When the experiment is already `COMPLETED` but
`reproducibility_metadata` is `None`, the manifest is built and the
hypothesis outcome is recorded before returning (rather than returning
without completing the manifest).

#### `establish_baseline(exp_id, model_id, revision, metrics, compute)`

Establishes a baseline for an experiment by recording the baseline model,
revision, metrics, compute used, and timestamp.  The baseline is stored as
a dict on `exp.baseline` and saved.

**Secret check:** Metrics are scrubbed via `assert_no_secrets()` before
storage.

#### `add_candidate(exp_id, model_id, metrics)`

Adds a candidate model to an experiment and automatically computes
comparisons against the baseline using `ExperimentComparison.from_metrics()`.

Returns a dict with the candidate and any new comparisons.

#### `evaluate_for_promotion(exp_id, criteria, evaluator)`

Evaluates the experiment's candidate for promotion via `PromotionGate`:
1. Builds an `EvaluationCriteria` from the experiment's comparison metrics
2. Calls `PromotionGate.evaluate_for_promotion()` with the candidate model
   ID, criteria, and evaluator
3. Returns the promotion outcome and details

**Fallback:** If the candidate model is not found in PromotionGate, it
returns `(PromotionOutcome.REJECTED, {"reason": "Model not found"})`.

#### `report_blocked(exp_id, reason)`

Reports an experiment as blocked with a reason, transitioning to `BLOCKED`
and updating `blocked_reason`.

#### `_build_reproducibility_manifest(exp) → ReproducibilityManifest`

Builds a full reproducibility manifest capturing:
- Code revision (from git)
- Dataset versions (from experiment's datasets)
- Model versions (from baseline + candidates)
- Configuration (from experiment's `configurations`)
- Hyperparameters (from compute requirements)
- Evaluation suite ID:version
- Compute resource (selected resource)
- Environment (Python, platform, torch, safetensors versions)
- Random seed (from configuration)
- Software versions
- Artifacts
- Metrics (from baseline + candidates)

#### `_record_hypothesis_outcome(exp)`

Records the experiment's outcome against the parent mission's hypotheses
via `HypothesisEngine.record_experiment_outcome()`.

#### `_submit_evaluation_job(exp) → dict`

Submits an evaluation job to `JobRegistry` using the experiment's selected
resource and configuration.  Returns `{"success": bool, "job_id": str}` or
`{"success": False, "error": str}`.

---

## Supporting Types

### ExperimentRunResult

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether the run succeeded |
| `experiment_id` | `str` | Experiment ID |
| `status` | `str` | Final status |
| `message` | `str` | Result message |
| `job_ids` | `list[str]` | Submitted job IDs |
| `metrics` | `list[dict]` | Computed metrics |
| `blocked_reason` | `Optional[str]` | Blocking reason if blocked |
| `resources_selected` | `Optional[str]` | Selected resource ID |

### ResourceSelectionResult

| Field | Type | Description |
|-------|------|-------------|
| `selected` | `bool` | Whether a resource was selected |
| `resource_id` | `str` | Selected resource ID |
| `reason` | `str` | Selection/blocking reason |
| `details` | `dict` | Full selection details |
| `available_resources` | `list[dict]` | All available resources |

### ComputeBounds

Wraps `cloud_fabric.local_hardware()` + `select_compute()`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gpu_required` | `bool` | `False` | GPU required? |
| `min_gpu_memory_gb` | `float` | `0.0` | Minimum VRAM (GB) |
| `min_cpu_cores` | `int` | `1` | Minimum CPU cores |
| `min_ram_gb` | `float` | `1.0` | Minimum RAM (GB) |
| `task_type` | `str` | `"evaluation"` | Task type |
| `max_cost_class` | `str` | `"free_local"` | Max cost tier |
| `network_required` | `bool` | `False` | Network needed? |
| `docker_required` | `bool` | `False` | Docker needed? |
| `offline_ok` | `bool` | `True` | Offline execution OK? |

---

## State Machine

The experiment lifecycle state machine (`ExperimentLifecycle` in
`experiment.py`):

```
                              READY
                                |
DESIGNED ───────────────────────┤
  │                             │
  │ BLOCKED                     │ RUNNING
  ▼                             ▼
BLOCKED ───────────► RUNNING ──► ANALYZING ─────────► VERIFYING
  │                   │              │                    │
  │ CANCELLED         │ FAILED       │ FAILED             │
  │                   │              │ INCONCLUSIVE       │
  │                   │              │ CANCELLED            │
  │                   │              ▼                    ▼
  │                   │         INCONCLUSIVE          COMPLETED
  │                   │              ▲                    ▲
  │ CANCELLED         │ CANCELLED    │                    │
  ▼                   ▼              │                    │
CANCELLED           FAILED            │                    │
                                          └─────────────────┘
                                              COMPLETED
```

Transition rules (defined in `_EXPERIMENT_TRANSITIONS`):
- `VERIFYING` requires `require_baseline=True` (baseline must be set)
- `READY` and `RUNNING` require `require_design=True` (design must be non-empty)
- Terminal states (`COMPLETED`, `FAILED`, `CANCELLED`, `INCONCLUSIVE`) have no outgoing transitions

---

## Integration Points

| Component | Integration | File |
|-----------|-------------|------|
| `cloud_fabric` | Resource selection, health checks | `jarvis_backend/cloud_fabric.py` |
| `JobRegistry` | Job submission and tracking | `infrastructure/job_registry.py` |
| `ArtifactRegistry` | Artifact registration | `infrastructure/artifact_registry.py` |
| `PromotionGate` | Model promotion evaluation | `infrastructure/promotion_gate.py` |
| `HypothesisEngine` | Hypothesis outcome recording | `jarvis_backend/hypothesis_engine.py` |
| `brain_fabric` | Secret scrubbing | `jarvis_backend/brain_fabric.py` |
| `EvaluationSuiteRegistry` | Task-based metric computation | `jarvis_backend/evaluation_suite.py` |
| `SuiteWrapper` | Delegates to real evaluation code | `jarvis_backend/evaluation_suite.py` |
| `DatasetValidator` | Dataset validation pipeline | `jarvis_backend/dataset.py` |
| `Critic` | Critique findings | `jarvis_backend/critic.py` |
| `Verifier` | Verification checks | `jarvis_backend/verifier.py` |

---

## REST API Router

Located at `jarvis_backend/routers/experiments.py`, registered in
`jarvis_backend/main.py` and `jarvis_backend/routers/__init__.py`.

| Route | Method | Handler |
|-------|--------|---------|
| `/api/v1/experiments` | `POST` | `create_experiment` |
| `/api/v1/experiments/{experiment_id}` | `GET` | `get_experiment` |
| `/api/v1/experiments/{experiment_id}/prepare` | `POST` | `prepare_experiment` |
| `/api/v1/experiments/{experiment_id}/run` | `POST` | `run_experiment` |
| `/api/v1/experiments/{experiment_id}/analyze` | `POST` | `analyze_experiment` |
| `/api/v1/experiments/{experiment_id}/verify` | `POST` | `verify_experiment` |
| `/api/v1/experiments/{experiment_id}/complete` | `POST` | `complete_experiment` |
| `/api/v1/experiments/{experiment_id}/baseline` | `POST` | `establish_baseline` |
| `/api/v1/experiments/{experiment_id}/candidate` | `POST` | `add_candidate` |
| `/api/v1/experiments/{experiment_id}/promote` | `POST` | `evaluate_for_promotion` |
| `/api/v1/experiments/{experiment_id}/block` | `POST` | `report_blocked` |
| `/api/v1/experiments/{experiment_id}/critique` | `GET` | `get_critique` |

---

## Test Coverage

`tests/test_experiment_engine.py` — **33 tests** covering:

| Category | Tests |
|----------|-------|
| ComputeBounds | `test_compute_bounds_from_requirements`, `test_compute_bounds_defaults`, `test_compute_bounds_to_requirements_dict` |
| Design | `test_design_experiment`, `test_design_experiment_rejects_secrets` |
| Resource Selection | `test_select_resources_for_experiment`, `test_select_resources_not_found`, `test_select_resources_gpu_required` |
| Preparation | `test_prepare_experiment_selects_local`, `test_prepare_experiment_blocks_on_gpu`, `test_prepare_experiment_from_designed` |
| Execution | `test_run_experiment_auto_prepares`, `test_run_experiment_already_ready`, `test_run_experiment_not_found`, `test_run_experiment_wrong_status` |
| Analysis | `test_analyze_results`, `test_analyze_results_wrong_status` |
| Verification | `test_verify_experiment_no_baseline`, `test_verify_experiment_with_baseline` |
| Completion | `test_complete_experiment`, `test_complete_experiment_requires_verifying` |
| Baseline/Candidate | `test_establish_baseline`, `test_add_candidate_through_orchestrator` |
| Promotion | `test_evaluate_for_promotion_no_candidate`, `test_evaluate_for_promotion_with_candidate` |
| Blocked | `test_report_blocked`, `test_report_blocked_not_found` |
| Real Experiments | `test_experiment_nvidia_gpu_required`, `test_experiment_evaluation_suite_lookup`, `test_experiment_dataset_validation`, `test_experiment_kaggle_no_auth`, `test_experiment_baseline_candidate_comparison`, `test_resource_selection_reports_real_availability` |

**Last run: 33/33 passed (229.82s).**

Note: Each test involving `cloud_resources()` takes ~7-8 seconds due to real
network health checks.  Tests involving `select_compute()` take ~15-30
seconds due to real resource probing.
