# Phase 12 Implementation Map: JARVIS Self-Improvement Engine

> **Status:** PLANNING — Audit complete, design before implementation.
> **DO NOT** rebuild Phase 8–11. Extend existing infrastructure only.
> Build a **controlled, evidence-driven** self-improvement system where JARVIS
> discovers weaknesses in its own AI capabilities and coordinates experiments
> that may improve them — always under verification and approval.

---

## 1. Audit Summary — What Already Exists

### 1.1 Training Infrastructure
- **`KAGGLE_TRAINING.md`** + **`kaggle_kernel/jarvis_brain_qwen3_4b.py` (517 lines)**: Full LoRA fine-tuning pipeline on Kaggle GPU (T4/P100).
  - Base model: `Qwen/Qwen3-4B` @ pinned revision `1cfa9a7208912126459214e8b04321603b3df60c`
  - LoRA config: `r=16`, `lora_alpha=32`, `target_modules=[q,k,v,o,gate,up,down]_proj`, `lora_dropout=0.05`, `task_type=CAUSAL_LM`
  - Training env vars: `BASE_MODEL`, `BATCH_SIZE`, `EPOCHS`, `MAX_SEQ`, `MAX_BATCH`, `LORA_RANK`, `MAX_STEPS`
  - Training args: `lr=2e-4`, `lr_scheduler=cosine`, `warmup_ratio=0.03`, `gradient_accumulation_steps=4`
  - Frozen base + LoRA adapter (never overwrite base weights)
  - Publication to HuggingFace: `videlisndichi/jarvis-brain-qwen3-4b-sft-v1`
- **`scripts/kaggle_train_jarvis_lora.py` (245 lines)**: Self-contained Kaggle kernel script for LoRA training
- **`scripts/train_jarvis_lora.py` (273 lines)**: Local-GPU equivalent, `--dry-run` for dataset validation (stdlib-only)
- **`train_experiment_b.py` (671 lines)**: Local training with `SilverwingModel` (Transformer implementation: RMSNorm, RoPE, Attention, SwiGLU MLP), BPE tokenizer, `save_checkpoint()`, `evaluate_model()`, `train_experiment_b()`

### 1.2 Benchmark / Evaluation Infrastructure
- **`kaggle_kernel/brain_benchmarks.py` (222 lines)**: Fixed prompt suite (12 prompts across 6 categories: conversation, math, logic, coding, knowledge, instruction) + deterministic rule-based scorer + `aggregate()` for per-category scores.
- **`qwen3_4b_baseline.md`**: Baseline Qwen3-4B scores (coding=0.833, conversation=0.833, instruction=0.5, knowledge=1.0, logic=1.0, math=1.0, overall=0.867)
- **`jarvis_backend/evaluation_suite.py` (893 lines)**: `EvaluationSuiteRegistry` with 13 suites (math_reasoning, code_generation, code_repair, general_reasoning, document_analysis, data_analysis, tool_use, rag, geography, security, instruction_following, generation_quality, perplexity). Must call `initialize()` before `get()`.
- **`jarvis_backend/verifier.py` (269 lines)**: `VerificationEngine` with `classify_tool_result()`, `verify_claim()`, `verify_reproduction()`
- **`jarvis_backend/evidence_engine.py` (427 lines)**: `EvidenceEngine` with `assert_no_fabrication()`, `register_evidence()`, `register_from_tool_result()`, `verify_evidence()`
- **`run_baseline_suite.py`**, **`evaluate_checkpoints_auto.py`**, **`evaluate_experiment_b.py`**, **`evaluate_kaggle_model.py`**, **`evaluate_local_model.py`**, **`evaluate_perplexity.py`**: Existing evaluation scripts

### 1.3 Model Registry & Promotion
- **`infrastructure/model_registry.py` (649 lines)**: `ModelRegistry` with `register()`, `get()`, `update_lifecycle()`, `record_evaluation()`, `list_models()`, `promote_model()`, `search()`. `ModelLifecycleState`: discovered → registered → evaluating → candidate → approved → blocked → deployed → deprecated → retired. `ModelInfo`: 24 fields including `model_id`, `capabilities`, `evaluation_results`, `lifecycle_status`, `parent_model_id`, `checksum`, `provenance`, `training_run_id`, `dataset_id`.
- **`infrastructure/promotion_gate.py` (531 lines)**: `PromotionGate` with `evaluate_for_promotion(model_id, criteria: EvaluationCriteria, evaluator)` returning `(PromotionOutcome, evidence)`. `PromotionOutcome`: APPROVED, REJECTED, NEEDS_MORE_EVAL, BLOCKED. `EvaluationCriteria`: min_accuracy, min_pass_rate, max_latency_ms, etc. `PromotionDecision` with audit trail. Pre-configured criteria: `get_default_criteria()`, `get_reasoning_criteria()`, `get_vision_criteria()`, `get_cost_efficient_criteria()`, `get_high_quality_criteria()`.

