"""Tool Selector for the Silverwing Intelligence Fabric.

The ``ToolSelector`` resolves which tools a task's agent needs to
execute.  It validates that the requested tools are allowed for the
assigned agent and returns an ordered list of ``ToolSelection`` objects
that the ``Orchestrator`` can act on.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fabric_models import AgentSpec, TaskSpec, RiskLevel

# ---------------------------------------------------------------------------
# Tool registry — static metadata about every tool the Fabric knows about.
#
# This mirrors the 22 tools defined in the Silverwing root layer
# (tool_runtime.py) but is self-contained here so the Fabric can reason
# about tools without importing the root layer directly.
# ---------------------------------------------------------------------------

_TOOL_CATALOG: Dict[str, Dict[str, Any]] = {
    "web_search":       {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "web_fetch":        {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "openalex":         {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "arxiv":            {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "crossref":         {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "semantic_scholar": {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "github_search":    {"category": "development", "risk": RiskLevel.MEDIUM,
                         "requires_api": True,   "local_ok": True},
    "kiwix_search":     {"category": "research",   "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "organic_maps":     {"category": "geospatial", "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "python":           {"category": "execution",  "risk": RiskLevel.MEDIUM,
                         "requires_api": False,  "local_ok": False},
    "shell":            {"category": "execution",  "risk": RiskLevel.HIGH,
                         "requires_api": False,  "local_ok": False},
    "filesystem":       {"category": "execution",  "risk": RiskLevel.MEDIUM,
                         "requires_api": False,  "local_ok": False},
    "memory_read":      {"category": "memory",     "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "memory_write":     {"category": "memory",     "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "knowledge_graph":  {"category": "knowledge",  "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
    "model_inference":  {"category": "ai",         "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "mission_control":  {"category": "control",    "risk": RiskLevel.MEDIUM,
                         "requires_api": False,  "local_ok": True},
    "openai":           {"category": "ai",         "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "anthropic":        {"category": "ai",         "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "groq":             {"category": "ai",         "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "ollama":           {"category": "ai",         "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "deepseek":         {"category": "ai",         "risk": RiskLevel.LOW,
                         "requires_api": True,   "local_ok": True},
    "mesh_relay":       {"category": "mesh",       "risk": RiskLevel.LOW,
                         "requires_api": False,  "local_ok": True},
}


class ToolSelection:
    """A selected tool with its execution parameters and constraints."""

    def __init__(self, name: str, step: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.step = step
        self.config = config or {}
        self.info = _TOOL_CATALOG.get(name, {})

    @property
    def category(self) -> str:
        return self.info.get("category", "unknown")

    @property
    def risk(self) -> RiskLevel:
        return self.info.get("risk", RiskLevel.LOW)

    @property
    def requires_api(self) -> bool:
        return self.info.get("requires_api", False)

    def allowed_for(self, agent: AgentSpec, privacy: str,
                    cost: str) -> bool:
        """Check whether this tool is permitted for *agent* under the
        given privacy and cost constraints."""

        if self.name not in agent.allowed_tools and "model_inference" not in agent.allowed_tools:
            return False

        # High-risk tools require CRITICAL/SHELL_EXEC permissions
        if self.risk == RiskLevel.HIGH and "shell_exec" not in agent.permissions:
            return False

        # API-requiring tools are blocked under private-only cost policy
        if self.requires_api and cost == "private_only":
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "step": self.step,
            "category": self.category,
            "risk": self.risk.value if isinstance(self.risk, RiskLevel) else self.risk,
            "requires_api": self.requires_api,
            "config": self.config,
        }


class ToolSelector:
    """Selects and validates tools for a task based on agent permissions,
    task constraints, privacy, and cost policy."""

    def __init__(self) -> None:
        self._catalog = _TOOL_CATALOG

    @property
    def tool_names(self) -> List[str]:
        return list(self._catalog.keys())

    def select_for_step(self, agent: AgentSpec, task: TaskSpec,
                        step: Dict[str, Any]) -> List[ToolSelection]:
        """Select tools needed for a specific execution step."""

        step_name = step["step"]
        step_tool = step.get("tool", "model")

        # If the step says "builtin", no external tool needed
        if step_tool == "builtin":
            return []

        # If the step says "model", use model_inference
        if step_tool == "model":
            ts = ToolSelection("model_inference", step_name)
            if ts.allowed_for(agent, task.privacy, task.cost):
                return [ts]
            return []

        # If the step says "multi", select all task-required tools that
        # are both in the step context and allowed for the agent
        if step_tool == "multi":
            selections: List[ToolSelection] = []
            for tool_name in task.required_tools:
                ts = ToolSelection(tool_name, step_name)
                if ts.allowed_for(agent, task.privacy, task.cost):
                    selections.append(ts)
            return selections

        # Otherwise, the step names a specific tool
        ts = ToolSelection(step_tool, step_name)
        if ts.allowed_for(agent, task.privacy, task.cost):
            return [ts]

        return []

    def select_for_task(self, agent: AgentSpec, task: TaskSpec,
                        steps: List[Dict[str, Any]]) -> List[ToolSelection]:
        """Select all tools needed for the entire task."""

        all_selections: List[ToolSelection] = []
        seen: set[str] = set()
        for step in steps:
            for ts in self.select_for_step(agent, task, step):
                if ts.name not in seen:
                    all_selections.append(ts)
                    seen.add(ts.name)
        return all_selections

    def validate(self, selections: List[ToolSelection],
                 agent: AgentSpec) -> List[str]:
        """Return a list of validation warnings for the given selections."""

        warnings: List[str] = []
        for ts in selections:
            if not ts.allowed_for(agent, "public", "best_quality"):
                warnings.append(
                    f"Tool '{ts.name}' may not be allowed for agent "
                    f"'{agent.agent_id}' (risk={ts.risk.value})"
                )
        return warnings
