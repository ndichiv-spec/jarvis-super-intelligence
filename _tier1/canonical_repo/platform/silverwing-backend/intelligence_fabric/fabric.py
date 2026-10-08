"""Intelligence Fabric Orchestrator.

This module implements the ``IntelligenceFabric`` — the unified runtime
layer that sits *above* the existing Model Gateway.  It is responsible for:

* Deciding **what needs to happen** (MissionPlanner)
* Selecting **which agent** should do it (AgentScheduler)
* Selecting **which tools** are required (ToolSelector)
* Deciding **what model capability** is required (delegates to ModelRouter)
* Deciding **what needs verification** (VerificationCoordinator)

The ModelRouter remains responsible for *which specific model* — the
Fabric never replaces it.

Architecture flow:

    IntelligenceRequest
            │
            ▼
    Mission Context  (MissionPlanner)
            │
    Orchestrator
            │
    ┌────────┼──────────┐
    ▼        ▼          ▼
   Agent   Tool        Memory
    │        │          │
    └────────┼──────────┘
            ▼
      Model Router  (from Model Gateway)
            │
            ▼
         Model
            │
            ▼
      Verification  (VerificationCoordinator)
            │
            ▼
        Evidence
            │
            ▼
       Result
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from fabric_models import (
    IntelligenceRequest,
    MissionContext,
    TaskSpec,
    TaskStatus,
    TaskPriority,
    AgentSpec,
    FabricResult,
    AgentCapability,
    RiskLevel,
    FrameworkInfo,
)
from mission_planner import MissionPlanner
from task_planner import TaskPlanner
from agent_scheduler import AgentScheduler
from tool_selector import ToolSelector
from verification_coordinator import VerificationCoordinator
from adapters import get_adapter, get_adapter_info_all


class IntelligenceFabric:
    """The unified runtime layer above the Model Gateway.

    The Fabric wires together:

    * ``MissionPlanner`` — objective → sub-missions → tasks
    * ``TaskPlanner``    — task → ordered execution steps
    * ``AgentScheduler`` — task → agent assignment
    * ``ToolSelector``   — task + agent → tool selections
    * ``ModelRouter``    — (from the Gateway) capability → model
    * ``VerificationCoordinator`` — claims → verification

    The Fabric does **not** reimplement the Model Gateway.  It imports
    and delegates to it for all model routing decisions.
    """

    def __init__(self, router=None) -> None:
        self._router = router  # ModelRouter from the Model Gateway
        self._planner = MissionPlanner()
        self._task_planner = TaskPlanner()
        self._scheduler = AgentScheduler()
        self._tool_selector = ToolSelector()
        self._verifier = VerificationCoordinator(router=router)
        self._adapter_registry: Dict[str, Any] = {}
        self._routing_decisions: List[Dict[str, Any]] = []
        self._tool_executions: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def planner(self) -> MissionPlanner:
        return self._planner

    @property
    def task_planner(self) -> TaskPlanner:
        return self._task_planner

    @property
    def scheduler(self) -> AgentScheduler:
        return self._scheduler

    @property
    def tool_selector(self) -> ToolSelector:
        return self._tool_selector

    @property
    def verifier(self) -> VerificationCoordinator:
        return self._verifier

    @property
    def router(self):
        """The ModelRouter from the Gateway (may be None in tests)."""
        return self._router

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_frameworks(self) -> List[FrameworkInfo]:
        """Return metadata about all orchestration framework adapters."""

        adapter_infos = get_adapter_info_all()
        result: List[FrameworkInfo] = []
        for info in adapter_infos:
            result.append(FrameworkInfo(**info))
        return result

    def get_adapter(self, name: str) -> Any:
        """Return an adapter instance by name.

        Lazily instantiates and caches the adapter.
        """

        if name not in self._adapter_registry:
            self._adapter_registry[name] = get_adapter(name)
        return self._adapter_registry[name]

    def get_routing_decision(self, capability: str = "",
                             privacy: str = "public",
                             cost: str = "best_quality",
                             latency: str = "normal",
                             task: str = "",
                             model_classes: Optional[List[str]] = None) -> Optional[Any]:
        """Delegate to the ModelRouter to select a model.

        Returns a ``RoutingDecision`` if a router is available, else None.
        """

        if self._router is None:
            return None

        decision = self._router.select(
            capability=capability,
            privacy=privacy,
            cost=cost,
            latency=latency,
            task=task,
            model_classes=model_classes,
        )
        self._routing_decisions.append(decision.model_dump())
        return decision

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def handle_request(self, request: IntelligenceRequest) -> FabricResult:
        """Process an ``IntelligenceRequest`` end-to-end through the Fabric.

        This is the primary public API.  Callers submit an
        ``IntelligenceRequest`` and receive a ``FabricResult`` containing
        findings, claims, sources, evidence, routing decisions, and
        tool executions.
        """

        start_time = time.time()

        # 1. Create mission context
        context = self._planner.create_context(request)

        # 2. Plan tasks
        tasks = self._planner.plan(request, context)

        # 3. Decompose each task into steps
        steps_map: Dict[str, List[Dict[str, Any]]] = {}
        for task in tasks:
            steps_map[task.task_id] = self._task_planner.decompose(task)

        # 4. Schedule agents to tasks
        for task in tasks:
            agent_spec = self._scheduler.schedule(task)

        # 5. Select tools for each task
        tool_selections_map: Dict[str, List[Any]] = {}
        for task in tasks:
            agent_spec = self._scheduler.get_spec(task.agent_id or "")
            if agent_spec:
                selections = self._tool_selector.select_for_task(
                    agent_spec, task, steps_map[task.task_id])
                tool_selections_map[task.task_id] = selections

        # 6. Register with verification coordinator
        #    (claims are registered by agents during execution)

        # 7. Execute via the selected framework (default: native)
        framework = request.framework or "native"
        adapter = self.get_adapter(framework)

        if not adapter.is_available():
            framework = "native"
            adapter = self.get_adapter("native")

        execution_result = await adapter.execute_mission(context, tasks,
                                                          steps_map)

        # 8. Simulate model routing for each task (delegated to ModelRouter)
        for task in tasks:
            if task.required_model_classes and self._router:
                decision = self.get_routing_decision(
                    capability=task.capability,
                    privacy=task.privacy,
                    cost=task.cost,
                    latency=task.latency,
                    task=task.capability,
                    model_classes=task.required_model_classes,
                )

        # 9. Collect results
        result = FabricResult(
            mission_id=context.mission_id,
            success=execution_result.get("status") == "completed",
            query=request.query,
            findings=self._collect_findings(tasks),
            claims=[],
            sources=[],
            evidence=[],
            routing_decisions=self._routing_decisions[-len(tasks):]
                               if self._routing_decisions else [],
            tool_executions=self._tool_executions,
            tasks=[t.model_dump() for t in tasks],
            agents=[a.model_dump()
                    for a in [self._scheduler.get_spec(t.agent_id or "")
                              for t in tasks] if a],
            elapsed_ms=round((time.time() - start_time) * 1000, 2),
            total_cost_usd=self._estimate_total_cost(),
            error=None if execution_result.get("status") == "completed"
                   else execution_result.get("error"),
        )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_findings(self, tasks: List[TaskSpec]) -> List[Dict[str, Any]]:
        """Extract structured findings from completed task results."""

        findings: List[Dict[str, Any]] = []
        for task in tasks:
            if task.result:
                findings.append({
                    "task_id": task.task_id,
                    "capability": task.capability,
                    "agent_id": task.agent_id,
                    "finding": task.result.get("output", ""),
                    "status": task.status,
                })
        return findings

    def _estimate_total_cost(self) -> float:
        """Sum estimated costs from routing decisions."""

        total = 0.0
        for dec in self._routing_decisions:
            total += dec.get("cost_estimate", 0.0)
        return round(total, 6)

    def reset(self) -> None:
        """Clear internal state (useful for tests)."""

        self._routing_decisions.clear()
        self._tool_executions.clear()
        self._verifier = VerificationCoordinator(router=self._router)
