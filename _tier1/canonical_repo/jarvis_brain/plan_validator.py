"""Plan Validation pipeline (Phase 8 §4).

Every Brain-proposed plan must pass, in order::

    schema validation            -> validate_brain_output (Phase 8 §4 stage 1)
    capability existence         -> capability id is registered
    input/output compatibility   -> args satisfy the tool's JSON schema
    permission requirements      -> caller holds the capability's required_permissions
    risk assessment              -> risk_level vs autonomy; destructive -> HUMAN_APPROVAL
    execution-mode compatibility -> offline mode may only use supports_offline caps
    dependency validation        -> step depends_on must resolve + be acyclic

Invalid plans are REJECTED, unauthorized ones map to AUTHORIZATION_REQUIRED /
DENIED, unavailable ones map to PLAN_BLOCKED.  A malformed plan can never reach
the ToolRegistry / control plane.

This module performs NO network/credential/host I/O. It delegates authorization
to the *existing* ``ToolRegistry.authorize`` boundary and never sees secrets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .contract import (
    BrainOutput, PlanDecision, SchemaValidationError,
    AutonomyLevel, ExecutionMode, validate_brain_output,
)
from research_engine.tool_registry import ToolRegistry

# jsonschema is optional: used for args-shape checks when present. The contract's
# own validate_brain_output always provides a hard structural gate regardless.
try:  # pragma: no cover - import guard
    import jsonschema as _jsonschema  # type: ignore
    _HAS_JSONSCHEMA = True
except Exception:  # noqa: BLE001
    _jsonschema = None  # type: ignore
    _HAS_JSONSCHEMA = False


@dataclass
class PlanIssue:
    stage: str
    severity: str  # "reject" | "block" | "deny" | "approve"
    message: str
    capability: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "severity": self.severity,
                "message": self.message, "capability": self.capability}


@dataclass
class ValidationResult:
    decision: PlanDecision
    issues: list[PlanIssue] = field(default_factory=list)
    authorized_capabilities: list[str] = field(default_factory=list)
    denied_capabilities: list[str] = field(default_factory=list)
    needs_approval_for: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)  # e.g. ["human_confirmation"]

    def accept(self) -> bool:
        return self.decision == PlanDecision.ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "issues": [i.to_dict() for i in self.issues],
            "authorized_capabilities": list(self.authorized_capabilities),
            "denied_capabilities": list(self.denied_capabilities),
            "needs_approval_for": list(self.needs_approval_for),
            "requires": list(self.requires),
        }


# Capabilities whose execution is considered destructive / high-risk and so
# always requires explicit human approval, regardless of autonomy level.
_DESTRUCTIVE = {
    "sandbox_run", "documents.ingest", "data.ingest", "data.export",
    "cloud.execution_mode", "remote.compute.verify", "docker.remote.containers",
}


class PlanValidator:
    """The single authority that gates a Brain proposal before execution."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    # ------------------------------------------------------------------ #
    def validate(
        self,
        raw_output: Any,
        *,
        user_id: str = "anonymous",
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
        execution_mode: str = ExecutionMode.ONLINE.value,
        autonomy: str = AutonomyLevel.AUTONOMOUS.value,
    ) -> ValidationResult:
        issues: list[PlanIssue] = []
        authorized: list[str] = []
        hard_denied: list[str] = []        # authorization denied (security-first)
        blocked: list[str] = []            # unavailable / mode-incompatible
        needs_approval: list[str] = []     # destructive or confirmation-gated
        rejected: list[str] = []           # schema / structural / nonexistent

        # ---- Stage 1: schema validation ---------------------------------
        try:
            output: BrainOutput = validate_brain_output(raw_output)
        except SchemaValidationError as e:
            return ValidationResult(
                PlanDecision.PLAN_REJECTED,
                [PlanIssue("schema", "reject", f"malformed brain output: {e}")],
            )

        described = {d["name"]: d for d in self.registry.describe()}
        contracts = self._contracts()

        for req in output.capability_requests:
            cap = req.capability
            stage = "capability"

            # Stage 2: capability existence
            if cap not in described:
                issues.append(PlanIssue(stage, "reject",
                                        f"capability {cap!r} is not registered", cap))
                rejected.append(cap)
                continue

            tool = self.registry._tools.get(cap)
            desc = described[cap]

            # Stage 3: input/output compatibility (args vs schema)
            if not self._args_match_schema(req.args, desc.get("parameters")):
                issues.append(PlanIssue(stage, "reject",
                                        f"args for {cap!r} do not match schema", cap))
                rejected.append(cap)
                continue

            # Stage 2b: availability (real capability existence check)
            contract = contracts.get(cap)
            avail = contract.get("availability", "UNKNOWN") if contract else "UNKNOWN"
            if avail not in {"AVAILABLE", "DEGRADED"}:
                issues.append(PlanIssue(stage, "block",
                                        f"capability {cap!r} unavailable ({avail})", cap))
                blocked.append(cap)
                continue

            # Stage 4: permission requirements (existing authz boundary)
            status, reason = self._permission_check(
                cap, tool, user_id, permissions, principal)
            if status == "deny":
                issues.append(PlanIssue(stage, "deny",
                                        f"{cap!r} authorization: {reason}", cap))
                hard_denied.append(cap)
                continue
            elif status == "needs_approval":
                needs_approval.append(cap)
                issues.append(PlanIssue(stage, "approve",
                                        f"{cap!r} requires human confirmation "
                                        f"({reason})", cap))
                continue

            # Stage 5: execution-mode compatibility (offline only)
            if execution_mode == ExecutionMode.OFFLINE.value and not (
                contract and contract.get("supports_offline")):
                issues.append(PlanIssue(stage, "block",
                                        f"{cap!r} not usable in OFFLINE mode", cap))
                blocked.append(cap)
                continue

            # Stage 6: risk assessment
            risk = desc.get("risk", "read")
            needs_human = cap in _DESTRUCTIVE
            if risk in ("network", "admin") and autonomy != AutonomyLevel.AUTONOMOUS.value:
                needs_human = True
            if needs_human:
                needs_approval.append(cap)
                issues.append(PlanIssue(stage, "approve",
                                        f"{cap!r} ({risk}) requires human approval "
                                        f"at autonomy={autonomy}", cap))
                continue

            authorized.append(cap)

        # ---- Stage 7: dependency validation (within the plan) ------------
        self._validate_dependencies(output, issues, rejected)

        # ---- Decision (spec §4 precedence) ------------------------------
        denied_all = hard_denied + blocked
        if rejected:
            decision = PlanDecision.PLAN_REJECTED
        elif hard_denied:
            decision = PlanDecision.DENIED
        elif blocked:
            decision = PlanDecision.PLAN_BLOCKED
        elif needs_approval:
            decision = PlanDecision.HUMAN_APPROVAL
        elif authorized:
            decision = PlanDecision.ACCEPTED
        else:
            decision = PlanDecision.PLAN_REJECTED

        return ValidationResult(
            decision, issues,
            authorized_capabilities=authorized,
            denied_capabilities=list(dict.fromkeys(denied_all)),
            needs_approval_for=needs_approval,
            requires=(["fix_plan"] if decision == PlanDecision.PLAN_REJECTED
                      else ["human_approval"] if decision == PlanDecision.HUMAN_APPROVAL
                      else ["authorization"] if decision == PlanDecision.DENIED
                      else ["routing"] if decision == PlanDecision.PLAN_BLOCKED
                      else []),
        )

    # ------------------------------------------------------------------ #
    def _contracts(self) -> dict[str, Any]:
        try:
            from research_engine.capability_contract import build_contracts
            from research_engine.capability_tools import build_capability_registry
            return build_contracts(build_capability_registry())
        except Exception:
            return {n: {"availability": "UNKNOWN", "supports_offline": False,
                        "required_permissions": []} for n in
                    (d["name"] for d in self.registry.describe())}

    def _args_match_schema(self, args: Any, schema: Any) -> bool:
        if not isinstance(args, dict):
            return False
        if not isinstance(schema, dict):
            return True
        if _HAS_JSONSCHEMA:
            try:
                _jsonschema.validate(instance=args, schema=schema)
                return True
            except Exception:
                return False
        # Manual fallback.
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in args:
                return False
        for k, v in args.items():
            prop = props.get(k)
            if prop is None:
                return False  # strict: no unknown args
            if not _matches_type(v, prop.get("type")):
                return False
        return True

    def _permission_check(
        self,
        cap: str, tool: Any, user_id: str,
        permissions: Optional[set[str]], principal: Optional[dict[str, Any]],
    ) -> tuple[str, str]:
        """Return a status tri-state: ok / needs_approval / deny.

        Reuses the EXISTING authorization boundary on ToolRegistry — the Brain
        never sees credentials or raw auth decisions.  A capability that merely
        *requires confirmation* is routed to needs_approval (the orchestrator's
        approval gate decides), never a hard deny.
        """
        ok, reason = self.registry.authorize(user_id, cap, permissions, principal)
        if ok:
            required = tuple(getattr(tool, "required_permissions", ()) or ())
            if required:
                from research_engine.tool_registry import resolve_permissions, permission_granted
                granted = resolve_permissions(user_id, permissions, principal)
                missing = [p for p in required if not permission_granted(granted, p)]
                if missing:
                    return "deny", "PERMISSION_DENIED:" + ",".join(missing)
            return "ok", reason
        # authorize refused — distinguish confirmation-gated from hard-denied.
        if "confirmation" in reason.lower() or "confirm" in reason.lower():
            return "needs_approval", reason
        return "deny", reason

    @staticmethod
    def _validate_dependencies(output: BrainOutput, issues: list[PlanIssue],
                               rejected: list[str]) -> None:
        seen_ids = {s.id for s in output.plan.steps}
        for req in output.capability_requests:
            for dep in req.depends_on:
                if dep not in seen_ids:
                    issues.append(PlanIssue("dependency", "reject",
                                            f"{req.capability!r} depends on unknown "
                                            f"step {dep!r}", req.capability))
                    if req.capability not in rejected:
                        rejected.append(req.capability)
        ids = [req.capability for req in output.capability_requests]
        if len(ids) != len(set(ids)):
            issues.append(PlanIssue("dependency", "reject",
                                    "duplicate capability requests in plan"))
            for dup in {c for c in ids if ids.count(c) > 1}:
                if dup not in rejected:
                    rejected.append(dup)


def _matches_type(value: Any, type_name: Optional[str]) -> bool:
    if type_name is None or value is None:
        return type_name is None
    mapping = {"string": str, "integer": int, "number": (int, float),
               "boolean": bool, "array": list, "object": dict}
    py = mapping.get(type_name)
    if py is None:
        return True
    if type_name == "integer" and isinstance(value, bool):
        return False
    if type_name == "number" and isinstance(value, bool):
        return False
    return isinstance(value, py)


__all__ = ["PlanValidator", "ValidationResult", "PlanIssue"]