### 1.4 Artifact & Job Infrastructure
- **`infrastructure/artifact_registry.py` (577 lines)**: `ArtifactRegistry` with `register()`, `get()`, `list_artifacts()`, `update_status()`, `link_to_model()`, `get_artifacts_by_model()`, `get_parent_chain()`, `compute_checksum()`. `ArtifactStatus`: uploading, available, verified, archived, failed, deleted. `ArtifactType`: model_weights, lora_adapter, checkpoint, eval_dataset, train_dataset, config, tokenizer, embedding, other.
- **`infrastructure/job_registry.py`**: `JobRegistry`, `JobInfo`, `JobType` (EVALUATION, TRAINING), `JobStatus` (QUEUED, RUNNING, COMPLETED, FAILED).
- **`infrastructure/provider_registry.py`**: `ProviderRegistry`, `ProviderInfo`, `ProviderStatus` (CONFIGURED, AUTHENTICATED, REACHABLE).

### 1.5 Existing Critic (Phase 11)
- **`jarvis_backend/critic.py` (835 lines)**: `Critic` class with `critique(state: CognitiveState) -> list[CriticFinding]` and `critique_experiment(experiment) -> list[CriticFinding]`. `CriticFinding`: `finding_id`, `at`, `severity`, `category`, `description`, `recommendation` (has `to_dict()`). 13 experiment critique checks (baseline adequacy, dataset size, evaluation suite coverage, regression detection, provenance, etc.).

### 1.6 Existing Experiment Lifecycle (Phase 11)
- **`jarvis_backend/experiment.py` (472 lines)**: `Experiment` dataclass with 30 fields (experiment_id, mission_id, name, objective, hypothesis, design, variables, controls, inputs, datasets, models, configurations, compute_requirements, evaluation_suite, baseline, candidates, comparisons, results, artifacts, job_ids, provenance, status, budget, event_timeline, etc.). `ExperimentStatus`: designed, ready, running, analyzing, verifying, completed, failed, cancelled, inconclusive, blocked. State machine with `transition()`, `validate_transition()`, `compute_comparison()`. `ExperimentLifecycle` with `valid_transitions` dict and `terminal_states`.
- **`jarvis_backend/experiment_engine.py` (819 lines)**: `ExperimentOrchestrator` — `design_experiment()`, `select_resources()`, `prepare_experiment()`, `run_experiment()`, `analyze_results()`, `verify_experiment()`, `complete_experiment()`, `establish_baseline()`, `add_candidate()`, `evaluate_for_promotion()`, `report_blocked()`. Uses `cloud_fabric.select_compute()` (returns dict), `cloud_resources()` (returns `{local_hardware, resources, by_id, count, note}`), `JobRegistry`, `ArtifactRegistry`, `PromotionGate`, `Critic`, `HypothesisEngine`, `brain_fabric.assert_no_secrets()`.

### 1.7 Budget & Usage Accounting
- **`infrastructure/usage_accounting.py`**: `BudgetManager` (`check_budget()`, `get_status()`, `set_budget()`), `UsageAccountant` (records inference/training/artifact usage), `BudgetLimit` (daily_usd, monthly_usd).
- **`infrastructure/routing_policy.py`**: Budget-related routing.

### 1.8 Cloud Fabric & Compute
- **`jarvis_backend/cloud_fabric.py`**: `cloud_resources()`, `select_compute()`, `local_hardware()`. Resources: `local:control-node`, `cloud:nvidia`, `cloud:kaggle`, `cloud:huggingface`, `docker:execution`, `remote_execution_host`.
- **`jarvis_compute/selector.py`**: `ComputeSelector` (existing Phase 12 compute selector).

### 1.9 Cognitive Kernel & Autonomy
- **`jarvis_backend/cognitive_kernel.py` (974 lines)**: `CognitiveKernel` with `run(mission, max_steps, permissions, principal)` and `resume(mission_id, max_steps)`. `AutonomyLevel`: LEVEL_0 (no autonomy) through LEVEL_3 (full autonomy). `permissions: set[str]` parameter for fine-grained capability control.
- **`jarvis_backend/mission.py`**: Mission lifecycle integration.

