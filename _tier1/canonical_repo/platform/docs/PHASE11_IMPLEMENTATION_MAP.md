# Phase 11 Implementation Map — JARVIS Laboratory

## Audit Results

### Infrastructure Identified (DO NOT DUPLICATE)

| Component | Location | What it provides |
|-----------|----------|-----------------|
| Persistence | `jarvis_backend/core.py` | `STORES` dict, `Store` class, `get_store(name)`, `now_iso()` |
| Mission lifecycle | `jarvis_backend/mission.py` | Mission dataclass, `ExperimentStatus`-style state machine, `save()`/`load()`/`list_all()`/`create()` via `get_store()` |
| Hypothesis engine | `jarvis_backend/hypothesis_engine.py` | `Hypothesis` dataclass, `HypothesisStatus` enum, `HypothesisEngine.evaluate()` (already accepts `experiments` param) |
| Critic | `jarvis_backend/critic.py` | `CriticFinding` dataclass, `FindingSeverity`, `FindingCategory`, `Critic.critique()` |
| Verifier | `jarvis_backend/verifier.py` | `Verifier.verify_claim()` |
| Cognitive state | `jarvis_backend/cognitive_state.py` | `CognitiveState`, `CognitivePhase`, `CriticFinding` (re-exported) |
| Compute fabric | `jarvis_backend/cloud_fabric.py` | `select_compute()`, `local_hardware()`, `cloud_resources()`, `cloud_status()`, `execution_mode()` |
| Brain fabric | `jarvis_backend/brain_fabric.py` | `assert_no_secrets()`, `discover_brain()`, `BRAIN_RUNTIME_UNAVAILABLE`, `_kaggle_real_status()`, `_hf_real_status()` |
| JobRegistry | `infrastructure/job_registry.py` | `JobInfo`, `JobType` (TRAINING, FINE_TUNING, INFERENCE, EVALUATION, DEPLOYMENT...), `JobStatus` (PENDING, RUNNING, COMPLETED, FAILED...), `create_job()`, `get()`, `update_status()`, `list_jobs()` |
| ArtifactRegistry | `infrastructure/artifact_registry.py` | `ArtifactRecord`, `ArtifactType` (CHECKPOINT, EVAL_DATASET, TRAIN_DATASET, MODEL_WEIGHTS, LORA_ADAPTER, CONFIG...), `ArtifactStatus`, `register()`, `get()`, `list_artifacts()`, `update_status()` |
| ModelRegistry | `infrastructure/model_registry.py` | `ModelRecord`, `ModelLifecycleState` (DISCOVERED→REGISTERED→EVALUATING→CANDIDATE→APPROVED→BLOCKED→DEPLOYED→DEPRECATED→RETIRED), `model_id`, `revision`, `provenance_chain`, `checksum`, `dataset_id`, `evaluation_results` |
| PromotionGate | `infrastructure/promotion_gate.py` | `PromotionGate`, `PromotionOutcome` (APPROVED, REJECTED, NEEDS_MORE_EVAL, BLOCKED), `EvaluationCriteria`, `evaluate_for_promotion()` |
| ProviderRegistry | `infrastructure/provider_registry.py` | `ProviderRecord`, `ProviderInfo`, `ProviderHealthState` |
| Control plane API | `jarvis_backend/routers/control_plane.py` | REST routes for providers, models, jobs, costs, audit, compute, capabilities, remote, health |
| Main wiring | `jarvis_backend/main.py` | `setup_routers()`, `build_app()` — registers router tuple, calls `integrate_silverwing()` |
| Silverwing evaluate | `evaluate_experiment_b.py` (root) | `evaluate_checkpoint()`, `evaluate_math()`, `evaluate_logic()`, `evaluate_coding()`, `evaluate_knowledge()`, `evaluate_generation()`, `evaluate_perplexity()`, `load_checkpoint()`, `PROMPTS` (8 evaluation prompts), `math_problems` (15), `logic_problems` (8), `coding_tasks` (5), `knowledge_qs` (15) |
| Silverwing auto-eval | `evaluate_checkpoints_auto.py` (root) | Automated checkpoint evaluation with perplexity + generation tests |
| Capability contract | `research_engine/capability_contract.py` | **Already defines all 12 `compute.*` capabilities** — NO new capabilities needed |
| Test bootstrap | `jarvis_runtime.py`, `tests/conftest.py` | `bootstrap_runtime()` sets paths + env. conftest sets `DATABASE_URL=sqlite:///./test_jarvis.db`, scrubs provider env vars |
| Store | `jarvis_backend/db.py` | SQL-backed Store (`sqlite:///./test_jarvis.db` in tests), `kv_load()`/`kv_save()` |

