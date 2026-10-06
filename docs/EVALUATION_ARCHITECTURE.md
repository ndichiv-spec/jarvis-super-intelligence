# JARVIS Evaluation Architecture

## Overview

JARVIS uses a **typed, versioned evaluation suite system** that produces
**real, provenance-tracked metrics**.  Metrics are never fabricated — if an
evaluation cannot run, a `Metric` with `value=0.0` is returned with
provenance noting the failure mode.

The evaluation system is built in `jarvis_backend/evaluation_suite.py` and
integrates with the Experiment Engine (`jarvis_backend/experiment_engine.py`)
and the existing evaluation code (`evaluate_experiment_b.py`).

---

## Design Principles

1. **No fabrication** — Every metric value comes from a real evaluation run.
   If the underlying code is unavailable or fails, a `Metric` with
   `value=0.0` is returned with `provenance` listing the failure reason (e.g.,
   `evaluation_unavailable:module_not_found`,
   `evaluation_failed:FileNotFoundError`).

2. **Typed metrics** — Metrics are `Metric` dataclass instances with name,
   value, unit, direction, sample count, evaluation version, and provenance.

3. **Versioned suites** — Each suite has a version.  The `versioned_id` is
   `f"{suite_id}:v{version}"` (e.g., `math_reasoning:v1`).

4. **Scoring rules** — Each suite defines how to score each metric via
   `ScoringRule` with `method` (`accuracy`, `pass_at_1`, `f1`,
   `exact_match`, `perplexity`).

5. **Capability contracts** — Suites declare `required_capabilities`
   (e.g., `compute.evaluation`) and `required_models`
   (e.g., `text-generation`, `causal-lm`).

6. **Resource awareness** — Suites declare `resource_requirements`
   (e.g., `min_vram_gb`, `offline_ok`).

7. **Reuse, not duplicate** — The evaluation system wraps the existing
   `evaluate_experiment_b.py` module via `SuiteWrapper`.  No new evaluator
   was created.

---

## Core Types

### Metric

```python
@dataclass
class Metric:
    name: str              # e.g. "math_accuracy", "val_ppl"
    value: float           # measured value (never fabricated)
    unit: str = ""         # e.g. "ratio", "perplexity"
    higher_is_better: bool = True
    sample_count: int = 0
    evaluation_version: str = ""   # suite_id:version
    provenance: list[str] = []     # run_ids, artifact_ids, failure notes
```

- `to_dict()` / `from_dict()` for serialization
- `assert_no_fabrication()` checks that no metric claims zero-value metrics
  without a failure provenance

### ScoringRule

```python
@dataclass
class ScoringRule:
    metric_name: str       # e.g. "math_accuracy"
    method: str            # "accuracy", "pass_at_1", "f1", "exact_match", "perplexity"
    higher_is_better: bool = True
    unit: str = "ratio"
    description: str = ""
```

### EvaluationTask

```python
@dataclass
class EvaluationTask:
    task_id: str           # e.g. "math_arithmetic", "code_python"
    name: str              # human-readable name
    description: str       # task description
    metrics: list[str]     # metric names produced by this task
    input_spec: dict       # task input specification
```

### EvaluationSuite

```python
@dataclass
class EvaluationSuite:
    suite_id: str          # e.g. "math_reasoning"
    name: str              # human-readable name
    version: str           # e.g. "1"
    description: str = ""
    tasks: list[dict] = [] # serialized EvaluationTasks
    scoring_rules: list[dict] = []
    required_capabilities: list[str] = []
    required_models: list[str] = []
    resource_requirements: dict = {}
```

- `versioned_id` property: `f"{suite_id}:v{version}"`
- `to_dict()` / `from_dict()` for persistence
- Persistence via `get_store("evaluation_suites")`

### ExperimentComparison

```python
@dataclass
class ExperimentComparison:
    metric_name: str
    baseline_value: float
    candidate_value: float
    absolute_difference: float       # candidate - baseline
    relative_difference: float       # (candidate - baseline) / baseline
    sample_count: int
    evaluation_version: str
```

- `from_metrics(baseline: Metric, candidate: Metric) → Optional[ExperimentComparison]`
  — computes differences from real metric values

---

## Scoring Functions

Located at the bottom of `evaluation_suite.py`:

| Function | Signature | Description |
|----------|-----------|-------------|
| `score_accuracy` | `(correct: int, total: int) -> float` | `correct / total` |
| `score_exact_match` | `(matches: int, total: int) -> float` | `matches / total` |
| `score_f1` | `(correct: int, total: int, false_positives: int = 0) -> float` | F1 score with precision/recall |

All functions handle division-by-zero safely (return `0.0` when `total=0`).

---

## Standard Evaluation Suites

The laboratory ships with **13 standardized suites** (version 1), defined in
`_standard_suite_defs`:

| Suite ID | Name | Tasks | Scoring Rules | Required Capabilities | Required Models |
|----------|------|-------|---------------|----------------------|-----------------|
| `math_reasoning` | Mathematical Reasoning | `math_arithmetic`, `math_algebra` | `accuracy` (math_accuracy) | `compute.evaluation` | `text-generation`, `causal-lm` |
| `code_generation` | Code Generation | `code_python` | `pass_at_1` (code_pass_at_1) | `compute.evaluation` | `code-generation`, `text-generation` |
| `code_repair` | Code Repair | `code_repair_python` | `pass_at_1` (code_repair_pass_at_1) | `compute.evaluation` | `code-generation`, `text-generation` |
| `general_reasoning` | General Reasoning | `reasoning_deduction`, `reasoning_causal` | `accuracy` (reasoning_accuracy) | `compute.evaluation` | `text-generation`, `causal-lm` |
| `document_analysis` | Document Analysis | `doc_qa` | `exact_match` (doc_answer_accuracy) | `compute.evaluation`, `document_analysis` | `text-generation`, `question-answering` |
| `data_analysis` | Data Analysis | `data_query` | `accuracy` (data_query_accuracy) | `compute.evaluation`, `data_analysis` | `text-generation`, `tool-use` |
| `tool_use` | Tool Use | `tool_selection`, `tool_execution` | `accuracy` (tool_use_accuracy) | `compute.evaluation`, `tool_use` | `text-generation`, `tool-use` |
| `rag` | RAG | `rag_qa` | `exact_match` (rag_answer_accuracy) | `compute.evaluation`, `rag` | `text-generation`, `retrieval` |
| `geography` | Geography | `geo_recall`, `geo_reasoning` | `accuracy` (geo_accuracy) | `compute.evaluation` | `text-generation`, `causal-lm` |
| `security` | Security | `sec_violation_detection`, `sec_code_analysis` | `f1` (sec_f1) | `compute.evaluation`, `security` | `text-generation`, `security` |
| `instruction_following` | Instruction Following | `if_exact_match`, `if_partial_match` | `exact_match` (if_exact_match_accuracy), `exact_match` (if_partial_match_accuracy) | `compute.evaluation` | `text-generation` |
| `generation_quality` | Generation Quality | `gq_fluency`, `gq_relevance` | `accuracy` (gq_fluency), `accuracy` (gq_relevance) | `compute.evaluation` | `text-generation` |
| `perplexity` | Perplexity | `perplexity_eval` | `perplexity` (val_ppl) | `compute.evaluation` | `causal-lm` |

**Initialization:** `EvaluationSuiteRegistry.initialize()` must be called
before `EvaluationSuiteRegistry.get()`.  The registry caches suites in
memory and also loads from the `evaluation_suites` store.

---

## SuiteWrapper — Real Evaluation Delegation

`SuiteWrapper` delegates to the existing `evaluate_experiment_b.py` module,
which provides real model loading and evaluation functions.

### `run_math_evaluation(checkpoint_dir, device, val_file=None, evaluation_version)`

Delegates to:
- `mod.load_checkpoint(checkpoint_dir, device)` — loads model + tokenizer
- `mod.evaluate_math(model, tokenizer, device)` — runs math evaluation

Returns `[Metric(name="math_accuracy", ...)]` with real accuracy and sample
count.  If the module is unavailable or evaluation fails, returns a `Metric`
with `value=0.0` and failure provenance.

### `run_coding_evaluation(checkpoint_dir, device, evaluation_version)`

Delegates to `mod.evaluate_coding()`.  Returns
`Metric(name="code_pass_at_1", ...)`.

### `run_knowledge_evaluation(checkpoint_dir, device, evaluation_version)`

Delegates to `mod.evaluate_knowledge()`.  Returns a metric with
`name="knowledge_accuracy"` or `"rag_answer_accuracy"` depending on the
calling context.

### `run_full_checkpoint_evaluation(checkpoint_dir, val_file, work_dir, tag, evaluation_version)`

Runs perplexity evaluation via `mod.run_full_checkpoint_evaluation()`.
Requires both `checkpoint_dir` and `val_file`.  Returns
`Metric(name="val_ppl", ...)` with `higher_is_better=False`.

### `run_security_redteam_evaluation(...)`

Runs security evaluation and returns multiple metrics covering
violation detection and code analysis.

### `run_perplexity_evaluation(...)`

Runs perplexity evaluation and returns `Metric(name="perplexity", ...)`
with `higher_is_better=False`.

---

## Experiment Engine Integration

The `ExperimentOrchestrator._compute_metrics()` method:

1. Looks up the evaluation suite by `exp.evaluation_suite` (an
   `suite_id:version` string)
2. Falls back to `EvaluationSuite.load()` if registry lookup fails
3. Iterates over `suite.tasks` (deserialized `EvaluationTask` objects)
4. Dispatches to the appropriate `SuiteWrapper` method based on `task_id`:
   - `math_arithmetic`, `math_algebra` → `run_math_evaluation()`
   - `code_python`, `code_repair_python` → `run_coding_evaluation()`
   - `doc_qa`, `rag_qa` → `run_knowledge_evaluation()`
   - `perplexity_eval` → `run_full_checkpoint_evaluation()` or returns a
     failure `Metric` if checkpoint/val_file not provided
   - unknown tasks → returns a failure `Metric` with
     `provenance=["task_not_mapped:<task_id>"]`
