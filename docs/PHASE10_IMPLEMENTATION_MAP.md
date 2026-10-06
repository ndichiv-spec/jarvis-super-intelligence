# Phase 10 Implementation Map — Long-Horizon Cognitive Intelligence

> **Goal:** Turn JARVIS from an execution-capable AI system into a **long-horizon
> cognitive intelligence platform** built around a durable **Mission** abstraction
> driven by a bounded **Cognitive Kernel**.
>
> **Constraint:** Phases 8 and 9 are COMPLETE. Do **not** rebuild them.
> Phase 10 reuses every piece of infrastructure already in place.

---

## 1. Architectural Target

```
USER
  ↓
MISSION                    (durable, lifecycle-managed long-running objective)
  ↓
COGNITIVE KERNEL           (bounded loop, step-budgeted, checkpointed)
  ↓
UNDERSTAND → HYPOTHESIZE → PLAN → AUTHORIZE → EXECUTE → OBSERVE
  ↓
CRITIQUE → VERIFY → LEARN → REPLAN
  ↓
MISSION COMPLETE           (only after success-criteria verification)
```

**Non-negotiable invariants**
- The Brain never receives credentials (secret isolation preserved from Phase 8).
- No infinite loops — every kernel cycle consumes a cognitive step; budgets are hard stops.
- A Mission does **not** become COMPLETED merely because a task succeeded; completion
  requires success-criteria verification through the existing VerificationEngine.
- The system never fabricates evidence, resources, performance, or execution results.
- No self-approval of authorization gates — humans (or the PromotionGate) approve.

---

## 2. Audit: What Already Exists (No Rebuilds)

### Core Persistence & Runtime
| Component | Location | Status |
|-----------|----------|--------|
| `get_store(name)` / `Store` class | `jarvis_backend/core.py` | ✅ Reused for Mission persistence |
| `now_iso()` / `now()` | `jarvis_backend/core.py` | ✅ Reused for timestamps |
| `STORES` dict (collection defaults) | `jarvis_backend/core.py:164` | ✅ Add `"missions": dict` |
| `bootstrap_runtime()` | `jarvis_runtime.py` | ✅ Already sets up sys.path |

### Task / Execution / DAG Abstraction (Phase 7 — REUSED)
| Component | Location | Status |
|-----------|----------|--------|
| `Task`, `TaskStatus`, `TaskPriority` | `execution_fabric.py:460-574` | ✅ Tasks are the Mission's unit of work |
| `ExecutionGraph` (DAG), `ExecutionNode` | `execution_fabric.py:135-453` | ✅ Reused as Task graph inside Missions |
| `ExecutionNodeStatus` | `execution_fabric.py:104` | ✅ Reused for node lifecycle |
| `FailureClass` | `execution_fabric.py:58` | ✅ Reused for failure classification |
| `AgentExecutor` | `execution_fabric.py:581` | ✅ Cognitive Kernel *delegates* execution to this |
| `build_verified_evidence_pack()` | `execution_fabric.py:1163` | ✅ Reused for evidence collection |
| `_TERMINAL_NODE_STATUSES` / `_DONE_NODE_STATUSES` | `execution_fabric.py:119,128` | ✅ Reused |
| Task persistence via `get_store("tasks")` | `execution_fabric.py:559-574` | ✅ Pattern reused for missions |

### Brain (Phase 8 — Coordinates, Not Replaced)
| Component | Location | Status |
|-----------|----------|--------|
| `discover_brain` / `brain_lifecycle` | `brain_fabric.py` | ✅ Kernel reads Brain readiness |
| `assert_no_secrets` | `brain_fabric.py` | ✅ Kernel enforces no-secret boundary |
| `integration_matrix` / `brain_lifecycle` | `brain_fabric.py` | ✅ Kernel consults for model federation |
| `BRAIN_RUNTIME_UNAVAILABLE` | `brain_fabric.py` | ✅ Kernel handles gracefully (degraded mode) |

