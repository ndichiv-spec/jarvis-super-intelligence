# JARVIS Laboratory

## Overview

The JARVIS Laboratory turns JARVIS from a generative assistant into a
**real experimentation, evaluation, simulation, and model-improvement
environment**.  Instead of merely producing text, JARVIS can now investigate
difficult questions by running controlled experiments, measuring real metrics,
comparing baselines against candidates, and feeding the conclusions back into
the hypothesis engine.

The laboratory is built as **Phase 11** of the JARVIS platform and reuses the
existing Mission Control, Cognitive Kernel, Compute Selector, Job Registry,
Artifact Registry, and Promotion Gate infrastructure.  No duplicate
infrastructure was invented.

---

## Core Laboratory Loop

```
QUESTION
   ↓
MISSION
   ↓
HYPOTHESES
   ↓
EXPERIMENT DESIGN
   ↓
RESOURCE SELECTION          ← ComputeSelector / cloud_fabric
   ↓
DATA / INPUT                ← Dataset pipeline
   ↓
EXECUTION                   ← JobRegistry + real compute
   ↓
OBSERVATION                 ← Metric collection
   ↓
ANALYSIS                    ← EvaluationSuite scoring
   ↓
CRITIQUE                    ← Critic findings
   ↓
VERIFICATION                ← Verifier / verify_experiment
   ↓
COMPARISON                  ← baseline vs candidate
   ↓
CONCLUSION                  ← hypothesis outcome
   ↓
ARTIFACT                    ← ArtifactRegistry
   ↓
LESSON                      ← feedback to HypothesisEngine
   ↓
NEXT EXPERIMENT
```

Every stage is traceable through provenance chains and audit events.

---

## Architecture

### Layers

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **Scientific Method** | `Experiment`, `ExperimentDesign` | Captures the question, hypothesis, variables, controls, and success criteria |
| **Experiment Execution** | `ExperimentOrchestrator` | Drives an experiment through the full lifecycle |
| **Compute** | `ComputeBounds`, `cloud_fabric` | Selects real compute resources based on task requirements |
| **Data** | `Dataset`, `DatasetValidator` | Manages dataset creation, validation, and versioning |
| **Evaluation** | `EvaluationSuite`, `SuiteWrapper` | Runs real evaluation tasks and produces typed metrics |
| **Comparison** | `ExperimentComparison`, `Metric` | Baseline vs candidate comparison with diff computation |
| **Verification** | `verify_experiment` | Validates metric schema, provenance, and comparison integrity |
| **Promotion** | `PromotionGate` | Evaluates whether a candidate model is worthy of promotion |
| **Learning** | `HypothesisEngine` | Records outcomes and updates hypothesis confidence |
| **Critique** | `Critic` | Flags inconsistencies, regressions, and unsupported conclusions |

### Brain Isolation Boundary

The Brain **never** receives:
- API keys
- OAuth tokens
- Provider credentials
- Database passwords
- Filesystem credentials
- SSH keys
- Cloud credentials
- Raw secret configuration
- Unrestricted shell authority

The `ExperimentOrchestrator` uses `brain_fabric.assert_no_secrets()` to
scrub every experiment design and metric dict before it ever touches
persistence or execution layers.

---

## Experiment Lifecycle

Experiments progress through a deterministic state machine:

```
DESIGNED → READY → RUNNING → ANALYZING → VERIFYING → COMPLETED
                ↘         ↘          ↘          ↘
               BLOCKED    FAILED      INCONCLUSIVE  CANCELLED
```

| Status | Meaning |
|--------|---------|
| `DESIGNED` | Design complete, awaiting resource selection |
| `READY` | Resources allocated, awaiting execution |
| `RUNNING` | Job submitted, execution in progress |
| `ANALYZING` | Raw results collected, computing metrics |
| `VERIFYING` | Verifying metric schema, provenance, comparison |
| `COMPLETED` | Verified baseline + candidate comparison with metrics |
| `FAILED` | Execution or analysis error |
| `CANCELLED` | Explicitly cancelled |
| `INCONCLUSIVE` | Results too ambiguous for a conclusion |
| `BLOCKED` | Required resource, dataset, or model unavailable |

### Transition Rules

