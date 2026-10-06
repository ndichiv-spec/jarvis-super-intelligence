"""Phase 11 — Experiments router for the JARVIS Laboratory.

All experiment endpoints delegate to the in-backend ExperimentOrchestrator.
The Brain never receives provider credentials, API keys, or secrets — all
secret handling is delegated to brain_fabric.assert_no_secrets().
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from jarvis_backend.core import get_current_user
from jarvis_backend.dataset import Dataset, DatasetRegistry, DatasetValidator
from jarvis_backend.evaluation_suite import (
    EvaluationSuite,
    EvaluationSuiteRegistry,
    SuiteWrapper,
)
from jarvis_backend.experiment import (
    Experiment,
    ExperimentComparison,
    ExperimentDesign,
    ExperimentLifecycle,
    ExperimentStatus,
    Metric,
    ReproducibilityManifest,
)
from jarvis_backend.experiment_engine import (
    ComputeBounds,
    ExperimentOrchestrator,
    ExperimentRunResult,
    ResourceSelectionResult,
)
from jarvis_backend.ownership import (
    can_access_owner,
    principal_owner_id,
    require_developer,
    require_owner_access,
)
from jarvis_backend.path_security import resolve_confined_path

logger = logging.getLogger("jarvis_backend.routers.experiments")

router = APIRouter(
    prefix="/api/v1/experiments",
    tags=["experiments"],
    dependencies=[Depends(get_current_user)],
)

# Shared orchestrator instance
_orchestrator: Optional[ExperimentOrchestrator] = None


def get_orchestrator() -> ExperimentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ExperimentOrchestrator()
    return _orchestrator


# ---------------------------------------------------------------------------
# Static collection routes — MUST come before /{exp_id} dynamic routes so that
# FastAPI's path-parameter catch-all doesn't shadow them.
# ---------------------------------------------------------------------------

# Design
@router.post("/design", response_model=dict)
def design_experiment(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Design a new experiment from a structured design."""
    orch = get_orchestrator()
    design = ExperimentDesign.from_dict(payload.get("design", {}))
    exp = orch.design_experiment(
        mission_id=payload.get("mission_id", ""),
        name=payload.get("name", "unnamed_experiment"),
        design=design,
        owner=principal_owner_id(user),
    )
    return {"experiment_id": exp.experiment_id, "status": exp.status, "name": exp.name}


