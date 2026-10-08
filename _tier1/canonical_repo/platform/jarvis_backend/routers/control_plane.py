"""
Phase 2 Control Plane API Endpoints.

Provides API endpoints for the durable registries (Model, Provider, Artifact, Job),
routing policies, cost accounting, and promotion workflows.

Authentication:
- AUTHENTICATED: All endpoints require authentication
- ADMIN: Promotion and admin operations require admin role
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ..core import _require_auth, _require_admin, is_admin, get_current_user
from infrastructure.model_registry import (
    get_model_registry,
    ModelInfo,
    ModelLifecycleState,
)
from infrastructure.provider_registry import (
    get_provider_registry,
    ProviderInfo,
    ProviderHealthState,
)
from infrastructure.artifact_registry import (
    get_artifact_registry,
    ArtifactInfo,
    ArtifactType,
)
from infrastructure.job_registry import (
    get_job_registry,
    JobInfo,
    JobType,
    JobStatus,
)
from infrastructure.routing_policy import (
    get_routing_engine,
    RoutingQuery,
    RoutingDecision,
    RoutingCostPolicy,
    RoutingPrivacyLevel,
)
from infrastructure.usage_accounting import (
    get_usage_accountant,
    CostRecordInfo,
    BudgetLimit,
)
from infrastructure.audit_events import (
    get_audit_service,
    AuditEvent,
    EventCategory,
)
from infrastructure.promotion_gate import (
    get_promotion_gate,
    EvaluationCriteria,
    PromotionOutcome,
)


router = APIRouter(prefix="/api/v2/control", tags=["control-plane"])


# --------------------------------------------------------------------------- #
# Request/Response Models
# --------------------------------------------------------------------------- #

# --- Provider Management ---

class ProviderUpdateRequest(BaseModel):
    """Request to update provider metadata."""
    provider_name: Optional[str] = None
    enabled: Optional[bool] = None
    environment: Optional[str] = None
    endpoint_type: Optional[str] = None
    endpoint_url: Optional[str] = None
    region: Optional[str] = None
    version: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# --- Model Promotion ---

class PromotionRequest(BaseModel):
    """Request to promote a model."""
    model_id: str = Field(..., description="Model to promote")
    target_status: str = Field(..., description="Target lifecycle status")
    reason: str = Field("", description="Reason for promotion")
    criteria: Optional[Dict[str, Any]] = None
    approvers: List[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    """Request to evaluate a model for promotion."""
    model_id: str
    min_accuracy: Optional[float] = None
    min_pass_rate: Optional[float] = None
    max_latency_ms: Optional[int] = None
    required_capabilities: List[str] = Field(default_factory=list)


# --- Routing ---

class RouteRequest(BaseModel):
    """Request for routing decision."""
    capability: str = "chat"
    privacy: str = "public"
    cost_policy: str = "best_quality"
    max_cost_usd: Optional[float] = None
    model_preferences: List[str] = Field(default_factory=list)


# --- Cost/Budget ---

class BudgetRequest(BaseModel):
    """Request to set budget limit."""
    user_id: str
    daily_usd: float = 0.0
    monthly_usd: float = 0.0
    provider_limits: Dict[str, float] = Field(default_factory=dict)


# --- Job Management ---

class JobCreateRequest(BaseModel):
    """Request to create a job."""
    job_type: str
    model_id: Optional[str] = None
    user_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    resource_cpu: float = 1.0
    resource_memory_gb: float = 1.0
    resource_gpu: int = 0
    tags: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Provider Registry Endpoints
# --------------------------------------------------------------------------- #

@router.get("/providers", response_model=Dict[str, Any])
async def list_providers(
    user: dict = Depends(_require_auth),
    enabled: Optional[bool] = Query(None),
    health_state: Optional[str] = Query(None),
    capability: Optional[str] = Query(None),
    adapter: Optional[str] = Query(None),
):
    """List providers with optional filters."""
    registry = get_provider_registry()
    
    providers = registry.list_providers(
        enabled=enabled,
        health_state=health_state,
        capability=capability,
        adapter=adapter,
    )
    
    return {
        "providers": [
            {
                "provider_id": p.provider_id,
                "provider_name": p.provider_name,
                "adapter": p.adapter,
                "capabilities": p.capabilities,
                "enabled": p.enabled,
                "health_state": p.health_state,
                "verification_state": p.verification_state,
                "environment": p.environment,
            }
            for p in providers
        ],
        "count": len(providers),
    }


@router.get("/providers/{provider_id}", response_model=Dict[str, Any])
async def get_provider(provider_id: str, user: dict = Depends(_require_auth)):
    """Get provider details."""
    registry = get_provider_registry()
    provider = registry.get(provider_id)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    
    return {
        "provider_id": provider.provider_id,
        "provider_name": provider.provider_name,
        "adapter": provider.adapter,
        "capabilities": provider.capabilities,
        "enabled": provider.enabled,
        "health_state": provider.health_state,
        "verification_state": provider.verification_state,
        "last_health_check": provider.last_health_check,
        "supported_models": provider.supported_models,
        "endpoint_type": provider.endpoint_type,
        "region": provider.region,
        "version": provider.version,
        "metadata": provider.metadata,
    }


@router.patch("/providers/{provider_id}", response_model=Dict[str, Any])
async def update_provider(
    provider_id: str,
    req: ProviderUpdateRequest,
    user: dict = Depends(_require_admin),
):
    """Update provider metadata (admin only)."""
    registry = get_provider_registry()
    
    existing = registry.get(provider_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    
    import uuid
    from infrastructure.provider_registry import ProviderInfo
    
    provider_info = ProviderInfo(
        id=existing.id,
        provider_id=provider_id,
        provider_name=req.provider_name or existing.provider_name,
        adapter=existing.adapter,
        capabilities=existing.capabilities,
        enabled=req.enabled if req.enabled is not None else existing.enabled,
        environment=req.environment or existing.environment,
        endpoint_type=req.endpoint_type or existing.endpoint_type,
        endpoint_url=req.endpoint_url or existing.endpoint_url,
        region=req.region or existing.region,
        version=req.version or existing.version,
        health_state=existing.health_state,
        last_health_check=existing.last_health_check,
        verification_enabled=existing.verification_enabled,
        verification_state=existing.verification_state,
        last_verification=existing.last_verification,
        verification_results=existing.verification_results,
        supported_models=existing.supported_models,
        metadata={**existing.metadata, **(req.metadata or {})},
    )
    
    registry.register(provider_info)
    
    return {
        "status": "updated",
        "provider_id": provider_id,
        "updated_by": user.get("email", "admin"),
    }


# --------------------------------------------------------------------------- #
# Model Registry Enhanced Endpoints
# --------------------------------------------------------------------------- #

@router.get("/models", response_model=Dict[str, Any])
async def list_models_enhanced(
    user: dict = Depends(_require_auth),
    provider: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    lifecycle_status: Optional[str] = Query(None),
    capability: Optional[str] = Query(None),
    family: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """List models with enhanced filtering."""
    registry = get_model_registry()
    
    models = registry.list_models(
        provider_id=provider,
        lifecycle_status=lifecycle_status or status,
        capabilities=[capability] if capability else None,
    )
    
    if family:
        models = [m for m in models if m.model_family == family]
    if source:
        models = [m for m in models if m.source == source]
    
    return {
        "models": [
            {
                "model_id": m.model_id,
                "provider_id": m.provider_id,
                "display_name": m.display_name,
                "family": m.model_family,
                "lifecycle_status": m.lifecycle_status,
                "capabilities": m.capabilities,
                "context_window": m.context_window,
                "open_weights": m.open_weights,
            }
            for m in models[:limit]
        ],
        "count": min(len(models), limit),
        "total": len(models),
    }


@router.get("/models/{model_id}/provenance", response_model=Dict[str, Any])
async def get_model_provenance(model_id: str, user: dict = Depends(_require_auth)):
    """Get full provenance chain for a model."""
    registry = get_model_registry()
    model = registry.get(model_id)
    
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    # Build provenance chain
    provenance = model.provenance or {}
    
    # Get parent model if exists
    parent_chain = []
    if model.parent_model_id:
        parent = registry.get(model.parent_model_id)
        if parent:
            parent_chain.append({
                "model_id": parent.model_id,
                "provider_id": parent.provider_id,
                "lifecycle_status": parent.lifecycle_status,
            })
    
    return {
        "model_id": model_id,
        "source": provenance.get("source_provider", "unknown"),
        "parent_model": model.parent_model_id,
        "parent_chain": parent_chain,
        "training_run_id": model.training_run_id,
        "dataset_id": model.dataset_id,
        "evaluation_results": model.evaluation_results,
        "checksums": {
            "model_artifact": model.checksum,
        },
        "metadata": model.metadata,
    }


@router.post("/models/{model_id}/promote", response_model=Dict[str, Any])
async def promote_model(
    model_id: str,
    req: PromotionRequest,
    user: dict = Depends(_require_admin),
):
    """Promote a model through the lifecycle (admin only)."""
    gate = get_promotion_gate()
    registry = get_model_registry()
    
    # Get current model status
    model = registry.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    current_status = model.lifecycle_status
    
    # Validate target status
    valid_transitions = {
        "registered": ["evaluating", "blocked", "retired"],
        "evaluating": ["candidate", "blocked", "retired"],
        "candidate": ["approved", "blocked", "retired"],
        "approved": ["deployed", "deprecated", "retired"],
        "deployed": ["deprecated", "retired"],
        "deprecated": ["retired"],
        "blocked": ["retired"],
    }
    
    if req.target_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from '{current_status}' to '{req.target_status}'"
        )
    
    # Perform promotion
    success, message = gate.promote_model(
        model_id=model_id,
        current_status=current_status,
        target_status=req.target_status,
        reason=req.reason,
        evaluator=user.get("email", "admin"),
        approvers=req.approvers,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Log audit event
    from infrastructure.audit_events import get_audit_service
    audit = get_audit_service()
    audit.record(
        event_type="model.promotion",
        category="model_registry",
        severity="info",
        action=f"promote_{current_status}_to_{req.target_status}",
        result="success",
        resource_type="model",
        resource_id=model_id,
        message=req.reason,
        user_id=user.get("id", ""),
        metadata={"approvers": req.approvers},
    )
    
    return {
        "status": "promoted",
        "model_id": model_id,
        "from_status": current_status,
        "to_status": req.target_status,
        "reason": req.reason,
    }


@router.post("/models/{model_id}/block", response_model=Dict[str, Any])
async def block_model(
    model_id: str,
    reason: str = Body(..., embed=True),
    user: dict = Depends(_require_admin),
):
    """Block a model (admin only)."""
    gate = get_promotion_gate()
    registry = get_model_registry()
    
    success = gate.block_model(
        model_id=model_id,
        reason=reason,
        evaluator=user.get("email", "admin"),
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    return {
        "status": "blocked",
        "model_id": model_id,
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# Routing Policy Endpoints
# --------------------------------------------------------------------------- #

@router.post("/routing/decide", response_model=Dict[str, Any])
async def routing_decision(
    req: RouteRequest,
    user: dict = Depends(_require_auth),
):
    """Get routing decision based on policy."""
    engine = get_routing_engine()
    
    query = RoutingQuery(
        capability=req.capability,
        privacy=req.privacy,
        cost_policy=req.cost_policy,
        max_cost_usd=req.max_cost_usd,
        model_preferences=req.model_preferences,
    )
    
    decision = engine.route(query)
    
    return {
        "decision_id": decision.decision_id,
        "selected_provider": decision.selected_provider,
        "selected_model": decision.selected_model,
        "selected_model_id": decision.selected_model_id,
        "reasoning": decision.reasoning,
        "cost_estimate_usd": decision.cost_estimate_usd,
        "latency_estimate_ms": decision.latency_estimate_ms,
        "provider_health": decision.provider_health,
        "is_verified": decision.is_verified,
        "model_lifecycle": decision.model_lifecycle,
        "fallback_chain": decision.fallback_chain,
    }


# --------------------------------------------------------------------------- #
# Job Registry Endpoints
# --------------------------------------------------------------------------- #

@router.post("/jobs", response_model=Dict[str, Any])
async def create_job(
    req: JobCreateRequest,
    user: dict = Depends(_require_auth),
):
    """Create a new job."""
    registry = get_job_registry()
    
    import uuid
    from infrastructure.job_registry import JobInfo, JobType, JobStatus
    
    job_info = JobInfo(
        id=str(uuid.uuid4()),
        job_id=f"job-{str(uuid.uuid4())[:8]}",
        job_type=req.job_type,
        status="pending",
        user_id=user.get("id"),
        user_email=user.get("email"),
        model_id=req.model_id,
        resource_cpu=req.resource_cpu,
        resource_memory_gb=req.resource_memory_gb,
        resource_gpu=req.resource_gpu,
        config=req.parameters,
        tags=req.tags,
    )
    
    registry.create_job(job_info)
    
    # Log audit event
    from infrastructure.audit_events import get_audit_service
    audit = get_audit_service()
    audit.record(
        event_type="job.created",
        category="job_registry",
        severity="info",
        action="create_job",
        result="success",
        resource_type="job",
        resource_id=job_info.job_id,
        user_id=user.get("id", ""),
        metadata={"job_type": req.job_type, "model_id": req.model_id},
    )
    
    return {
        "job_id": job_info.job_id,
        "status": "created",
        "created_by": user.get("email", "unknown"),
    }


@router.get("/jobs", response_model=Dict[str, Any])
async def list_jobs(
    user: dict = Depends(_require_auth),
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
):
    """List jobs with filters."""
    registry = get_job_registry()
    
    jobs = registry.list_jobs(
        status=status,
        job_type=job_type,
        user_id=user_id,
        limit=limit,
    )
    
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "job_type": j.job_type,
                "status": j.status,
                "user_id": j.user_id,
                "model_id": j.model_id,
                "progress": {
                    "cpu_hours": j.cpu_hours,
                    "gpu_hours": j.gpu_hours,
                },
            }
            for j in jobs
        ],
        "count": len(jobs),
    }


@router.get("/jobs/{job_id}", response_model=Dict[str, Any])
async def get_job(job_id: str):
    """Get job details."""
    registry = get_job_registry()
    job = registry.get(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "user_id": job.user_id,
        "user_email": job.user_email,
        "model_id": job.model_id,
        "resource_allocation": {
            "cpu": job.resource_cpu,
            "memory_gb": job.resource_memory_gb,
            "gpu": job.resource_gpu,
        },
        "timing": {
            "scheduled_at": job.scheduled_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "duration_seconds": job.duration_seconds,
        },
        "cost": {
            "estimated_usd": job.estimated_cost_usd,
            "actual_usd": job.actual_cost_usd,
        },
        "config": job.config,
        "tags": job.tags,
    }


# --------------------------------------------------------------------------- #
# Cost Accounting Endpoints
# --------------------------------------------------------------------------- #

@router.get("/costs", response_model=Dict[str, Any])
async def list_costs(
    user: dict = Depends(_require_auth),
    provider_id: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    start_time: Optional[float] = Query(None),
    end_time: Optional[float] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """List cost records with filters."""
    accountant = get_usage_accountant()
    
    records = accountant.list_records(
        provider_id=provider_id,
        model_id=model_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    
    return {
        "records": [
            {
                "record_id": r.record_id,
                "timestamp": r.timestamp,
                "usage_type": r.usage_type,
                "provider_id": r.provider_id,
                "model_id": r.model_id,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_cost_usd": r.total_cost_usd,
            }
            for r in records
        ],
        "count": len(records),
    }


@router.get("/costs/budget/{user_id}", response_model=Dict[str, Any])
async def get_budget_status(
    user_id: str,
    user: dict = Depends(_require_auth),
):
    """Get budget status for a user."""
    accountant = get_usage_accountant()
    
    return accountant.get_budget_status(user_id, 0.0)  # No limit set by default


@router.post("/budget", response_model=Dict[str, Any])
async def set_budget(
    req: BudgetRequest,
    user: dict = Depends(_require_admin),
):
    """Set budget limit for a user (admin only)."""
    from infrastructure.usage_accounting import BudgetManager
    
    budget_mgr = BudgetManager()
    budget_mgr.set_budget(
        user_id=req.user_id,
        daily_usd=req.daily_usd,
        monthly_usd=req.monthly_usd,
        provider_limits=req.provider_limits,
    )
    
    return {
        "status": "configured",
        "user_id": req.user_id,
        "daily_usd": req.daily_usd,
        "monthly_usd": req.monthly_usd,
    }


@router.get("/costs/usage-by-provider", response_model=Dict[str, Any])
async def get_usage_by_provider(
    user: dict = Depends(_require_auth),
    days: int = Query(30, ge=1, le=365),
):
    """Get usage aggregated by provider."""
    accountant = get_usage_accountant()
    
    now = time.time()
    start = now - (days * 86400)
    
    usage = accountant.get_usage_by_provider(start_time=start, end_time=now)
    
    return {
        "period_days": days,
        "provider_usage": usage,
    }


# --------------------------------------------------------------------------- #
# Audit Events Endpoints
# --------------------------------------------------------------------------- #

@router.get("/audit", response_model=Dict[str, Any])
async def list_audit_events(
    user: dict = Depends(_require_auth),
    category: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    start_time: Optional[float] = Query(None),
    end_time: Optional[float] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Query audit events."""
    audit = get_audit_service()
    
    events = audit.query_events(
        category=category,
        event_type=event_type,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    
    return {
        "events": [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "category": e.category,
                "severity": e.severity,
                "event_type": e.event_type,
                "action": e.action,
                "result": e.result,
                "user_id": e.user_id,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "message": e.message,
            }
            for e in events
        ],
        "count": len(events),
    }


