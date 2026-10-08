# JARVIS Self-Improvement Engine

## Overview

The JARVIS Self-Improvement Engine (Phase 12) is a controlled, evidence-driven
system that allows JARVIS to discover weaknesses in its own AI capabilities and
coordinate experiments that may improve them.

Self-improvement is **controlled improvement** of models, datasets, prompts,
policies, and capability implementations — always under verification and approval.

## Core Loop

```
OBSERVE → EVALUATE → FIND WEAKNESS → FORM HYPOTHESIS →
DESIGN IMPROVEMENT → GENERATE/CURATE DATA → BASELINE →
TRAIN/MODIFY CANDIDATE → EVALUATE → CRITIQUE → VERIFY →
COMPARE → PROMOTION GATE → DEPLOY CANDIDATE →
POST-DEPLOYMENT EVALUATION → LEARN → NEXT IMPROVEMENT
```

## Key Abstractions

### SelfImprovementCycle

A canonical representation of one controlled attempt to improve a JARVIS
capability. Fields include:

| Field | Type | Description |
|-------|------|-------------|
| `improvement_id` | str | Unique identifier (impr_\<uuid\>) |
| `mission_id` | str | Associated mission (if any) |
| `target_capability` | str | What capability is being improved |
| `target_model` | str | Model being improved (e.g. Qwen/Qwen3-4B) |
| `baseline_model` | str | Baseline model reference |
| `baseline_revision` | str | Git revision of baseline |
| `problem_statement` | str | Human-readable description of the problem |
| `failure_evidence` | list | Evidence of failures/regressions |
| `hypotheses` | list | List of Hypothesis objects |
| `proposed_change` | dict | The designed change |
| `change_type` | str | InterventionType value |
| `dataset` | dict | Improvement-generated dataset |
| `training_config` | dict | TrainingConfig as dict |
| `evaluation_suite` | str | Suite ID used for evaluation |
| `compute_requirements` | dict | Compute resource requirements |
| `budget` | dict | Budget constraints |
| `approval_requirements` | list | Required approvals before proceeding |
| `candidate_artifact` | dict | CandidateArtifact as dict (EXPERIMENTAL → APPROVED) |
| `baseline_results` | dict | Baseline evaluation results |
| `candidate_results` | dict | Candidate evaluation results |
| `regression_results` | dict | Regression detection results |
| `critic_findings` | list | Critic findings |
| `verification` | dict | Verification results |
| `promotion_decision` | dict | PromotionGate decision |
| `deployment` | dict | Deployment info |
| `post_deployment_results` | dict | Post-deployment evaluation |
| `status` | str | Current ImprovementStatus |
| `provenance` | list | Audit trail |
| `created_at` | str | ISO timestamp |
| `updated_at` | str | ISO timestamp |

### ImprovementStatus State Machine

```
IDENTIFIED → ANALYZING → HYPOTHESIS_FORMED → DESIGNED →
AWAITING_APPROVAL → DATA_PREPARATION → TRAINING → EVALUATING →
CRITIQUING → VERIFYING → PROMOTION_REVIEW → DEPLOYING → MONITORING →
COMPLETED | REJECTED | FAILED | BLOCKED | ROLLED_BACK
```

Terminal states: `completed`, `rejected`, `failed`, `blocked`, `rolled_back`

### Intervention Types

| Type | Risk | Description |
|------|------|-------------|
| `PROMPT_CHANGE` | Low | Changing prompt templates |
| `SYSTEM_POLICY_CHANGE` | Prohibited | Never autonomous — requires manual owner approval |
| `RETRIEVAL_CHANGE` | Low | Changing retrieval configuration |
| `CONTEXT_CHANGE` | Low | Changing context window/prompt structure |
| `DATASET_CHANGE` | Medium | Adding/curating training data |
| `TRAINING_CHANGE` | Medium | Modifying training config (LoRA, SFT) |
| `HYPERPARAMETER_CHANGE` | Medium | Tuning hyperparameters |
| `ARCHITECTURE_CHANGE` | High | Model architecture changes — requires manual approval |
| `MERGE_CHANGE` | Medium | Merging model weights |
| `PROMPT_TEMPLATE_CHANGE` | Low | Updating prompt templates |

### ImprovementPolicy

Defines measurable criteria for improvement:

- **target_capability**: What is being improved
- **target_metric**: Metric to optimize (e.g. "accuracy")
- **minimum_improvement**: Minimum relative improvement required
- **maximum_allowed_regression**: Max regression allowed on protected metrics
- **evaluation_population**: Size of evaluation population
- **confidence_required**: Confidence threshold (default 0.95)
- **budget_usd_daily**: Daily budget limit
- **budget_usd_monthly**: Monthly budget limit
- **risk_level**: "low", "medium", "high"
- **requires_manual_approval**: Whether manual approval is required

### Autonomy Levels

| Level | Description |
|-------|-------------|
| 0 | Fully manual — human must approve every step |
| 1 | Limited autonomy — can detect weaknesses, propose changes, but requires approval for training/deployment |
| 2 | Moderate autonomy — can run training, but deployment requires approval |
| 3 | Full autonomy — can run full cycle including production deployment |

## Security Guarantees

1. **Credentials Isolation**: The Brain never receives API keys, OAuth tokens,
   provider credentials, database passwords, or any secret configuration.
2. **Protected Paths**: AutonomyGuard blocks interventions on protected paths:
   `jarvis_backend/core.py`, `infrastructure/promotion_gate.py`,
   `infrastructure/audit_events.py`, `.env`, `providers/`, etc.
3. **Prohibited Interventions**: `SYSTEM_POLICY_CHANGE` is never autonomous.
4. **High-Risk Interventions**: `ARCHITECTURE_CHANGE` always requires manual approval.
5. **No Self-Promotion**: JARVIS cannot promote its own model without the
   existing PromotionGate approval.
6. **No Fabrication**: All metrics come from real evaluation data, tied to
   baseline/candidate via BaselineLock.
7. **No Evidence Erasure**: Audit trails are persisted and tamper-evident.

## API Endpoints

All endpoints are prefixed with `/api/v1/improvements`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all improvement cycles |
| POST | `/create` | Create a new improvement cycle |
| POST | `/{impr_id}/run` | Run a full improvement cycle |
| POST | `/{impr_id}/baseline` | Establish baseline lock |
| POST | `/{impr_id}/evaluate` | Evaluate candidate |
| POST | `/{impr_id}/critique` | Run critic on cycle |
| POST | `/{impr_id}/verify` | Verify cycle |
| GET | `/{impr_id}` | Get cycle details |
| POST | `/{impr_id}/transition` | Transition cycle status |
| GET | `/learning/lessons` | List all lessons |
| GET | `/learning/graph` | Get improvement graph |

## Test Coverage

- **Core tests** (`tests/test_self_improvement.py`): 81 tests covering all
  abstractions, state machines, persistence, deployment, and autonomy boundaries.
- **Security red-team** (`tests/test_self_improvement_redteam.py`): 38 tests
  verifying credentials access, protected paths, auth bypass, promotion
  security, metric fabrication, and evidence integrity.
- **No-fabrication audit** (`tests/test_self_improvement_no_fabrication.py`):
  18 tests verifying no metric fabrication across all code paths.
- **Validation scenarios** (`tests/test_self_improvement_scenarios.py`):
  16 tests covering end-to-end scenarios A-J.

**Total: 153 Phase 12 tests, all passing.**