### Compute Fabric (Phase 9 — Reused for Resource-Aware Cognition)
| Component | Location | Status |
|-----------|----------|--------|
| `local_hardware()` | `cloud_fabric.py` | ✅ Kernel calls for local resource awareness |
| `cloud_resources()` | `cloud_fabric.py` | ✅ Kernel calls for resource discovery |
| `select_compute()` | `cloud_fabric.py` | ✅ Kernel calls for execution-target selection |
| `cloud_status()` | `cloud_fabric.py` | ✅ Kernel calls for health/status |
| 12 `compute.*` capabilities | `capability_contract.py` _META | ✅ Kernel authorizes via ToolRegistry |
| 12 Compute Tool classes | `capability_tools.py` | ✅ Kernel invokes through ToolRegistry |
| `assert_no_secrets` | `brain_fabric.py` | ✅ Kernel re-applies before Brain interaction |

### Verification Engine (Phase 7 — Reused)
| Component | Location | Status |
|-----------|----------|--------|
| `VerificationEngine` | `research_engine/verification.py` | ✅ Kernel uses for claim verification |
| `VerificationStatus` | `research_engine/models.py:35` | ✅ Reused for verification results |
| `verify_claim()` / `verify_reproduction()` | `verification.py:36,103` | ✅ Kernel calls for hypothesis evaluation |

### Evidence / Models (Phase 7 — Reused)
| Component | Location | Status |
|-----------|----------|--------|
| `Evidence` dataclass | `research_engine/models.py:126` | ✅ Reused by Evidence Engine |
| `EvidenceStatus` / `SourceType` | `models.py:24,46` | ✅ Reused |
| `Experiment` dataclass | `models.py:167` | ✅ Reused for hypothesis testing |
| `ResearchBudgets` | `models.py:186` | ✅ Template for Mission budgets |

### Existing Agent Abstraction
| Component | Location | Status |
|-----------|----------|--------|
| `BrainAgent` | `research_engine/agent.py` | ✅ Reference for agent pattern; NOT rebuilt |

### Infrastructure (Phase 2 — Reused for Audit/Billing/Promotion)
| Component | Location | Status |
|-----------|----------|--------|
| `JobRegistry` / `JobInfo` / `JobStatus`/`JobType` | `infrastructure/job_registry.py` | ✅ Mission links to Jobs |
| `ArtifactRegistry` / `ArtifactInfo` / `ArtifactType`/`ArtifactStatus` | `infrastructure/artifact_registry.py` | ✅ Mission links to Artifacts |
| `PromotionGate` / `PromotionOutcome` / `ApprovalGate` | `infrastructure/promotion_gate.py` | ✅ Human approval gates |
| `AuditEventService` / `EventCategory`/`EventSeverity` | `infrastructure/audit_events.py` | ✅ Mission event timeline |
| `Permission` / `has_permission` | `infrastructure/security/auth.py` | ✅ Authorization checks |
| `KnowledgeStore` / `LearningController` | `infrastructure/knowledge/` | ✅ Mission memory / learning |

### Tooling Infrastructure
| Component | Location | Status |
|-----------|----------|--------|
| `ToolRegistry` / `ToolContext` / `RiskLevel` | `research_engine/tool_registry.py` | ✅ Kernel uses for capability execution |
| `DefaultPermissionPolicy` | `tool_registry.py` | ✅ Reused for confirmation-gating |
| `scrub_secrets` | `tool_registry.py` | ✅ Kernel ensures all results are scrubbed |
| `discover_capabilities()` | `capability_contract.py` | ✅ Kernel uses for capability discovery |
| `CapabilityContract` registry | `capability_contract.py` | ✅ 101 capabilities registered (no new needed) |

### Chat Lifecycle
| Component | Location | Status |
|-----------|----------|--------|
| `ChatService` / `_project_context` | `jarvis_backend/chat_service.py` | ✅ Chat→Mission escalation hooks into this |
| `detect_project_intent` / `select_capabilities` | `project_intel.py` | ✅ Complex objective detection (extended) |