### Files That DO NOT Exist (to create)
- `jarvis_backend/experiment.py`
- `jarvis_backend/evaluation_suite.py`
- `jarvis_backend/dataset.py`
- `jarvis_backend/experiment_engine.py`
- `jarvis_backend/routers/experiments.py` (new router — NOT modifying existing control_plane.py)
- Tests: `test_experiment_lifecycle.py`, `test_experiment_model.py`, `test_experiment_engine.py`, `test_evaluation_suite.py`, `test_dataset_provenance.py`, `test_experiment_redteam.py`

### Real Hardware State (truth)
- **CPU**: Intel Core i5-6300U @ 2.40GHz (2 cores)
- **GPU**: Intel HD Graphics 520 (integrated, NOT a compute GPU per `_is_compute_gpu()`)
- **RAM**: 7.9 GB
- **NVIDIA GPU**: NO local NVIDIA GPU → `cloud:nvidia` DEGRADED
- **Docker**: not installed → `docker:execution` BLOCKED
- **Network**: internet reachable (huggingface.co:443 confirmed)
- **Kaggle**: auth unknown — must probe via `_kaggle_real_status()`
- **Hugging Face**: auth unknown — must probe via `_hf_real_status()`
- **Brain**: `BRAIN_RUNTIME_UNAVAILABLE=True` — handled gracefully

### Existing compute.* capabilities (DO NOT CREATE NEW)
```
compute.discover, compute.select, compute.verify, compute.inference,
compute.training, compute.evaluation, compute.embedding,
compute.artifact_upload, compute.artifact_download,
compute.job_submit, compute.job_status, compute.job_cancel,
compute.resource_health
```

---

## Architecture

### Persistence Layer
- **Do NOT create a separate store.** Add `"experiments": dict` to `STORES` in `core.py` (same pattern as `"missions": dict`).
- Experiments persist via `get_store("experiments")` using the same `to_dict()` / `from_dict()` / `save()` / `load()` / `list_all()` / `create()` pattern as Mission.
- Datasets persist via `get_store("datasets")`.
- Evaluation suites persist via `get_store("evaluation_suites")`.

### State Machines

#### Experiment Lifecycle (ExperimentStatus)
```
DESIGNED → READY → RUNNING → ANALYZING → VERIFYING → COMPLETED
  ↓                   ↓           ↓             ↓
BLOCKED             CANCELLED   INCONCLUSIVE  FAILED
```
- DESIGNED: Design complete, awaiting resource selection.
- READY: Resources allocated, awaiting authorization.
- RUNNING: Job submitted, execution in progress.
- ANALYZING: Raw results collected, performing metric computation.
- VERIFYING: Metric schema, provenance, and comparison integrity verified.
- COMPLETED: Verified baseline + candidate comparison with metrics.
- BLOCKED: Required resource, dataset, or model unavailable.
- CANCELLED: User/test cancelled.
- FAILED: Execution error.
- INCONCLUSIVE: Results too ambiguous to draw a conclusion.

#### Dataset Validation Pipeline (DatasetValidationStage)
```
GENERATED → VALIDATING → DEDUPLICATING → QUALITY_CHECKING →
SECURITY_CHECKING → VERSIONED → REGISTERED
```