### 1.10 Existing Phase 12-Adjacent Code (Already Read)
- **`jarvis_backend/critic.py`**: 13 experiment critique checks + `critique_experiment()`
- **`jarvis_backend/evidence_engine.py`**: `assert_no_fabrication()` for no-fabrication audits
- **`jarvis_backend/specialist_roles.py`**: Specialist roles for multi-agent execution
- **`jarvis_backend/delegation.py`**: Delegation infrastructure
- **`jarvis_backend/mission_lifecycle.py`**: Mission lifecycle state machine
- **`jarvis_backend/verifier.py`**: VerificationEngine

### 1.11 Storage & Persistence
- **`jarvis_backend/core.py`**: `Store` class with `load()`/`save()`. Stores: `"experiments"`, `"datasets"`, `"evaluation_suites"`, `"missions"`, `"models"`, `"artifacts"`.

### 1.12 Existing Tests (Do NOT Break)
- **`tests/test_experiment_engine.py`**: 33 tests, ~230s (slow due to cloud_resources() ~30s/call)
- **`tests/test_mission_model.py`**: 352 lines
- **`tests/test_cognitive_kernel.py`**: 409 lines
- **`tests/test_compute_redteam.py`**: 929 lines
- **`tests/test_mission_redteam.py`**: 578 lines
- **`tests/test_experiment_model.py`**: 1088 lines
- **`tests/test_experiment_lifecycle.py`**: 362 lines
- **`tests/test_experiment_no_fabrication.py`**: 192 lines
- **`tests/test_evaluation_suite.py`**: 499 lines
- **`tests/test_dataset_provenance.py`**: 542 lines
- **`tests/test_experiment_redteam.py`**: 243 lines
- **Total Phase 8+9+10+11: 529 tests, 0 failures**

---

## 2. What Does NOT Exist (Must Be Created)

Searching the codebase confirms these Phase 12 concepts have **zero** existing implementation:

| Concept | Occurrences |
|---|---|
| `SelfImprovementCycle` / `ImprovementCycle` | 0 |
| `WeaknessDetector` / `FailureTaxonomy` | 0 (only "Weakness" in `challenges.py` router) |
| `InterventionType` / `Intervention` | 0 |
| `ImprovementPolicy` / `ImprovementStatus` | 0 |
| `BaselineLock` | 0 |
| `DatasetQualityGate` | 0 |
| `LearningMemory` / `Lesson` | 0 |
| `ImprovementGraph` | 0 |
| Phase 12 tests | 0 |
| Phase 12 docs | 0 |

---

## 3. Architecture Design

### 3.1 Core Abstractions (One New Module: `jarvis_backend/self_improvement.py`)

Extends existing infrastructure — no duplicate registries.

```
SelfImprovementCycle  ← extends Experiment lifecycle (uses ExperimentLifecycle.validate_transition)
├── ImprovementStatus (state machine)
├── ImprovementPolicy (target metrics, min improvement, max regression, budget, risk)
├── InterventionType (enum: PROMPT_CHANGE, SYSTEM_POLICY_CHANGE, RETRIEVAL_CHANGE,
│   CONTEXT_CHANGE, DATASET_CHANGE, TRAINING_CHANGE, HYPERPARAMETER_CHANGE,
│   ARCHITECTURE_CHANGE, MERGE_CHANGE, PROMPT_TEMPLATE_CHANGE)
├── Weakness (target_capability, failure_evidence, failure_type, severity, examples)
├── WeaknessDetector (failure taxonomy, clustering, gap analysis)
├── BaselineLock (immutable snapshot for comparison)
├── CandidateArtifact (EXPERIMENTAL until gates pass; lifecycle: staging → locked → promoting → released → deployed → retired)
├── EvaluationMatrix (target/regression/safety/robustness suites)
├── ImprovementResult (baseline_results, candidate_results, regression_results, comparison)
├── ImprovementDeployment (controlled: shadow/canary/blockbox; rollback)
├── AutonomyGuard (enforces autonomy boundary: cannot modify auth, secrets, production source)
├── LearningMemory (structured lessons persisted after cycle)
└── ImprovementGraph (weakness → hypothesis → intervention → dataset → training → artifact → evaluation → promotion → deployment → observation → next weakness)
```

### 3.2 Integration Points (Reuse, Don't Duplicate)