### REST API
| Component | Location | Status |
|-----------|----------|--------|
| `router` (APIRouter, prefix `/api/v2/control`) | `routers/control_plane.py:66` | ✅ Mission API endpoints added here |
| `_run_blocking()` | `control_plane.py:819` | ✅ Pattern reused for blocking kernel calls |
| `get_current_user` / `_require_admin` | `core.py` | ✅ Auth reused for Mission API |

### Silverwing Backend (SEPARATE — NOT Integrated)
| Component | Location | Status |
|-----------|----------|--------|
| `IntelligenceFabric`, `MissionPlanner`, `AgentScheduler` | `silverwing-backend/intelligence_fabric/` | ⚠️ Separate subsystem, not integrated with jarvis_backend. NOT rebuilt. |

---

## 3. Gap Analysis: What Phase 10 Must Create

### New Files (all in `jarvis_backend/`)

| File | Purpose |
|------|---------|
| `jarvis_backend/mission_lifecycle.py` | Mission lifecycle enum + explicit transition rules |
| `jarvis_backend/mission.py` | Mission dataclass with all Phase 10 fields, persistence via `get_store("missions")` |
| `jarvis_backend/cognitive_state.py` | Canonical CognitiveState dataclass |
| `jarvis_backend/hypothesis_engine.py` | Hypothesis dataclass + HypothesisEngine (PROPOSED/TESTING/SUPPORTED/WEAKENED/REJECTED/CONFIRMED/INCONCLUSIVE) |
| `jarvis_backend/evidence_engine.py` | Evidence model with provenance + EvidenceEngine |
| `jarvis_backend/critic.py` | Critic role — analysis only, NO execution authority |
| `jarvis_backend/specialist_roles.py` | 14 specialist role configurations (ARCHITECT, RESEARCHER, SOFTWARE_ENGINEER, DATA_ANALYST, ML_ENGINEER, MATHEMATICIAN, SCIENTIST, SECURITY_ANALYST, SYSTEMS_ENGINEER, DOCUMENT_ANALYST, GEOGRAPHIC_ANALYST, PLANNER, VERIFIER, OBSERVER) |
| `jarvis_backend/cognitive_kernel.py` | The bounded cognitive loop — coordinates Brain + AgentExecutor + all engines |
| `jarvis_backend/mission_api.py` | High-level Mission API (create, start, escalate, checkpoint, resume, complete, etc.) |

### Modified Files

| File | Change |
|------|--------|
| `jarvis_backend/core.py` | Add `"missions": dict` to `STORES` |
| `jarvis_backend/routers/control_plane.py` | Add `/api/v2/control/missions/*` endpoints |
| `jarvis_backend/project_intel.py` | Extend `select_capabilities()` for complex-objective → mission escalation |
| `jarvis_backend/chat_service.py` | Hook for chat → Mission escalation in `_project_context` |

### New Documentation

| File | Purpose |
|------|---------|
| `docs/COGNITIVE_ARCHITECTURE.md` | Cognitive Kernel design, bounded loop, step budgeting |
| `docs/MISSION_CONTROL.md` | Mission lifecycle, states, transitions |
| `docs/MULTI_AGENT_ARCHITECTURE.md` | Specialist roles, delegation, Critic/Verifier |
| `docs/HYPOTHESIS_AND_EVIDENCE.md` | Hypothesis Engine, Evidence Engine, verification |
| `docs/MISSION_SECURITY.md` | Secret isolation, approval gates, autonomy bounds |
| `docs/PHASE10_RESULT.md` | Phase 10 completion report |

### New Test Files

| File | Purpose |
|------|---------|
| `tests/test_mission_lifecycle.py` | Mission lifecycle state machine + transition validation |
| `tests/test_mission_model.py` | Mission dataclass, persistence, serialization |
| `tests/test_cognitive_kernel.py` | Bounded loop, step counting, budget enforcement, no infinite loops |
| `tests/test_hypothesis_engine.py` | Hypothesis statuses, evaluation logic |
| `tests/test_evidence_engine.py` | Evidence provenance, no fabrication |
| `tests/test_mission_redteam.py` | Security: no secret leakage, no credential escalation, no fabrication |
| `tests/test_mission_recovery.py` | Checkpointing, crash recovery, resume |
| `tests/test_mission_integration.py` | End-to-end Mission → Kernel → Task execution flow |