#### PromotionGate Extension (experiment-aware)
```
EXPERIMENTAL → EVALUATED → CANDIDATE → APPROVED → DEPLOYABLE → DEPLOYED
```
(Extends the existing PromotionGate; experiments feed evaluation results into it.)

### Abstraction Layers (new files — no duplicates)

#### 1. `jarvis_backend/experiment.py` — Core Experiment abstraction
Single file containing:
- **ExperimentStatus** enum: DESIGNED, READY, RUNNING, ANALYZING, VERIFYING, COMPLETED, FAILED, CANCELLED, INCONCLUSIVE, BLOCKED
- **ExperimentDesign** dataclass:
  - `question: str`
  - `hypothesis: str`
  - `independent_variables: list[str]`
  - `dependent_variables: list[str]`
  - `controls: list[str]`
  - `datasets: list[str]`
  - `models: list[str]`
  - `parameters: dict[str, Any]`
  - `expected_outcomes: dict[str, Any]`
  - `success_criteria: list[str]`
  - `failure_criteria: list[str]`
  - `evaluation_method: str`
  - `compute_requirements: dict[str, Any]`
- **Metric** dataclass:
  - `name: str`, `value: float`, `unit: str`, `higher_is_better: bool`, `sample_count: int`, `evaluation_version: str`, `provenance: list[str]`
- **ExperimentComparison** dataclass:
  - `baseline_value: float`, `candidate_value: float`, `absolute_difference: float`, `relative_difference: float`, `sample_count: int`, `evaluation_version: str`
- **ReproducibilityManifest** dataclass:
  - `code_revision: str`, `dataset_versions: list[dict]`, `model_versions: list[dict]`, `configuration: dict`, `hyperparameters: dict`, `evaluation_suite: str`, `compute_resource: str`, `environment: dict`, `random_seed: int`, `software_versions: dict`, `artifacts: list[str]`, `metrics: list[dict]`
- **Experiment** dataclass:
  - `experiment_id`, `mission_id`, `name`, `objective`, `hypothesis`, `variables`, `controls`, `inputs`, `datasets`, `models`, `configurations`, `compute_requirements`, `evaluation_suite`, `metrics`, `baseline`, `candidates`, `results`, `artifacts`, `provenance`, `status`, `created_at`, `started_at`, `completed_at`, `owner`, `budget`, `reproducibility_metadata`
  - `to_dict()` / `from_dict()` / `save()` / `load()` / `list_all()` / `create()` via `get_store("experiments")`
  - `transition(status, actor, reason)` with transition validation (ExperimentLifecycle table)
  - `set_baseline()`, `add_candidate()`, `compute_comparison()`, `to_comparison_dict()`
  - `is_terminal` property
- **ExperimentLifecycle** class:
  - `_TRANSITIONS: dict[ExperimentStatus, frozenset[ExperimentStatus]]`
  - `can_transition(current, target) -> bool`
  - `validate_transition(current, target) -> None` (raises ExperimentTransitionError)

#### 2. `jarvis_backend/evaluation_suite.py` — Versioned evaluation suites
- **EvaluationSuite** dataclass:
  - `suite_id: str`, `name: str`, `version: str`, `tasks: list[dict]`, `scoring_rules: dict`, `required_capabilities: list[str]`, `required_models: list[str]`, `resource_requirements: dict`
  - `to_dict()` / `from_dict()` / `save()` / `load()` / `list_all()` / `create()` via `get_store("evaluation_suites")`
- **Standard suites** (registered via `register_standard_suites()`):
  - MATH_REASONING (accuracy, exact_match)
  - CODE_GENERATION (pass_at_1, exact_match)
  - CODE_REPAIR (pass_at_1)
  - GENERAL_REASONING (accuracy, f1)
  - DOCUMENT_ANALYSIS (f1, exact_match)
  - DATA_ANALYSIS (accuracy, exact_match)
  - TOOL_USE (accuracy, exact_match)
  - RAG (accuracy, f1, exact_match)
  - GEOGRAPHY (accuracy)
  - SECURITY (accuracy, f1)
  - INSTRUCTION_FOLLOWING (accuracy, f1)
