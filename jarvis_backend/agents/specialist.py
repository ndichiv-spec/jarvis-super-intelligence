"""Specialist agent framework for JARVIS multi-agent orchestration.

Each specialist agent is a role-based AI agent that connects to the JARVIS
capability registry and can execute capabilities, use tools, and communicate
with other agents via the message board.

Roles (matching the upgrade plan):
  - orchestrator: Coordinates other agents, assigns tasks, aggregates results
  - researcher:   Performs web research, knowledge gathering, arXiv search
  - analyst:      Data analysis, scientific computation, reasoning
  - engineer:     Code generation, browser automation, file system operations
  - verifier:     Validation, testing, fact-checking, quality control

Each agent:
  1. Receives tasks/messages via the message board
  2. Uses the capability registry to execute capabilities (brain, tools, etc.)
  3. Can spawn sub-agents for complex multi-step workflows
  4. Reports results back to the sender or message board

Usage:
    agent = SpecialistAgent("researcher-abc123", "researcher", config={...})
    result = await agent.execute({"action": "research", "query": "Tesla FSD"})
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.agents.specialist")


# Role definitions: maps role name to capabilities and description
_ROLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "orchestrator": {
        "description": "Coordinates other agents, assigns tasks, aggregates results",
        "capabilities": ["brain", "memory", "task", "conversation"],
        "default_model": "gpt-4o",
        "max_sub_agents": 10,
    },
    "researcher": {
        "description": "Web research, knowledge gathering, arXiv search, RSS ingestion",
        "capabilities": ["research_cortex", "knowledge", "browser", "science"],
        "default_model": "gpt-4o-mini",
        "max_sub_agents": 3,
    },
    "analyst": {
        "description": "Data analysis, scientific computation, mathematical reasoning",
        "capabilities": ["science", "brain", "knowledge", "task"],
        "default_model": "gpt-4o",
        "max_sub_agents": 2,
    },
    "engineer": {
        "description": "Code generation, browser automation, file system operations, tool use",
        "capabilities": ["browser", "github", "science", "brain"],
        "default_model": "o1-preview",
        "max_sub_agents": 3,
    },
    "verifier": {
        "description": "Validation, testing, fact-checking, quality control, security review",
        "capabilities": ["science", "brain", "knowledge", "task"],
        "default_model": "gpt-4o",
        "max_sub_agents": 2,
    },
}


class SpecialistAgent:
    """A role-based AI agent that can execute JARVIS capabilities.

    Each agent has:
    - A unique ID (from the graph store)
    - A role defining its capabilities and behavior
    - A configuration dict for role-specific settings
    - Access to the JARVIS capability registry
    - A message board for inter-agent communication
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        config: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None,
    ):
        self.agent_id = agent_id
        self.role = role
        self.config = config or {}
        self._capabilities = capabilities or []
        self._registry = None
        self._store = None
        self._execution_history: List[Dict[str, Any]] = []
        self._memory: List[Dict[str, Any]] = []

        role_def = _ROLE_DEFINITIONS.get(role, _ROLE_DEFINITIONS["researcher"])
        self._role_def = role_def
        self._default_model = self.config.get("model", role_def["default_model"])
        self._max_sub_agents = self.config.get("max_sub_agents", role_def["max_sub_agents"])

    # -- registry access ----------------------------------------------------

    def _get_registry(self):
        if self._registry is None:
            from jarvis_backend.capabilities import get_registry
            self._registry = get_registry()
        return self._registry

    def _get_store(self):
        if self._store is None:
            from jarvis_backend.agents.graph_store import AgentGraphStore
            self._store = AgentGraphStore.get_shared()
        return self._store

    @property
    def available_capabilities(self) -> List[str]:
        """List of capability names this agent can execute."""
        reg = self._get_registry()
        try:
            registered = set(reg.list_all())
        except Exception:
            registered = set()
        return [c for c in self._capabilities if c in registered]

    @property
    def role_description(self) -> str:
        return self._role_def["description"]

    # -- memory management --------------------------------------------------

    def remember(self, entry: Dict[str, Any]) -> None:
        """Add an entry to the agent's working memory."""
        self._memory.append({
            **entry,
            "timestamp": time.time(),
        })
        # Cap memory to prevent unbounded growth
        if len(self._memory) > 100:
            self._memory = self._memory[-50:]

    def recall(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Simple recall from working memory (keyword matching)."""
        results = []
        query_lower = query.lower()
        for entry in self._memory:
            text = json.dumps(entry, default=str).lower()
            if query_lower in text:
                results.append(entry)
        return results[-top_k:]

    # -- capability execution ----------------------------------------------

    async def execute_capability(
        self,
        capability_name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a capability through the JARVIS capability registry."""
        reg = self._get_registry()
        cap = reg.get(capability_name)

        if cap is None:
            return {
                "success": False,
                "error": f"Capability '{capability_name}' not available",
                "error_type": "NOT_FOUND",
            }

        from jarvis_backend.capability import ExecutionContext

        context = ExecutionContext(
            user_id=f"agent:{self.agent_id}",
            session_id=f"agent-session-{self.agent_id[:8]}",
            correlation_id=f"agent-{uuid.uuid4().hex[:12]}",
        )

        start = time.time()
        try:
            result = await cap.execute({"action": action, "params": params or {}}, context)
            result_dict = result.to_dict() if hasattr(result, "to_dict") else {
                "success": result.success,
                "data": result.data,
                "error": result.error,
            }
            result_dict["latency_ms"] = round((time.time() - start) * 1000, 2)
            self._execution_history.append({
                "capability": capability_name,
                "action": action,
                "success": result_dict.get("success", False),
                "timestamp": time.time(),
            })
            return result_dict
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "latency_ms": round((time.time() - start) * 1000, 2),
            }
            self._execution_history.append({
                "capability": capability_name,
                "action": action,
                "success": False,
                "error": str(e),
                "timestamp": time.time(),
            })
            return error_result

    async def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task request. Delegates to the appropriate capability.

        The request dict should contain:
        - capability: Name of capability to use
        - action: Action to perform
        - params: Parameters for the action
        - Or: query (free-form, handled by brain/reasoning)
        """
        capability = request.get("capability")
        action = request.get("action", "")
        params = request.get("params", {})

        # If no specific capability, use the brain for reasoning
        if not capability:
            query = request.get("query", request.get("task", ""))
            memory = self.recall(query)

            result = await self.execute_capability(
                "brain", "process",
                {
                    "query": query,
                    "role": self.role,
                    "role_description": self.role_description,
                    "memory_context": memory,
                    "model": self._default_model,
                    "agent_id": self.agent_id,
                },
            )
            self.remember({"type": "reasoning", "query": query, "result": result})
            return result

        # Execute the requested capability
        result = await self.execute_capability(capability, action, params)
        self.remember({"type": "action", "capability": capability, "action": action, "result": result})
        return result

    # -- sub-agent spawning -------------------------------------------------

    async def spawn_sub_agent(
        self,
        role: str = "researcher",
        config: Optional[Dict[str, Any]] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Spawn a child agent to handle a sub-task."""
        store = self._get_store()
        parent = await store.get_agent(self.agent_id)
        child_config = {**(config or {})}
        if parent and parent.config.get("_owner_id"):
            child_config["_owner_id"] = parent.config["_owner_id"]
        agent_id = await store.create_agent(
            name=f"{self.role}-sub-{uuid.uuid4().hex[:8]}",
            role=role,
            config=child_config,
            parent_id=self.agent_id,
        )

        # Update parent's children list
        if parent and agent_id not in parent.children_ids:
            parent.children_ids.append(agent_id)

        # Start the sub-agent via the lifecycle manager
        from jarvis_backend.agents.lifecycle import AgentLifecycleManager
        manager = AgentLifecycleManager.get_shared()
        safe_request = await manager._initialize_lifecycle_checkpoint(agent_id, request)

        # Register the config and spawn
        manager._agent_configs[agent_id] = {
            "name": f"sub-{role}",
            "role": role,
            "config": child_config,
            "capabilities": _ROLE_DEFINITIONS.get(role, {}).get("capabilities", []),
            "request": safe_request,
            "spawned_at": time.time(),
        }

        await store.update_agent_status(agent_id, "spawned")
        task = asyncio.create_task(manager._run_agent(agent_id))
        manager._tasks[agent_id] = task

        log.info("Sub-agent spawned: %s (parent=%s)", agent_id, self.agent_id)
        return agent_id

    # -- conversation -------------------------------------------------------

    async def think(self, prompt: str, tools: Optional[List[Dict[str, Any]]] = None) -> str:
        """Use the brain capability to reason about a prompt.

        Args:
            prompt: The reasoning prompt.
            tools: Optional list of tool descriptions to include in context.

        Returns:
            The reasoning result (string).
        """
        tool_descs = ""
        if tools:
            tool_descs = "\n".join(f"- {t.get('name', '')}: {t.get('description', '')}" for t in tools)

        result = await self.execute_capability(
            "brain", "process",
            {
                "query": prompt,
                "role": self.role,
                "role_description": self.role_description,
                "system_context": f"You are a {self.role} agent. {self.role_description}",
                "available_tools": tool_descs,
                "model": self._default_model,
                "agent_id": self.agent_id,
            },
        )

        if result.get("success") and result.get("data"):
            data = result.get("data", {})
            if isinstance(data, dict) and "response" in data:
                return data["response"]
            return json.dumps(data, default=str)
        return result.get("error", "No response")

    async def shutdown(self) -> bool:
        """Clean shutdown of the agent's resources."""
        self._memory.clear()
        self._execution_history.clear()
        return True


# ---------------------------------------------------------------------------
# Factory: create the right specialist agent for a role
# ---------------------------------------------------------------------------

def create_agent(agent_id: str, role: str, config: Optional[Dict[str, Any]] = None) -> SpecialistAgent:
    """Factory function to create a specialist agent of the given role."""
    return SpecialistAgent(agent_id, role, config)


def get_role_definitions() -> Dict[str, Dict[str, Any]]:
    """Return all available role definitions."""
    return _ROLE_DEFINITIONS.copy()


__all__ = [
    "SpecialistAgent",
    "create_agent",
    "get_role_definitions",
    "ROLE_DEFINITIONS",
]

# Module-level alias for convenience
ROLE_DEFINITIONS = _ROLE_DEFINITIONS
