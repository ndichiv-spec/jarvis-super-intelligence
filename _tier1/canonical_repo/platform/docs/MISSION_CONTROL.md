# Phase 10 — Mission Control

## Overview

A **Mission** is a durable, long-running objective that coordinates the Cognitive Kernel through a structured lifecycle. Missions persist across process restarts and survive provider outages, network interruptions, and user disconnects.

## Mission Model

A `Mission` is a dataclass with 27 fields, persisted via the existing `core.py` store infrastructure (same pattern as Phase 7 `Task`):

| Field | Type | Purpose |
|-------|------|---------|
| `mission_id` | str | Unique identifier (`mission_<uuid>`) |
| `title` | str | Human-readable title |
| `objective` | str | The mission's objective |
| `constraints` | list[str] | Hard constraints on execution |
| `success_criteria` | list[str] | Criteria for mission completion |
| `failure_criteria` | list[str] | Criteria for mission failure |
| `priority` | MissionPriority | LOW, NORMAL, HIGH, CRITICAL |
| `autonomy_level` | int | LEVEL_0–3 (0=assisted, 3=bounded autonomous) |
| `risk_level` | RiskLevel | LOW, MEDIUM, HIGH, CRITICAL |
| `budget` | MissionBudget | Step/token/cost/time limits |
| `allowed_capabilities` | list[str] | Capabilities the mission may use |
| `required_capabilities` | list[str] | Capabilities the mission must use |
| `execution_mode` | ExecutionMode | ONLINE, OFFLINE, DEGRADED |
| `status` | MissionStatus | Current lifecycle state |
| `created_by` | str | User who created the mission |
| `created_at` | str | ISO timestamp |
| `updated_at` | str | ISO timestamp |
| `deadline` | str? | Optional deadline |
| `context_snapshot` | dict | Mission-scoped memory/context |
| `current_phase` | str | Current cognitive phase |
| `parent_mission` | str? | Parent mission for sub-missions |
| `tasks` | list[dict] | Linked tasks (Phase 7 Task records) |
| `artifacts` | list[str] | Artifact IDs |
| `evidence` | list[dict] | Evidence entries with provenance |
| `decisions` | list[dict] | Structured decisions |
| `checkpoints` | list[dict] | Cognitive state checkpoints |
| `metrics` | dict | Including `event_timeline` |

## Mission Lifecycle

### States

```
DRAFT → ACTIVE → PAUSED → ACTIVE
               → BLOCKED → ACTIVE
               → WAITING_FOR_APPROVAL → ACTIVE
               → WAITING_FOR_RESOURCE → ACTIVE
               → VERIFYING → COMPLETED (terminal)
               → FAILED (terminal)
               → CANCELLED (terminal)
```

### Legal Transitions

| From | Allowed To | Conditions |
|------|-----------|------------|
| DRAFT | ACTIVE | Requires objective + success_criteria |
| DRAFT | CANCELLED | No conditions |
| ACTIVE | PAUSED, BLOCKED, WAITING_FOR_APPROVAL, WAITING_FOR_RESOURCE, VERIFYING, FAILED, CANCELLED | No active tasks for PAUSED/CANCELLED |
| PAUSED | ACTIVE, CANCELLED | — |
| BLOCKED | ACTIVE, CANCELLED | — |
| WAITING_FOR_APPROVAL | ACTIVE, FAILED, CANCELLED | — |
| WAITING_FOR_RESOURCE | ACTIVE, BLOCKED, CANCELLED | — |
| VERIFYING | COMPLETED, FAILED, CANCELLED | COMPLETED only if success criteria verified |
| COMPLETED | (none) | Terminal |
| FAILED | (none) | Terminal |
| CANCELLED | (none) | Terminal |

### Key Rules

1. **A mission cannot become COMPLETED merely because a task succeeded.** Completion requires VERIFYING state with verified success criteria.
2. **Terminal states cannot transition.** Once COMPLETED, FAILED, or CANCELLED, the mission is immutable.
3. **PAUSED/CANCELLED requires no active tasks.** Tasks must drain first.
4. **All transitions are auditable.** Every transition records an event on the mission timeline.

## Budget Enforcement

The `MissionBudget` dataclass enforces hard limits:

| Field | Purpose |
|-------|---------|
| `max_steps` | Maximum cognitive cycles |
| `max_tokens` | Maximum tokens consumed |
| `max_cost_usd` | Maximum cost in USD |
| `max_seconds` | Maximum wall-clock time |
| `max_iterations` | Maximum tool call iterations |
| `max_cost_provider` | Per-provider cost caps |

The Cognitive Kernel checks these limits at the top of every cycle and stops immediately when any limit is exceeded.

## Checkpointing & Resume

### Checkpointing

After every cognitive cycle, the kernel calls `mission.checkpoint()`:

```python
mission.checkpoint(
    cycle=state.cycle,
    phase=state.phase,
    cognitive_state=state.to_dict(),
    task_states={...},
    hypothesis_states={...},
    evidence_count=len(evidence_engine),
    notes="cycle N complete",
)
```

A `MissionCheckpoint` contains:

| Field | Content |
|-------|---------|
| `checkpoint_id` | Unique ID (`ckpt_<uuid>`) |
| `mission_id` | Parent mission |
| `at` | ISO timestamp |
| `cycle` | Cognitive cycle number |
| `phase` | Cognitive phase |
| `cognitive_state` | Full CognitiveState snapshot |
| `task_states` | Task execution states |
| `hypothesis_states` | Hypothesis engine state |
| `evidence_count` | Number of evidence entries |
| `notes` | Free-text notes |

### Resume

```python
kernel.resume(mission_id, max_steps=N)
```

Resumes from the latest checkpoint:
1. Loads mission from the persistent store
2. Restores `CognitiveState` from the latest checkpoint
3. Rehydrates the Hypothesis Engine from checkpoint data
4. Resets per-run budget exhaustion flag
5. Continues the bounded loop

## Event Timeline

Every mission records an auditable event timeline:

| Event Kind | When |
|------------|------|
| `created` | Mission created |
| `transition` | State transition (with from/to) |
| `checkpoint` | State checkpoint |
| `task_created` | Task added |
| `task_completed` | Task completed |
| `evidence_registered` | Evidence added |
| `decision` | Decision made |
| `verify` | Verification attempted |
| `budget_exhausted` | Budget limit hit |

Events are stored in `mission.metrics["event_timeline"]` and persisted via `to_dict()`/`from_dict()`.

## Mission API Endpoints

The following REST endpoints are available under `/api/v2/control/missions/*`:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/missions` | Create a new mission |
| GET | `/missions` | List all missions |
| GET | `/missions/{mission_id}` | Get mission details |
| POST | `/missions/{mission_id}/start` | Start (DRAFT → ACTIVE) |
| POST | `/missions/{mission_id}/pause` | Pause mission |
| POST | `/missions/{mission_id}/resume` | Resume mission |
| POST | `/missions/{mission_id}/cancel` | Cancel mission |
| POST | `/missions/{mission_id}/approve` | Approve (WAITING_FOR_APPROVAL → ACTIVE) |
| GET | `/missions/{mission_id}/tasks` | List mission tasks |
| GET | `/missions/{mission_id}/events` | Get event timeline |
| GET | `/missions/{mission_id}/evidence` | Get evidence |
| GET | `/missions/{mission_id}/artifacts` | Get artifacts |
| GET | `/missions/{mission_id}/explain` | User-facing explanation |
| GET | `/missions/{mission_id}/status` | Detailed status |