- `DESIGNED` → `READY`, `BLOCKED`, `CANCELLED`, `FAILED`
- `READY` → `RUNNING`, `BLOCKED`, `CANCELLED`
- `RUNNING` → `ANALYZING`, `FAILED`, `CANCELLED`, `BLOCKED`
- `ANALYZING` → `VERIFYING`, `FAILED`, `INCONCLUSIVE`
- `VERIFYING` → `COMPLETED`, `FAILED`, `INCONCLUSIVE`, `CANCELLED`
- `BLOCKED` → `READY`, `DESIGNED`, `CANCELLED`
- Terminal states (`COMPLETED`, `FAILED`, `CANCELLED`, `INCONCLUSIVE`) have no outgoing transitions.

Transitioning to `VERIFYING` requires that a baseline has been established
(`require_baseline=True`).  Transitioning to `READY` or `RUNNING` requires a
non-empty design (`require_design=True`).

---

## Experiment Data Model

### Experiment

| Field | Type | Description |
|-------|------|-------------|
| `experiment_id` | `str` | Unique identifier (`exp_<uuid>`) |
| `mission_id` | `str` | Parent mission reference |
| `name` | `str` | Human-readable name |
| `objective` | `str` | The question being investigated |
| `hypothesis` | `str` | The hypothesis being tested |
| `design` | `dict` | Serialized `ExperimentDesign` |
| `variables` | `list[str]` | Independent variables |
| `controls` | `list[str]` | Controlled variables |
| `inputs` | `list[str]` | Input artifacts |
| `datasets` | `list[str]` | Dataset identifiers |
| `models` | `list[str]` | Model identifiers |
| `configurations` | `dict` | Experiment configuration |
| `compute_requirements` | `dict` | Resource requirements (GPU, CPU, RAM, etc.) |
| `evaluation_suite` | `str` | Suite ID:version (e.g., `math_reasoning:v1`) |
| `baseline` | `Optional[dict]` | Baseline model, revision, metrics, compute, timestamp |
| `candidates` | `list[dict]` | Candidate results |
| `comparisons` | `list[dict]` | Baseline vs candidate comparisons |
| `results` | `dict` | Computed metrics and verification results |
| `artifacts` | `list[str]` | Registered artifact IDs |
| `job_ids` | `list[str]` | Submitted job IDs |
| `provenance` | `list[str]` | Audit trail of state changes and decisions |
| `reproducibility_metadata` | `Optional[dict]` | Reproducibility manifest (built at completion) |
| `status` | `str` | Current lifecycle status |
| `created_at` / `started_at` / `completed_at` | `str` | Timestamps |
| `owner` | `str` | Experiment owner |
| `budget` | `dict` | Budget constraints (max cost, time, jobs, steps) |

### ExperimentDesign

Encapsulates the scientific method:

- `question` — What are we trying to answer?
- `hypothesis` — What do we predict?
- `independent_variables` — Variables we control/change
- `dependent_variables` — Variables we measure
- `controls` — Variables held constant
- `datasets` — Datasets used
- `models` — Models involved
- `parameters` — Experiment parameters
- `expected_outcomes` — Expected results
- `success_criteria` — Conditions for success
- `failure_criteria` — Conditions for failure
- `evaluation_method` — Which evaluation suite to use
- `compute_requirements` — Resource needs

### Metric

A typed, verifiable metric with full provenance:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Metric name (e.g., `math_accuracy`) |
| `value` | `float` | Measured value (never fabricated) |
| `unit` | `str` | Unit (e.g., `ratio`, `perplexity`) |
| `higher_is_better` | `bool` | Optimization direction |
| `sample_count` | `int` | Number of samples evaluated |
| `evaluation_version` | `str` | Suite version ID |
| `provenance` | `list[str]` | Run IDs, artifact IDs, failure notes |

### ExperimentComparison

A truthful comparison computed from real baseline and candidate metrics:

| Field | Type | Description |
|-------|------|-------------|
| `metric_name` | `str` | Name of compared metric |
| `baseline_value` | `float` | Baseline measurement |
| `candidate_value` | `float` | Candidate measurement |
| `absolute_difference` | `float` | Candidate - baseline |
| `relative_difference` | `float` | (candidate - baseline) / baseline |
| `sample_count` | `int` | Sample count |
| `evaluation_version` | `str` | Suite version |

