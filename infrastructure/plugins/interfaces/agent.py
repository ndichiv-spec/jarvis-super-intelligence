"""
Agent subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Any


class AgentPluginInterface(ABC):
    """Interface for plugins that extend agent capabilities."""

    @abstractmethod
    async def on_agent_before_execute(self, agent_id: str, task: str,
                                       context: Dict[str, Any]) -> Optional[str]:
        """Called before an agent executes a task. Return modified task or None."""
        ...

    @abstractmethod
    async def on_agent_after_execute(self, agent_id: str, task: str,
                                      result: Any, context: Dict[str, Any]) -> None:
        """Called after an agent completes execution."""
        ...

    @abstractmethod
    async def on_agent_tool_invoke(self, agent_id: str, tool: str,
                                    args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called when an agent invokes a tool. Return modified args or None."""
        ...