# Prepare (resource selection)
@router.post("/prepare", response_model=dict)
def prepare_experiment(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Prepare an experiment: select compute resources."""
    experiment = _get_owned_experiment(payload["experiment_id"], user)
    orch = get_orchestrator()
    exp = orch.prepare_experiment(experiment.experiment_id)
    return {"experiment_id": exp.experiment_id, "status": exp.status,
            "blocked_reason": exp.blocked_reason}


# Baseline/candidate comparison
@router.post("/baseline-candidate", response_model=dict)
def compare_baseline_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare baseline vs candidate using Metric.from_metrics."""
    baseline_metrics = [Metric.from_dict(m) if isinstance(m, dict) else m
                        for m in payload.get("baseline_metrics", [])]
    candidate_metrics = [Metric.from_dict(m) if isinstance(m, dict) else m
                         for m in payload.get("candidate_metrics", [])]
    comparisons = []
    for comp in ExperimentComparison.from_metrics(baseline_metrics, candidate_metrics):
        comparisons.append(comp.to_dict())
    return {"comparisons": comparisons}


# List all experiments
@router.get("", response_model=list)
@router.get("/", response_model=list)
def list_experiments(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List all experiments."""
    return [e.to_dict() for e in Experiment.list_all() if can_access_owner(e.owner, user)]


# List by mission
@router.get("/mission/{mission_id}", response_model=list)
def list_experiments_by_mission(
    mission_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List experiments for a given mission."""
    return [
        e.to_dict()
        for e in Experiment.list_by_mission(mission_id)
        if can_access_owner(e.owner, user)
    ]


# Resource discovery and selection
@router.get("/resources", response_model=dict)
def discover_resources() -> dict[str, Any]:
    """Discover available compute resources."""
    try:
        from jarvis_backend.cloud_fabric import cloud_resources
        cf = cloud_resources()
        # cloud_resources returns {'local_hardware': dict, 'resources': list,
        #                          'by_id': dict, 'count': N, 'note': str}
        return {
            "local_hardware": cf.get("local_hardware", {}),
            "resources": cf.get("resources", []),
            "by_id": cf.get("by_id", {}),
            "count": cf.get("count", 0),
            "note": cf.get("note", ""),
        }
    except Exception as exc:
        return {"resources": [], "by_id": {}, "error": str(exc)}


@router.post("/resources/select", response_model=dict)
def select_resources_for_experiment(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Select a compute resource for an experiment."""
    experiment = _get_owned_experiment(payload["experiment_id"], user)
    orch = get_orchestrator()
    result = orch.select_resources(experiment.experiment_id)
    return {
        "selected": result.selected,
        "resource_id": result.resource_id,
        "reason": result.reason,
        "available_resources": result.available_resources,
    }


# Resource health
@router.get("/resources/{resource_id}/health", response_model=dict)
def resource_health(resource_id: str) -> dict[str, Any]:
    """Check the health of a specific compute resource."""
    try:
        from jarvis_backend.cloud_fabric import cloud_resources
        cf = cloud_resources()
        by_id = cf.get("by_id", {})
        rinfo = by_id.get(resource_id)
        if rinfo is None:
            return {"resource_id": resource_id, "status": "UNKNOWN", "present": False}
        return {"resource_id": resource_id, "status": rinfo.get("status", "UNKNOWN"),
                "type": rinfo.get("type", ""), "present": True}
    except Exception as exc:
        return {"resource_id": resource_id, "status": "ERROR", "error": str(exc)}


# Evaluation suites
@router.get("/evaluation-suites", response_model=list)
def list_evaluation_suites() -> list[dict[str, Any]]:
    """List all evaluation suites."""
    return [s.to_dict() for s in EvaluationSuite.list_all()]


@router.get("/evaluation-suites/{suite_id}", response_model=dict)
def get_evaluation_suite(suite_id: str) -> dict[str, Any]:
    """Get a specific evaluation suite."""
    suite = EvaluationSuite.load(suite_id)
    if suite is None:
        suite = EvaluationSuiteRegistry.get(suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Evaluation suite not found")
    return suite.to_dict()


@router.post("/evaluation-suites/run", response_model=dict)
def run_evaluation_suite(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Run an evaluation suite against a checkpoint."""
    require_developer(user)
    suite_id = payload.get("suite_id")
    try:
        checkpoint = str(
            resolve_confined_path(payload.get("checkpoint_dir", ""), must_be_directory=True)
        )
        val_file = str(resolve_confined_path(payload.get("val_file", "")))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    suite = EvaluationSuite.load(suite_id)
    if suite is None:
        suite = EvaluationSuiteRegistry.get(suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Evaluation suite not found")

    # Use SuiteWrapper to run the suite — never fabricates
    full_metrics = SuiteWrapper.run_full_checkpoint_evaluation(
        checkpoint_dir=checkpoint,
        val_file=val_file,
        work_dir="jarvis_data/experiments",
        tag=payload.get("tag", suite_id),
    )
    return {
        "suite_id": suite_id,
        "metrics": [m.to_dict() for m in full_metrics],
        "count": len(full_metrics),
    }


# Datasets
@router.post("/datasets/validate", response_model=dict)
def validate_dataset(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a dataset through the full pipeline."""
    try:
        location = str(resolve_confined_path(payload.get("location", "")))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ds = Dataset.create(
        name=payload.get("name", ""),
        source=payload.get("source", ""),
        location=location,
        owner=principal_owner_id(user),
    )
    validator = DatasetValidator()
    ds = validator.validate_format(ds)
    ds = validator.deduplicate(ds)
    ds = validator.quality_check(ds)
    ds = validator.security_check(ds)
    if ds.blocked:
        return {"dataset_id": ds.dataset_id, "blocked": True,
                "validation_stage": ds.validation_stage.value,
                "block_reason": ds.block_reason}
    ds = validator.version_dataset(ds)
    ds = validator.register_dataset(ds)
    ds.save()
    return {"dataset_id": ds.dataset_id, "version": ds.version,
            "validation_stage": ds.validation_stage.value, "blocked": False}


@router.get("/datasets", response_model=list)
def list_datasets(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List all datasets."""
    return [d.to_dict() for d in Dataset.list_all() if can_access_owner(d.owner, user)]


@router.get("/datasets/{dataset_id}", response_model=dict)
def get_dataset(
    dataset_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a dataset."""
    ds = Dataset.load(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    require_owner_access(ds.owner, user)
    return ds.to_dict()


# ---------------------------------------------------------------------------
# Dynamic experiment routes — /{exp_id} — registered AFTER all static routes.
# ---------------------------------------------------------------------------

def _get_owned_experiment(exp_id: str, user: dict[str, Any]) -> Experiment:
    exp = Experiment.load(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    require_owner_access(exp.owner, user)
    return exp

# Run
@router.post("/{exp_id}/run", response_model=dict)
def run_experiment(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Run an experiment."""
    require_developer(user)
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    result = orch.run_experiment(exp_id)
    return {
        "experiment_id": result.experiment_id,
        "success": result.success,
        "status": result.status,
        "message": result.message,
        "job_ids": result.job_ids,
        "resources_selected": result.resources_selected,
        "blocked_reason": result.blocked_reason,
    }


# Analyze
@router.post("/{exp_id}/analyze", response_model=dict)
def analyze_experiment(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Analyze experiment results: compute metrics."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    exp = orch.analyze_results(exp_id)
    return {"experiment_id": exp.experiment_id, "status": exp.status,
            "metrics": exp.results.get("metrics", [])}


# Verify
@router.post("/{exp_id}/verify", response_model=dict)
def verify_experiment(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Verify experiment's results."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    exp = orch.verify_experiment(exp_id)
    return {"experiment_id": exp.experiment_id, "status": exp.status,
            "verification_passed": exp.results.get("verification_passed"),
            "verification_issues": exp.results.get("verification_issues", []),
            "verification_at": exp.results.get("verification_at")}


# Complete
@router.post("/{exp_id}/complete", response_model=dict)
def complete_experiment(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Complete a verified experiment and generate reproducibility manifest."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    exp = orch.complete_experiment(exp_id)
    return {"experiment_id": exp.experiment_id, "status": exp.status,
            "manifest_id": exp.reproducibility_metadata.manifest_id if exp.reproducibility_metadata else None}


# Get experiment
@router.get("/{exp_id}", response_model=dict)
def get_experiment(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get experiment details."""
    exp = _get_owned_experiment(exp_id, user)
    return exp.to_dict()


# Get comparison
@router.get("/{exp_id}/comparison", response_model=dict)
def get_experiment_comparison(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get baseline/candidate comparison."""
    exp = _get_owned_experiment(exp_id, user)
    return {
        "experiment_id": exp.experiment_id,
        "comparisons": [c.to_dict() if hasattr(c, "to_dict") else c for c in exp.comparisons],
        "baseline": exp.baseline,
        "candidates": exp.candidates,
    }


# Get reproducibility manifest
@router.get("/{exp_id}/manifest", response_model=dict)
def get_experiment_manifest(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the reproducibility manifest."""
    exp = _get_owned_experiment(exp_id, user)
    if exp.reproducibility_metadata is None:
        raise HTTPException(status_code=404, detail="No reproducibility manifest")
    return exp.reproducibility_metadata.to_dict() if hasattr(
        exp.reproducibility_metadata, "to_dict") else exp.reproducibility_metadata


# Establish baseline
@router.post("/{exp_id}/baseline", response_model=dict)
def establish_baseline(
    exp_id: str,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Establish the baseline for an experiment."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    metrics = [Metric.from_dict(m) if isinstance(m, dict) else m
               for m in payload.get("metrics", [])]
    exp = orch.establish_baseline(
        exp_id=exp_id,
        model=payload["model"],
        revision=payload.get("revision", ""),
        metrics=metrics,
        compute=payload.get("compute", "local:control-node"),
    )
    return {"experiment_id": exp.experiment_id, "baseline": exp.baseline}


# Add candidate
@router.post("/{exp_id}/candidate", response_model=dict)
def add_candidate(
    exp_id: str,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Add a candidate model to an experiment."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    metrics = [Metric.from_dict(m) if isinstance(m, dict) else m
               for m in payload.get("metrics", [])]
    idx = orch.add_candidate(
        exp_id=exp_id,
        model=payload["model"],
        revision=payload.get("revision", ""),
        metrics=metrics,
        compute=payload.get("compute", "local:control-node"),
    )
    return {"experiment_id": exp_id, "candidate_index": idx}


# Promotion evaluation
@router.post("/{exp_id}/promote", response_model=dict)
def evaluate_for_promotion(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Evaluate experiment results against the PromotionGate."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    result = orch.evaluate_for_promotion(exp_id)
    return result


# Status
@router.get("/{exp_id}/status", response_model=dict)
def experiment_status(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get experiment status and lifecycle info."""
    exp = _get_owned_experiment(exp_id, user)
    lifecycle = ExperimentLifecycle()
    return {
        "experiment_id": exp.experiment_id,
        "name": exp.name,
        "status": exp.status,
        "blocked_reason": exp.blocked_reason,
        "can_transition_to_completed": lifecycle.can_transition(
            exp.status, ExperimentStatus.COMPLETED),
        "is_terminal": lifecycle.is_terminal(exp.status),
        "provenance": exp.provenance,
    }


# Block
@router.post("/{exp_id}/block", response_model=dict)
def block_experiment(
    exp_id: str,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Report an experiment as blocked (e.g., resource unavailable)."""
    _get_owned_experiment(exp_id, user)
    orch = get_orchestrator()
    resource_id = payload.get("resource_id", "")
    reason = payload.get("reason", "Resource unavailable")
    exp = orch.report_blocked(exp_id, resource_id, reason)
    return {"experiment_id": exp.experiment_id, "status": exp.status,
            "blocked_reason": exp.blocked_reason}


# Critique
@router.get("/{exp_id}/critique", response_model=dict)
def get_critique(
    exp_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get critic findings for an experiment."""
    exp = _get_owned_experiment(exp_id, user)
    from jarvis_backend.critic import Critic
    critic = Critic()
    findings = critic.critique_experiment(exp)
    return {"experiment_id": exp_id,
            "findings": [f.to_dict() if hasattr(f, "to_dict") else f for f in findings]}