- **SuiteWrapper**: wraps existing `evaluate_experiment_b.py` functions — `evaluate_math()`, `evaluate_logic()`, `evaluate_coding()`, `evaluate_knowledge()`, `evaluate_generation()`, `evaluate_perplexity()`, `evaluate_checkpoint()`. Delegates to real evaluation, does NOT fabricate.
- **Metric** is imported from experiment.py (shared).

#### 3. `jarvis_backend/dataset.py` — Dataset abstraction + validation pipeline
- **DatasetValidationStage** enum: GENERATED, VALIDATING, DEDUPLICATING, QUALITY_CHECKING, SECURITY_CHECKING, VERSIONED, REGISTERED
- **Dataset** dataclass:
  - `dataset_id: str`, `name: str`, `version: str`, `source: str`, `location: str`, `schema: dict`, `license: str`, `hash: str`, `provenance: list[str]`, `validation_stage: str`, `created_at`, `updated_at`, `size_bytes`, `record_count`, `owner`
  - `to_dict()` / `from_dict()` / `save()` / `load()` / `list_all()` / `create()` via `get_store("datasets")`
- **DatasetRegistry**: `register()`, `get()`, `list_datasets()`, `update_validation_stage()`, `verify_integrity()`
- **DatasetValidator**: validation pipeline engine
  - `validate(dataset) -> ValidationResult`
  - Stages: validate format → deduplicate → quality check → security check → version → register
  - No mock/fake data generation — validates existing datasets or files provided by caller

#### 4. `jarvis_backend/experiment_engine.py` — Experiment orchestration
- **ExperimentOrchestrator** class:
  - `design_experiment(design: ExperimentDesign) -> Experiment` — creates Experiment in DESIGNED state
  - `prepare_experiment(exp_id) -> Experiment` — selects compute, validates prerequisites, transitions to READY
  - `run_experiment(exp_id) -> Experiment` — submits job to JobRegistry, transitions to RUNNING
  - `analyze_results(exp_id) -> Experiment` — computes metrics via EvaluationSuite, transitions to ANALYZING
  - `verify_experiment(exp_id) -> Experiment` — verifies metric schema, provenance, comparison integrity, transitions to VERIFYING
  - `complete_experiment(exp_id) -> Experiment` — transitions to COMPLETED
  - `compare_baseline_candidate(baseline_metrics, candidate_metrics) -> ExperimentComparison` — NEVER fabricates, requires both
  - `report_blocked(resource_id, reason)` — truthfully reports BLOCKED
- **ExperimentExecutor**: thin adapter that delegates to existing compute infrastructure (`cloud_fabric.select_compute`, `JobRegistry.create_job`) — does NOT execute directly.
- **ComputeBounds**: wraps `cloud_fabric.local_hardware()` + `select_compute()` for performance bounds.

### Integration Points (extend existing, do NOT duplicate)

#### Critic Extension (`jarvis_backend/critic.py`)
- Add `FindingCategory.EXPERIMENT = "experiment"`
- Add `CritiqueResult` type and `critique_experiment(state, experiment)` method:
  - `_check_experiment_missing_baseline`: ERROR if model-improvement experiment has no baseline
  - `_check_experiment_dataset_leakage`: ERROR if candidate trained on evaluation data
  - `_check_experiment_invalid_comparison`: ERROR if baseline/candidate evaluated with different suite versions
  - `_check_experiment_small_sample`: WARNING/ERROR if sample_count below threshold
  - `_check_experiment_metric_mismatch`: ERROR if metrics inconsistent between baseline/candidate
  - `_check_experiment_contamination`: ERROR if datasets overlap
  - `_check_experiment_uncontrolled_variables`: WARNING if IV changed without controls
  - `_check_experiment_missing_provenance`: ERROR if no provenance chain
  - `_check_experiment_unsupported_conclusion`: WARNING if conclusion exceeds evidence
  - `_check_experiment_regression`: ERROR if metric regressed beyond tolerance and not acknowledged
  - `_check_experiment_resource_mismatch`: ERROR if resources don't match compute_requirements
  - `_check_experiment_incomplete_verification`: ERROR if VERIFYING not completed
  - `_check_experiment_self_approval`: ERROR if experiment tries to self-approve or bypass PromotionGate

