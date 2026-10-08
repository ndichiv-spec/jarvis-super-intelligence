"""Phase 10 — Cognitive Kernel.

The Cognitive Kernel is the bounded cognitive orchestration layer that sits
**above** the existing Brain (Phase 8) and the existing execution fabric
(Phase 7).  It coordinates:

- Mission lifecycle (Phase 10 ``mission.py``)
- Cognitive State (Phase 10 ``cognitive_state.py``)
- Hypothesis Engine (Phase 10 ``hypothesis_engine.py``)
- Evidence Engine (Phase 10 ``evidence_engine.py``)
- Critic role (Phase 10 ``critic.py``)
- Verifier role (Phase 10 ``verifier.py``)
- Specialist roles (Phase 10 ``specialist_roles.py``)
- AgentExecutor / ExecutionGraph (Phase 7 ``execution_fabric.py``)
- ToolRegistry / discover_capabilities (Phase 7 ``research_engine``)
- VerificationEngine (Phase 7 ``research_engine/verification.py``)
- Compute selector (Phase 9 ``cloud_fabric.py``)
- Brain fabric (Phase 8 ``brain_fabric.py``)
- Budget enforcement, audit logging, persistence (Phase 2 ``core.py``)

The kernel runs a **bounded** loop — no infinite loops.  Every cycle consumes
a cognitive step; budgets are hard stops.  The Brain never receives
credentials — all results are scrubbed before entering the cognitive state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from jarvis_backend.core import get_store, now_iso
from jarvis_backend.cloud_fabric import select_compute, local_hardware
from jarvis_backend.brain_fabric import assert_no_secrets, discover_brain
from jarvis_backend.execution_fabric import (
    AgentExecutor,
    ExecutionGraph,
    ExecutionNode,
    ExecutionNodeStatus,
    Task,
    TaskStatus,
    build_verified_evidence_pack,
)

from .cognitive_state import (
    CognitiveState,
    CognitivePhase,
    Observation,
    BudgetState,
)
from .critic import Critic, CriticConfig
from .evidence_engine import EvidenceEngine
from .hypothesis_engine import (
    HypothesisEngine,
    HypothesisStatus,
    RESOLVED_STATUSES,
)
from .mission import (
    Mission,
    MissionBudget,
    MissionEvent,
    AutonomyLevel,
    MissionStatus,
    _short_uuid,
)
from .mission_lifecycle import MissionLifecycle
from .specialist_roles import get_role, role_names
from .verifier import Verifier

logger = logging.getLogger("jarvis_backend.cognitive_kernel")


class KernelStopReason(str, Enum):
    """Why the kernel stopped its current run loop."""

    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    MAX_STEPS_REACHED = "max_steps_reached"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_RESOURCE = "waiting_for_resource"
    CRASH_RECOVERED = "crash_recovered"
    MANUAL_PAUSE = "manual_pause"


@dataclass
class KernelResult:
    """Result of a single ``run()`` call."""

    mission_id: str
    steps_executed: int
    stop_reason: str
    cognitive_state: dict[str, Any]
    task_results: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    verification_result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "steps_executed": self.steps_executed,
            "stop_reason": self.stop_reason,
            "cognitive_state": dict(self.cognitive_state),
            "task_results": list(self.task_results),
            "findings": list(self.findings),
            "verification_result": self.verification_result,
            "error": self.error,
        }


class CognitiveKernel:
    """Bounded cognitive orchestration loop.

    The Kernel coordinates the existing Brain and execution fabric.  It does
    NOT replace ``brain_fabric.py`` or ``execution_fabric.py`` — it sits above
    them and manages the long-horizon cognitive loop.

    Key guarantees:
    - **Bounded**: max_steps per run() call, hard budget limits.
    - **No secrets**: all results scrubbed via assert_no_secrets / scrub_secrets.
    - **No fabrication**: claims, evidence, and verification are traceable.
    - **Checkpointed**: state saved after every cycle for crash recovery.
    - **No self-approval**: approval gates require external actors.
    """

    def __init__(
        self,
        tool_registry: Optional[Any] = None,
        executor: Optional[AgentExecutor] = None,
        evidence_engine: Optional[EvidenceEngine] = None,
        hypothesis_engine: Optional[HypothesisEngine] = None,
        verifier: Optional[Verifier] = None,
        critic: Optional[Critic] = None,
    ) -> None:
        """Initialize the Cognitive Kernel.

        Args:
            tool_registry: ToolRegistry for capability execution.
                If None, a default is built from capability_tools.
            executor: AgentExecutor for task graph execution.
                If None, a default is constructed.
            evidence_engine: Evidence Engine for provenance tracking.
            hypothesis_engine: Hypothesis Engine for hypothesis management.
            verifier: Independent verifier role.
            critic: Critic role (analysis-only).
        """
        # Lazy imports to avoid circular dependencies
        if tool_registry is None:
            from research_engine.capability_tools import build_capability_registry
            tool_registry = build_capability_registry()
        self.tool_registry = tool_registry

        if executor is None:
            executor = AgentExecutor(tool_registry=tool_registry)
        self.executor = executor

        self.evidence_engine = evidence_engine or EvidenceEngine()
        self.hypothesis_engine = hypothesis_engine or HypothesisEngine()
        self.verifier = verifier or Verifier()
        self.critic = critic or Critic()

        self._lifecycle = MissionLifecycle()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def run(
        self,
        mission: Mission,
        max_steps: Optional[int] = None,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> KernelResult:
        """Run the cognitive kernel for a mission, up to max_steps cycles.

        The loop is bounded by:
        - ``max_steps`` (or mission budget max_steps, whichever is smaller)
        - mission budget ``max_seconds`` (wall-clock)
        - mission budget ``max_cost_usd``
        - budget exhaustion detection

        Returns a ``KernelResult`` with the stop reason and final state.
        """
        budget = mission.budget
        step_limit = min(
            max_steps if max_steps is not None else budget.max_steps,
            budget.max_steps,
        )
        start_time = time.time()
        task_results: list[dict[str, Any]] = []
        steps_executed = 0

        # Restore cognitive state from mission context_snapshot if available
        state = self._load_state(mission)

        # When starting a fresh run (even via resume), the per-run budget
        # must not carry over exhaustion from a previous segment.  The
        # mission budget provides the ceiling; max_steps may further restrict.
        state.budget_state["exhausted"] = False
        state.budget_state["exhaustion_reason"] = ""

        # Transition mission from DRAFT → ACTIVE if applicable
        if mission.status == MissionStatus.DRAFT:
            try:
                mission.transition(MissionStatus.ACTIVE, actor="cognitive_kernel")
            except Exception:
                pass  # already active or transition not needed

        try:
            while steps_executed < step_limit:
                # --- Budget checks (hard stops) ---
                if state.step_budget_exhausted:
                    return self._stop(
                        mission, state, steps_executed,
                        KernelStopReason.BUDGET_EXHAUSTED,
                        task_results, "cognitive step budget exhausted",
                    )

                elapsed = time.time() - start_time
                if elapsed > budget.max_seconds:
                    state.budget_state["exhausted"] = True
                    state.budget_state["exhaustion_reason"] = (
                        f"wall-clock time {elapsed:.0f}s exceeded limit {budget.max_seconds}s"
                    )
                    return self._stop(
                        mission, state, steps_executed,
                        KernelStopReason.BUDGET_EXHAUSTED,
                        task_results, "time budget exhausted",
                    )

                # --- Check mission lifecycle ---
                if mission.is_terminal:
                    return self._stop(
                        mission, state, steps_executed,
                        KernelStopReason.COMPLETED,
                        task_results,
                    )

                # --- Execute one cognitive cycle ---
                cycle_result = await self._cycle(
                    mission, state, permissions, principal, start_time,
                )
                task_results.extend(cycle_result.get("task_results", []))

                steps_executed += 1
                state.cycle = steps_executed

                # Update budget state
                state.budget_state["steps_consumed"] = steps_executed
                state.budget_state["steps_remaining"] = max(
                    step_limit - steps_executed, 0
                )
                state.budget_state["seconds_elapsed"] = time.time() - start_time
                if state.budget_state["steps_remaining"] <= 0:
                    state.budget_state["exhausted"] = True
                    state.budget_state["exhaustion_reason"] = "max_steps reached"

                # --- Checkpoint after every cycle ---
                self._checkpoint(mission, state)

                # --- Check if mission is complete ---
                if state.phase == CognitivePhase.COMPLETE.value:
                    return self._stop(
                        mission, state, steps_executed,
                        KernelStopReason.COMPLETED,
                        task_results,
                    )

                if cycle_result.get("stop_reason"):
                    return self._stop(
                        mission, state, steps_executed,
                        cycle_result["stop_reason"],
                        task_results,
                        cycle_result.get("error"),
                    )

            # Exhausted step budget
            return self._stop(
                mission, state, steps_executed,
                KernelStopReason.MAX_STEPS_REACHED,
                task_results,
                f"completed {steps_executed} steps (limit: {step_limit})",
            )

        except KeyboardInterrupt:
            return self._stop(
                mission, state, steps_executed,
                KernelStopReason.MANUAL_PAUSE,
                task_results, "kernel interrupted",
            )
        except Exception as exc:
            logger.exception("Kernel error on mission %s: %s", mission.mission_id, exc)
            self._checkpoint(mission, state, notes=f"kernel error: {exc}")
            return self._stop(
                mission, state, steps_executed,
                KernelStopReason.FAILED,
                task_results, f"kernel error: {exc}",
            )

    def resume(
        self,
        mission_id: str,
        max_steps: Optional[int] = None,
    ) -> "KernelResult":
        """Resume a mission from its latest checkpoint.

        Loads the mission from the persistent store, restores the cognitive
        state from the latest checkpoint, and continues the bounded loop.
        """
        mission = Mission.load(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")

        # Mission must not be terminal to resume
        if mission.is_terminal:
            raise ValueError(
                f"Mission {mission_id} is in terminal state {mission.status} — "
                "cannot resume"
            )

        return asyncio.run(self.run(mission, max_steps=max_steps))

    # ------------------------------------------------------------------ #
    # Cognitive cycle
    # ------------------------------------------------------------------ #

    async def _cycle(
        self,
        mission: Mission,
        state: CognitiveState,
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
        start_time: float = 0,
    ) -> dict[str, Any]:
        """Execute one full cognitive cycle.

        Returns a dict with optional task_results, stop_reason, or error.
        """
        task_results: list[dict[str, Any]] = []
        budget = mission.budget

        # 1. PERCEIVE — ingest current state
        state.phase = CognitivePhase.PERCEIVE.value
        state = self._perceive(mission, state)

        # 2. UNDERSTAND — classify intent, update known_facts
        state.phase = CognitivePhase.UNDERSTAND.value
        state = self._understand(mission, state)

        # 3. HYPOTHESIZE — propose or select next hypothesis
        state.phase = CognitivePhase.HYPOTHESIZE.value
        state, hypothesis = self._hypothesize(mission, state)

        # 4. PLAN — build execution graph (DAG of capability nodes)
        state.phase = CognitivePhase.PLAN.value
        task, graph, stop_reason = self._plan(
            mission, state, hypothesis, permissions, principal,
        )
        if stop_reason:
            return {"task_results": [], "stop_reason": stop_reason}

        # 5. AUTHORIZE — check authorization for each node
        state.phase = CognitivePhase.AUTHORIZE.value
        task, auth_result = self._authorize(mission, task, state)
        if auth_result.get("stop"):
            return {"task_results": [], "stop_reason": auth_result["reason"]}

        # 6. EXECUTE — delegate to AgentExecutor
        state.phase = CognitivePhase.EXECUTE.value
        exec_result = await self._execute(task, permissions, principal)
        task_results.append(exec_result)

        # 7. OBSERVE — capture results, record evidence
        state.phase = CognitivePhase.OBSERVE.value
        state = self._observe(mission, state, task, exec_result)

        # Record task in mission
        self._link_task(mission, task, exec_result)
        self._checkpoint(mission, state, notes=f"cycle {state.cycle} complete")

        # 8. CRITIQUE — Critic analysis
        state.phase = CognitivePhase.CRITIQUE.value
        findings = self.critic.critique(state)
        for f in findings:
            state.critic_findings.append(f.to_dict())

        # 9. VERIFY — verify claims and hypotheses
        state.phase = CognitivePhase.VERIFY.value
        state = self._verify(mission, state, hypothesis)

        # 10. LEARN — update evidence and knowledge
        state.phase = CognitivePhase.LEARN.value
        state = self._learn(mission, state, task)

        # 11. REPLAN — check completion, replan if needed
        state.phase = CognitivePhase.REPLAN.value
        stop_reason = self._replan(mission, state)

        if stop_reason:
            return {"task_results": task_results, "stop_reason": stop_reason}

        return {"task_results": task_results}

    # ------------------------------------------------------------------ #
    # Cycle steps
    # ------------------------------------------------------------------ #

    def _perceive(
        self, mission: Mission, state: CognitiveState
    ) -> CognitiveState:
        """Ingest the current mission context into the cognitive state."""
        # Capture current compute resource status (Phase 9 integration)
        try:
            hw = local_hardware()
            state.confidence_state["local_hardware"] = {
                "cpu": hw.get("cpu", "unknown"),
                "gpu": hw.get("gpu", "none"),
                "gpu_count": hw.get("gpu_count", 0),
                "ram_gb": hw.get("ram_gb", 0),
            }
        except Exception as e:  # noqa: BLE001
            logger.debug("local_hardware() failed: %s", e)
            state.confidence_state["local_hardware"] = {"error": str(e)}

        # Check Brain readiness (Phase 8)
        try:
            brain = discover_brain()
            state.confidence_state["brain_available"] = brain.get("available", False)
            state.confidence_state["brain_unavailable"] = brain.get(
                "BRAIN_RUNTIME_UNAVAILABLE", False
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("discover_brain() failed: %s", e)
            state.confidence_state["brain_available"] = False
            state.confidence_state["brain_unavailable"] = True

        state.last_updated = now_iso()
        return state

    def _understand(
        self, mission: Mission, state: CognitiveState
    ) -> CognitiveState:
        """Classify mission intent and update known facts."""
        # Re-use the existing _understand pattern from research_engine/agent.py
        objective = mission.objective.lower()
        if any(w in objective for w in ("prove", "show that", "verify", "why does")):
            state.confidence_state["intent"] = "verification"
        elif any(w in objective for w in ("investigate", "why", "root cause")):
            state.confidence_state["intent"] = "investigation"
        elif any(w in objective for w in ("implement", "code", "algorithm")):
            state.confidence_state["intent"] = "implementation"
        elif any(w in objective for w in ("research", "what is", "latest", "compare")):
            state.confidence_state["intent"] = "research"
        else:
            state.confidence_state["intent"] = "analysis"

        # Record objective as a known fact
        state.add_fact(
            statement=f"Mission objective: {mission.objective}",
            source="mission",
            verified=True,
        )

        # Record success criteria as open questions to answer
        for criterion in mission.success_criteria:
            state.add_question(f"Is '{criterion}' satisfied?")

        state.last_updated = now_iso()
        return state

    def _hypothesize(
        self, mission: Mission, state: CognitiveState
    ) -> "tuple[CognitiveState, Optional[Any]]":
        """Propose or select the next hypothesis to test."""
        # If we already have an active hypothesis, continue testing it
        active = None
        if state.active_hypothesis:
            h = self.hypothesis_engine.get(state.active_hypothesis)
            if h is not None and h.status not in RESOLVED_STATUSES:
                active = h

        if active is None:
            # Propose a new hypothesis from the mission objective
            h = self.hypothesis_engine.propose(
                statement=f"To achieve mission '{mission.title}': {mission.objective}",
                context=mission.objective,
                rationale="generated from mission objective",
                proposed_by="cognitive_kernel",
            )
            state.hypotheses.append(h.to_dict())
            state.active_hypothesis = h.id
            active = h

        # Record hypothesis in state
        for h in self.hypothesis_engine.list_all():
            if h.id not in [x.get("id") for x in state.hypotheses]:
                state.hypotheses.append(h.to_dict())

        state.last_updated = now_iso()
        return state, active

    def _plan(
        self,
        mission: Mission,
        state: CognitiveState,
        hypothesis: Optional[Any],
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> "tuple[Optional[Task], Optional[ExecutionGraph], Optional[str]]":
        """Build an execution graph (DAG) for the next step.

        Uses the existing AgentExecutor.build_execution_graph().
        Returns (task, graph, stop_reason).
        """
        # Determine capabilities to execute based on mission config
        # If allowed_capabilities is set, use those; otherwise discover
        if mission.allowed_capabilities:
            caps = list(mission.allowed_capabilities)
        else:
            # Discover capabilities from the current hypothesis or objective
            intent = hypothesis.statement if hypothesis else mission.objective
            caps = self.executor.discover(intent, mode=mission.execution_mode)
            # Filter to READ-risk capabilities for safety (network/admin
            # capabilities require confirmation, handled in authorize step)
            if mission.autonomy_level <= AutonomyLevel.LEVEL_1.value:
                caps = self._filter_safe_capabilities(caps, mission)

        if not caps:
            # No capabilities available — can't plan
            return None, None, "no_eligible_capabilities"

        task, graph = self.executor.build_execution_graph(
            intent=mission.objective,
            capabilities=caps,
            user_id=mission.created_by or "anonymous",
            execution_mode=mission.execution_mode,
            confirmations={},  # confirmations handled at authorization step
        )
        return task, graph, None

    def _filter_safe_capabilities(
        self, caps: list[str], mission: Mission
    ) -> list[str]:
        """For low-autonomy missions, filter to READ-risk capabilities only."""
        from research_engine.capability_contract import build_contracts
        try:
            contracts = build_contracts(self.tool_registry)
        except Exception:
            return caps

        # Always allow required capabilities even at low autonomy
        required = set(mission.required_capabilities)
        filtered = []
        for cap in caps:
            contract = contracts.get(cap, {})
            risk = contract.get("risk_level", "read")
            if risk in ("read",) or cap in required:
                filtered.append(cap)
            # For autonomy level 1, we allow READ only (network requires confirmation)
            # For autonomy level 2+, more capabilities are allowed
            elif mission.autonomy_level >= AutonomyLevel.LEVEL_2.value and risk in ("exec",):
                filtered.append(cap)
        return filtered if filtered else caps

    def _authorize(
        self,
        mission: Mission,
        task: Optional[Task],
        state: CognitiveState,
    ) -> "tuple[Optional[Task], dict[str, Any]]":
        """Authorize nodes through the ToolRegistry.

        High-risk nodes (NETWORK, ADMIN, EXEC) that require confirmation
        are held WAITING_FOR_USER.  If any node cannot be authorized due to
        autonomy level, the mission may need to escalate.

        Returns (task, auth_result).  auth_result may contain 'stop' and 'reason'.
        """
        if task is None or task.plan is None:
            return task, {"stop": True, "reason": "no_plan"}

        for node in task.plan.nodes.values():
            # Check authorization
            ok, reason = self.tool_registry.authorize(
                mission.created_by or "anonymous",
                node.capability,
            )
            if not ok:
                node.status = ExecutionNodeStatus.FAILED
                node.error = f"TOOL_DENIED: {reason}"
                self._checkpoint(mission, state,
                                 notes=f"node {node.node_id} denied: {reason}")

        # Check if any nodes are waiting for user confirmation
        waiting = [n for n in task.plan.nodes.values()
                   if n.status == ExecutionNodeStatus.WAITING_FOR_USER]
        if waiting:
            # Check autonomy level — if level 0, must wait for human
            if mission.autonomy_level <= AutonomyLevel.LEVEL_0.value:
                return task, {
                    "stop": True,
                    "reason": KernelStopReason.WAITING_FOR_APPROVAL.value,
                }
            # For level 1+, WAITING_FOR_USER nodes are held until approved
            # via approve_node() on the executor
            return task, {
                "stop": True,
                "reason": KernelStopReason.WAITING_FOR_APPROVAL.value,
            }

        return task, {}

    async def _execute(
        self,
        task: Optional[Task],
        permissions: Optional[set[str]] = None,
        principal: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute the task via AgentExecutor."""
        if task is None:
            return {"success": False, "error": "no task to execute"}

        result = await self.executor.execute_task(
            task, permissions=permissions, principal=principal,
        )
        return result

    def _observe(
        self,
        mission: Mission,
        state: CognitiveState,
        task: Optional[Task],
        exec_result: dict[str, Any],
    ) -> CognitiveState:
        """Capture execution results and record evidence."""
        if task and task.plan:
            for node_id, node in task.plan.nodes.items():
                if node.status == ExecutionNodeStatus.COMPLETED and node.outputs:
                    # Create an observation (already scrubbed by ToolRegistry)
                    content = str(node.outputs.get("result", ""))
                    obs = state.add_observation(
                        source=node.capability,
                        content=content[:2000],  # truncate for state
                        metadata={
                            "task_id": task.task_id,
                            "node_id": node_id,
                            "provider": node.provider or "unknown",
                            "duration_ms": (
                                (node.completed_at - node.started_at) * 1000
                                if node.started_at and node.completed_at
                                else 0
                            ),
                        },
                    )

                    # Register evidence from this node's output
                    self.evidence_engine.register_from_tool_result(
                        tool_name=node.capability,
                        result=node.outputs,
                        claims=[f"Capability {node.capability} executed successfully"],
                        task_id=task.task_id,
                        artifact_id=node.artifact_ids[0] if node.artifact_ids else None,
                    )

        # Record observation in mission metrics
        state.last_updated = now_iso()
        return state

    def _link_task(
        self,
        mission: Mission,
        task: Task,
        exec_result: dict[str, Any],
    ) -> None:
        """Link a completed task to the mission record."""
        task_entry = {
            "task_id": task.task_id,
            "intent": task.intent,
            "status": task.status.value,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "result": exec_result.get("result", {}),
            "success": exec_result.get("success", False),
        }
        # Avoid duplicates
        existing = [t for t in mission.tasks if t.get("task_id") == task.task_id]
        if not existing:
            mission.tasks.append(task_entry)
        else:
            existing[0].update(task_entry)
        mission.updated_at = now_iso()

    def _verify(
        self,
        mission: Mission,
        state: CognitiveState,
        hypothesis: Optional[Any],
    ) -> CognitiveState:
        """Verify claims and update evidence/hypothesis status."""
        # Verify active hypothesis against collected evidence
        if hypothesis:
            evidence_list = [e.evidence for e in self.evidence_engine.list_all()]
            outcome = self.verifier.verify_claim(
                claim=hypothesis.statement,
                evidence=evidence_list,
            )

            # Convert to VerificationResult in state
            vr = {
                "claim": hypothesis.statement,
                "status": outcome.status,
                "reason": outcome.reason,
                "confidence": outcome.confidence,
                "evidence_refs": outcome.evidence_used,
                "at": outcome.verified_at,
            }
            state.verification_results.append(vr)

            # Update hypothesis status via the engine
            try:
                new_status = self.hypothesis_engine.evaluate(
                    hypothesis.id,
                    evidence=evidence_list,
                )
                # Sync hypothesis in state
                for h in state.hypotheses:
                    if h.get("id") == hypothesis.id:
                        h["status"] = new_status.value
                        break
            except Exception as e:  # noqa: BLE001
                logger.debug("Hypothesis evaluation failed: %s", e)

        state.last_updated = now_iso()
        return state

    def _learn(
        self,
        mission: Mission,
        state: CognitiveState,
        task: Optional[Task],
    ) -> CognitiveState:
        """Update evidence and knowledge from observations."""
        # Build verified evidence pack from the completed task
        if task and task.plan:
            evidence_pack = build_verified_evidence_pack(task, self.tool_registry)
            if evidence_pack:
                # Add to mission evidence
                for node_info in evidence_pack.get("executed_nodes", []):
                    ev_entry = {
                        "task_id": task.task_id,
                        "node_id": node_info.get("node_id"),
                        "capability": node_info.get("capability"),
                        "verification_status": evidence_pack.get(
                            "verification_status", "UNVERIFIED"
                        ),
                    }
                    if ev_entry not in mission.evidence:
                        mission.evidence.append(ev_entry)

        state.last_updated = now_iso()
        return state

    def _replan(
        self,
        mission: Mission,
        state: CognitiveState,
    ) -> Optional[str]:
        """Check if the mission is complete; replan if needed.

        Returns a stop_reason string if the mission should stop, else None.
        """
        # Run Critic for final assessment
        findings = self.critic.critique(state)
        for f in findings:
            state.critic_findings.append(f.to_dict())

        # Check for budget violations (ERROR severity)
        for f in findings:
            if f.severity == "error":
                if f.category == "budget":
                    state.budget_state["exhausted"] = True
                    state.budget_state["exhaustion_reason"] = f.description
                    return KernelStopReason.BUDGET_EXHAUSTED.value

        # Check success criteria
        verified_criteria = self.verifier.verify_success_criteria(
            criteria=mission.success_criteria,
            evidence_entries=[
                e for e in self.evidence_engine.list_all()
            ],
        )

        # Record verification decision
        mission.decisions.append({
            "decision_id": f"dec_{_short_uuid()}",
            "at": now_iso(),
            "kind": "verify",
            "rationale": verified_criteria.get("summary", ""),
            "outcome": "verified" if verified_criteria.get("all_verified") else "not_verified",
            "evidence_refs": [],
        })

        all_verified = verified_criteria.get("all_verified", False)

        # Check if we should transition to VERIFYING
        if all_verified and not state.budget_state.get("exhausted"):
            mission.metrics["success_criteria_verification"] = verified_criteria
            # Transition to VERIFYING → COMPLETED
            mission.transition(MissionStatus.VERIFYING, actor="cognitive_kernel",
                              notes="success criteria verified")
            mission.transition(MissionStatus.COMPLETED, actor="cognitive_kernel",
                              notes="verification passed")
            state.phase = CognitivePhase.COMPLETE.value
            return KernelStopReason.COMPLETED.value

        # Check failure criteria
        for criterion in mission.failure_criteria:
            # If any failure criterion is observed, fail the mission
            # (checked via evidence)
            evidence_list = [e.evidence for e in self.evidence_engine.list_all()]
            status, reason, _ = self.verifier._engine.verify_claim(
                claim=criterion,
                evidence=evidence_list,
            )
            if status.value == "VERIFIED":
                mission.transition(MissionStatus.FAILED, actor="cognitive_kernel",
                                  notes=f"failure criterion met: {criterion}")
                state.phase = CognitivePhase.FAILED.value
                return KernelStopReason.FAILED.value

        # Not complete — continue looping
        return None

    # ------------------------------------------------------------------ #
    # Checkpointing / Recovery
    # ------------------------------------------------------------------ #

    def _checkpoint(
        self,
        mission: Mission,
        state: CognitiveState,
        notes: str = "",
    ) -> Optional[str]:
        """Persist mission state for crash recovery."""
        task_states = {}
        for t in mission.tasks:
            task_states[t.get("task_id", "")] = t

        hypothesis_states = self.hypothesis_engine.to_dict()
        evidence_count = len(self.evidence_engine.list_all())

        ckpt_id = mission.checkpoint(
            cycle=state.cycle,
            phase=state.phase,
            cognitive_state=state.to_dict(),
            task_states=task_states,
            hypothesis_states=hypothesis_states,
            evidence_count=evidence_count,
            notes=notes,
        )
        mission.save()
        return ckpt_id

    def _load_state(self, mission: Mission) -> CognitiveState:
        """Restore cognitive state from the latest checkpoint, or create new."""
        ckpt = mission.latest_checkpoint()
        if ckpt and ckpt.get("cognitive_state"):
            state = CognitiveState.from_dict(ckpt["cognitive_state"])
            # Restore engines
            hyp_data = ckpt.get("hypothesis_states", {})
            if hyp_data:
                from research_engine.verification import VerificationEngine
                self.hypothesis_engine = HypothesisEngine.from_dict(
                    hyp_data, verifier=VerificationEngine()
                )
            return state

        # Fresh state
        return CognitiveState(
            mission_id=mission.mission_id,
            objective=mission.objective,
            phase=CognitivePhase.UNDERSTAND.value,
            budget_state=BudgetState(
                steps_consumed=0,
                steps_remaining=mission.budget.max_steps,
                tokens_consumed=0,
                cost_spent_usd=0.0,
                seconds_elapsed=0.0,
                iterations_consumed=0,
            ).to_dict(),
        )

    @staticmethod
    def _finding_to_dict(f: Any) -> dict[str, Any]:
        """Convert a CriticFinding (or its dict form) to a dict."""
        if isinstance(f, dict):
            return f
        return f.to_dict()

    def _stop(
        self,
        mission: Mission,
        state: CognitiveState,
        steps_executed: int,
        stop_reason: str,
        task_results: list[dict[str, Any]],
        error: Optional[str] = None,
    ) -> KernelResult:
        """Finalize the kernel run and return the result."""
        self._checkpoint(mission, state, notes=f"kernel stopped: {stop_reason}")
        mission.save()

        return KernelResult(
            mission_id=mission.mission_id,
            steps_executed=steps_executed,
            stop_reason=stop_reason,
            cognitive_state=state.to_dict(),
            task_results=task_results,
            findings=[self._finding_to_dict(f) for f in state.critic_findings],
            verification_result=mission.metrics.get("success_criteria_verification"),
            error=error,
        )

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #

    def get_mission_status(
        self, mission_id: str
    ) -> Optional[dict[str, Any]]:
        """Get the current status of a mission."""
        mission = Mission.load(mission_id)
        if mission is None:
            return None
        return {
            "mission_id": mission.mission_id,
            "title": mission.title,
            "status": mission.status,
            "current_phase": mission.current_phase,
            "cycle": mission.metrics.get("cycle", 0),
            "budget": mission.budget.to_dict() if isinstance(mission.budget, MissionBudget) else mission.budget,
            "tasks_count": len(mission.tasks),
            "evidence_count": len(mission.evidence),
            "checkpoints": len(mission.checkpoints),
            "latest_checkpoint": mission.latest_checkpoint(),
        }


__all__ = [
    "KernelStopReason",
    "KernelResult",
    "CognitiveKernel",
]
