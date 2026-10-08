# Model Improvement Lifecycle

## Overview

The Model Improvement Lifecycle (MIL) governs how JARVIS coordinates controlled
experiments to improve AI model capabilities. Each cycle represents one
end-to-end attempt to improve a specific capability.

## Lifecycle Stages

### 1. OBSERVE

The orchestrator observes evaluation results from the baseline model and
candidate model across the evaluation matrix (target, regression, safety, and
robustness suites).

### 2. EVALUATE

The `WeaknessDetector` compares baseline vs candidate metrics. Only metrics
with matching `evaluation_version` are compared. Regression threshold is
configurable via the ImprovementPolicy.

### 3. FIND WEAKNESS

`Weakness` objects are created for each detected regression, classified by
`FailureCategory` and `FailureSeverity`, and clustered by category+severity.

### 4. FORM HYPOTHESIS

A `Hypothesis` is formed:

```python
hypothesis = Hypothesis(
    statement="Applying TRAINING_CHANGE to math_reasoning will improve "
              "Qwen/Qwen3-4B performance on math_reasoning by "
              "addressing <weakness description>",
    target_metric="accuracy",
    expected_improvement=0.15,
    confidence=weakness.confidence,
)
```

### 5. DESIGN IMPROVEMENT

An `InterventionType` and `TrainingConfig` are designed. The `AutonomyGuard`
checks the intervention before proceeding:

- `SYSTEM_POLICY_CHANGE` → always blocked
- `ARCHITECTURE_CHANGE` → always requires manual approval
- Protected paths → blocked
- Secret-shaped fields → blocked

### 6. GENERATE/CURATE DATA

The `DatasetImprovementLoop` extracts failure examples from evaluation results:

```
Evaluation Results → FailureExtractor → DatasetQualityGate → Versioned Dataset
```

**DatasetQualityGate stages**:
1. Schema validation (prompt, response, category, source required)
2. Safety/contamination check (no harmful content, no training data refs)
3. Deduplication (SHA256 hash of prompt+response)
4. Answer validation + provenance assignment
5. Size/budget check (5–50000 examples)

### 7. BASELINE

A `BaselineLock` is established:

```python
lock = BaselineLock(
    model_id="Qwen/Qwen3-4B",
    revision="abc123",
    metrics={"accuracy": 0.88},
    dataset_id="dataset_001",
)
# lock.lock_hash is a SHA256 hash of sorted JSON of (model_id, revision, metrics, dataset_id)
```

The baseline lock is **immutable** — any change to its fields breaks verification.

### 8. TRAIN / MODIFY CANDIDATE

A training job is submitted to the existing `JobRegistry`:

```python
job = JobInfo(
    id=str(uuid4()),
    job_id=f"train_{short_uuid()}",
    job_type=JobType.TRAINING.value,
    ...
)
```

The candidate artifact starts in `EXPERIMENTAL` status.

### 9. EVALUATE

The candidate is evaluated against the `EvaluationMatrix`:

- **Target suite**: The primary metric being optimized
- **Regression suites**: 6 suites (code_generation, code_repair, general_reasoning,
  document_analysis, data_analysis, instruction_following)
- **Safety suites**: 2 suites (security, geography)
- **Robustness suites**: 2 suites (generation_quality, rag)

Thresholds:
- `min_regression_threshold = 0.02` (2% max regression)
- `min_safety_threshold = 1.0` (no safety regressions allowed)

### 10. CRITIQUE

The `Critic` runs on the cycle's `CognitiveState`, producing findings:

- **Critical**: Missing policy, missing baseline lock, etc.
- **Warning**: Potential regressions, incomplete evaluation
- **Info**: Suggestions for improvement

### 11. VERIFY

The `VerificationEngine` and `EvidenceEngine` verify:

- Baseline lock integrity (hash matches)
- No secrets in cycle data
- Candidate artifact safety
- Evaluation results present with provenance
- No fabrication detected

### 12. COMPARE

`evaluate_improvement()` compares baseline vs candidate:

```python
result = cycle.evaluate_improvement(policy)
# Returns ImprovementResult with:
# - verdict: "improved" | "regressed" | "no_change" | "mixed"
# - target_improvement: relative improvement
# - regression_detected: bool
# - regressions: list of regression descriptions
# - confidence: 1.0 - max_regression (0.0 if regression >= 0.5)
```

### 13. PROMOTION GATE

`PromotionGate.evaluate_for_promotion()` checks the candidate:

- Must be `APPROVED` status
- Must pass all safety checks
- Must not have regressions on protected metrics
- If no candidate: returns `("rejected", "no_candidate_artifact")`

### 14. DEPLOY CANDIDATE

Controlled deployment modes:

| Mode | Autonomy Level | Description |
|------|----------------|-------------|
| `SHADOW` | 1+ | Deploy as shadow, no traffic |
| `CANARY` | 1+ | Canary deployment, small traffic |
| `BLOCKBOX` | 2+ | Blockbox testing |
| `PRODUCTION` | 3 only | Full production deployment |

Production deployment requires `autonomy_level >= 3` or manual approval.

### 15. POST-DEPLOYMENT EVALUATION

After deployment, the cycle monitors:

- Real-world performance metrics
- User feedback
- Safety incidents
- Resource usage

### 16. LEARN

A `Lesson` is generated and stored in `LearningMemory`:

```python
Lesson(
    lesson_id="lesson_<uuid>",
    improvement_id="impr_<uuid>",
    weakness_id="weak_<uuid>",
    hypothesis_id="hyp_<uuid>",
    intervention_type="training_change",
    outcome="success",
    what_worked="...",
    what_failed="",
    key_learning="...",
)
```

Lessons are queryable by capability.

### 17. NEXT IMPROVEMENT

The `ImprovementGraph` tracks the DAG of improvements:

- Nodes: `GraphNode(improvement_id, weakness_id, hypothesis_id, ...)`
- Edges: `follows_from`, `addresses`, `depends_on`

The system can trace the improvement chain to identify which interventions
led to successful outcomes.

## Candidate Status Lifecycle

```
EXPERIMENTAL → STAGING → LOCKED → EVALUATED → VERIFIED →
PROMOTION_REVIEW → APPROVED → DEPLOYED_SHADOW → DEPLOYED_CANARY → DEPLOYED
```

Failure paths:
- Any stage → FAILED
- EVALUATED → REJECTED
- VERIFIED → REJECTED
- PROMOTION_REVIEW → REJECTED
- DEPLOYED → ROLLED_BACK
- DEPLOYED → DEPRECATED → RETIRED

## Rollback

When a deployed candidate causes issues:

```python
deployment = orch.rollback_deployment(cycle, reason="post-deployment regression")
# Sets rolled_back=True, rollback_reason, rollback_at
# Transitions candidate back from DEPLOYED → ROLLED_BACK
```

## Integration Points

| Phase 11 Infrastructure | Phase 12 Integration |
|------------------------|---------------------|
| `JobRegistry` | Training job submission |
| `ArtifactRegistry` | Candidate artifact registration |
| `ModelRegistry` | Candidate model registration |
| `PromotionGate` | Promotion approval |
| `EvaluationSuiteRegistry` | Evaluation matrix suites |
| `EvidenceEngine` | No-fabrication checks |
| `VerificationEngine` | Claim verification |
| `Critic` | Cycle critique |
| `BudgetManager` | Cost tracking |
| `cloud_fabric` | Compute selection |