#### HypothesisEngine Extension (`jarvis_backend/hypothesis_engine.py`)
- `HypothesisEngine.record_experiment_outcome(hypothesis_id, experiment_id, metrics, comparison) -> HypothesisStatus`
  - Links experiment results to hypothesis evaluation
  - Uses `verifier.verify_claim()` with experiment evidence
  - Records `experiment_ids` in Hypothesis for provenance
- Extend `evaluate()` to use experiment metrics as evidence

#### CognitiveKernel Extension (`jarvis_backend/cognitive_kernel.py`)
- Add `_run_experiment()` step in cognitive loop: if mission context has experiment design, delegate to `ExperimentOrchestrator.design_experiment()`.
- Experiments are linked to missions via `mission_id`.
- No changes to existing cycle logic — new step is additive.

#### PromotionGate Integration (`infrastructure/promotion_gate.py`)
- `PromotionGate.evaluate_experiment(experiment) -> PromotionDecision`
  - Feeds ExperimentComparison metrics into `EvaluationCriteria`
  - Transition: candidate model after successful experiment → APPROVED → DEPLOYABLE
- Experiments must pass through PromotionGate; no self-approval.

#### JobRegistry Integration (`infrastructure/job_registry.py`)
- `ExperimentOrchestrator` calls `JobRegistry.create_job()` for each experiment step.
- Job status tracked via `JobStatus` enum.
- Experiment tracks `job_ids` in provenance.

#### ArtifactRegistry Integration (`infrastructure/artifact_registry.py`)
- `ExperimentOrchestrator.register_artifact()` calls `ArtifactRegistry.register()` for:
  - Dataset artifacts (ArtifactType.EVAL_DATASET, TRAIN_DATASET)
  - Checkpoint artifacts (ArtifactType.CHECKPOINT)
  - Model artifacts (ArtifactType.MODEL_WEIGHTS, LORA_ADAPTER)
  - Evaluation reports (ArtifactType.OTHER)
  - Metrics logs (ArtifactType.OTHER)
  - Reproducibility manifests (ArtifactType.CONFIG)

#### Control Plane API (`jarvis_backend/routers/control_plane.py`)
- **NEW router**: `jarvis_backend/routers/experiments.py` — registered in `main.py`
- Routes:
  - `POST /experiments/design` — create experiment from design
  - `POST /experiments/prepare` — select resources, validate
  - `POST /experiments/{id}/run` — submit job
  - `POST /experiments/{id}/analyze` — compute metrics
  - `POST /experiments/{id}/verify` — verify experiment
  - `POST /experiments/{id}/complete` — finalize
  - `GET /experiments/{id}` — get experiment
  - `GET /experiments/{id}/comparison` — get baseline/candidate comparison
  - `GET /experiments/{id}/manifest` — get reproducibility manifest
  - `POST /experiments/baseline-candidate` — establish baseline + candidate
  - `POST /experiments/dataset/validate` — run dataset validation pipeline
  - `GET /experiments/evaluation-suites` — list available suites
  - `POST /experiments/evaluation-suites/run` — run suite on model/checkpoint
- **NO experiment endpoints in control_plane.py** — all go through new `experiments.py` router to avoid bloating the existing 1703-line file.