---

## 4. Design Details

### 4.1 Mission Abstraction (`jarvis_backend/mission.py`)

A Mission is the orchestration layer. **JobRegistry remains responsible for executable jobs.**
Missions reference tasks (from `execution_fabric.py`) but do NOT replace JobRegistry.

**Mission fields** (all specified in the Phase 10 requirements):
```
mission_id, title, objective, constraints, success_criteria,
failure_criteria, priority, autonomy_level, risk_level, budget,
allowed_capabilities, required_capabilities, execution_mode, status,
created_by, created_at, updated_at, deadline, context_snapshot,
current_phase, parent_mission, tasks, artifacts, evidence, decisions,
checkpoints, metrics
```

**Persistence:** Uses `get_store("missions")` with `to_dict()`/`from_dict()` pattern
mirroring `Task.save()`/`Task.load()` from `execution_fabric.py`.

**Autonomy levels:**
- `AUTONOMY_LEVEL_0` — fully manual (human approves every step)
- `AUTONOMY_LEVEL_1` — kernel can execute READ tasks, but EXEC/WRITE/NETWORK
  requires explicit human confirmation (delegated to ToolRegistry authorization)
- `AUTONOMY_LEVEL_2` — kernel can execute READ + low-risk WRITE, high-risk
  requires approval
- `AUTONOMY_LEVEL_3` — kernel can self-plan and execute within declared
  capability budget, but cannot approve its own promotion/deployment

**Budget:** `MissionBudget` dataclass with `max_steps`, `max_tokens`,
`max_cost_usd`, `max_seconds`, `max_iterations`. The Kernel enforces these as
hard stops.

### 4.2 Mission Lifecycle (`jarvis_backend/mission_lifecycle.py`)

```
DRAFT → ACTIVE → PAUSED → ACTIVE
  ↓        ↓        ↓
BLOCKED  VERIFYING  ACTIVE
  ↓        ↓
WAITING_FOR_APPROVAL → ACTIVE
  ↓        ↓
WAITING_FOR_RESOURCE → ACTIVE
  ↓        ↓
COMPLETED  FAILED
  ↓        ↓
CANCELLED
```

**Explicit transition rules** — a `MissionLifecycle` class validates every
transition. Illegal transitions raise `ValueError`. Notable rules:

- DRAFT → ACTIVE requires: objective non-empty, at least one capability,
  success_criteria defined.
- ACTIVE → COMPLETED requires: success_criteria verified through
  VerificationEngine (not just task completion).
- COMPLETED → ACTIVE is illegal (missions are terminal once verified complete).
- FAILED → ACTIVE is illegal (requires new mission / explicit reopen via DRAFT).
- Any state → CANCELLED is allowed (human-initiated abort).
- Any state → PAUSED is allowed only if no nodes are actively executing.

### 4.3 Cognitive Kernel (`jarvis_backend/cognitive_kernel.py`)

The Kernel is the **cognitive orchestration layer above the existing Brain**.
It does NOT replace `brain_fabric.py` or `jarvis_backend/brain_fabric.py`.

**Bounded loop** — the kernel runs at most `max_steps` cycles per
`run()` call. Each cycle:

```
1. PERCEIVE    — ingest current cognitive state (facts, evidence, observations)
2. UNDERSTAND  — classify mission phase, update known_facts / unknowns
3. HYPOTHESIZE — propose next hypothesis via HypothesisEngine
4. PLAN        — build ExecutionGraph (DAG) via AgentExecutor.build_execution_graph
5. AUTHORIZE   — check ToolRegistry authorization for each node
6. EXECUTE     — delegate to AgentExecutor.execute_task (which invokes ToolRegistry)
7. OBSERVE     — capture TaskResult, node outputs, artifacts
8. CRITIQUE    — Critic analyzes results, flags inconsistency/fabrication
9. VERIFY      — VerificationEngine verifies claims against evidence
10. LEARN       — update Mission memory (LearningController)
11. REPLAN      — if not complete, return to step 1
```

