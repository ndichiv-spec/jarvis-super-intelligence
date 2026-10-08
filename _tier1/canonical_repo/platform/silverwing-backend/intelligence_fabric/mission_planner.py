"""Mission Planner for the Silverwing Intelligence Fabric.

The ``MissionPlanner`` decomposes a high-level objective (an
``IntelligenceRequest``) into one or more sub-missions and an ordered
sequence of tasks.  It is *not* a model caller — it only decides **what**
needs to happen.  The ``ModelRouter`` (inside the Model Gateway) decides
**which model** will execute each step.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fabric_models import (
    IntelligenceRequest,
    MissionContext,
    TaskSpec,
    TaskPriority,
    TaskStatus,
    RiskLevel,
)

# Maps a keyword or phrase to the task that should be spawned.
# These are *capability hints* — the AgentScheduler resolves the actual
# agent that performs the task.
_TASK_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "research",
        "capability": "research",
        "agents": ["researcher", "analyst", "librarian"],
        "tools": ["web_search", "openalex", "arxiv", "crossref",
                  "semantic_scholar", "knowledge_graph"],
        "model_classes": ["REASONING", "RESEARCH", "LOCAL_OPEN_WEIGHT"],
        "risk": RiskLevel.LOW,
        "priority": TaskPriority.NORMAL,
        "timeout": 120,
        "keywords": ["research", "find", "search", "what", "how", "latest",
                      "recent", "study", "paper", "evidence"],
    },
    {
        "name": "analysis",
        "capability": "analysis",
        "agents": ["analyst"],
        "tools": ["python", "memory_read", "knowledge_graph", "web_fetch"],
        "model_classes": ["REASONING", "LARGE_FRONTIER"],
        "risk": RiskLevel.MEDIUM,
        "priority": TaskPriority.NORMAL,
        "timeout": 180,
        "keywords": ["analyze", "analysis", "compare", "evaluate", "assess",
                      "impact", "pros", "cons", "trade-off", "tradeoff"],
    },
    {
        "name": "coding",
        "capability": "coding",
        "agents": ["coder", "engineer"],
        "tools": ["python", "shell", "filesystem"],
        "model_classes": ["CODE"],
        "risk": RiskLevel.HIGH,
        "priority": TaskPriority.NORMAL,
        "timeout": 300,
        "keywords": ["code", "script", "implement", "build", "program",
                      "develop", "algorithm", "python", "test", "debug"],
    },
    {
        "name": "verification",
        "capability": "verification",
        "agents": ["verifier"],
        "tools": ["web_fetch", "openalex", "crossref", "arxiv",
                  "semantic_scholar", "python"],
        "model_classes": ["REASONING"],
        "risk": RiskLevel.MEDIUM,
        "priority": TaskPriority.HIGH,
        "timeout": 120,
        "keywords": ["verify", "check", "validate", "confirm", "fact-check",
                      "fact check", "contradict", "truth"],
    },
    {
        "name": "synthesis",
        "capability": "synthesis",
        "agents": ["analyst", "librarian"],
        "tools": ["memory_read", "knowledge_graph", "python"],
        "model_classes": ["REASONING", "CREATIVE", "LARGE_FRONTIER"],
        "risk": RiskLevel.LOW,
        "priority": TaskPriority.NORMAL,
        "timeout": 180,
        "keywords": ["summarize", "synthesis", "synthesise", "report",
                      "conclusion", "findings", "overview", "roundup",
                      "round-up", "insights", "final"],
    },
    {
        "name": "memory_consolidation",
        "capability": "memory_management",
        "agents": ["librarian"],
        "tools": ["memory_write", "knowledge_graph"],
        "model_classes": ["LOCAL_OPEN_WEIGHT", "FREE_TIER"],
        "risk": RiskLevel.LOW,
        "priority": TaskPriority.LOW,
        "timeout": 60,
        "keywords": [],
    },
]


class MissionPlanner:
    """Decomposes an ``IntelligenceRequest`` into tasks and sub-missions."""

    def __init__(self) -> None:
        self._templates: List[Dict[str, Any]] = _TASK_TEMPLATES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_context(self, request: IntelligenceRequest) -> MissionContext:
        """Create a ``MissionContext`` from an incoming request."""

        mission_id = request.mission_id or f"mission-{uuid.uuid4().hex[:12]}"
        return MissionContext(
            mission_id=mission_id,
            objective=request.query,
            privacy=request.privacy,
            cost=request.cost,
            budget_remaining_usd=request.max_budget_usd or 0.0,
            deadline=self._deadline_from_request(request),
            memory_access=request.memory_access,
            constraints=request.constraints,
        )

    def plan(self, request: IntelligenceRequest,
             context: Optional[MissionContext] = None) -> List[TaskSpec]:
        """Decompose *request* into an ordered list of ``TaskSpec`` objects.

        The planner inspects the query text, identifies which capability
        templates are triggered, and creates tasks accordingly.  A
        *verification* task is always appended when evidence-based work
        is involved, and a *memory_consolidation* task is appended at the
        end to persist findings.
        """

        if context is None:
            context = self.create_context(request)

        tasks: List[TaskSpec] = []
        query_lower = request.query.lower()

        # 1. Match keyword templates to determine task sequence
        matched = self._match_templates(query_lower, request.constraints)

        if not matched:
            # Default: always do research + analysis + verification
            matched = ["research", "analysis", "verification"]

        # 2. Ensure ordering: research → analysis → coding → verification → synthesis
        ordered = self._order_tasks(matched)

        # 3. Always append verification and memory consolidation
        if "verification" not in ordered:
            ordered.append("verification")
        ordered.append("memory_consolidation")

        for idx, name in enumerate(ordered):
            template = self._template_for(name)
            task = TaskSpec(
                task_id=f"task-{uuid.uuid4().hex[:12]}",
                mission_id=context.mission_id,
                parent_task_id=context.task_ids[-1] if context.task_ids else None,
                description=self._task_description(name, request.query),
                capability=template["capability"],
                priority=template["priority"],
                risk=template["risk"],
                status=TaskStatus.PENDING,
                required_tools=template["tools"],
                required_model_classes=template["model_classes"],
                privacy=context.privacy,
                cost=context.cost,
                latency=request.latency,
                timeout_seconds=template["timeout"],
                budget_usd=self._allocate_budget(context, template),
                inputs=self._task_inputs(name, context, request),
                max_retries=2 if template["risk"] == RiskLevel.HIGH else 1,
            )
            tasks.append(task)
            context.task_ids.append(task.task_id)

        # 4. Update context
        context.sub_mission_ids = [f"sub-{i}" for i in range(len(ordered))]

        return tasks

    def sub_missions(self, context: MissionContext,
                     request: IntelligenceRequest) -> List[Dict[str, Any]]:
        """Return high-level sub-mission descriptors for observability."""

        result: List[Dict[str, Any]] = []
        for i, sm_id in enumerate(context.sub_mission_ids):
            result.append({
                "sub_mission_id": sm_id,
                "objective": f"{context.objective} (sub-mission {i + 1})",
                "task_ids": context.task_ids[i::len(context.sub_mission_ids)]
                                if len(context.sub_mission_ids) > 1 else context.task_ids,
            })
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_templates(self, query_lower: str,
                         constraints: Dict[str, Any]) -> List[str]:
        """Return ordered list of template names triggered by the query."""

        # Explicit framework constraints can force certain tasks
        forced = constraints.get("force_tasks", [])
        forced = [t for t in forced if any(t == tmpl["name"] or t in tmpl["keywords"]
                                           for tmpl in self._templates)]

        matched: List[str] = []
        for tmpl in self._templates:
            if tmpl["name"] in forced:
                matched.append(tmpl["name"])
                continue
            if tmpl["name"] == "memory_consolidation":
                continue  # always appended
            if any(kw in query_lower for kw in tmpl["keywords"]):
                matched.append(tmpl["name"])

        # If no keyword matched, fall back to defaults
        if not matched:
            matched = ["research", "analysis", "verification"]

        return matched

    def _order_tasks(self, names: List[str]) -> List[str]:
        """Order task names by a canonical dependency graph."""

        order = ["research", "analysis", "coding", "verification",
                 "synthesis"]
        result = [n for n in order if n in names]

        # Append anything not in the canonical order
        for n in names:
            if n not in result and n != "memory_consolidation":
                result.append(n)

        return result

    def _template_for(self, name: str) -> Dict[str, Any]:
        for tmpl in self._templates:
            if tmpl["name"] == name:
                return tmpl
        # Fallback
        return self._templates[0]

    def _task_description(self, name: str, query: str) -> str:
        return f"[{name}] for: {query}"

    def _allocate_budget(self, context: MissionContext,
                         template: Dict[str, Any]) -> Optional[float]:
        """Allocate a per-task slice of the remaining budget."""

        if context.budget_remaining_usd <= 0:
            return None
        # Simple equal split across tasks; refinement is a future concern
        total_tasks = 5  # research, analysis, coding, verification, synthesis + mem
        return round(context.budget_remaining_usd / total_tasks, 4)

    def _deadline_from_request(self, request: IntelligenceRequest) -> Optional[float]:
        if request.timeout_seconds:
            return time.time() + request.timeout_seconds
        return None

    def _task_inputs(self, name: str, context: MissionContext,
                     request: IntelligenceRequest) -> Dict[str, Any]:
        return {
            "query": request.query,
            "context": request.context or "",
            "memory_access": request.memory_access,
            "constraints": request.constraints,
        }
