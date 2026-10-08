"""JARVIS Brain contract, role separation and structured I/O (Phase 8 §2-3, §8, §25).

This module is the *boundary* between the Brain (reasoning + planning) and the
control plane (authority + execution).  It deliberately contains **no** I/O,
**no** credentials, **no** network and **no** host-execution authority — it only
defines the structured data that the Brain may *propose* and that the control
plane must validate before executing anything.

Architectural invariant (spec §2)::

    USER -> JARVIS BRAIN -> INTENT/PLAN -> CONTROL PLANE -> CAPABILITY FABRIC
      -> PROVIDER/TOOL/RESOURCE -> RESULT -> VERIFICATION -> BRAIN -> USER

What the Brain OWNS here (the ``BrainOutput`` it proposes):

    * request understanding (intent)
    * task decomposition / planning (plan.steps)
    * capability selection *proposals* (capability_requests)
    * dependency reasoning (step depends_on)
    * result synthesis + verification interpretation (completion_conditions)
    * context selection (the control plane hands back a bounded pack)
    * memory retrieval *decisions* (it asks, the registry recalls)
    * user-facing explanation (summary, confidence_summary)
    * confidence / uncertainty (ConfidenceState -- never a fabricated float)

What the Brain does NOT own (enforced elsewhere, not by this module):

    * provider secrets / raw credentials      (ToolRegistry authorization boundary)
    * arbitrary shell / DB / filesystem         (only registered capabilities)
    * authorization decisions                   (PlanValidator + PermissionPolicy)
    * artifact persistence / job truth           (control plane / TaskManager)
    * provider health truth                      (Observer / ProviderControlCenter)

The Brain *proposes*; the control plane *authorizes and executes*.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ExecutionMode(str, Enum):
    """Operating mode handed to the Brain by the control plane."""

    ONLINE = "ONLINE"      # full capability set, including cloud/network
    DEGRADED = "DEGRADED"  # Brain up but providers limited
    OFFLINE = "OFFLINE"    # no network/cloud -- only supports_offline capabilities


class ConfidenceState(str, Enum):
    """Honest, qualitative uncertainty states (Phase 8 §8).

    These are NEVER a fabricated numeric score.  The Brain surfaces one of these
    verbatim so the control plane knows whether it can trust a proposal or must
    ask the user / degrade.
    """

    SUFFICIENT_INFORMATION = "SUFFICIENT_INFORMATION"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    AMBIGUOUS_REQUEST = "AMBIGUOUS_REQUEST"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ASK_USER = "ASK_USER"


class AutonomyLevel(str, Enum):
    """How far the control plane may go on the Brain's behalf (Phase 8 §25)."""

    ASSISTED = "ASSISTED"        # propose only; every step needs explicit user approval
    SUPERVISED = "SUPERVISED"    # auto-run read/exec/local-write; confirm network/admin
    AUTONOMOUS = "AUTONOMOUS"    # auto-run anything policy-allows; bounded by budget only


class PlanDecision(str, Enum):
    """Outcome of validating a Brain-proposed plan (Phase 8 §4)."""

    ACCEPTED = "ACCEPTED"               # plan is valid, authorized, executable
    PLAN_REJECTED = "PLAN_REJECTED"     # schema / structural / malformed
    PLAN_BLOCKED = "PLAN_BLOCKED"       # capability exists but unavailable / deps fail
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    DENIED = "DENIED"                   # permission/risk denied by policy
    HUMAN_APPROVAL = "HUMAN_APPROVAL"  # destructive or high-risk -> needs approval


_CONFIDENCE_VALUES = frozenset(c.value for c in ConfidenceState)


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #
@dataclass
class BrainInput:
    """Structured input envelope the control plane hands to the Brain.

    ``available_capabilities`` is a *bounded context pack* -- a sliced,
    relevance-scored view of the capability catalogue -- never the full registry.
    """

    request: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    available_capabilities: list[dict[str, Any]] = field(default_factory=list)
    execution_mode: str = ExecutionMode.ONLINE.value
    task_state: dict[str, Any] = field(default_factory=dict)
    relevant_artifacts: list[dict[str, Any]] = field(default_factory=list)
    user_id: str = "anonymous"
    autonomy: str = AutonomyLevel.AUTONOMOUS.value
    budget: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "context": dict(self.context),
            "available_capabilities": [dict(c) for c in self.available_capabilities],
            "execution_mode": self.execution_mode,
            "task_state": dict(self.task_state),
            "relevant_artifacts": [dict(a) for a in self.relevant_artifacts],
            "user_id": self.user_id,
            "autonomy": self.autonomy,
            "budget": dict(self.budget),
        }


# --------------------------------------------------------------------------- #
# Output (what the Brain may PROPOSE -- the control plane never executes a plan
# that did not pass PlanValidator first)
# --------------------------------------------------------------------------- #
@dataclass
class CapabilityRequest:
    """A single proposed capability invocation (NOT executed by the Brain)."""

    capability: str
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    depends_on: list[str] = field(default_factory=list)  # refs to sibling cap ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "args": dict(self.args),
            "reason": self.reason,
            "depends_on": list(self.depends_on),
        }


