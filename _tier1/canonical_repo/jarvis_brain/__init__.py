"""JARVIS Brain integration package (Phase 8).

Wire-up glue that integrates the existing JARVIS Brain (reasoning) into the
execution / control plane (authority + execution).  The package does NOT
rebuild Phase 5/6/7 infrastructure — it reuses ``brain_runtime``, ``backend``,
``research_engine``, ``providers`` and ``identity`` and simply bounds the loop:

    USER → BRAIN (propose) → PLAN_VALIDATOR → AUTHORIZE → EXECUTE via
           ToolRegistry (auth + secret-scrubbing) → OBSERVE (sanitized) →
           VERIFY (evidence) → REASON → REPLAN (bounded) → COMPLETE

Modules:
    contract        structured Brain input/output, confidence states, autonomy
    budget          hard limits (max_plan_iterations, max_retries, max_replans,
                    max_execution_time, max_cost) + TASK_BUDGET_EXCEEDED
    context_engine  bounded, scrubbed context packs (never the full catalog)
    plan_validator  6-stage validation gate (schema→existence→I/O→permission→
                    risk→mode→dependency)
    protocol        ordered Brain↔Control Plane state machine
    audit           observability events, cost accounting, user-facing summary
    adapters        BrainAdapter protocol; ModelBrainAdapter (honesty-gated) +
                    DeterministicBrainAdapter (offline, no-fabrication)
    orchestrator    the controlled PLAN→...→REPLAN loop tying it all together
"""
from __future__ import annotations

from . import contract, budget, context_engine, plan_validator, protocol, audit, adapters, orchestrator

from .contract import (
    AutonomyLevel, BrainInput, BrainIntent, BrainOutput, CapabilityRequest,
    CompletionCondition, ConfidenceState, ExecutionMode, Plan, PlanStep,
    PlanDecision, SchemaValidationError, validate_brain_output,
    brain_output_schema, safe_parse_brain_json,
)
from .budget import TaskBudget, TaskBudgetExceeded
from .context_engine import ContextEngine, ContextPack, ContextLimits
from .plan_validator import PlanValidator, ValidationResult, PlanIssue
from .protocol import BrainControlProtocol, ProtocolState, ProtocolTransition
from .audit import BrainAudit, EventType
from .adapters import (
    BrainAdapter, ModelBrainAdapter, DeterministicBrainAdapter,
    BrainAvailability, build_brain_adapter,
)
from .orchestrator import BrainOrchestrator, TaskResult

__all__ = [
    "contract", "budget", "context_engine", "plan_validator", "protocol",
    "audit", "adapters", "orchestrator",
    "AutonomyLevel", "BrainInput", "BrainIntent", "BrainOutput",
    "CapabilityRequest", "CompletionCondition", "ConfidenceState",
    "ExecutionMode", "Plan", "PlanStep", "PlanDecision",
    "SchemaValidationError", "validate_brain_output", "brain_output_schema",
    "safe_parse_brain_json", "TaskBudget", "TaskBudgetExceeded",
    "ContextEngine", "ContextPack", "ContextLimits", "PlanValidator",
    "ValidationResult", "PlanIssue", "BrainControlProtocol", "ProtocolState",
    "ProtocolTransition", "BrainAudit", "EventType", "BrainAdapter",
    "ModelBrainAdapter", "DeterministicBrainAdapter", "BrainAvailability",
    "build_brain_adapter", "BrainOrchestrator", "TaskResult",
]
