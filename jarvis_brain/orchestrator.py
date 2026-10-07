"""Brain Orchestrator — the controlled PLAN→EXECUTE→OBSERVE→VERIFY→REASON→REPLAN
loop (Phase 8 §5-6, §17, §19-21, §25-30).

This is the *integration glue*.  It reuses, and never rebuilds:

    * BrainClient / ModelBrainAdapter    (reasoning + honesty gate)
    * ToolRegistry.invoke                (authorization + secret-scrubbing boundary)
    * PlanValidator                      (6-stage plan gate)
    * BrainControlProtocol               (ordered state machine)
    * TaskManager / Task / TaskState      (durability + resume)
    * VerificationEngine                (verification interpretation)
    * ContextEngine                     (bounded context packs)
    * TaskBudget                        (hard limits)

The Brain NEVER touches credentials, shell, DB, provider SDKs, or the
filesystem.  It may only *propose* capabilities; the control plane validates,
authorizes, and dispatches them through :class:`ToolRegistry`, which is the sole
authority for execution and for scrubbing results before they return to the
Brain.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .audit import BrainAudit, EventType
from .budget import TaskBudget, TaskBudgetExceeded
from .contract import (
    AutonomyLevel, BrainInput, BrainIntent, BrainOutput, CapabilityRequest,
    ConfidenceState, ExecutionMode, Plan, PlanDecision, PlanStep,
)
from .context_engine import ContextEngine, ContextLimits
from .plan_validator import PlanValidator, ValidationResult
from .protocol import BrainControlProtocol, ProtocolViolationError
from research_engine.models import VerificationStatus, ToolResult
from research_engine.tool_registry import ToolRegistry, ToolContext, scrub_secrets


@dataclass
class TaskResult:
    """Final outcome of a Brain-driven task run."""

    task_id: str
    status: str = "UNKNOWN"  # COMPLETED | FAILED | CANCELLED | BUDGET_EXCEEDED
    confidence_state: ConfidenceState = ConfidenceState.INSUFFICIENT_EVIDENCE
    summary: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    completion_condition_met: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "status": self.status,
            "confidence_state": self.confidence_state.value,
            "summary": self.summary, "evidence_count": len(self.evidence),
            "audit_events": len(self.audit),
            "provenance": dict(self.provenance), "cost": dict(self.cost),
            "completion_condition_met": self.completion_condition_met,
        }


# A callable that decides whether a proposed (possibly destructive) step may
# run without explicit approval.  Signature: (capability_ids, autonomy) -> bool.
ApprovalGate = Any


def _approval_req(ids: list[str]) -> dict[str, Any]:
    return {"capabilities": list(ids)}


def _record_plan_proposal(audit: BrainAudit, output: BrainOutput) -> None:
    steps = output.plan.steps or [
        PlanStep(
            id=request.capability,
            capability=request.capability,
            summary=request.reason or request.capability,
            args=request.args,
            depends_on=request.depends_on,
        )
        for request in output.capability_requests
    ]
    audit.record(
        "BRAIN_PLAN_PROPOSED",
        detail=output.plan.summary,
        provenance={
            "model": output.model_ref,
            "capabilities": [
                {
                    "step_id": step.id,
                    "capability": step.capability,
                    "summary": step.summary,
                    "depends_on": list(step.depends_on),
                }
                for step in steps
            ],
        },
    )


class BrainOrchestrator:
    """Coordinates the Brain ↔ Control Plane controlled loop."""

    def __init__(
        self,
        brain_adapter: Any,
        tool_registry: ToolRegistry,
        plan_validator: PlanValidator,
        *,
        context_engine: Optional[ContextEngine] = None,
        task_manager: Any = None,          # Phase 5 TaskManager (optional, reused)
        verifier: Any = None,              # research_engine.VerificationEngine
        approval_gate: Optional[ApprovalGate] = None,
        cancel_token: Optional[asyncio.Event] = None,
        budget: Optional[TaskBudget] = None,
        context_limits: Optional[ContextLimits] = None,
        conversation_id: Optional[str] = None,
        user_id: str = "anonymous",
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
        audit_callback: Any = None,
    ):
        self.brain_adapter = brain_adapter
        self.registry = tool_registry
        self.validator = plan_validator
        self.context_engine = context_engine or ContextEngine(context_limits)
        self.task_manager = task_manager
        self.verifier = verifier
        self.approval_gate = approval_gate
        self.cancel_token = cancel_token
        self._default_budget = budget or TaskBudget()
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.permissions = permissions
        self.principal = principal
        self.audit_callback = audit_callback

    # ------------------------------------------------------------------ #
    async def run(
        self,
        request: str,
        *,
        execution_mode: str = ExecutionMode.ONLINE.value,
        autonomy: str = AutonomyLevel.AUTONOMOUS.value,
        task_id: Optional[str] = None,
        budget: Optional[TaskBudget] = None,
        task_state: Optional[dict[str, Any]] = None,
    ) -> TaskResult:
        """Execute the controlled loop to completion (or a terminal state)."""
        task_id = task_id or f"brain-{uuid.uuid4().hex[:10]}"
        budget = budget or self._default_budget
        self.cancel_token = self.cancel_token or asyncio.Event()
        audit = BrainAudit(task_id=task_id, on_record=self.audit_callback)
        protocol = BrainControlProtocol(task_id, budget=budget, audit=audit)
        task = self._create_task(task_id, request, execution_mode, autonomy)

        # --- PLAN: build bounded context + get Brain proposal --------------
        pack = self.context_engine.build(
            request, execution_mode=execution_mode,
            task_state=task_state or self._task_state_snapshot(task),
            capability_query=request,
        )
        self._set_task_state(task, "PLANNING")
        protocol.emit(EventType.PLAN_CREATED, detail="brain plan proposed",
                      provenance={"adapter": type(self.brain_adapter).__name__,
                                  "conversation_id": self.conversation_id})

        brain_input = BrainInput(
            request=request,
            context=pack.to_dict(),
            available_capabilities=pack.available_capabilities,
            execution_mode=execution_mode,
            task_state=task_state or self._task_state_snapshot(task),
            relevant_artifacts=pack.relevant_artifacts,
            user_id=self.user_id,
            autonomy=autonomy,
            budget=budget,
        )
        brain_output = await self._brain_propose(brain_input, budget, audit, task_id)
        _record_plan_proposal(audit, brain_output)

        # Honest gate: no capability proposals + cannot-proceed confidence →
        # stop and ask the user rather than fabricate a plan.
        if not brain_output.capability_requests:
            if brain_output.confidence_state in (
                    ConfidenceState.ASK_USER, ConfidenceState.INSUFFICIENT_EVIDENCE,
                    ConfidenceState.MISSING_INFORMATION,
                    ConfidenceState.AMBIGUOUS_REQUEST):
                protocol.emit(EventType.QUESTION_ASKED,
                              detail="Brain needs user input before planning")
                return self._terminal(task_id, "FAILED", audit, budget,
                                      brain_output.summary or "needs user input",
                                      brain_output.confidence_state,
                                      completion_cond="")
            # Empty proposal with sufficient confidence is structurally odd →
            # still cannot execute nothing.
            protocol.emit(EventType.PLAN_REJECTED,
                          detail="Brain produced a plan with no capability requests")
            return self._terminal(task_id, "FAILED", audit, budget,
                                  "plan with no executable steps",
                                  ConfidenceState.INSUFFICIENT_EVIDENCE)

        # --- VALIDATE → AUTHORIZE ------------------------------------------
        decision = self._run_validation(
            brain_output, execution_mode=execution_mode, autonomy=autonomy)
        protocol.emit(EventType.PLAN_VALIDATED,
                      detail=f"plan validated: {decision.decision.value}",
                      provenance={"decision": decision.decision.value,
                                  "authorized": decision.authorized_capabilities})

        authorized, approved = await self._authorize(
            decision, protocol, audit, autonomy
        )
        if not approved:
            if self.cancel_token.is_set():
                self._cancel_task(task)
                return self._terminal(task_id, "CANCELLED", audit, budget,
                                      "cancelled by user", ConfidenceState.ASK_USER)
            return self._terminal(task_id, "FAILED", audit, budget,
                                  "plan denied by authorization gate",
                                  ConfidenceState.ASK_USER)
        if not authorized:
            # Approved but nothing executable (all destructive/skipped in
            # autonomous) — do NOT fabricate completion.
            protocol.emit(EventType.PLAN_REJECTED,
                          detail="no capability remained executable after authorization")
            return self._terminal(task_id, "FAILED", audit, budget,
                                  "no executable capability after authorization",
                                  ConfidenceState.INSUFFICIENT_EVIDENCE)

        protocol.emit(EventType.PLAN_AUTHORIZED,
                      detail="execution authorized",
                      provenance={"autonomy": autonomy,
                                  "authorized": authorized})

        # Filter the proposal to the authorized capability set only.
        brain_output = self._filter_to_authorized(brain_output, authorized)

        # --- EXECUTE → OBSERVE → VERIFY → REASON → REPLAN ------------------
        evidence: list[ToolResult] = []
        completed_cond = ""
        final_confidence = brain_output.confidence_state

        try:
            while True:
                self._check_cancelled()
                protocol.emit(EventType.EXECUTION_STARTED,
                              detail="executing capability requests")

                step_results = await self._execute_plan(
                    brain_output, brain_input, budget, audit, task_id,
                    execution_mode, evidence)
                evidence.extend(step_results)
                for r in step_results:
                    protocol.emit(EventType.EXECUTION_RESULT,
                                  detail=f"{r.name} success={r.success}",
                                  capability=r.name, success=r.success,
                                  cost={"duration_ms": getattr(r, "duration_ms", 0)})

                # VERIFY against completion conditions using real evidence.
                completed_cond = self._evaluate_completion(
                    brain_output.completion_conditions, evidence)
                if completed_cond:
                    protocol.emit(EventType.VERIFICATION_RESULT,
                                  detail=f"completion condition satisfied: {completed_cond}",
                                  success=True)
                    protocol.emit(EventType.TASK_COMPLETED,
                                  detail="completion condition satisfied by evidence")
                    final_confidence = ConfidenceState.SUFFICIENT_INFORMATION
                    break

                # REASON → replan or stop honestly.
                reason_to_replan = self._should_replan(
                    brain_output, step_results, budget)
                if not reason_to_replan["replan"]:
                    protocol.emit(EventType.VERIFICATION_RESULT,
                                  detail=f"cannot continue: {reason_to_replan['why']}")
                    final_confidence = reason_to_replan.get(
                        "confidence", ConfidenceState.INSUFFICIENT_EVIDENCE)
                    return self._terminal(task_id, "FAILED", audit, budget,
                                          f"halt: {reason_to_replan['why']}",
                                          final_confidence)

                # REPLAN (bounded) — feed back SANITIZED results only.
                protocol.emit(EventType.REASSESSMENT,
                              detail=f"brain reassessment: {reason_to_replan['why']}")
                try:
                    brain_input = self._reassessment_input(
                        brain_input, evidence, step_results,
                        execution_mode, autonomy, budget)
                    brain_output = await self._brain_propose(
                        brain_input, budget, audit, task_id)
                    _record_plan_proposal(audit, brain_output)
                except TaskBudgetExceeded:
                    return self._terminal(task_id, "BUDGET_EXCEEDED", audit,
                                          budget, "max_replans exceeded during reassessment",
                                          final_confidence)

                # Empty replan → ask/stop honestly (no fabrication).
                if not brain_output.capability_requests:
                    return self._terminal(task_id, "FAILED", audit, budget,
                                          "replan produced no executable capability",
                                          brain_output.confidence_state)

                decision = self._run_validation(
                    brain_output, execution_mode=execution_mode, autonomy=autonomy)
                protocol.emit(EventType.PLAN_VALIDATED,
                              detail=f"replan validated: {decision.decision.value}")
                if decision.decision == PlanDecision.PLAN_BLOCKED and not decision.authorized_capabilities:
                    return self._terminal(task_id, "FAILED", audit, budget,
                                          "replan blocked — capability unavailable",
                                          final_confidence)
                authorized, approved = await self._authorize(
                    decision, protocol, audit, autonomy
                )
                if not approved:
                    if self.cancel_token.is_set():
                        self._cancel_task(task)
                        return self._terminal(
                            task_id, "CANCELLED", audit, budget,
                            "cancelled by user", ConfidenceState.ASK_USER,
                        )
                    return self._terminal(
                        task_id, "FAILED", audit, budget,
                        "replan denied by authorization gate",
                        ConfidenceState.ASK_USER,
                    )
                if not authorized:
                    return self._terminal(task_id, "FAILED", audit, budget,
                                          "replan not authorized", final_confidence)
                brain_output = self._filter_to_authorized(brain_output,
                                                          authorized)
                # Re-authorize the replan before re-executing: the protocol
                # requires PLAN_AUTHORIZED -> EXECUTION_STARTED (Phase 8 §5).
                protocol.emit(EventType.PLAN_AUTHORIZED,
                              detail="replan re-authorized for re-execution",
                              provenance={"autonomy": autonomy,
                                          "authorized": authorized})

        except TaskBudgetExceeded as e:
            return self._terminal(task_id, "BUDGET_EXCEEDED", audit, budget,
                                  str(e), final_confidence)
        except ProtocolViolationError as e:
            return self._terminal(task_id, "FAILED", audit, budget, str(e),
                                  final_confidence)
        except asyncio.CancelledError:
            self._cancel_task(task)
            return self._terminal(task_id, "CANCELLED", audit, budget,
                                  "cancelled by interrupt", final_confidence)
        except Exception as e:  # noqa: BLE001 - last-resort honesty
            return self._terminal(task_id, "FAILED", audit, budget,
                                  f"orchestrator error: {e}", final_confidence)

        return self._build_result(task_id, "COMPLETED", audit, budget,
                                  evidence, final_confidence, completed_cond)

    # ------------------------------------------------------------------ #
    async def _brain_propose(
        self, brain_input: BrainInput, budget: TaskBudget,
        audit: BrainAudit, task_id: str,
    ) -> BrainOutput:
        try:
            output = await self.brain_adapter.propose(brain_input, budget)
        except TaskBudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - degrade honestly
            audit.record(EventType.DEGRADED,
                         detail=f"brain adapter error: {type(e).__name__}: {e}")
            output = self._honest_empty_proposal(brain_input, str(e))
        if not output.capability_requests and output.confidence_state == \
                ConfidenceState.ASK_USER:
            return output
        return output

    @staticmethod
    def _honest_empty_proposal(brain_input: BrainInput, err: str) -> BrainOutput:
        return BrainOutput(
            intent=BrainIntent(
                domain=brain_input.execution_mode,
                task=brain_input.request,
                confidence=ConfidenceState.ASK_USER,
            ),
            plan=Plan(summary="Brain unavailable — no plan proposed."),
            capability_requests=[], completion_conditions=[],
            confidence_state=ConfidenceState.ASK_USER,
            questions_for_user=["The Brain could not produce a plan at this time."],
            model_ref="unavailable",
            provenance={"adapter": "error-fallback", "reason": "brain_adapter_error"},
            summary=f"Brain proposal failed: {err}",
        )

    # ------------------------------------------------------------------ #
    # Execute a plan's capability requests through the auth+scrub boundary.
    # ------------------------------------------------------------------ #
    async def _execute_plan(
        self, brain_output: BrainOutput, brain_input: BrainInput,
        budget: TaskBudget, audit: BrainAudit, task_id: str,
        execution_mode: str, evidence: list[ToolResult],
    ) -> list[ToolResult]:
        ctx = self._tool_context()
        ordered = self._order_requests(brain_output.capability_requests)
        results: list[ToolResult] = []
        for req in ordered:
            if self.cancel_token.is_set():
                raise asyncio.CancelledError("cancelled between steps")
            audit.record(
                "CAPABILITY_STARTED",
                detail="capability dispatch started",
                capability=req.capability,
            )
            result = await self._execute_with_retries(
                req, ctx, budget, audit, execution_mode)
            results.append(result)
            budget.spend_tool_call()
            budget.account_result(result)
            audit.record(
                "CAPABILITY_COMPLETED" if result.success else "CAPABILITY_FAILED",
                detail=("capability returned successfully" if result.success
                        else _safe_err(result)),
                capability=req.capability,
                success=result.success,
                cost={"duration_ms": getattr(result, "duration_ms", 0)},
            )
            if not result.success:
                audit.record(EventType.PROVIDER_UNAVAILABLE,
                             capability=req.capability,
                             detail=f"{req.capability} failed: {_safe_err(result)}")
                # Stop this plan; the reassess loop will propose an alternate.
                break
        return results

    async def _execute_with_retries(
        self, req: CapabilityRequest, ctx: ToolContext, budget: TaskBudget,
        audit: BrainAudit, execution_mode: str,
    ) -> ToolResult:
        """Execute a capability request, retrying transient failures only.

        Non-transient failures (UNAVAILABLE / NOT_CONFIGURED / DENIED /
        TOOL_NOT_REGISTERED / BLOCKED) are NOT retried — they surface the
        real provider state so the reassess loop can route around them.
        """
        last: Optional[ToolResult] = None
        for attempt in range(1, budget.max_retries + 2):
            try:
                result = await self.registry.invoke(req.capability, dict(req.args), ctx)
            except Exception as e:  # noqa: BLE001
                result = ToolResult(tool_id=req.capability, name=req.capability,
                                    success=False, error=f"invoke_error: {e}",
                                    duration_ms=0)
            last = result
            if result.success:
                return result
            err = (result.error or "").upper()
            if any(k in err for k in ("UNAVAILABLE", "NOT_CONFIGURED", "DENIED",
                                      "TOOL_NOT_REGISTERED", "BLOCKED")):
                return result
            # Transient — consume a retry budget unit and try again.
            try:
                budget.note_retry()
            except TaskBudgetExceeded:
                return result
        return last  # type: ignore[return-value]

    def _order_requests(self, reqs: list[CapabilityRequest]) -> list[CapabilityRequest]:
        """Topological order of capability_requests by their depends_on (refs other
        request ``capability`` ids).  Phase 8 §4.3 dependency ordering."""
        by_id = {r.capability: r for r in reqs}
        order: list[CapabilityRequest] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(r: CapabilityRequest) -> None:
            if r.capability in visited:
                return
            if r.capability in visiting:
                return  # cycle — break it to avoid infinite recursion
            visiting.add(r.capability)
            for dep in r.depends_on:
                d = by_id.get(dep)
                if d is not None:
                    visit(d)
            visiting.discard(r.capability)
            visited.add(r.capability)
            order.append(r)

        for r in reqs:
            visit(r)
        return order

    # ------------------------------------------------------------------ #
    # Completion evaluation — EVIDENCE ONLY, never model self-declaration.
    # ------------------------------------------------------------------ #
    def _evaluate_completion(
        self, conditions: list[Any], evidence: list[ToolResult],
    ) -> str:
        if not conditions:
            return ""
        for cond in conditions:
            ctype = getattr(cond, "type", "") or ""
            if ctype == "artifact_created" and any(
                    r.success and getattr(r, "artifacts", None) for r in evidence):
                return ctype
            if ctype == "answer_generated" and any(
                    r.success and (getattr(r, "result", None) or "") for r in evidence):
                return ctype
            if ctype == "evidence_sufficient" and any(r.success for r in evidence):
                return ctype if len([r for r in evidence if r.success]) >= 1 else ""
            if ctype == "tests_passed" and any(
                    r.success and ("passed" in str(getattr(r, "result", "")).lower()
                                   or self._exit_zero(r)) for r in evidence):
                return ctype
            if ctype == "verification_passed":
                if self._verification_verified(evidence):
                    return ctype
        return ""

    def _exit_zero(self, r: ToolResult) -> bool:
        m = getattr(r, "metrics", None) or {}
        return bool(isinstance(m, dict) and m.get("exit_code") == 0)

    def _verification_verified(self, evidence: list[ToolResult]) -> bool:
        if self.verifier is None:
            return bool(evidence and all(r.success for r in evidence))
        try:
            claim = "task requirements satisfied"
            collected = [str(getattr(r, "result", "") or getattr(r, "error", ""))
                         for r in evidence]
            status, _, _ = self.verifier.verify_claim(claim, collected, [])
            return status == VerificationStatus.VERIFIED
        except Exception:  # noqa: BLE001
            return bool(evidence and all(r.success for r in evidence))

    # ------------------------------------------------------------------ #
    def _should_replan(self, brain_output: BrainOutput,
                       step_results: list[ToolResult],
                       budget: TaskBudget) -> dict[str, Any]:
        """Bounded replanning decision (Phase 8 §6)."""
        if not step_results:
            return {"replan": False, "why": "no capability results observed",
                    "confidence": ConfidenceState.INSUFFICIENT_EVIDENCE}
        all_ok = all(r.success for r in step_results)
        if all_ok:
            if budget.exhausted_replans:
                return {"replan": False,
                        "why": "steps succeeded but no completion condition met "
                               "and replans exhausted",
                        "confidence": ConfidenceState.CONFLICTING_EVIDENCE}
            return {"replan": True,
                    "why": "steps succeeded, completion not yet verified",
                    "confidence": ConfidenceState.INSUFFICIENT_EVIDENCE}
        if budget.exhausted_replans:
            return {"replan": False, "why": "step failed and replans exhausted",
                    "confidence": ConfidenceState.CONFLICTING_EVIDENCE}
        return {"replan": True, "why": "step failed, proposing alternate path",
                "confidence": ConfidenceState.CONFLICTING_EVIDENCE}

    def _reassessment_input(
        self, brain_input: BrainInput, evidence: list[ToolResult],
        step_results: list[ToolResult],
        execution_mode: str, autonomy: str, budget: TaskBudget,
    ) -> BrainInput:
        # The Brain may only see SANITIZED model-view results (Phase 8 §5).
        # The ToolRegistry already scrubs result/error, but we defend-in-depth
        # here too: orchestration-built error results (e.g. invoke_error) and
        # artifact payloads are scrubbed again so a secret-shaped exception
        # message can never reach the model.
        sanitized = [self._sanitize_result_for_brain(r)
                     for r in (evidence + step_results)]
        brain_input.task_state = {
            "last_request": brain_input.request,
            "observed_results": sanitized,
            "replan": True,
            "iteration": budget.iterations + 1,
        }
        brain_input.context = {
            **brain_input.context,
            "reassessment_note": "Previous attempt did not satisfy completion "
                                 "conditions.",
        }
        return brain_input

    @staticmethod
    def _sanitize_result_for_brain(result: ToolResult) -> dict[str, Any]:
        """Return the model-safe view of a ToolResult, scrubbed of secrets."""
        if hasattr(result, "to_model_view"):
            view = result.to_model_view()
        else:
            view = {}
        for key in ("result", "error"):
            val = view.get(key)
            if isinstance(val, str):
                scrubbed, _ = scrub_secrets(val)
                view[key] = scrubbed
        arts = view.get("artifacts")
        if isinstance(arts, list):
            view["artifacts"] = [BrainOrchestrator._scrub_artifact(a)
                                 for a in arts]
        return view

    @staticmethod
    def _scrub_artifact(a: Any) -> Any:
        if isinstance(a, dict):
            return {k: BrainOrchestrator._scrub_artifact(v) for k, v in a.items()}
        if isinstance(a, list):
            return [BrainOrchestrator._scrub_artifact(x) for x in a]
        if isinstance(a, str):
            s, _ = scrub_secrets(a)
            return s
        return a

    # ------------------------------------------------------------------ #
    def _filter_to_authorized(self, brain_output: BrainOutput,
                               authorized: list[str]) -> BrainOutput:
        if not authorized:
            return brain_output
        filtered = BrainOutput(
            intent=brain_output.intent,
            plan=Plan(summary=brain_output.plan.summary,
                      steps=[s for s in brain_output.plan.steps
                             if s.capability in authorized]),
            capability_requests=[r for r in brain_output.capability_requests
                                 if r.capability in authorized],
            questions_for_user=brain_output.questions_for_user,
            completion_conditions=brain_output.completion_conditions,
            confidence_state=brain_output.confidence_state,
            model_ref=brain_output.model_ref,
            provenance=brain_output.provenance,
            summary=brain_output.summary,
        )
        return filtered

    # ------------------------------------------------------------------ #
    def _tool_context(self) -> ToolContext:
        perms = self.permissions
        if perms is None:
            try:
                from research_engine.tool_registry import resolve_permissions
                perms = resolve_permissions(self.user_id, None, self.principal)
            except Exception:  # noqa: BLE001
                perms = set()
        return ToolContext(
            user_id=self.user_id, permissions=perms or set(),
            principal=self.principal or {}, request_id=str(uuid.uuid4()),
            budgets=None, research_dir=None,
        )

    # ------------------------------------------------------------------ #
    def _run_validation(
        self, brain_output: BrainOutput,
        *, execution_mode: str, autonomy: str,
    ) -> ValidationResult:
        return self.validator.validate(
            brain_output.to_dict(),
            user_id=self.user_id, permissions=self.permissions,
            principal=self.principal,
            execution_mode=execution_mode, autonomy=autonomy,
        )

    async def _authorize(
        self, decision: ValidationResult, protocol: BrainControlProtocol,
        audit: BrainAudit, autonomy: str,
    ) -> tuple[list[str], bool]:
        if decision.decision == PlanDecision.ACCEPTED:
            return decision.authorized_capabilities, True
        if decision.decision == PlanDecision.HUMAN_APPROVAL:
            protocol.emit(
                EventType.HUMAN_APPROVAL,
                detail="explicit user authorization required",
                provenance={"capabilities": decision.needs_approval_for},
            )
            if self.approval_gate is None:
                return [], False
            approved = self.approval_gate(
                _approval_req(decision.needs_approval_for), autonomy
            )
            if hasattr(approved, "__await__"):
                approved = await approved
            if approved:
                # Approved confirmation-gated capabilities become executable.
                auth = list(decision.authorized_capabilities) + \
                    list(decision.needs_approval_for)
                return auth, True
            return [], False
        if decision.decision in (PlanDecision.DENIED, PlanDecision.PLAN_REJECTED,
                                 PlanDecision.PLAN_BLOCKED):
            return [], False
        # AUTHORIZATION_REQUIRED / generic
        if self.approval_gate is not None:
            approved = self.approval_gate(_approval_req(["authorization"]), autonomy)
            if hasattr(approved, "__await__"):
                approved = await approved
            return (decision.authorized_capabilities, True) if approved else ([], False)
        return [], False

    # ------------------------------------------------------------------ #
    # TaskManager (Phase 5) integration — best-effort; never blocks.
    # ------------------------------------------------------------------ #
    def _create_task(self, task_id: str, request: str,
                     execution_mode: str, autonomy: str) -> Optional[Any]:
        if self.task_manager is None:
            return None
        try:
            from backend.control_plane.task_runtime import Task, TaskType
            return Task(
                task_id=task_id, name=request[:80], description=request,
                task_type=TaskType.FROM_USER, owner=self.user_id,
                principal=self.principal or {}, requested_inputs={},
            )
        except Exception:  # noqa: BLE001
            return None

    def _set_task_state(self, task: Optional[Any], state: str) -> None:
        if task is not None:
            try:
                task.state = state
            except Exception:  # noqa: BLE001
                pass

    def _cancel_task(self, task: Optional[Any]) -> None:
        if task is not None:
            try:
                if hasattr(task, "cancel"):
                    task.cancel()
            except Exception:  # noqa: BLE001
                pass

    def _task_state_snapshot(self, task: Optional[Any]) -> dict[str, Any]:
        if task is None:
            return {}
        snap: dict[str, Any] = {}
        for f in ("task_id", "state", "status", "retry_count", "current_step"):
            if hasattr(task, f):
                snap[f] = getattr(task, f)
        return snap

    def _check_cancelled(self) -> None:
        if self.cancel_token is not None and self.cancel_token.is_set():
            raise asyncio.CancelledError("cancelled by interrupt")

    def _terminal(self, task_id: str, status: str, audit: BrainAudit,
                  budget: TaskBudget, detail: str,
                  confidence: ConfidenceState,
                  completion_cond: str = "") -> TaskResult:
        """Record exactly ONE terminal audit event (by status) and return.

        Callers must NOT pre-emit the same terminal event — this is the single
        sink for FAILED / COMPLETED / CANCELLED / BUDGET_EXCEEDED.
        """
        event_map = {
            "FAILED": EventType.TASK_FAILED,
            "COMPLETED": EventType.TASK_COMPLETED,
            "CANCELLED": EventType.TASK_CANCELLED,
            "BUDGET_EXCEEDED": EventType.BUDGET_EXCEEDED,
        }
        audit.record(event_map.get(status, EventType.TASK_FAILED), detail=detail)
        return TaskResult(
            task_id=task_id, status=status, confidence_state=confidence,
            summary=detail, audit=audit.timeline(), provenance={},
            cost=budget.spent(), completion_condition_met=completion_cond,
        )

    def _build_result(
        self, task_id: str, status: str, audit: BrainAudit, budget: TaskBudget,
        evidence: list[ToolResult], confidence: ConfidenceState,
        completion_cond: str,
    ) -> TaskResult:
        return TaskResult(
            task_id=task_id, status=status, confidence_state=confidence,
            summary=audit.explanation(confidence),
            evidence=[r.to_model_view() if hasattr(r, "to_model_view") else
                      {"name": getattr(r, "name", ""), "success": r.success}
                      for r in evidence],
            audit=audit.timeline(), provenance={},
            cost=budget.spent(), completion_condition_met=completion_cond,
        )

    # ------------------------------------------------------------------ #
    def run_sync(self, request: str, **kw: Any) -> TaskResult:
        """Blocking wrapper around :meth:`run` (for sync callers/tests)."""
        return asyncio.run(self.run(request, **kw))


def _safe_err(result: ToolResult) -> str:
    return (result.error or result.result or "")[:120]


__all__ = ["BrainOrchestrator", "TaskResult", "ApprovalGate"]