@dataclass
class PlanStep:
    """One narrative step of the proposed plan (machine-enforced too)."""

    id: str
    capability: str
    summary: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "capability": self.capability, "summary": self.summary,
            "args": dict(self.args), "depends_on": list(self.depends_on),
        }


@dataclass
class Plan:
    summary: str = ""
    steps: list[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "steps": [s.to_dict() for s in self.steps]}


@dataclass
class CompletionCondition:
    """An explicit, observable stop condition (Phase 8 §7).

    Completion is ONLY declared when evidence satisfies one of these -- never
    when the Brain merely says "done".
    """

    type: str = ""          # artifact_created|verification_passed|answer_generated|...
    target: str = ""        # what artifact / claim / test to look for
    expected: Any = None    # expected value/shape, if applicable

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "target": self.target, "expected": self.expected}


@dataclass
class BrainIntent:
    domain: str = ""
    task: str = ""
    confidence: ConfidenceState = ConfidenceState.SUFFICIENT_INFORMATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain, "task": self.task,
            "confidence_state": self.confidence.value,
        }


@dataclass
class BrainOutput:
    """Structured output the Brain is allowed to PRODUCE.

    ``confidence_state`` is always populated (never fabricated).  ``model_ref``
    and ``provenance`` let the control plane attribute the proposal honestly.
    """

    intent: BrainIntent = field(default_factory=BrainIntent)
    plan: Plan = field(default_factory=Plan)
    capability_requests: list[CapabilityRequest] = field(default_factory=list)
    questions_for_user: list[str] = field(default_factory=list)
    completion_conditions: list[CompletionCondition] = field(default_factory=list)
    confidence_state: ConfidenceState = ConfidenceState.SUFFICIENT_INFORMATION
    # Honest attribution -- which provider/backend actually produced this.
    model_ref: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    summary: str = ""  # user-facing explanation (NO chain-of-thought)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.to_dict(),
            "plan": self.plan.to_dict(),
            "capability_requests": [c.to_dict() for c in self.capability_requests],
            "questions_for_user": list(self.questions_for_user),
            "completion_conditions": [c.to_dict() for c in self.completion_conditions],
            "confidence_state": self.confidence_state.value,
            "model_ref": self.model_ref,
            "provenance": dict(self.provenance),
            "summary": self.summary,
        }


# --------------------------------------------------------------------------- #
# Validation (Phase 8 §4 stage 1 -- schema validation)
# --------------------------------------------------------------------------- #
_BRAIN_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["intent", "plan", "capability_requests", "completion_conditions",
                 "confidence_state"],
    "properties": {
        "intent": {"type": "object", "required": ["confidence_state"], "properties": {
            "domain": {"type": "string"},
            "task": {"type": "string"},
            "confidence_state": {"type": "string"},
        }},
        "plan": {"type": "object", "required": ["steps"], "properties": {
            "summary": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}},
        }},
        "capability_requests": {"type": "array", "items": {"type": "object",
            "required": ["capability"], "properties": {
                "capability": {"type": "string"},
                "args": {"type": "object"},
                "reason": {"type": "string"},
                "depends_on": {"type": "array", "items": {"type": "string"}},
            }}},
        "questions_for_user": {"type": "array", "items": {"type": "string"}},
        "completion_conditions": {"type": "array", "items": {"type": "object"}},
        "confidence_state": {"type": "string"},
        "model_ref": {"type": "string"},
        "provenance": {"type": "object"},
        "summary": {"type": "string"},
    },
}


class SchemaValidationError(ValueError):
    """Raised when Brain output is structurally invalid (Phase 8 §4 stage 1)."""


def _validate_type(name: str, value: Any, expected: str, errors: list[str]) -> None:
    if expected == "object":
        if not isinstance(value, dict):
            errors.append(f"{name}: expected object, got {type(value).__name__}")
    elif expected == "array":
        if not isinstance(value, (list, tuple)):
            errors.append(f"{name}: expected array, got {type(value).__name__}")
    elif expected == "string":
        if not isinstance(value, str):
            errors.append(f"{name}: expected string, got {type(value).__name__}")