### ReproducibilityManifest

Built at experiment completion. Captures everything needed to reproduce:

- `code_revision` — Git commit hash
- `dataset_versions` — Dataset IDs, versions, hashes
- `model_versions` — Model IDs and revisions
- `configuration` — Experiment configuration
- `hyperparameters` — Compute requirements (used as hyperparams)
- `evaluation_suite` — Suite ID:version
- `compute_resource` — Selected resource ID
- `environment` — Python version, platform, torch availability
- `random_seed` — Seed from configuration
- `software_versions` — Python, platform, torch, safetensors
- `artifacts` — Artifact IDs
- `metrics` — All measured metrics
- `manifest_id` — Unique identifier (`manifest_<uuid>`)

---

## Compute Resource Selection

The laboratory integrates with `cloud_fabric` to select real compute resources.
Resources are truthfully reported with actual verification:

| Resource ID | Description |
|-------------|-------------|
| `local:control-node` | Local CPU execution |
| `cloud:nvidia` | NVIDIA GPU cloud |
| `cloud:kaggle` | Kaggle training runtime |
| `cloud:huggingface` | Hugging Face inference/serving |
| `remote:<id>` | Future remote GPU resources |
| `docker:execution` | Docker-based execution |

Resource states are determined by actual health checks — never by credential
presence alone:

```
CONFIGURED → AUTHENTICATED → REACHABLE → HEALTHY →
RESOURCE_VERIFIED → JOB_VERIFIED → AVAILABLE
```

If resources are unavailable, the experiment is truthfully **BLOCKED** rather
than silently falling back.

---

## Evaluation Suites

The laboratory ships with 13 standard evaluation suites (version 1):

| Suite ID | Name | Tasks |
|----------|------|-------|
| `math_reasoning` | Mathematical Reasoning | `math_arithmetic`, `math_algebra` |
| `code_generation` | Code Generation | `code_python` |
| `code_repair` | Code Repair | `code_repair_python` |
| `general_reasoning` | General Reasoning | `reasoning_deduction`, `reasoning_causal` |
| `document_analysis` | Document Analysis | `doc_qa` |
| `data_analysis` | Data Analysis | `data_query` |
| `tool_use` | Tool Use | `tool_selection`, `tool_execution` |
| `rag` | RAG | `rag_qa` |
| `geography` | Geography | `geo_recall`, `geo_reasoning` |
| `security` | Security | `sec_violation_detection`, `sec_code_analysis` |
| `instruction_following` | Instruction Following | `if_exact_match`, `if_partial_match` |
| `generation_quality` | Generation Quality | `gq_fluency`, `gq_relevance` |
| `perplexity` | Perplexity | `perplexity_eval` |

Each suite defines:
- **Tasks** — Individual evaluation tasks with metrics and input specs
- **Scoring rules** — How to score each metric (accuracy, pass_at_1, f1, exact_match, perplexity)
- **Required capabilities** — e.g., `compute.evaluation`
- **Required models** — e.g., `text-generation`, `causal-lm`
- **Resource requirements** — VRAM, offline capability

Scoring functions: `score_accuracy(correct, total)`,
`score_exact_match(matches, total)`, `score_f1(correct, total, false_positives)`.

---

## Real Experiments

The laboratory runs five real experiment templates:

### Experiment A: NVIDIA Inference Benchmark
- Requires GPU (`gpu_required=True`, 16GB VRAM)
- Truthfully **BLOCKED** when no NVIDIA GPU is available
- Uses `cloud:nvidia` resource

### Experiment B: Model Evaluation Using Real Eval Suite
- Uses `math_reasoning:v1` suite
- Evaluation suites are looked up via `EvaluationSuiteRegistry` after
  `initialize()` is called
- Metrics are computed via `SuiteWrapper` which delegates to real evaluation
  code (`evaluate_experiment_b.py`)

### Experiment C: Dataset Validation
- Creates a CSV dataset and runs it through the full validation pipeline:
  `GENERATE → VALIDATE → DEDUPLICATE → QUALITY CHECK → SECURITY CHECK →
  VERSION → REGISTER`
