# Phase 10 — Cognitive Architecture

## Overview

The Cognitive Kernel is the bounded cognitive orchestration layer that sits **above** the existing Phase 8 Brain and Phase 7 Execution Fabric. It coordinates long-horizon reasoning through a structured 11-step cycle, maintaining explicit cognitive state throughout.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USER                                     │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│  MISSION (durable, persisted)                              │
│  mission.py: Mission dataclass + MissionLifecycle          │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│  COGNITIVE KERNEL (bounded loop)                           │
│  cognitive_kernel.py: CognitiveKernel.run()                │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────┴────────┬────────┬────────┬────────┬────────┐
    ↓                 ↓        ↓        ↓        ↓        ↓
 PERCEIVE        UNDERSTAND HYPOTHESIZE PLAN    AUTHORIZE EXECUTE
    ↓                 ↓        ↓        ↓        ↓        ↓
 OBSERVE ←─────────── LEARN ←── CRITIQUE ←── VERIFY ←── REPLAN
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│  COGNITIVE STATE (explicit representation)                 │
│  cognitive_state.py: CognitiveState                        │
└─────────────────────────────────────────────────────────────┘
```

## The 11-Step Cognitive Cycle

### 1. PERCEIVE
Ingests current context into the cognitive state:
- Local hardware status (Phase 9 `local_hardware()`)
- Brain readiness (Phase 8 `discover_brain()`)
- Current mission phase and objectives

### 2. UNDERSTAND
Classifies mission intent and updates known facts:
- Intent classification: verification, investigation, implementation, research, or analysis
- Records objective as a verified known fact
- Records success criteria as open questions

### 3. HYPOTHESIZE
Proposes or selects the next hypothesis to test:
- If an active hypothesis exists and is unresolved, continues testing it
- Otherwise, proposes a new hypothesis from the mission objective
- Hypotheses are managed by the Hypothesis Engine

### 4. PLAN
Builds an execution graph (DAG of capability nodes):
- Uses existing `AgentExecutor.build_execution_graph()` (Phase 7)
- Filters capabilities based on autonomy level (LEVEL_0 blocks EXEC/NETWORK)
- Preserves the Phase 8 `PlanValidator` protocol

### 5. AUTHORIZE
Checks authorization for each node:
- Confirms permissions for the requesting principal
- EXEC/WRITE/NW capabilities require explicit confirmation
- Unconfirmed → WAITING_FOR_APPROVAL

### 6. EXECUTE
Delegates to the existing `AgentExecutor`:
- Runs the execution graph via Phase 7 infrastructure
- Results are scrubbed of secrets via `scrub_secrets()`

### 7. OBSERVE
Captures results and records evidence:
- Observations stored in `CognitiveState.observations`
- Tool results registered in the Evidence Engine with provenance chains
- Tasks linked to the mission record

### 8. CRITIQUE
The Critic (analysis-only, no execution authority) reviews:
- Potential fabrication (VERIFIED evidence without provenance)
- Evidence quality (unverified count, empty content)
- Hypothesis quality (untested count)
- Budget status (warn/exhaust thresholds)
- Confidence calibration
- Evidence conflicts
- Verification gaps

### 9. VERIFY
Uses the existing `VerificationEngine` (Phase 7):
- Verifies claims, success criteria, evidence, and hypotheses
- Verification is traceable — results carry proof state

### 10. LEARN
Updates evidence and knowledge:
- Evidence registered with provenance
- Lessons structured (not applied to production directly)

### 11. REPLAN
Checks completion and replans if needed:
- Runs final Critic assessment
- Checks success criteria verification
- If all verified → transition to VERIFYING → COMPLETED
- If budget exhausted → BUDGET_EXHAUSTED
- Otherwise → continue loop

## Bounding Guarantees

The kernel enforces hard limits:

| Limit | Source |
|-------|--------|
| Max steps per call | `max_steps` parameter or `budget.max_steps` |
| Wall-clock time | `budget.max_seconds` |
| Cost | `budget.max_cost_usd` |
| Token budget | `budget.max_tokens` |
| Parallel tasks | `budget.max_iterations` |
| Infinite loops | Not possible — loop is `while N < step_limit` |

## Checkpointing

After every cycle, the kernel calls `_checkpoint()`:
- Saves cognitive state to the mission's latest checkpoint
- Saves task states, hypothesis states, evidence count
- Persists via the existing `core.py` store infrastructure
- Enables crash recovery via `resume()`

## Crash Recovery

```python
def resume(mission_id, max_steps=None) -> KernelResult:
    mission = Mission.load(mission_id)
    state = CognitiveState.from_dict(latest_checkpoint["cognitive_state"])
    # Restore hypothesis engine from checkpoint
    # Reset per-run budget exhaustion flag
    # Continue bounded loop
```

The kernel restores cognitive state from the latest checkpoint, rehydrates the Hypothesis Engine, and continues execution. Per-run budget exhaustion flags are reset so resumed missions can make progress within their remaining budget.

## Cognitive State

The `CognitiveState` dataclass captures only structured reasoning artifacts — never raw chain-of-thought:

| Field | Content |
|-------|---------|
| `mission_id` | Link to the parent mission |
| `cycle` | Current cognitive cycle number |
| `phase` | Current phase in the 11-step cycle |
| `objective` | Mission objective |
| `known_facts` | Verified facts with source and confidence |
| `unknowns` | Open questions |
| `hypotheses` | Active and resolved hypotheses |
| `active_hypothesis` | Currently tested hypothesis ID |
| `plan` | Execution plan (DAG reference) |
| `observations` | Collected observations |
| `evidence` | Evidence entries with provenance |
| `critic_findings` | Critic analysis results |
| `verification_results` | Verification outcomes |
| `decisions` | Structured decisions made |
| `open_questions` | Unanswered questions |
| `confidence_state` | Confidence metrics (hardware, brain, intent) |
| `next_action` | Next action to take |
| `budget_state` | Steps/tokens/cost/time consumed |

The user sees concise explanations derived from structured state — private chain-of-thought is never exposed.