**Hard stops:**
- `max_steps` per run() call (default: 10, configurable per mission)
- `max_seconds` budget (kernel timer)
- `max_cost_usd` budget (checked against cost accounting)
- If Brain is unavailable (`BRAIN_RUNTIME_UNAVAILABLE`): kernel falls back to
  evidence-driven synthesis, never fabricating model answers

**Checkpointing:** After each cycle, the Kernel calls `mission.checkpoint()`
which persists the full CognitiveState + Task graph to `get_store("missions")`.
On `resume()`, the Kernel restores from the latest checkpoint.

**Delegation to AgentExecutor:** The Kernel creates Tasks via
`AgentExecutor.build_execution_graph()` and executes them via
`AgentExecutor.execute_task()`. The Kernel manages the *mission-level*
loop; AgentExecutor manages the *task-level* execution graph.

### 4.4 Canonical Cognitive State (`jarvis_backend/cognitive_state.py`)

```python
@dataclass
class CognitiveState:
    mission_id: str
    cycle: int                    # current cognitive step
    phase: str                    # current mission phase (understand, hypothesize, ...)
    objective: str
    known_facts: list[str]
    unknowns: list[str]
    hypotheses: list[Hypothesis]  # from HypothesisEngine
    active_hypothesis: Optional[str]
    plan: Optional[ExecutionGraph]  # from execution_fabric
    observations: list[Observation]
    evidence: list[Evidence]      # from research_engine.models
    critic_findings: list[CriticFinding]
    verification_results: list[VerificationResult]
    decisions: list[MissionDecision]
    open_questions: list[str]
    confidence_state: dict[str, Any]
    next_action: Optional[str]
    budget_state: dict[str, Any]  # steps consumed, cost spent, etc.
```

Serialized to dict for checkpointing.

### 4.5 Hypothesis Engine (`jarvis_backend/hypothesis_engine.py`)

**Hypothesis dataclass:**
```python
@dataclass
class Hypothesis:
    id: str
    statement: str          # the testable claim
    context: str            # what this hypothesis is about
    status: HypothesisStatus  # PROPOSED, TESTING, SUPPORTED, WEAKENED,
                              # REJECTED, CONFIRMED, INCONCLUSIVE
    rationale: str          # why this hypothesis was proposed
    proposed_by: str        # role that proposed it
    proposed_at: str        # ISO-8601
    tested_at: Optional[str]
    confidence: Optional[float]  # None unless deterministically computed
    evidence_ids: list[str]  # supporting evidence
    refuted_by: list[str]   # conflicting evidence IDs
    verification_status: VerificationStatus
    conclusion: Optional[str]  # final verdict when CONFIRMED/REJECTED
```

**HypothesisStatus enum:** PROPOSED, TESTING, SUPPORTED, WEAKENED, REJECTED,
CONFIRMED, INCONCLUSIVE.

**HypothesisEngine** — manages hypothesis lifecycle:
- `propose(statement, context, role)` → creates PROPOSED hypothesis
- `select_next()` → picks highest-priority PROPOSED/TESTING hypothesis
- `evaluate(hypothesis_id, evidence)` → updates status based on evidence
  via VerificationEngine
- No fabrication — CONFIRMED requires VerificationStatus.VERIFIED; REJECTED
  requires CONFIRMED or CONTRADICTED evidence

### 4.6 Evidence Engine (`jarvis_backend/evidence_engine.py`)

Builds on `research_engine.models.Evidence` (existing). Adds provenance tracking
and integration with ArtifactRegistry + JobRegistry.

**EvidenceEngine** — manages evidence collection with full provenance:
- `register_evidence(source_type, source_url, title, content, claims, provider)`
  → creates Evidence with `verification_status=UNVERIFIED`