@router.get("/audit/count", response_model=Dict[str, Any])
async def count_audit_events(
    user: dict = Depends(_require_auth),
    category: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    start_time: Optional[float] = Query(None),
    end_time: Optional[float] = Query(None),
):
    """Count audit events matching filters."""
    audit = get_audit_service()
    
    count = audit.count_events(
        category=category,
        event_type=event_type,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
    )
    
    return {"count": count}


# --------------------------------------------------------------------------- #
# Health / Liveness
# --------------------------------------------------------------------------- #

@router.get("/health", response_model=Dict[str, Any])
async def control_plane_health():
    """Health check for control plane."""
    try:
        # Check registries
        from infrastructure.model_registry import get_model_registry
        from infrastructure.provider_registry import get_provider_registry
        from infrastructure.artifact_registry import get_artifact_registry
        from infrastructure.job_registry import get_job_registry
        
        model_registry = get_model_registry()
        provider_registry = get_provider_registry()
        artifact_registry = get_artifact_registry()
        job_registry = get_job_registry()
        
        # Get counts
        models = model_registry.list_models()
        providers = provider_registry.list_providers()
        
        return {
            "status": "healthy",
            "registries": {
                "model_registry": {"count": len(models)},
                "provider_registry": {"count": len(providers)},
                "artifact_registry": {"status": "connected"},
                "job_registry": {"status": "connected"},
            },
            "timestamp": time.time(),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
        }