5. Returns `list[Metric]` — all with truthful provenance

### Critical: No Fabrication

Every code path in `SuiteWrapper` that cannot run real evaluation returns a
`Metric` with:
- `value=0.0`
- `provenance` listing the specific failure reason
- `sample_count=0`

This is truthful — the metric reports the evaluation could not run, rather
than fabricating a passing score.

The `EvidenceEngine.assert_no_fabrication()` method further verifies that
no claim has zero-value metrics without failure provenance.

---

## Comparison Architecture

### Baseline Establishment

`ExperimentOrchestrator.establish_baseline()` records:
```json
{
  "model": "<model_id>",
  "revision": "<git_revision>",
  "metrics": [<Metric.to_dict(), ...>],
  "compute": "<resource_id>",
  "timestamp": "<iso_timestamp>"
}
```

Baseline provenance is always stored.  Every model-improvement experiment
**must** establish a baseline before modification.

### Candidate Evaluation

`ExperimentOrchestrator.add_candidate()` records:
```json
{
  "model": "<model_id>",
  "revision": "<git_revision>",
  "metrics": [<Metric.to_dict(), ...>],
  "compute": "<resource_id>",
  "timestamp": "<iso_timestamp>"
}
```

Automatically computes `ExperimentComparison` entries via
`ExperimentComparison.from_metrics()` for each pair of baseline/candidate
metrics.

### Comparison Computation

```
absolute_difference = candidate_value - baseline_value
relative_difference = (candidate_value - baseline_value) / abs(baseline_value)
```

If `baseline_value == 0`, `relative_difference` is set to `0.0` (division
safety).  If baseline and candidate metrics have different names or
evaluation versions, no comparison is produced (returns `None`).

---

## Promotion Gate Integration

`ExperimentOrchestrator.evaluate_for_promotion()` evaluates the experiment's
candidate against success criteria using `PromotionGate`:

1. Builds `EvaluationCriteria` from the experiment's comparison metrics:
   - If all comparisons are positive (candidate > baseline for
     `higher_is_better` metrics), criteria is marked as met
   - Criteria name: `experiment_outcome`, description from experiment
2. Calls `PromotionGate.evaluate_for_promotion(model_id, criteria, evaluator)`
3. Returns `(PromotionOutcome, details_dict)`

**Fallback:** If the candidate model is not registered in PromotionGate,
returns `(PromotionOutcome.REJECTED, {"reason": "Model not found"})`.

Promotion states flow:
```
EXPERIMENTAL → EVALUATED → CANDIDATE → APPROVED → DEPLOYABLE → DEPLOYED
```

---

## Verification

The `Verifier` checks experiments via `verify_experiment()`:

| Check | What it verifies |
|-------|-----------------|
| Metric schema | Each metric dict has `name`, `value`, `unit` |
| Provenance | Each metric has non-empty `provenance` list |
| Comparison integrity | Each comparison has `metric_name`, `baseline_value`, `candidate_value`, `absolute_difference`, `relative_difference` |
| Baseline presence | `exp.baseline` is not None/empty |
| Job status | All job IDs are tracked and not stuck in error state |
| Artifact existence | All referenced artifacts exist in ArtifactRegistry |

Issues are collected in `exp.results["verification_issues"]` and can trigger
`FAILED` status if critical.

---

## Test Coverage

| Test File | Tests | Description |
|-----------|-------|-------------|
| `tests/test_evaluation_suite.py` | 24 | Suite registration, lookup, tasks, scoring rules, versioned IDs, persistence |
| `tests/test_experiment_engine.py` | 33 | Full experiment lifecycle including evaluation suite lookup |

**13 suites** are available after `EvaluationSuiteRegistry.initialize()`.

---

## Configuration

Evaluation suites are persisted via `get_store("evaluation_suites")` —
a SQLite-backed key-value store at `jarvis_backend.db`.  The standard suites
are registered in-memory at startup via `initialize_standard_suites()`.

Each suite's `versioned_id` (e.g., `math_reasoning:v1`) is used as the key
in both the in-memory registry and the persistent store.

### Usage Example

```python
from jarvis_backend.evaluation_suite import EvaluationSuiteRegistry

# Initialize once at startup
EvaluationSuiteRegistry.initialize()

# Look up a suite
suite = EvaluationSuiteRegistry.get("math_reasoning:v1")
# suite has tasks: math_arithmetic, math_algebra
# suite has scoring_rules: [ScoringRule(metric_name="math_accuracy", method="accuracy", ...)]

# Or via ExperimentOrchestrator
orchestrator = ExperimentOrchestrator()
metrics = orchestrator._compute_metrics(exp)
# metrics: list[Metric] with real values and provenance
```