def validate_brain_output(data: Any) -> BrainOutput:
    """Validate a raw Brain-output dict against the contract schema.

    Raises :class:`SchemaValidationError` on the first structural problem so
    malformed/malicious model output can never reach the control plane.
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"brain output must be an object, got {type(data).__name__}")
    errors: list[str] = []
    for req in ("intent", "plan", "capability_requests", "completion_conditions",
                "confidence_state"):
        if req not in data:
            errors.append(f"missing required field: {req}")
    if errors:
        raise SchemaValidationError("; ".join(errors))

    intent = data["intent"]
    if not isinstance(intent, dict) or "confidence_state" not in intent:
        errors.append("intent.confidence_state is required")
    else:
        _validate_type("intent.domain", intent.get("domain", ""), "string", errors)
        _validate_type("intent.task", intent.get("task", ""), "string", errors)

    plan = data["plan"]
    if not isinstance(plan, dict):
        errors.append("plan must be an object")
    elif "steps" not in plan:
        errors.append("plan.steps is required")
    else:
        _validate_type("plan.summary", plan.get("summary", ""), "string", errors)
        steps = plan.get("steps")
        if not isinstance(steps, list):
            errors.append("plan.steps must be an array")
        else:
            for i, s in enumerate(steps):
                if not isinstance(s, dict):
                    errors.append(f"plan.steps[{i}] must be an object")
                    continue
                if not isinstance(s.get("id", ""), str) or not s.get("id"):
                    errors.append(f"plan.steps[{i}].id must be a non-empty string")
                if not isinstance(s.get("capability", ""), str) or not s.get("capability"):
                    errors.append(f"plan.steps[{i}].capability must be a non-empty string")

    cr = data["capability_requests"]
    if not isinstance(cr, list):
        errors.append("capability_requests must be an array")
    elif isinstance(cr, list):
        for i, c in enumerate(cr):
            if not isinstance(c, dict):
                errors.append(f"capability_requests[{i}] must be an object")
                continue
            if not isinstance(c.get("capability", ""), str) or not c.get("capability"):
                errors.append(f"capability_requests[{i}].capability must be a non-empty string")
            if not isinstance(c.get("args", {}), dict):
                errors.append(f"capability_requests[{i}].args must be an object")

    cc = data["completion_conditions"]
    if not isinstance(cc, list):
        errors.append("completion_conditions must be an array")
    elif isinstance(cc, list):
        for i, c in enumerate(cc):
            if not isinstance(c, dict) or not isinstance(c.get("type", ""), str):
                errors.append(f"completion_conditions[{i}].type must be a string")

    if not isinstance(data.get("confidence_state", ""), str):
        errors.append("confidence_state must be a string")
    elif data["confidence_state"] not in _CONFIDENCE_VALUES:
        errors.append(f"confidence_state {data['confidence_state']!r} not a valid ConfidenceState")

    if errors:
        raise SchemaValidationError("; ".join(errors))

    # Coerce into dataclasses.
    intent_cs = intent.get("confidence_state")
    intent_obj = BrainIntent(
        domain=str(intent.get("domain", "")),
        task=str(intent.get("task", "")),
        confidence=ConfidenceState(intent_cs) if intent_cs in _CONFIDENCE_VALUES
        else ConfidenceState.INSUFFICIENT_EVIDENCE,
    )
    steps_out = []
    for s in plan.get("steps", []) or []:
        steps_out.append(PlanStep(
            id=str(s.get("id", "")), capability=str(s.get("capability", "")),
            summary=str(s.get("summary", "")),
            args=dict(s.get("args", {}) or {}),
            depends_on=list(s.get("depends_on", []) or []),
        ))
    cr_out = []
    for c in cr:
        cr_out.append(CapabilityRequest(
            capability=str(c.get("capability", "")),
            args=dict(c.get("args", {}) or {}),
            reason=str(c.get("reason", "")),
            depends_on=list(c.get("depends_on", []) or []),
        ))
    cc_out = []
    for c in cc:
        cc_out.append(CompletionCondition(
            type=str(c.get("type", "")), target=str(c.get("target", "")),
            expected=c.get("expected"),
        ))
    cs = data["confidence_state"]
    try:
        cs_enum = ConfidenceState(cs)
    except ValueError:
        cs_enum = ConfidenceState.INSUFFICIENT_EVIDENCE
    return BrainOutput(
        intent=intent_obj,
        plan=Plan(summary=str(plan.get("summary", "")), steps=steps_out),
        capability_requests=cr_out,
        questions_for_user=list(data.get("questions_for_user", []) or []),
        completion_conditions=cc_out,
        confidence_state=cs_enum,
        model_ref=str(data.get("model_ref", "")),
        provenance=dict(data.get("provenance", {}) or {}),
        summary=str(data.get("summary", "")),
    )


def brain_output_schema() -> dict[str, Any]:
    """Return the JSON schema the control plane shows to the model backend."""
    return _BRAIN_OUTPUT_SCHEMA


def safe_parse_brain_json(text: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON extraction from model text. Returns None if unparseable.

    Never raises and never fabricates structure -- a non-JSON / partial response
    yields None so the caller can degrade honestly (Phase 8 §8 honesty).
    """
    if not text:
        return None
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    for fence in ("```json", "```"):
        start = stripped.find(fence)
        if start != -1:
            end = stripped.find("```", start + len(fence))
            payload = stripped[start + len(fence):end if end != -1 else len(stripped)]
            try:
                obj = json.loads(payload.strip())
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None


__all__ = [
    "ExecutionMode", "ConfidenceState", "AutonomyLevel", "PlanDecision",
    "BrainInput", "BrainOutput", "Plan", "PlanStep", "CapabilityRequest",
    "CompletionCondition", "BrainIntent",
    "SchemaValidationError", "validate_brain_output", "brain_output_schema",
    "safe_parse_brain_json",
]
