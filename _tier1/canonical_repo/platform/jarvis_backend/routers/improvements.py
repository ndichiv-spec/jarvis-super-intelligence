"""Phase 12 — Self-Improvement router for the JARVIS Self-Improvement Engine.

All improvement endpoints delegate to the in-backend SelfImprovementOrchestrator.
The Brain never receives provider credentials, API keys, or secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from jarvis_backend.core import get_store
from jarvis_backend.self_improvement import (
    SelfImprovementCycle,
    CandidateArtifact,
    CandidateStatus,
    ImprovementPolicy,
    ImprovementStatus,
    InterventionType,
    TrainingConfig,
    EvaluationMatrix,
    AutonomyGuard,
    Lesson,
    LearningMemory,
    ImprovementGraph,
    GraphNode,
)
from jarvis_backend.self_improvement_engine import SelfImprovementOrchestrator

logger = logging.getLogger("jarvis_backend.routers.improvements")

router = APIRouter(prefix="/api/v1/improvements", tags=["improvements"])

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
@router.get("/", response_model=list)
def list_improvements() -> list[dict[str, Any]]:
    """List all improvement cycles."""
    return [c.to_dict() for c in SelfImprovementCycle.list_all()]


# Create a new improvement cycle
@router.post("/create", response_model=dict)
def create_improvement(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new self-improvement cycle."""
    cycle = SelfImprovementCycle.create(
        target_capability=payload.get("target_capability", "unknown"),
        baseline_model=payload.get("baseline_model", "Qwen/Qwen3-4B"),
        baseline_revision=payload.get("baseline_revision", "main"),
        problem_statement=payload.get("problem_statement", ""),
        mission_id=payload.get("mission_id", ""),
        owner=payload.get("owner", "system"),
    )
    return {
        "improvement_id": cycle.improvement_id,
        "status": cycle.status,
        "target_capability": cycle.target_capability,
    }


# Run a full improvement cycle
@router.post("/{impr_id}/run", response_model=dict)
def run_improvement(impr_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run a full improvement cycle through all steps."""
    orch = get_orchestrator()
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
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
def establish_baseline(impr_id: str) -> dict[str, Any]:
    """Establish a baseline lock for an improvement cycle."""
    orch = get_orchestrator()
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
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
def evaluate_candidate_route(impr_id: str) -> dict[str, Any]:
    """Evaluate the candidate artifact against evaluation matrix."""
    orch = get_orchestrator()
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
    matrix = EvaluationMatrix()
    result = orch.evaluate_candidate(cycle, matrix)
    return {
        "improvement_id": impr_id,
        "evaluation_version": result.get("evaluation_version"),
        "results": result.get("results", {}),
    }


# Critique
@router.post("/{impr_id}/critique", response_model=dict)
def critique_cycle_route(impr_id: str) -> dict[str, Any]:
    """Run critic on an improvement cycle."""
    orch = get_orchestrator()
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
    findings = orch.critique_cycle(cycle)
    return {
        "improvement_id": impr_id,
        "findings_count": len(findings),
        "findings": findings,
    }


# Verify
@router.post("/{impr_id}/verify", response_model=dict)
def verify_cycle_route(impr_id: str) -> dict[str, Any]:
    """Verify an improvement cycle."""
    orch = get_orchestrator()
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
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
def get_improvement(impr_id: str) -> dict[str, Any]:
    """Get improvement cycle details."""
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
    return cycle.to_dict()


# Transition status
@router.post("/{impr_id}/transition", response_model=dict)
def transition_status(impr_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Transition an improvement cycle to a new status."""
    cycle = SelfImprovementCycle.load(impr_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Improvement cycle not found")
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
def list_lessons() -> list[dict[str, Any]]:
    """List all lessons from the learning memory."""
    memory = LearningMemory()
    return [l.to_dict() for l in memory.get_lessons()]


# List graph
@router.get("/learning/graph", response_model=dict)
def get_graph() -> dict[str, Any]:
    """Get the improvement graph."""
    store = get_store("improvements")
    data = store.load()
    return data.get("graph", {"nodes": {}, "edges": []})