| Phase 12 Component | Reuses |
|---|---|
| `SelfImprovementCycle` | `Experiment` dataclass model + `ExperimentLifecycle` state machine |
| Status state machine | Follow pattern from `ExperimentStatus` / `ExperimentLifecycle` / `ModelLifecycleState` |
| `ImprovementPolicy` | `BudgetManager` (usage_accounting), `EvaluationCriteria` (promotion_gate) |
| Intervention execution | `ExperimentOrchestrator.select_resources()`, `ComputeBounds` |
| `WeaknessDetector` | `Critic.critique_experiment()`, existing evaluation results |
| `BaselineLock` | `Experiment.set_baseline()`, `ExperimentComparison` |
| `CandidateArtifact` | `ArtifactRegistry` (ArtifactType.LORA_ADAPTER, ArtifactStatus.VERIFIED), `ModelRegistry` (lifecycle: candidate → approved → deployed) |
| `EvaluationMatrix` | `EvaluationSuiteRegistry`, `SuiteWrapper`, `brain_benchmarks.py` |
| Baseline/candidate comparison | `Experiment.compute_comparison()`, `ExperimentComparison` |
| Critic integration | `Critic.critique_experiment()`, `CriticFinding` |
| Verification | `VerificationEngine.verify_claim()`, `VerificationStatus` |
| PromotionGate | `PromotionGate.evaluate_for_promotion(model_id, criteria, evaluator)` |
| Budget | `BudgetManager.check_budget()`, `UsageAccountant.record_training()` |
| Autonomy boundary | `AutonomyLevel`, `permissions: set[str]` in `CognitiveKernel.run()` |
| Learning memory | `get_store()`, new store key `"improvements"` |
| Chat experience | `CognitiveKernel` / `Mission` (user requests become missions) |
| Holographic state | Existing holographic state infrastructure |
| No-fabrication | `EvidenceEngine.assert_no_fabrication()`, `brain_fabric.assert_no_secrets()` |

### 3.3 File Layout

```
jarvis_backend/
├── self_improvement.py       # Phase 12: all new abstractions
├── self_improvement_engine.py # Phase 12: orchestrator (extends ExperimentOrchestrator patterns)
└── routers/
    └── self_improvement.py    # Phase 12: API endpoints

tests/
├── test_self_improvement.py      # Phase 12 core tests
├── test_self_improvement_redteam.py  # Phase 12 security red-team tests
└── test_self_improvement_no_fabrication.py  # No-fabrication audit

docs/
├── PHASE12_IMPLEMENTATION_MAP.md  # This file
├── SELF_IMPROVEMENT.md
├── WEAKNESS_DETECTION.md
├── MODEL_IMPROVEMENT_LIFECYCLE.md
├── DATASET_IMPROVEMENT.md
├── SELF_IMPROVEMENT_SECURITY.md
└── PHASE12_RESULT.md
```

---

## 4. Implementation Plan (Step-by-Step)

### Step 1: `self_improvement.py` — Core Abstractions
Create the `SelfImprovementCycle` dataclass with all specified fields, `ImprovementStatus` enum (15 states), `InterventionType` enum (9 types), `ImprovementPolicy` dataclass, `Weakness` dataclass, `BaselineLock` dataclass, `CandidateArtifact` dataclass, `EvaluationMatrix`, `ImprovementResult`, `ImprovementDeployment`, `AutonomyGuard`, `LearningMemory`, `ImprovementGraph`.

### Step 2: `self_improvement_engine.py` — Orchestrator
Create `SelfImprovementOrchestrator` that:
- Detects weaknesses from evaluation results + Critic findings
- Forms hypotheses for each weakness
- Designs interventions (maps to existing Experiment/ExperimentDesign)
- Establishes baseline (uses `Experiment.set_baseline()`, `BaselineLock`)
- Triggers training (uses existing `ExperimentOrchestrator.select_resources()` + Kaggle LoRA pipeline)
- Registers candidate artifacts (EXPERIMENTAL status via `ArtifactRegistry`)
- Evaluates baseline vs candidate (uses `EvaluationSuiteRegistry`, `brain_benchmarks`)
- Critiques (uses `Critic.critique_experiment()`)
- Verifies (uses `VerificationEngine`)
- Compares with regression detection (uses `Experiment.compute_comparison()`)
- Promotion gate check (uses `PromotionGate.evaluate_for_promotion()`)
- Controlled deployment (shadow → canary → production)
- Rollback on regression
- Budget check (uses `BudgetManager.check_budget()`)
- Autonomy enforcement (uses `AutonomyGuard`, `AutonomyLevel`)
- Persists learning memory

### Step 3: Router — `routers/self_improvement.py`
API endpoints for improvement cycles, weakness detection, candidate management, promotion decisions.