- Security check scans for secret-shaped strings (key=value patterns)
- Never passes if secrets are found

### Experiment D: Kaggle Training (BLOCKED without auth)
- Requires GPU and network access
- Truthfully **BLOCKED** when no Kaggle credentials are available

### Experiment E: Baseline/Candidate Comparison
- Establishes a baseline model with measured metrics
- Adds a candidate model with measured metrics
- Computes `ExperimentComparison` with absolute and relative differences
- Integrates with `PromotionGate` for model promotion decisions

---

## Laboratory Pipeline

```
BASELINE → EXPERIMENT → CANDIDATE → EVALUATION → COMPARISON
```

1. **BASELINE** — `establish_baseline()` records baseline model, revision,
   metrics, and compute used.  Baseline provenance is always stored.
2. **EXPERIMENT** — `design_experiment()` creates an experiment with a
   structured `ExperimentDesign`.  Secrets are scrubbed via
   `assert_no_secrets()`.
3. **CANDIDATE** — `add_candidate()` adds a candidate model and automatically
   computes comparisons vs the baseline.
4. **EVALUATION** — `_compute_metrics()` runs the experiment through the
   evaluation suite, producing typed `Metric` objects.
5. **COMPARISON** — `ExperimentComparison.from_metrics()` computes absolute
   and relative differences.

Never claim improvement without a baseline.

---

## API Endpoints

The laboratory exposes a REST API via `jarvis_backend.routers.experiments`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/experiments` | `POST` | Create an experiment |
| `/api/v1/experiments/{id}` | `GET` | Get experiment details |
| `/api/v1/experiments/{id}/prepare` | `POST` | Select resources and prepare |
| `/api/v1/experiments/{id}/run` | `POST` | Run the experiment |
| `/api/v1/experiments/{id}/verify` | `POST` | Verify experiment results |
| `/api/v1/experiments/{id}/complete` | `POST` | Complete and generate manifest |
| `/api/v1/experiments/{id}/baseline` | `POST` | Establish baseline |
| `/api/v1/experiments/{id}/candidate` | `POST` | Add candidate |
| `/api/v1/experiments/{id}/complete` | `GET` | Get experiment (completed) |
| `/api/v1/experiments/{id}/promote` | `POST` | Evaluate for promotion |
| `/api/v1/experiments/{id}/block` | `POST` | Report blocked experiment |
| `/api/v1/experiments/{id}/critique` | `GET` | Get critic findings |

---

## Security Model

The laboratory enforces strict security boundaries:

1. **Secret Scrubbing** — `design_experiment()` and `establish_baseline()` /
   `add_candidate()` call `assert_no_secrets()` on all design and metric data.
   Experiments with secrets are **BLOCKED** and a `ValueError` is raised.

2. **Truthful Blocking** — When compute resources (GPU, Kaggle auth, NVIDIA
   API keys) are unavailable, experiments are **BLOCKED** with a clear reason.
   No silent fallback or fabrication occurs.

3. **Dataset Security** — `DatasetValidator.security_check()` scans all
   dataset content for secret-shaped strings.  Datasets with secrets are
   **BLOCKED** and not registered.

4. **Brain Isolation** — The Brain never receives credentials.  All provider
   secrets are handled by `cloud_fabric` and `ProviderGateway`, which are
   isolated behind capability contracts.

See `docs/EXPERIMENT_SECURITY.md` for full security documentation.

---

## Test Suite

The laboratory has 33 engine tests covering:

- `ComputeBounds` (3 tests)
- Experiment design + secret rejection (2 tests)
- Resource selection (3 tests)
- Experiment preparation (3 tests)
- Experiment execution (4 tests)
- Analysis (2 tests)
- Verification (2 tests)
- Completion (2 tests)
- Baseline/candidate management (2 tests)
- Promotion evaluation (2 tests)
- Blocked reporting (2 tests)
- Real experiments A-E (5 tests)
- No-fabrication resource selection (1 test)

Plus 20 additional test files covering experiment lifecycle, model, design,
evaluation suite, dataset provenance, critic, no-fabrication, and red-team
audits.

**Current status: 191 Phase 11 tests + 148 Phase 10 tests + 190 Phase 8+9 tests = 529 total, 0 failures.**