- `verify_evidence(evidence_id)` → uses VerificationEngine to upgrade status
- `get_chain_of_custody(evidence_id)` → traces evidence from source to
  ArtifactRegistry entry to Task node output
- `assert_no_fabrication()` → ensures no evidence is marked VERIFIED without
  a corresponding deterministic check

### 4.7 Critic Role (`jarvis_backend/critic.py`)

The Critic has **NO execution authority**. It only analyzes.
- `critique(state: CognitiveState)` → returns list of CriticFinding
- Checks: evidence quality, confidence calibration, fabrication detection,
  logical consistency, budget adherence, autonomy-level compliance
- Cannot modify state directly — returns findings for the Kernel to act on

### 4.8 Specialist Roles (`jarvis_backend/specialist_roles.py`)

14 roles, each a named configuration that influences how the Cognitive Kernel
interprets its mandate:

| Role | Purpose |
|------|---------|
| ARCHITECT | System structure, interfaces, design |
| RESEARCHER | Information gathering, source evaluation |
| SOFTWARE_ENGINEER | Code implementation, testing |
| DATA_ANALYST | Statistical analysis, data processing |
| ML_ENGINEER | Model training, evaluation, tuning |
| MATHEMATICIAN | Formal reasoning, proof, computation |
| SCIENTIST | Hypothesis formation, experimental design |
| SECURITY_ANALYST | Threat modeling, vulnerability assessment |
| SYSTEMS_ENGINEER | Infrastructure, deployment, resource planning |
| DOCUMENT_ANALYST | Text analysis, summarization, extraction |
| GEOGRAPHIC_ANALYST | Spatial/geo data analysis |
| PLANNER | Task decomposition, dependency analysis |
| VERIFIER | Independent verification of claims |
| OBSERVER | Passive monitoring, evidence collection |

Each role defines: `preferred_capabilities` (set of capability names),
`risk_tolerance` (read/exec/write/network levels), `minimum_evidence`
(threshold for confidence), and `prompt_template` (role-specific reasoning
prefix, used only when a model provider is available).

### 4.9 Cognitive Kernel Integration with Existing Systems

| Kernel step | Delegates to |
|-------------|-------------|
| PLAN | `AgentExecutor.build_execution_graph()` → `ExecutionGraph` (DAG) |
| EXECUTE | `AgentExecutor.execute_task()` → `ToolRegistry.invoke()` |
| VERIFY | `VerificationEngine.verify_claim()` / `verify_reproduction()` |
| COMPUTE SELECTION | `cloud_fabric.select_compute()` (Phase 9) |
| RESOURCE HEALTH | `cloud_fabric.cloud_status()` (Phase 9) |
| BRAIN READINESS | `brain_fabric.discover_brain()` (Phase 8) |
| SECRET SCRUBBING | `brain_fabric.assert_no_secrets()` + `tool_registry.scrub_secrets` |
| AUDIT LOGGING | `AuditEventService.record()` |
| APPROVAL GATES | `PromotionGate.evaluate_for_promotion()` |
| JOB REGISTRY | `JobRegistry.create_job()` / `update_status()` |
| ARTIFACT REGISTRY | `ArtifactRegistry.register()` / `record_access()` |
| LEARNING | `LearningController.propose()` / `approve()` |
| PERSISTENCE | `get_store("missions")` (mirroring `get_store("tasks")`) |

### 4.10 Resource-Aware Cognition (Phase 9 Integration)

The Kernel calls `select_compute(requirements)` before EXECUTE to determine
the appropriate compute target. The ExecutionGraph nodes carry a `provider`
and `model` field (already present on ExecutionNode in execution_fabric.py).
If no compute resource is AVAILABLE, the Kernel transitions the Mission to
WAITING_FOR_RESOURCE rather than fabricating availability.

### 4.11 Chat → Mission Escalation

