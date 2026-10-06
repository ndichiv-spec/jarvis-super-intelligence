"""Phase 10 — Specialist Agent Roles.

Each role is a named configuration that influences how the Cognitive Kernel
interprets its mandate.  Roles determine:

- ``preferred_capabilities``: which capabilities the role favors
- ``risk_tolerance``: which risk levels the role may authorize
- ``minimum_evidence``: threshold of verified evidence before drawing conclusions
- ``prompt_template``: role-specific reasoning prefix (used only when a model
  provider is available; the Brain never sees credentials)
- ``can_delegate``: whether this role can delegate to child roles
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("jarvis_backend.specialist_roles")


class RoleName(str, Enum):
    """Canonical specialist roles for the cognitive platform."""

    ARCHITECT = "architect"
    RESEARCHER = "researcher"
    SOFTWARE_ENGINEER = "software_engineer"
    DATA_ANALYST = "data_analyst"
    ML_ENGINEER = "ml_engineer"
    MATHEMATICIAN = "mathematician"
    SCIENTIST = "scientist"
    SECURITY_ANALYST = "security_analyst"
    SYSTEMS_ENGINEER = "systems_engineer"
    DOCUMENT_ANALYST = "document_analyst"
    GEOGRAPHIC_ANALYST = "geographic_analyst"
    PLANNER = "planner"
    VERIFIER = "verifier"
    OBSERVER = "observer"


class RiskTolerance(str, Enum):
    """How much risk a role may authorize."""

    CONSERVATIVE = "conservative"   # read only
    MODERATE = "moderate"           # read + safe write
    AGGRESSIVE = "aggressive"       # read + write + network (with confirmation)


@dataclass
class RoleConfig:
    """Configuration for a specialist role.

    A role is a *reasoning configuration* — it influences capability
    selection, risk tolerance, and evidence thresholds.  It never grants
    credential access or unrestricted shell authority.
    """

    name: str
    description: str
    preferred_capabilities: list[str] = field(default_factory=list)
    excluded_capabilities: list[str] = field(default_factory=list)
    risk_tolerance: str = RiskTolerance.CONSERVATIVE.value
    minimum_evidence: float = 0.7    # min fraction of verified evidence before concluding
    minimum_evidence_count: int = 1  # min number of verified evidence items
    can_delegate: bool = False
    child_roles: list[str] = field(default_factory=list)
    prompt_template: str = ""
    max_delegations: int = 0
    requires_human_approval_for: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "preferred_capabilities": list(self.preferred_capabilities),
            "excluded_capabilities": list(self.excluded_capabilities),
            "risk_tolerance": self.risk_tolerance,
            "minimum_evidence": self.minimum_evidence,
            "minimum_evidence_count": self.minimum_evidence_count,
            "can_delegate": self.can_delegate,
            "child_roles": list(self.child_roles),
            "max_delegations": self.max_delegations,
            "requires_human_approval_for": list(self.requires_human_approval_for),
        }


def _role_configs() -> dict[str, RoleConfig]:
    """Build the canonical set of 14 specialist role configurations."""
    return {
        RoleName.ARCHITECT: RoleConfig(
            name=RoleName.ARCHITECT.value,
            description="System structure, interfaces, and architectural design",
            preferred_capabilities=[
                "project.status", "model.status", "provider.status",
                "fabric.integrations", "cloud.status",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.8,
            can_delegate=True,
            child_roles=[
                RoleName.SOFTWARE_ENGINEER.value,
                RoleName.SYSTEMS_ENGINEER.value,
            ],
            max_delegations=3,
            requires_human_approval_for=["cloud.*", "model.*"],
        ),
        RoleName.RESEARCHER: RoleConfig(
            name=RoleName.RESEARCHER.value,
            description="Information gathering and source evaluation",
            preferred_capabilities=[
                "search_web", "search_web_detailed", "wikipedia", "read_url",
                "document_analysis", "model_consult",
            ],
            risk_tolerance=RiskTolerance.MODERATE.value,
            minimum_evidence=0.6,
            can_delegate=True,
            child_roles=[
                RoleName.DOCUMENT_ANALYST.value,
                RoleName.GEOGRAPHIC_ANALYST.value,
            ],
            max_delegations=2,
            requires_human_approval_for=["model_consult"],
        ),
        RoleName.SOFTWARE_ENGINEER: RoleConfig(
            name=RoleName.SOFTWARE_ENGINEER.value,
            description="Code implementation, testing, and debugging",
            preferred_capabilities=[
                "sandbox_run", "unit_test", "type_check", "static_analysis",
                "code_analysis", "code_search",
            ],
            risk_tolerance=RiskTolerance.MODERATE.value,
            minimum_evidence=0.7,
            minimum_evidence_count=3,
        ),
        RoleName.DATA_ANALYST: RoleConfig(
            name=RoleName.DATA_ANALYST.value,
            description="Statistical analysis and data processing",
            preferred_capabilities=[
                "sandbox_run", "data_analytics", "search_web",
            ],
            risk_tolerance=RiskTolerance.MODERATE.value,
            minimum_evidence=0.6,
        ),
        RoleName.ML_ENGINEER: RoleConfig(
            name=RoleName.ML_ENGINEER.value,
            description="Model training, evaluation, and tuning",
            preferred_capabilities=[
                "model.status", "model.list", "compute.training",
                "compute.evaluation", "model_consult",
            ],
            risk_tolerance=RiskTolerance.AGGRESSIVE.value,
            minimum_evidence=0.7,
            requires_human_approval_for=["compute.training", "compute.job_submit"],
        ),
        RoleName.MATHEMATICIAN: RoleConfig(
            name=RoleName.MATHEMATICIAN.value,
            description="Formal reasoning, proof, and mathematical computation",
            preferred_capabilities=[
                "sandbox_run", "unit_test", "static_analysis", "model_consult",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.9,
        ),
        RoleName.SCIENTIST: RoleConfig(
            name=RoleName.SCIENTIST.value,
            description="Scientific hypothesis formation and experimental design",
            preferred_capabilities=[
                "sandbox_run", "experiment", "search_web", "model_consult",
            ],
            risk_tolerance=RiskTolerance.MODERATE.value,
            minimum_evidence=0.8,
            can_delegate=True,
            child_roles=[RoleName.OBSERVER.value],
            max_delegations=1,
        ),
        RoleName.SECURITY_ANALYST: RoleConfig(
            name=RoleName.SECURITY_ANALYST.value,
            description="Threat modeling and vulnerability assessment",
            preferred_capabilities=[
                "security_check", "system.status", "audit_logs",
                "code_analysis", "static_analysis",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.9,
        ),
        RoleName.SYSTEMS_ENGINEER: RoleConfig(
            name=RoleName.SYSTEMS_ENGINEER.value,
            description="Infrastructure, deployment, and resource planning",
            preferred_capabilities=[
                "compute.discover", "compute.resource_health",
                "compute.select", "system.status", "cloud.status",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.8,
        ),
        RoleName.DOCUMENT_ANALYST: RoleConfig(
            name=RoleName.DOCUMENT_ANALYST.value,
            description="Text analysis, summarization, and information extraction",
            preferred_capabilities=[
                "document_analysis", "read_url", "search_web",
                "data_analytics",
            ],
            risk_tolerance=RiskTolerance.MODERATE.value,
            minimum_evidence=0.6,
        ),
        RoleName.GEOGRAPHIC_ANALYST: RoleConfig(
            name=RoleName.GEOGRAPHIC_ANALYST.value,
            description="Spatial and geographic data analysis",
            preferred_capabilities=[
                "geography_query", "geography_analysis", "search_web",
                "document_analysis",
            ],
            risk_tolerance=RiskTolerance.MODERATE.value,
            minimum_evidence=0.6,
        ),
        RoleName.PLANNER: RoleConfig(
            name=RoleName.PLANNER.value,
            description="Task decomposition and dependency analysis",
            preferred_capabilities=[
                "project.status", "model.status", "compute.discover",
                "search_web",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.5,
        ),
        RoleName.VERIFIER: RoleConfig(
            name=RoleName.VERIFIER.value,
            description="Independent verification of claims and evidence",
            preferred_capabilities=[
                "unit_test", "type_check", "static_analysis",
                "sandbox_run", "experiment",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.9,
            minimum_evidence_count=2,
        ),
        RoleName.OBSERVER: RoleConfig(
            name=RoleName.OBSERVER.value,
            description="Passive monitoring and evidence collection",
            preferred_capabilities=[
                "system.status", "audit_logs", "provider.status",
                "model.status", "compute.resource_health",
            ],
            risk_tolerance=RiskTolerance.CONSERVATIVE.value,
            minimum_evidence=0.5,
            can_delegate=False,
        ),
    }


# Module-level singleton for easy lookup
_ROLES: Optional[dict[str, RoleConfig]] = None


def get_role(name: str) -> Optional[RoleConfig]:
    """Get a role configuration by name."""
    global _ROLES
    if _ROLES is None:
        _ROLES = _role_configs()
    return _ROLES.get(name)


def get_all_roles() -> list[RoleConfig]:
    """Return all role configurations."""
    global _ROLES
    if _ROLES is None:
        _ROLES = _role_configs()
    return list(_ROLES.values())


def role_names() -> list[str]:
    """Return all role names."""
    return [r.value for r in RoleName]


def can_delegate_to(delegator: str, delegatee: str) -> bool:
    """Check if the delegator role can delegate to the delegatee role."""
    role = get_role(delegator)
    if role is None:
        return False
    if not role.can_delegate:
        return False
    return delegatee in role.child_roles


__all__ = [
    "RoleName",
    "RiskTolerance",
    "RoleConfig",
    "get_role",
    "get_all_roles",
    "role_names",
    "can_delegate_to",
]