#### Brain Isolation
- `brain_fabric.assert_no_secrets()` called on all experiment data before it enters Brain context.
- `brain_fabric.discover_brain()` used to check `BRAIN_RUNTIME_UNAVAILABLE` — experiments run regardless.
- Compute selection via `cloud_fabric.select_compute()` — Brain never sees credentials.
- Provider state via `live_provider_status()` — Brain sees only `{"available": bool, "state": str}` not credentials.

### Real Experiments (A-E) — resource-aware
| Experiment | Description | Expected Status |
|-----------|-------------|----------------|
| A | NVIDIA inference benchmark | BLOCKED (no local NVIDIA GPU, no API key) |
| B | Model evaluation using real eval suite | DESIGNED/COMPLETED (local CPU, uses evaluate_experiment_b.py functions where torch available) |
| C | Dataset validation | DESIGNED/COMPLETED (validates existing files) |
| D | Kaggle training | BLOCKED (if no Kaggle auth) or DESIGNED (if auth present) |
| E | Baseline/candidate comparison | DESIGNED (computes comparison from metrics) |

### Security Constraints (enforced)
- `assert_no_secrets()` scrub on all experiment data
- No self-approval — PromotionGate gate is mandatory
- No secrets in experiment data — `find_secrets()` check at every stage
- No fabricated metrics — only values from actual EvaluationSuite runs
- No direct provider credential access — only via cloud_fabric provider state

### No-Fabrication Audit
- Production paths searched for: `mock`, `fake`, `dummy`, `placeholder`, `simulated`, `hardcoded result`, `demo`, `echo`
- Experiment tests include `test_no_fabrication.py` pattern that validates no fabricated metrics
- `Metric.value` must come from actual evaluation, not generated
- `Dataset.hash` must be computed from actual file content

### Test Strategy
- **test_experiment_model.py** — Experiment dataclass, ExperimentDesign, ExperimentStatus, Metric, ExperimentComparison, ReproducibilityManifest (to_dict/from_dict round-trip, transitions)
- **test_experiment_lifecycle.py** — ExperimentLifecycle state machine, transition validation, is_terminal
- **test_experiment_engine.py** — ExperimentOrchestrator: design → prepare → run → analyze → verify → complete, blocked when no resources, baseline mandatory
- **test_evaluation_suite.py** — EvaluationSuite registry, standard suites, SuiteWrapper delegation guard
- **test_dataset_provenance.py** — Dataset dataclass, DatasetRegistry, validation pipeline stages, hash computation
- **test_experiment_redteam.py** — Security: no secrets in data, no self-approval, no fabricated metrics, no bypass of PromotionGate, no arbitrary cloud resource creation
- **test_experiment_no_fabrication.py** — Audit: search production paths for mock/fake/dummy/placeholder/simulated/hardcoded

### Test Command
```bash
cd /d "F:\AI"; python -m pytest Jarvis-super-intelligence-/tests/test_experiment_model.py Jarvis-super-intelligence-/tests/test_experiment_lifecycle.py Jarvis-super-intelligence-/tests/test_experiment_engine.py Jarvis-super-intelligence-/tests/test_evaluation_suite.py Jarvis-super-intelligence-/tests/test_dataset_provenance.py Jarvis-super-intelligence-/tests/test_experiment_redteam.py Jarvis-super-intelligence-/tests/test_experiment_no_fabrication.py -v --tb=short
```

### Regression Test Command
```bash
cd /d "F:\AI"; python -m pytest Jarvis-super-intelligence-/tests/test_capability_contract.py Jarvis-super-intelligence-/tests/test_compute_redteam.py Jarvis-super-intelligence-/tests/test_mission_lifecycle.py Jarvis-super-intelligence-/tests/test_mission_model.py Jarvis-super-intelligence-/tests/test_cognitive_kernel.py Jarvis-super-intelligence-/tests/test_mission_redteam.py -v --tb=short
```