Extended in `project_intel.py` — complex objectives (multi-step, requiring
multiple capabilities, or long-horizon) trigger Mission creation instead of
plain capability routing. The `select_capabilities()` function is extended
with a `detect_mission_eligibility()` helper that returns True for objectives
that span multiple domains or require sustained analysis.

`chat_service.py._project_context` is extended to check mission eligibility
and, if appropriate, create a Mission and return a "mission_created" response
rather than just an evidence block.

### 4.12 Mission API (`/api/v2/control/missions/*`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/control/missions` | POST | Create a new Mission (from objective) |
| `/api/v2/control/missions/{id}` | GET | Get mission status + state |
| `/api/v2/control/missions/{id}` | PUT | Update mission (title, pause, resume) |
| `/api/v2/control/missions/{id}/start` | POST | Start the Cognitive Kernel for this mission |
| `/api/v2/control/missions/{id}/pause` | POST | Pause the mission |
| `/api/v2/control/missions/{id}/cancel` | POST | Cancel the mission |
| `/api/v2/control/missions/{id}/checkpoint` | POST | Force a checkpoint |
| `/api/v2/control/missions/{id}/resume` | POST | Resume from checkpoint |
| `/api/v2/control/missions/{id}/verify` | POST | Run success-criteria verification |
| `/api/v2/control/missions/{id}/evidence` | GET | Get evidence chain |
| `/api/v2/control/missions/{id}/tasks` | GET | List sub-tasks |
| `/api/v2/control/missions` | GET | List all missions |
| `/api/v2/control/missions/{id}/explain` | GET | User-facing natural-language explanation |

---

## 5. Implementation Order

1. **`mission_lifecycle.py`** — state machine (foundation, no deps on new code)
2. **`mission.py`** — Mission dataclass with persistence
3. **`cognitive_state.py`** — CognitiveState dataclass
4. **`hypothesis_engine.py`** — Hypothesis + HypothesisEngine
5. **`evidence_engine.py`** — EvidenceEngine
6. **`specialist_roles.py`** — role definitions
7. **`critic.py`** — Criti

8. **`cognitive_kernel.py`** — ties everything together (depends on 1-7)
9. **`mission_api.py`** — high-level API (depends on 1-8)
10. **API endpoints** — add to `control_plane.py`
11. **Chat escalation** — extend `project_intel.py` + `chat_service.py`
12. **Core edit** — add `"missions"` to `STORES` in `core.py`
13. **Tests** — comprehensive test suite
14. **Documentation** — detailed docs
15. **Full test run** — verify no regressions

---

## 6. No-Rebuild Guarantees

The following are explicitly NOT rebuilt in Phase 10:
- Phase 8 Brain integration (`brain_fabric.py`, Brain contract, Protocol state machine)
- Phase 9 compute fabric (`cloud_fabric.py`, 12 compute.* capabilities, ComputeSelector)
- Phase 7 Execution Fabric (`execution_fabric.py`, Task, AgentExecutor, ExecutionGraph)
- All infrastructure registries (`JobRegistry`, `ArtifactRegistry`, `ProviderRegistry`,
  `PromotionGate`, `AuditEventService`)
- Silverwing `intelligence_fabric/` subsystem (separate, unintegrated — noted but not rebuilt)
- `capability_contract.py` `_META` (101 entries) and `capability_tools.py` Tool classes (12)
- All Phase 8+9 test files (204 tests must remain green)

---

## 7. Constraints Honored

- **`test_contract_count_matches_registry`**: No new capabilities added → 101 == 101 stays in sync.
- **`test_no_shell_gateway_in_capability_tools`**: No shell primitives introduced in capability tools.
- **`test_compute_*_chat_routing`**: Phase 9 chat routing rules preserved.
- Secret isolation: Brain never sees credentials (enforced by `assert_no_secrets` + `scrub_secrets`).
- No automatic cloud infrastructure creation.
- No automatic production promotion (PromotionGate requires explicit approval).
- No silent money spending (budget enforcement + audit logging).
- Bounded cognitive cycles (hard step/second/cost limits).
