"""Agent Scheduler for the Silverwing Intelligence Fabric.

The ``AgentScheduler`` is responsible for matching ``TaskSpec`` objects
to the appropriate agent based on:

* The task's required capability
* The agent's declared capabilities
* Available agent capacity (how many tasks an agent is already running)
* Priority and risk of the task

It does **not** execute tasks — it assigns tasks to agents and returns
``AgentSpec`` descriptors.  The ``Orchestrator`` uses those descriptors
to dispatch work.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fabric_models import (
    AgentSpec,
    TaskSpec,
    TaskStatus,
    TaskPriority,
    RiskLevel,
    AgentCapability,
)

# ---------------------------------------------------------------------------
# Agent registry — declarative agent definitions.
#
# Each entry mirrors the 8 agents from the Silverwing root layer
# (agent_runtime.py) but is self-contained in the Fabric namespace.
# The Fabric owns the mission lifecycle; external frameworks are adapters.
# ---------------------------------------------------------------------------

_AGENT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "agent_id": "orchestrator",
        "role": "orchestrator",
        "capabilities": ["orchestration", "planning", "analysis"],
        "allowed_tools": ["memory_read", "knowledge_graph", "mission_control",
                          "model_inference", "python"],
        "preferred_model_classes": ["REASONING", "LARGE_FRONTIER"],
        "memory_access": ["working", "episodic", "semantic"],
        "permissions": ["mission_control"],
        "verification_policy": "strict",
        "system_prompt": (
            "You are Silverwing Orchestrator. You decompose objectives into "
            "sub-tasks, schedule agents, and verify that each step contributes "
            "to the overall mission."
        ),
        "model_preference": "deep-thinking",
    },
    {
        "agent_id": "researcher",
        "role": "researcher",
        "capabilities": ["research", "tool_use"],
        "allowed_tools": ["web_search", "openalex", "arxiv", "crossref",
                          "semantic_scholar", "web_fetch"],
        "preferred_model_classes": ["REASONING", "RESEARCH", "LOCAL_OPEN_WEIGHT"],
        "memory_access": ["working", "episodic"],
        "permissions": ["search"],
        "verification_policy": "standard",
        "system_prompt": (
            "You are Silverwing Researcher. You search academic and web "
            "sources to gather evidence. You prioritise open-weight and "
            "free-tier sources when available."
        ),
        "model_preference": "deep-thinking",
    },
    {
        "agent_id": "analyst",
        "role": "analyst",
        "capabilities": ["analysis", "synthesis", "memory_management"],
        "allowed_tools": ["python", "memory_read", "memory_write",
                          "knowledge_graph", "web_fetch"],
        "preferred_model_classes": ["REASONING", "LARGE_FRONTIER"],
        "memory_access": ["working", "semantic"],
        "permissions": ["analysis"],
        "verification_policy": "standard",
        "system_prompt": (
            "You are Silverwing Analyst. You analyse evidence, identify "
            "patterns, resolve conflicts, and produce structured findings."
        ),
        "model_preference": "deep-thinking",
    },
    {
        "agent_id": "verifier",
        "role": "verifier",
        "capabilities": ["verification"],
        "allowed_tools": ["web_fetch", "openalex", "crossref", "arxiv",
                          "semantic_scholar", "python"],
        "preferred_model_classes": ["REASONING"],
        "memory_access": ["working", "semantic"],
        "permissions": ["verification"],
        "verification_policy": "strict",
        "system_prompt": (
            "You are Silverwing Verifier. You independently verify every "
            "claim against evidence sources. You flag contradictions."
        ),
        "model_preference": "fast-reasoning",
    },
    {
        "agent_id": "engineer",
        "role": "engineer",
        "capabilities": ["execution", "coding"],
        "allowed_tools": ["python", "shell", "filesystem"],
        "preferred_model_classes": ["CODE"],
        "memory_access": ["working"],
        "permissions": ["shell_exec"],
        "verification_policy": "strict",
        "system_prompt": (
            "You are Silverwing Engineer. You implement production-grade "
            "solutions, write tests, and ensure robustness."
        ),
        "model_preference": "code-specialized",
    },
    {
        "agent_id": "coder",
        "role": "coder",
        "capabilities": ["coding"],
        "allowed_tools": ["python", "filesystem"],
        "preferred_model_classes": ["CODE"],
        "memory_access": ["working"],
        "permissions": ["code_exec"],
        "verification_policy": "standard",
        "system_prompt": (
            "You are Silverwing Coder. You write and iterate on scripts "
            "and small programs to support research and analysis."
        ),
        "model_preference": "code-specialized",
    },
    {
        "agent_id": "librarian",
        "role": "librarian",
        "capabilities": ["librarian", "memory_management", "research"],
        "allowed_tools": ["memory_read", "memory_write", "knowledge_graph",
                          "web_search"],
        "preferred_model_classes": ["LOCAL_OPEN_WEIGHT", "FREE_TIER"],
        "memory_access": ["working", "episodic", "semantic", "procedural"],
        "permissions": ["memory_write", "knowledge_write"],
        "verification_policy": "standard",
        "system_prompt": (
            "You are Silverwing Librarian. You curate knowledge, maintain "
            "the knowledge graph, and ensure information is properly "
            "indexed and retrievable."
        ),
        "model_preference": "fast-reasoning",
    },
    {
        "agent_id": "planner",
        "role": "planner",
        "capabilities": ["planning", "orchestration"],
        "allowed_tools": ["memory_read", "knowledge_graph", "model_inference"],
        "preferred_model_classes": ["REASONING", "LARGE_FRONTIER"],
        "memory_access": ["working", "semantic"],
        "permissions": ["planning"],
        "verification_policy": "standard",
        "system_prompt": (
            "You are Silverwing Planner. You break down complex objectives "
            "into structured sub-missions and task sequences."
        ),
        "model_preference": "deep-thinking",
    },
]


class AgentScheduler:
    """Matches tasks to agents and tracks agent load."""

    def __init__(self) -> None:
        self._definitions: List[Dict[str, Any]] = _AGENT_DEFINITIONS
        self._agent_specs: Dict[str, AgentSpec] = {
            d["agent_id"]: self._to_spec(d) for d in self._definitions
        }
        # Track current load: {agent_id: int}
        self._load: Dict[str, int] = {d["agent_id"]: 0 for d in self._definitions}
        # Track running tasks: {task_id: agent_id}
        self._assignments: Dict[str, str] = {}
        self._max_concurrent: int = 3

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def agent_ids(self) -> List[str]:
        return list(self._agent_specs.keys())

    def get_spec(self, agent_id: str) -> Optional[AgentSpec]:
        return self._agent_specs.get(agent_id)

    def all_specs(self) -> List[AgentSpec]:
        return list(self._agent_specs.values())

    def capabilities(self) -> List[str]:
        """Return the union of all agent capabilities."""

        caps: List[str] = []
        for spec in self._agent_specs.values():
            for c in spec.capabilities:
                if c not in caps:
                    caps.append(c)
        return caps

    def schedule(self, task: TaskSpec) -> AgentSpec:
        """Assign *task* to the best available agent.

        Selection criteria (in priority order):
        1. The agent's capabilities must include the task's capability.
        2. The agent must have at least one allowed tool matching the
           task's required tools (at least one overlap).
        3. Among matching agents, prefer the one with the lowest current
           load.
        4. If the task priority is CRITICAL, skip the load cap.
        """

        capability = task.capability
        required_tools = set(task.required_tools)

        candidates: List[tuple[int, str]] = []

        for agent_id, spec in self._agent_specs.items():
            # Criterion 1: capability match
            if capability not in spec.capabilities:
                continue

            # Criterion 2: tool overlap (at least one required tool allowed)
            allowed = set(spec.allowed_tools)
            if required_tools and not (required_tools & allowed):
                # The agent can still be selected if it has model_inference
                # (it can call the model directly for some steps).
                if "model_inference" not in allowed:
                    continue

            # Criterion 3: lower load is better
            candidates.append((self._load[agent_id], agent_id))

        if not candidates:
            # Fallback: pick any agent that has the capability
            for agent_id, spec in self._agent_specs.items():
                if capability in spec.capabilities:
                    return spec

        # Sort by load ascending
        candidates.sort(key=lambda x: x[0])

        # Load cap check (except for critical tasks)
        if task.priority == TaskPriority.CRITICAL and candidates:
            _, best_id = candidates[0]
        elif candidates:
            best_load, best_id = candidates[0]
            if best_load >= self._max_concurrent:
                # Still assign — the Orchestrator will serialize
                _, best_id = candidates[0]
            else:
                best_id = candidates[0][1]
        else:
            best_id = candidates[0][1]

        # Record assignment
        task.agent_id = best_id
        task.agent_role = self._agent_specs[best_id].role
        task.status = TaskStatus.ASSIGNED
        self._load[best_id] += 1
        self._assignments[task.task_id] = best_id

        return self._agent_specs[best_id]

    def release(self, task: TaskSpec) -> None:
        """Mark a task as complete and free the agent's capacity."""

        agent_id = self._assignments.pop(task.task_id, None)
        if agent_id and agent_id in self._load:
            self._load[agent_id] = max(0, self._load[agent_id] - 1)
        task.status = TaskStatus.COMPLETED

    def release_failed(self, task: TaskSpec) -> None:
        """Mark a task as failed and free the agent's capacity."""

        agent_id = self._assignments.pop(task.task_id, None)
        if agent_id and agent_id in self._load:
            self._load[agent_id] = max(0, self._load[agent_id] - 1)
        task.status = TaskStatus.FAILED

    def load_summary(self) -> Dict[str, int]:
        return dict(self._load)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_spec(self, d: Dict[str, Any]) -> AgentSpec:
        return AgentSpec(
            agent_id=d["agent_id"],
            role=d["role"],
            capabilities=d["capabilities"],
            allowed_tools=d["allowed_tools"],
            preferred_model_classes=d["preferred_model_classes"],
            memory_access=d["memory_access"],
            permissions=d["permissions"],
            verification_policy=d["verification_policy"],
            system_prompt=d["system_prompt"],
            model_preference=d["model_preference"],
        )