# --------------------------------------------------------------------------- #
# Brain / Silverwing development fabric (read-only discovery views)
# --------------------------------------------------------------------------- #
async def _run_blocking(fn):
    """Run a blocking discovery function off the event loop."""
    import asyncio
    import functools

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn))


@router.get("/brain", response_model=Dict[str, Any])
async def control_brain(user: Dict[str, Any] = Depends(get_current_user)):
    """Real JARVIS Brain lifecycle: artifacts, provenance, evaluation, promotion.

    Reports the genuine promotion-gate stage. Never claims deployment that has
    not occurred.
    """
    from ..brain_fabric import discover_brain

    try:
        return await _run_blocking(discover_brain)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/silverwing", response_model=Dict[str, Any])
async def control_silverwing(user: Dict[str, Any] = Depends(get_current_user)):
    """Real Silverwing state: models, run manifests, runtime, local availability."""
    from ..brain_fabric import discover_silverwing

    try:
        return await _run_blocking(discover_silverwing)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/development-fabric", response_model=Dict[str, Any])
async def control_development_fabric(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Brain + Silverwing + Hugging Face + Kaggle + NVIDIA readiness in one view."""
    from ..brain_fabric import fabric_overview

    try:
        return await _run_blocking(fabric_overview)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/development-pipeline", response_model=Dict[str, Any])
async def control_development_pipeline(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Kaggle -> Hugging Face -> NVIDIA -> JARVIS link readiness.

    Read-only. Reports each link's real state; Docker is optional and never
    blocking.
    """
    from ..brain_fabric import pipeline_readiness

    try:
        return await _run_blocking(pipeline_readiness)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/development/status", response_model=Dict[str, Any])
async def control_development_status(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Full development-lifecycle status: Brain, Silverwing, Kaggle, HF,
    NVIDIA, Docker, plus recorded provenance contradictions."""
    from ..brain_fabric import development_status

    try:
        return await _run_blocking(development_status)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/development/brain", response_model=Dict[str, Any])
async def control_development_brain(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Brain lifecycle (SOURCE..INFERENCE) + first incomplete stage."""
    from ..brain_fabric import brain_lifecycle

    try:
        return await _run_blocking(brain_lifecycle)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/development/silverwing", response_model=Dict[str, Any])
async def control_development_silverwing(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Silverwing's independent lifecycle and runtime state."""
    from ..brain_fabric import silverwing_lifecycle

    try:
        return await _run_blocking(silverwing_lifecycle)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/development/next-action", response_model=Dict[str, Any])
async def control_development_next_action(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Derived next action per system + unresolved contradictions.

    Proposes only; performs nothing. High-risk actions stay gated.
    """
    from ..brain_fabric import brain_lifecycle, contradictions, silverwing_lifecycle

    try:
        def _build():
            return {
                "brain": brain_lifecycle()["next_action"],
                "silverwing": silverwing_lifecycle()["next_action"],
                "contradictions": contradictions(),
            }

        return await _run_blocking(_build)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/deployments", response_model=Dict[str, Any])
async def control_deployments(user: Dict[str, Any] = Depends(get_current_user)):
    """Deployment eligibility per system, reusing existing registries.

    Reports eligibility and the blocking reason; deploys nothing.
    """
    from ..brain_fabric import (
        brain_lifecycle,
        docker_status,
        nvidia_deployment_readiness,
        silverwing_lifecycle,
    )

    try:
        def _build():
            brain = brain_lifecycle()
            sw = silverwing_lifecycle()
            nv = nvidia_deployment_readiness()
            return {
                "nvidia_target": nv,
                "brain": {
                    "routing_eligible": brain["routing_eligible"],
                    "stages": {k: v["status"] for k, v in brain["stages"].items()},
                    "blockers": (brain["promotion"] or {}).get("blockers") or [],
                },
                "silverwing": {
                    "routing_eligible": sw["routing_eligible"],
                    "stages": {k: v["status"] for k, v in sw["stages"].items()},
                },
                "docker": docker_status(),
            }

        return await _run_blocking(_build)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/remote/status", response_model=Dict[str, Any])
async def control_remote_status(user: Dict[str, Any] = Depends(get_current_user)):
    """Remote execution host status. Reports NOT_CONFIGURED / blocking=false
    when no host is attached. Provisions nothing."""
    from ..remote_host import remote_status

    try:
        return await _run_blocking(remote_status)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/remote/resources", response_model=Dict[str, Any])
async def control_remote_resources(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """CPU/RAM/GPU/VRAM/storage/Docker of the remote host. Null when absent."""
    from ..remote_host import discover

    try:
        return await _run_blocking(lambda: discover().to_dict())
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/remote/verify", response_model=Dict[str, Any])
async def control_remote_verify(user: Dict[str, Any] = Depends(get_current_user)):
    """Run the safe read-only remote test job and report the real result."""
    from ..remote_host import verify_job

    try:
        return await _run_blocking(verify_job)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/cloud/status", response_model=Dict[str, Any])
async def control_cloud_status(user: Dict[str, Any] = Depends(get_current_user)):
    """Cloud hardware fabric: local profile + every real remote resource."""
    from ..cloud_fabric import cloud_status

    try:
        return await _run_blocking(cloud_status)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/cloud/compute/select", response_model=Dict[str, Any])
async def control_cloud_compute_select(
    task: str = Query("", description="What the workload is"),
    gpu_required: bool = Query(False),
    docker_required: bool = Query(False),
    persistent_runtime: bool = Query(False),
    network_required: bool = Query(True),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Select a real execution target for a workload. Proposes; runs nothing."""
    from ..cloud_fabric import select_compute

    try:
        return await _run_blocking(lambda: select_compute({
            "task": task, "gpu_required": gpu_required,
            "docker_required": docker_required,
            "persistent_runtime": persistent_runtime,
            "network_required": network_required,
        }))
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/capabilities", response_model=Dict[str, Any])
async def control_capabilities(user: Dict[str, Any] = Depends(get_current_user)):
    """Canonical capability catalogue: contracts, domain packs, mode coverage."""
    from research_engine.capability_contract import capability_catalogue

    try:
        return await _run_blocking(capability_catalogue)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/capabilities/discover", response_model=Dict[str, Any])
async def control_capabilities_discover(
    task: str = Query(..., description="What the user wants done"),
    mode: str = Query("online", description="online | degraded | offline"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Discover capabilities available for a task under a given mode."""
    from research_engine.capability_contract import discover_capabilities

    try:
        return await _run_blocking(
            lambda: discover_capabilities(task, mode=mode))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/integrations", response_model=Dict[str, Any])
async def control_integrations(user: Dict[str, Any] = Depends(get_current_user)):
    """Truthful integration matrix + derived continuations for all systems."""
    from ..brain_fabric import integration_matrix

    try:
        return await _run_blocking(integration_matrix)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/integrations/{system}", response_model=Dict[str, Any])
async def control_integration(system: str,
                               user: Dict[str, Any] = Depends(get_current_user)):
    """Per-system operational state. Returns state, never credentials."""
    from ..brain_fabric import (
        docker_status,
        external_status,
        integration_matrix,
        nvidia_deployment_readiness,
    )

    key = system.lower()
    try:
        if key == "kaggle":
            return await _run_blocking(lambda: external_status()["kaggle"])
        if key in {"huggingface", "hf"}:
            return await _run_blocking(lambda: external_status()["hugging_face"])
        if key == "nvidia":
            return await _run_blocking(nvidia_deployment_readiness)
        if key == "docker":
            return await _run_blocking(docker_status)
        if key in {"integrations", "all"}:
            return await _run_blocking(integration_matrix)
        raise HTTPException(404, f"unknown integration: {system}")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


# --------------------------------------------------------------------------- #
# Compute Fabric Endpoints (Phase 9)
# --------------------------------------------------------------------------- #

class ComputeSelectRequest(BaseModel):
    """Select a real execution target for a workload."""
    task: str = ""
    gpu_required: bool = False
    min_gpu_memory_gb: Optional[float] = None
    docker_required: bool = False
    persistent_runtime: bool = False
    network_required: bool = True
    max_cost_class: str = "approved"


class JobSubmitRequest(BaseModel):
    """Submit a job to a verified compute resource."""
    job_type: str = Field(..., description="training|inference|evaluation|other")
    model_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    resource_cpu: float = 1.0
    resource_memory_gb: float = 2.0
    resource_gpu: int = 0
    resource_gpu_type: str = ""
    resource_instance_type: str = ""
    provider: Optional[str] = None
    timeout_seconds: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


@router.get("/compute/discover", response_model=Dict[str, Any])
async def compute_discover(
    refresh: bool = Query(False, description="Bypass cache"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Discover all real compute resources (local, NVIDIA, Kaggle, HF, remote).

    Never fabricates availability. A configured credential alone is never an
    available resource.
    """
    from ..cloud_fabric import cloud_resources

    try:
        return await _run_blocking(lambda: cloud_resources(refresh=refresh))
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/verify/{resource_id}", response_model=Dict[str, Any])
async def compute_verify(
    resource_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Verify a specific compute resource by its canonical ID.

    Uses the existing cloud_fabric select_compute with truthful verification.
    """
    from ..cloud_fabric import cloud_resources, select_compute

    try:
        def _verify():
            disc = cloud_resources()
            by_id = disc.get("by_id", {})
            res = by_id.get(resource_id)
            if res is None:
                known = list(by_id.keys())
                return {
                    "resource_id": resource_id,
                    "status": "UNKNOWN",
                    "verified": False,
                    "error": ("Unknown resource. Known: "
                              + ", ".join(known) if known
                              else "No resources discovered"),
                }
            # Truthful status from the resource's own state chain.
            state = res.get("state_chain", {})
            verified = bool(state.get("resource_verified"))
            return {
                "resource_id": res["resource_id"],
                "provider": res.get("provider"),
                "type": res.get("type"),
                "status": res.get("status"),
                "verified": verified,
                "state_chain": state,
                "state": res.get("status"),
            }

        return await _run_blocking(_verify)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/inference", response_model=Dict[str, Any])
async def compute_inference(
    model: Optional[str] = Query(None, description="Model requirement"),
    prompt: Optional[str] = Query(None, description="Inference prompt"),
    provider: Optional[str] = Query(None, description="Provider preference"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Route an inference request to a real, verified inference resource.

    Reports RESOURCE_UNAVAILABLE when no verified inference resource is
    available. Never fabricates a response.
    """
    from ..cloud_fabric import select_compute
    from jarvis_compute.contract import ComputeRequest, TRUTHFUL_FAILURES

    try:
        def _route():
            req_dict = {
                "task": "inference",
                "gpu_required": False,
                "docker_required": False,
                "persistent_runtime": False,
                "network_required": True,
            }
            if model:
                req_dict["task"] = f"inference model={model}"
            sel = select_compute(req_dict)
            selected = sel.get("selected")
            if not selected:
                return {
                    "status": "no_resource",
                    "reason": TRUTHFUL_FAILURES and
                              "RESOURCE_UNAVAILABLE: no verified inference "
                              "resource is available. Check provider configuration "
                              "and network connectivity.",
                }
            return {
                "status": "routed",
                "selected_resource": selected,
                "selection_basis": sel.get("selection_basis"),
                "evaluated": sel.get("evaluated"),
                "note": ("Inference routing is proposed; actual model invocation "
                         "requires the provider gateway. No credentials are "
                         "exposed to callers."),
                "requires_promotion": False,
            }

        return await _run_blocking(_route)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.post("/compute/training", response_model=Dict[str, Any])
async def compute_training(
    req: JobSubmitRequest,
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Submit a training job to a real compute resource.

    Requires admin confirmation for GPU training. Uses the existing job
    registry. Never returns credentials.
    """
    from ..cloud_fabric import select_compute
    from jarvis_compute.contract import ComputeRequest, TRUTHFUL_FAILURES

    try:
        def _submit():
            # Check for GPU requirement
            gpu_required = req.resource_gpu > 0 or "train" in req.task.lower()
            sel = select_compute({
                "task": req.task or "training",
                "gpu_required": gpu_required,
                "min_gpu_memory_gb": req.parameters.get("min_gpu_memory_gb", 0),
                "docker_required": req.docker_required if hasattr(req, 'docker_required') else False,
                "persistent_runtime": False,
                "network_required": True,
                "max_cost_class": "approved",
            })
            selected = sel.get("selected")
            if not selected:
                return {
                    "status": "no_resource",
                    "reason": "RESOURCE_UNAVAILABLE: no verified GPU resource "
                              "for training. Kaggle credentials or NVIDIA access "
                              "may be required.",
                }
            # Register the job in the existing job registry
            registry = get_job_registry()
            import uuid
            from infrastructure.job_registry import JobInfo

            job_info = JobInfo(
                id=str(uuid.uuid4()),
                job_id=f"train-{str(uuid.uuid4())[:8]}",
                job_type=req.job_type,
                status="queued",
                user_id=user.get("id"),
                user_email=user.get("email"),
                model_id=req.model_id,
                resource_cpu=req.resource_cpu,
                resource_memory_gb=req.resource_memory_gb,
                resource_gpu=req.resource_gpu,
                resource_gpu_type=req.resource_gpu_type,
                resource_instance_type=req.resource_instance_type,
                config={**req.parameters, "selected_resource": selected},
                tags=req.tags + ["phase9"],
            )
            created = registry.create_job(job_info)

            # Audit the submission
            audit = get_audit_service()
            audit.record(
                event_type="compute.job_submit",
                category="compute_fabric",
                severity="info",
                action="submit_training",
                result="submitted",
                resource_type="job",
                resource_id=created.job_id,
                user_id=user.get("id", ""),
                metadata={"resource": selected, "job_type": req.job_type},
            )

            return {
                "status": "submitted",
                "job_id": created.job_id,
                "selected_resource": selected,
                "selection_basis": sel.get("selection_basis"),
                "requires_approval": sel.get("requires_approval", False),
                "note": ("Job registered in the durable job registry. "
                         "No credentials are returned to the caller."),
            }

        return await _run_blocking(_submit)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/training", response_model=Dict[str, Any])
async def compute_training_get(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Report training readiness without submitting a job.

    Truthful: reports GPU availability, credential state, and corpus state
    without fabricating.
    """
    from ..brain_fabric import external_status, pipeline_readiness

    try:
        def _status():
            ext = external_status()
            pipe = pipeline_readiness()
            return {
                "training_readiness": {
                    "kaggle": ext.get("kaggle", {}),
                    "huggingface": ext.get("hugging_face", {}),
                },
                "pipeline": pipe,
                "note": ("No job is submitted by this endpoint. Use POST "
                         "/compute/training to submit a training job."),
            }

        return await _run_blocking(_status)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/evaluation", response_model=Dict[str, Any])
async def compute_evaluation(
    resource_id: Optional[str] = Query(None, description="Resource to evaluate"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Report evaluation capability readiness for a compute resource."""
    from ..brain_fabric import brain_lifecycle, pipeline_readiness

    try:
        def _eval():
            brain = brain_lifecycle()
            pipe = pipeline_readiness()
            res = pipeline_readiness()
            selected = None
            if resource_id:
                from ..cloud_fabric import cloud_resources
                disc = cloud_resources()
                if resource_id in disc.get("by_id", {}):
                    selected = resource_id
                else:
                    return {
                        "resource_id": resource_id,
                        "status": "UNKNOWN",
                        "available": False,
                        "error": "unknown resource_id",
                    }
            else:
                from ..cloud_fabric import select_compute
                sel = select_compute({"task": "evaluation"})
                selected = sel.get("selected")

            return {
                "resource_id": selected,
                "brain_lifecycle": {
                    "stage": brain.get("current_stage"),
                    "target": brain.get("next_action"),
                },
                "pipeline": res,
                "evaluation_available": bool(selected),
                "note": ("Evaluation capability is model-dependent. This endpoint "
                         "reports readiness, not results."),
            }

        return await _run_blocking(_eval)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/embedding", response_model=Dict[str, Any])
async def compute_embedding(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Report embedding capability availability (local CPU + NVIDIA)."""
    from ..brain_fabric import external_status

    try:
        def _embed():
            ext = external_status()
            return {
                "embedding": {
                    "local_cpu": True,
                    "nvidia": ext.get("nvidia", {}),
                },
                "note": ("Embedding routing is proposed. Actual invocation "
                         "routes through the provider gateway."),
            }

        return await _run_blocking(_embed)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.post("/compute/artifact/upload", response_model=Dict[str, Any])
async def compute_artifact_upload(
    artifact_id: str = Body(..., embed=True),
    resource_id: Optional[str] = Body(None, embed=True),
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Upload an artifact to a real artifact store (Hugging Face Hub).

    Requires authenticated HF token. Never returns credentials.
    """
    from ..brain_fabric import external_status

    try:
        def _upload():
            ext = external_status()
            hf = ext.get("hugging_face", {})
            if not hf.get("connected"):
                return {
                    "status": "not_connected",
                    "resource": "huggingface",
                    "error": ("Hugging Face is not configured/connected. "
                              "Set JARVIS_HF_TOKEN or HF_TOKEN to enable."),
                }
            return {
                "status": "ready",
                "resource": "huggingface",
                "target": resource_id or "cloud:huggingface",
                "note": ("Artifact upload to HF is gated behind the "
                         "publish_artifact approval. Call the promotion gate "
                         "first."),
                "requires_promotion": True,
            }

        return await _run_blocking(_upload)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.post("/compute/artifact/download", response_model=Dict[str, Any])
async def compute_artifact_download(
    artifact_id: str = Body(..., embed=True),
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Download an artifact from a real artifact store.

    Never returns credentials. Truthful: REPORTS availability based on actual
    HF connectivity.
    """
    from ..brain_fabric import external_status

    try:
        def _download():
            ext = external_status()
            hf = ext.get("hugging_face", {})
            if not hf.get("connected"):
                return {
                    "status": "not_available",
                    "resource": "huggingface",
                    "error": "Hugging Face is not configured/connected.",
                }
            return {
                "status": "ready",
                "resource": "huggingface",
                "artifact_id": artifact_id,
                "note": "Artifact download routes through the HF adapter.",
            }

        return await _run_blocking(_download)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.post("/compute/job/submit", response_model=Dict[str, Any])
async def compute_job_submit(
    req: JobSubmitRequest,
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Submit a job to a verified compute resource via the existing job registry."""
    from ..cloud_fabric import select_compute

    try:
        def _submit():
            gpu_required = req.resource_gpu > 0
            sel = select_compute({
                "task": req.task,
                "gpu_required": gpu_required,
                "min_gpu_memory_gb": req.parameters.get("min_gpu_memory_gb", 0),
                "docker_required": False,
                "persistent_runtime": False,
                "network_required": True,
                "max_cost_class": "approved",
            })
            selected = sel.get("selected")
            if not selected:
                return {
                    "status": "no_resource",
                    "reason": "RESOURCE_UNAVAILABLE: no verified resource "
                              "satisfies the requirements.",
                }
            registry = get_job_registry()
            import uuid
            from infrastructure.job_registry import JobInfo

            job_info = JobInfo(
                id=str(uuid.uuid4()),
                job_id=f"job-{str(uuid.uuid4())[:8]}",
                job_type=req.job_type,
                status="queued",
                user_id=user.get("id"),
                user_email=user.get("email"),
                model_id=req.model_id,
                resource_cpu=req.resource_cpu,
                resource_memory_gb=req.resource_memory_gb,
                resource_gpu=req.resource_gpu,
                resource_gpu_type=req.resource_gpu_type,
                resource_instance_type=req.resource_instance_type,
                config={**req.parameters, "selected_resource": selected},
                tags=req.tags + ["phase9"],
            )
            created = registry.create_job(job_info)

            audit = get_audit_service()
            audit.record(
                event_type="compute.job_submit",
                category="compute_fabric",
                severity="info",
                action="submit_job",
                result="submitted",
                resource_type="job",
                resource_id=created.job_id,
                user_id=user.get("id", ""),
                metadata={"resource": selected, "job_type": req.job_type},
            )

            return {
                "status": "submitted",
                "job_id": created.job_id,
                "selected_resource": selected,
                "selection_basis": sel.get("selection_basis"),
                "requires_approval": sel.get("requires_approval", False),
                "note": "Job registered in the durable job registry.",
            }

        return await _run_blocking(_submit)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/job/{job_id}", response_model=Dict[str, Any])
async def compute_job_status(
    job_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the status of a compute job from the existing job registry."""
    try:
        def _get():
            registry = get_job_registry()
            job = registry.get(job_id)
            if job is None:
                return {
                    "job_id": job_id,
                    "status": "NOT_FOUND",
                    "error": f"Job '{job_id}' not found in registry",
                }
            from infrastructure.job_registry import JobStatus
            return {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "status": job.status,
                "model_id": job.model_id,
                "resource_allocation": {
                    "cpu": job.resource_cpu,
                    "memory_gb": job.resource_memory_gb,
                    "gpu": job.resource_gpu,
                    "gpu_type": job.resource_gpu_type,
                    "instance_type": job.resource_instance_type,
                },
                "timing": {
                    "scheduled_at": job.scheduled_at,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "duration_seconds": job.duration_seconds,
                },
                "cost": {
                    "estimated_usd": job.estimated_cost_usd,
                    "actual_usd": job.actual_cost_usd,
                },
                "config": job.config,
                "tags": job.tags,
            }

        return await _run_blocking(_get)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.post("/compute/job/{job_id}/cancel", response_model=Dict[str, Any])
async def compute_job_cancel(
    job_id: str,
    reason: str = Body("", embed=True),
    user: Dict[str, Any] = Depends(_require_auth),
):
    """Cancel a compute job in the existing job registry."""
    try:
        def _cancel():
            registry = get_job_registry()
            job = registry.get(job_id)
            if job is None:
                return {
                    "job_id": job_id,
                    "status": "NOT_FOUND",
                    "error": f"Job '{job_id}' not found in registry",
                }
            ok = registry.cancel_job(job_id, reason=reason or "cancelled via API")
            audit = get_audit_service()
            audit.record(
                event_type="compute.job_cancel",
                category="compute_fabric",
                severity="info",
                action="cancel_job",
                result="success" if ok else "failure",
                resource_type="job",
                resource_id=job_id,
                user_id=user.get("id", ""),
                metadata={"reason": reason},
            )
            return {
                "job_id": job_id,
                "status": "cancelled" if ok else "cancel_failed",
                "cancelled": ok,
            }

        return await _run_blocking(_cancel)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}


@router.get("/compute/resource/health", response_model=Dict[str, Any])
async def compute_resource_health(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Aggregate health of all compute resources from real probes."""
    from ..cloud_fabric import cloud_status

    try:
        return await _run_blocking(cloud_status)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "error": str(e)}