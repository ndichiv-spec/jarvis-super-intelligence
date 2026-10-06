"""Phase 12 — Self-Improvement router for the JARVIS Self-Improvement Engine.

All improvement endpoints delegate to the in-backend SelfImprovementOrchestrator.
The Brain never receives provider credentials, API keys, or secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from jarvis_backend.core import get_current_user, get_store
from jarvis_backend.ownership import (
    can_access_owner,
    principal_owner_id,
    require_developer,
    require_owner_access,
)
from jarvis_backend.self_improvement import (
    AutonomyGuard,
    CandidateArtifact,
    CandidateStatus,
    EvaluationMatrix,
    GraphNode,
    ImprovementGraph,
    ImprovementPolicy,
    ImprovementStatus,
    InterventionType,
    LearningMemory,
    Lesson,
    SelfImprovementCycle,
    TrainingConfig,
)
from jarvis_backend.self_improvement_engine import SelfImprovementOrchestrator

logger = logging.getLogger("jarvis_backend.routers.improvements")

router = APIRouter(
    prefix="/api/v1/improvements",
    tags=["improvements"],
    dependencies=[Depends(get_current_user)],
)

# Shared orchestrator instance
_orchestrator: Optional[SelfImprovementOrchestrator] = None


def get_orchestrator() -> SelfImprovementOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SelfImprovementOrchestrator(autonomy_level=1)
    return _orchestrator


# ---------------------------------------------------------------------------
# Static collection routes — MUST come before /{impr_id} dynamic routes.
# ---------------------------------------------------------------------------

# List all improvement cycles
@router.get("", response_model=list)
@router.get("/", response_model=list)
def list_improvements(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all improvement cycles."""
    return [c.to_dict() for c in SelfImprovementCycle.list_all() if can_access_owner(c.owner, user)]


# Create a new improvement cycle
@router.post("/create", response_model=dict)
def create_improvement(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new self-improvement cycle."""
    cycle = SelfImprovementCycle.create(
        target_capability=payload.get("target_capability", "unknown"),
        baseline_model=payload.get("baseline_model", "Qwen/Qwen3-4B"),
        baseline_revision=payload.get("baseline_revision", "main"),
        problem_statement=payload.get("problem_statement", ""),
        mission_id=payload.get("mission_id", ""),
        owner=principal_owner_id(user),
    )
    return {
        "improvement_id": cycle.improvement_id,
        "status": cycle.status,
        "target_capability": cycle.target_capability,
    }


# Run a full improvement cycle
def _get_owned_cycle(impr_id: str, user: dict[str, Any]) -> SelfImprovementCycle:
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
    require_owner_access(cycle.owner, user)
    return cycle


def _accessible_improvement_ids(user: dict[str, Any]) -> set[str]:
    data = get_store("improvements").load()
    return {
        improvement_id
        for improvement_id, cycle in data.get("cycles", {}).items()
        if can_access_owner(cycle.get("owner", "system"), user)
    }


@router.post("/{impr_id}/run", response_model=dict)
def run_improvement(
    impr_id: str,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Run a full improvement cycle through all steps."""
    require_developer(user)
    orch = get_orchestrator()
    cycle = _get_owned_cycle(impr_id, user)
    policy = ImprovementPolicy.from_dict(payload.get("policy", {}))
    matrix = EvaluationMatrix.from_dict(payload.get("evaluation_matrix", {}))
    tc = TrainingConfig.from_dict(payload.get("training_config", {}))
    result = orch.run_improvement_cycle(cycle, policy, matrix, tc)
    return {
        "improvement_id": cycle.improvement_id,
        "steps_completed": len(result.get("steps", [])),
        "blocked_step": result.get("blocked_step"),
        "final_status": cycle.status,
    }


# Establish baseline
@router.post("/{impr_id}/baseline", response_model=dict)
def establish_baseline(
    impr_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Establish a baseline lock for an improvement cycle."""
    orch = get_orchestrator()
    cycle = _get_owned_cycle(impr_id, user)
    lock = orch.establish_baseline(
        cycle,
        baseline_model=cycle.baseline_model,
        baseline_revision=cycle.baseline_revision,
        baseline_metrics={"accuracy": 0.85},
    )
    return {
        "improvement_id": impr_id,
        "lock_hash": lock.lock_hash,
        "verified": lock.verify(),
    }


# Evaluate candidate
@router.post("/{impr_id}/evaluate", response_model=dict)
def evaluate_candidate_route(
    impr_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Evaluate the candidate artifact against evaluation matrix."""
    orch = get_orchestrator()
    cycle = _get_owned_cycle(impr_id, user)
    matrix = EvaluationMatrix()
    result = orch.evaluate_candidate(cycle, matrix)
    return {
        "improvement_id": impr_id,
        "evaluation_version": result.get("evaluation_version"),
        "results": result.get("results", {}),
    }


# Critique
@router.post("/{impr_id}/critique", response_model=dict)
def critique_cycle_route(
    impr_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Run critic on an improvement cycle."""
    orch = get_orchestrator()
    cycle = _get_owned_cycle(impr_id, user)
    findings = orch.critique_cycle(cycle)
    return {
        "improvement_id": impr_id,
        "findings_count": len(findings),
        "findings": findings,
    }


# Verify
@router.post("/{impr_id}/verify", response_model=dict)
def verify_cycle_route(
    impr_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Verify an improvement cycle."""
    orch = get_orchestrator()
    cycle = _get_owned_cycle(impr_id, user)
    policy = ImprovementPolicy(
        target_capability=cycle.target_capability,
        target_metric="accuracy",
    )
    result = orch.verify_cycle(cycle, policy)
    return {
        "improvement_id": impr_id,
        "verified": result["verified"],
        "checks": result["checks"],
    }


# ---------------------------------------------------------------------------
# Dynamic improvement routes — /{impr_id} — registered AFTER static routes.
# ---------------------------------------------------------------------------

# Get improvement cycle
@router.get("/{impr_id}", response_model=dict)
def get_improvement(
    impr_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get improvement cycle details."""
    cycle = _get_owned_cycle(impr_id, user)
    return cycle.to_dict()


# Transition status
@router.post("/{impr_id}/transition", response_model=dict)
def transition_status(
    impr_id: str,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Transition an improvement cycle to a new status."""
    cycle = _get_owned_cycle(impr_id, user)
    new_status = payload.get("status", "")
    try:
        cycle.transition(ImprovementStatus(new_status))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {cycle.status} to {new_status}"
        )
    cycle.save()
    return {"improvement_id": impr_id, "new_status": cycle.status}


# List lessons
@router.get("/learning/lessons", response_model=list)
def list_lessons(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all lessons from the learning memory."""
    memory = LearningMemory()
    allowed_ids = _accessible_improvement_ids(user)
    return [
        lesson.to_dict()
        for lesson in memory.get_lessons()
        if lesson.improvement_id in allowed_ids
    ]


# List graph
@router.get("/learning/graph", response_model=dict)
def get_graph(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return graph nodes and edges owned by the authenticated user."""
    store = get_store("improvements")
    data = store.load()
    graph = data.get("graph", {"nodes": {}, "edges": []})
    allowed_ids = _accessible_improvement_ids(user)
    nodes = {
        node_id: node
        for node_id, node in graph.get("nodes", {}).items()
        if node_id in allowed_ids
    }
    edges = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("source") in nodes and edge.get("target") in nodes
    ]
    return {"nodes": nodes, "edges": edges}
