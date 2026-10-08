"""jarvis_compute.contract - Brain-facing compute contracts (Phase 9 §3/§6).

Dataclasses only; no credentials, no execution authority. These describe *what*
the Brain wants, never *how* it is executed. The control plane resolves them to
a real resource and runs them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .resource import ComputeResource


@dataclass
class ComputeRequest:
    """A Brain capability request for compute, resolved by the control plane."""

    task: str = ""
    task_type: str = "inference"  # inference|training|evaluation|embedding|artifact
    requirements: dict[str, Any] = field(default_factory=dict)
    model: Optional[str] = None
    execution_mode: str = "ONLINE"  # ONLINE|DEGRADED|OFFLINE
    selected_provider: Optional[str] = None
    selected_resource: Optional[str] = None

    def require_field(self, name: str) -> Any:
        return self.requirements.get(name)


@dataclass
class TrainingRequest:
    """A training job the Brain proposes; the control plane submits it."""

    base_model: str
    dataset: str
    hyperparams: dict[str, Any] = field(default_factory=dict)
    budget_usd: float = 0.0
    max_duration_minutes: int = 360
    target: str = "kaggle"  # kaggle | local | remote

    def to_job_info(self) -> dict[str, Any]:
        return {
            "entity": self.base_model,
            "dataset": self.dataset,
            "hyperparams": dict(self.hyperparams),
            "budget_usd": float(self.budget_usd),
            "max_duration_minutes": int(self.max_duration_minutes),
            "target": self.target,
        }


@dataclass
class ComputeJobHandle:
    """A handle to a submitted compute job, read back from the JobRegistry."""

    job_id: str
    status: str  # QUEUED|RUNNING|COMPLETED|FAILED|CANCELLED|RESOURCE_UNAVAILABLE|JOB_SUBMISSION_UNAVAILABLE
    resource: Optional[str] = None
    provider: Optional[str] = None
    provider_job_id: Optional[str] = None
    selected: Optional[ComputeResource] = None
    error: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "resource": self.resource,
            "provider": self.provider,
            "provider_job_id": self.provider_job_id,
            "selected": self.selected.to_dict() if self.selected else None,
            "error": self.error,
            "metrics": dict(self.metrics),
        }


# Truthful failure-state tokens the orchestrator's reassessment path recognizes
# (Phase 9 §9/§11). These mirror Phase 8 protocol outcomes and never masquerade
# as success.
RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
RATE_LIMITED = "RATE_LIMITED"
AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
SECRET_LEAK_REFUSED = "SECRET_LEAK_REFUSED"
JOB_SUBMISSION_UNAVAILABLE = "JOB_SUBMISSION_UNAVAILABLE"
EVALUATION_UNAVAILABLE = "EVALUATION_UNAVAILABLE"
PROMOTION_REQUIRED = "PROMOTION_REQUIRED"
JOB_VERIFIED = "JOB_VERIFIED"
RESOURCE_VERIFIED = "RESOURCE_VERIFIED"

TRUTHFUL_FAILURES = frozenset({
    RESOURCE_UNAVAILABLE, PROVIDER_UNAVAILABLE, RATE_LIMITED,
    AUTHENTICATION_REQUIRED, SECRET_LEAK_REFUSED, JOB_SUBMISSION_UNAVAILABLE,
    EVALUATION_UNAVAILABLE, PROMOTION_REQUIRED,
})
