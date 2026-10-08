# Phase 10 — Multi-Agent Architecture

## Overview

Phase 10 introduces 14 **specialist roles** that operate under the Cognitive Kernel's bounded loop. These are **not** independent autonomous agents — they are role-specific reasoning configurations that share the same Brain, ToolRegistry, Capability Fabric, PlanValidator, VerificationEngine, budget infrastructure, and audit system.

## Design Principles

- **No role gets special access to secrets.** All roles operate through the same security boundary.
- **No role can elevate its own privileges.** Autonomy levels are set by the mission creator, not by agents.
- **No role is an unrestricted autonomous system.** All actions are bounded by budgets, authorization, and the Cognitive Kernel's step limits.
- **Roles communicate through structured artifacts**, not unrestricted conversational state.

## Specialist Roles

| Role | Risk Tolerance | Preferred Capabilities | Excluded Capabilities | Requires Approval For | Can Delegate |
|------|---------------|----------------------|----------------------|----------------------|-------------|
| ARCHITECT | conservative | system.*, project.* | compute.training | cloud.*, model.* | True |
| RESEARCHER | moderate | project.*, web.* | compute.training, compute.job_submit | model_consult | True |
| SOFTWARE_ENGINEER | moderate | code.*, project.* | compute.training, compute.job_submit | — | False |
| DATA_ANALYST | moderate | data.*, project.* | compute.training | — | False |
| ML_ENGINEER | aggressive | compute.training, compute.evaluation | — | compute.training, compute.job_submit | True |
| MATHEMATICIAN | conservative | math.*, project.* | compute.training | — | False |
| SCIENTIST | moderate | research.*, project.* | compute.training | — | False |
| SECURITY_ANALYST | conservative | security.*, project.* | compute.training | cloud.* | True |
| SYSTEMS_ENGINEER | conservative | system.*, project.* | compute.training | — | False |
| DOCUMENT_ANALYST | moderate | document.*, project.* | compute.training | — | False |
| GEOGRAPHIC_ANALYST | moderate | geo.*, project.* | compute.training | — | False |
| PLANNER | conservative | planning.*, project.* | compute.training | — | True |
| VERIFIER | conservative | verification.* | compute.training, compute.job_submit | — | False |
| OBSERVER | conservative | system.*.status, project.status | — | — | False |

## Role Configuration

Each role is configured via `RoleConfig`:

```python
@dataclass
class RoleConfig:
    name: str
    preferred_capabilities: list[str]   # Capabilities this role favors
    excluded_capabilities: list[str]     # Capabilities this role never uses
    risk_tolerance: str                  # conservative | moderate | aggressive
    minimum_evidence: float              # 0.0–1.0 confidence threshold
    can_delegate: bool                   # Whether this role can spawn sub-agents
    child_roles: list[str]               # Roles this role can delegate to
    requires_human_approval_for: list[str]  # Patterns requiring human approval
```

## Multi-Agent Delegation

### DelegationManager

`DelegationManager` coordinates work decomposition:

```python
class DelegationManager:
    _delegation_depth: int = 3  # Maximum delegation depth

    def plan_delegation(mission, role_name, task_description) -> Delegation
    def can_delegate_to(from_role, to_role) -> bool
    def execute_delegation(delegation) -> dict
```

### Delegation Depth Bounding

The maximum delegation depth is 3. This means:
- Cycle 1: Root task (depth 0)
- Cycle 2: Role A delegates to Role B (depth 1)
- Cycle 3: Role B delegates to Role C (depth 2)
- Cycle 4: Role C delegates to Role D (depth 3) — **maximum**

Beyond depth 3, delegation is rejected.

### Delegation Record

```python
@dataclass
class Delegation:
    delegation_id: str
    mission_id: str
    from_role: str
    to_role: str
    task_description: str
    intent: str
    required_capabilities: list[str]
    assigned_at: str
    completed_at: Optional[str]
    result: Optional[dict]
    status: str  # pending, running, completed, failed
    depth: int
```

## Role Hierarchy

```
ARCHITECT
├── RESEARCHER
│   ├── DOCUMENT_ANALYST
│   ├── GEOGRAPHIC_ANALYST
│   └── SCIENTIST
├── SOFTWARE_ENGINEER
├── DATA_ANALYST
├── ML_ENGINEER
├── MATHEMATICIAN
├── SECURITY_ANALYST
├── SYSTEMS_ENGINEER
├── PLANNER
│   ├── OBSERVER
│   └── (sub-tasks)
├── VERIFIER
└── OBSERVER
```

Roles that `can_delegate=True` (ARCHITECT, RESEARCHER, ML_ENGINEER, SECURITY_ANALYST, PLANNER) can decompose work to child roles. Roles with `can_delegate=False` execute only through capability tools.

## Communication Through Structured Artifacts

Roles do **not** pass arbitrary state between each other. Instead:

1. Each role produces **structured outputs** (facts, evidence, observations, decisions)
2. These are stored in the `CognitiveState`
3. The next role reads from `CognitiveState` and adds its own contributions
4. All artifacts are traceable with provenance chains

Example flow:
```
RESEARCHER → known_facts, evidence, observations
    ↓
DATA_ANALYST → analysis, evidence (with provenance from RESEARCHER's output)
    ↓
MATHEMATICIAN → hypothesis (with evidence_refs)
    ↓
VERIFIER → verification_results
```

## Critic Role

The Critic is a **specialist role** that operates under all other roles. It has:

- **No execution authority** — cannot run tools, submit jobs, or create tasks
- **Only `critique()` method** — analyzes state and produces findings
- **No `execute`, `run_tool`, `submit_job`, `create_task`, `transition`, or `authorize` methods**

The Critic checks:
- Fabrication (VERIFIED evidence without provenance)
- Evidence quality (unverified count, empty content)
- Hypothesis quality (untested count)
- Budget status (warn/exhaust thresholds)
- Confidence calibration
- Evidence conflicts
- Verification gaps

## Verifier Role

The Verifier wraps the existing Phase 7 `VerificationEngine`. It determines:

| State | Meaning |
|-------|---------|
| GENERATED | Claim was generated but not yet tested |
| EXECUTED | Tool/job was executed |
| OBSERVED | Result was observed |
| VERIFIED | Result was independently verified |
| FAILED_VERIFICATION | Verification failed |

These states are **never conflated**. "Model was trained" ≠ "Training job completed" ≠ "Model passed evaluation" ≠ "Model approved for production."

## Autonomy Enforcement

The Cognitive Kernel enforces autonomy levels at the planning stage:

```python
if mission.autonomy_level <= AutonomyLevel.LEVEL_1.value:
    caps = self._filter_safe_capabilities(caps, mission)
```

- **LEVEL_0**: Only READ-risk capabilities
- **LEVEL_1**: READ + filtered EXEC (no NETWORK without confirmation)
- **LEVEL_2**: READ + low-risk EXEC (requires approval for high-risk)
- **LEVEL_3**: Full capability set (subject to PromotionGate for model promotion)

The Brain cannot elevate its own autonomy level — it is set at mission creation and can only be changed by an authorized human actor.