### Step 4: Tests
- `test_self_improvement.py`: Core tests (cycle lifecycle, weakness detection, intervention types, baseline lock, evaluation matrix, comparison, regression, candidate artifact, promotion, deployment, rollback, budget, autonomy)
- `test_self_improvement_redteam.py`: Security tests (cannot access credentials, modify secrets, bypass auth, promote unverified, fabricate metrics, erase audit)
- `test_self_improvement_no_fabrication.py`: No-fabrication audit

### Step 5: Validation Scenarios A–J
Real validation scenarios verifying the complete pipeline end-to-end with verified evidence.

### Step 6: Documentation
Write all 6 documentation files.

### Step 7: Regression Test
Run Phase 8+9+10+11+12 tests, confirm 0 failures, 0 regressions.

---

## 5. State Machine: ImprovementStatus

```
IDENTIFIED → ANALYZING → HYPOTHESIS_FORMED → DESIGNED → AWAITING_APPROVAL
   ↓              ↓              ↓              ↓              ↓
   └─ (find issues)  └─ (analyze failures)  └─ (form hypothesis)  └─ (design intervention)  └─ (await approval)
         ↘                   ↘                   ↘                ↘               ↓
          └──────────→ ANALYZING   └──────────→ HYPOTHESIS_FORMED   └──────────→ DESIGNED
                                                        ↓
                                               DATA_PREPARATION
                                                        ↓
                                                   TRAINING
                                                        ↓
                                                 EVALUATING
                                                        ↓
                                                 CRITIQUING
                                                        ↓
                                                   VERIFYING
                                                        ↓
                                               PROMOTION_REVIEW
                                                        ↓
                                                  DEPLOYING
                                                        ↓
                                                  MONITORING
                                                        ↓
                                            COMPLETED / REJECTED / FAILED / BLOCKED
```

Terminal: COMPLETED, REJECTED, FAILED, BLOCKED
Non-terminal: IDENTIFIED, ANALYZING, HYPOTHESIS_FORMED, DESIGNED, AWAITING_APPROVAL,
  DATA_PREPARATION, TRAINING, EVALUATING, CRITIQUING, VERIFYING, PROMOTION_REVIEW,
  DEPLOYING, MONITORING

---

## 6. Key Design Decisions

1. **Extend, don't duplicate**: `SelfImprovementCycle` reuses `Experiment` dataclass and `ExperimentLifecycle` transition validation. The improvement cycle IS an experiment with additional Phase 12 metadata.

2. **Truthful state**: Resources report AVAILABLE only after actual verification (reuse `cloud_fabric` health checks).

3. **Immutable baselines**: `BaselineLock` captures a cryptographic snapshot of baseline metrics, config, and dataset version. Cannot be modified after lock.

4. **Candidate safety**: All candidate artifacts start as `EXPERIMENTAL` in `ArtifactRegistry` and `candidate` in `ModelRegistry.lifecycle_status`. Only `PromotionGate` can approve to `approved`.

5. **Autonomy boundary**: `AutonomyGuard` blocks any operation that would modify auth, secrets, production source, or bypass approval gates, regardless of `AutonomyLevel`. The Brain proposes interventions; `AutonomyGuard` enforces.

6. **No fabrication**: All metrics must come from `EvaluationSuite` or `brain_benchmarks` with `provenance` tracking. `assert_no_fabrication()` is run on every cycle result.

7. **Budget enforcement**: Every improvement cycle must declare a budget. `BudgetManager.check_budget()` is called before training submission.

8. **Controlled deployment**: Deployment modes: shadow (parallel, no traffic), canary (gradual traffic), blockbox (isolated testing). Production promotion requires `PromotionGate.approve_model()` with manual approval.

9. **Learning memory**: After each cycle, `LearningMemory` persists structured lessons (weakness, intervention, outcome, what worked, what didn't) to the `"improvements"` store.

10. **Improvement graph**: Directed acyclic graph of improvement nodes, each linking weakness → hypothesis → intervention → dataset → training → artifact → evaluation → promotion → deployment → observation → next weakness.

---

## 7. Success Criteria

1. All 27 implementation steps complete
2. Phase 12 test suite passes with 0 failures
3. Security red-team tests pass (10 tests)
4. No-fabrication audit passes on all Phase 12 source
5. Phases 8+9+10+11+12 regression: 0 failures (529 + Phase 12 tests)
6. 10 real validation scenarios (A–J) produce verified evidence
7. JARVIS server (port 8000) still running and serving after Phase 12 implementation
8. All 6 documentation files written
9. No existing infrastructure broken — no duplicate systems created
