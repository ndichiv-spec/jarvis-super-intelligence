"""
Automation subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class AutomationPluginInterface(ABC):
    """Interface for plugins that extend automation capabilities."""

    @abstractmethod
    async def on_automation_before_execute(self, rule_id: str, action: str,
                                            context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called before an automation rule executes. Return modified context or None."""
        ...

    @abstractmethod
    async def on_automation_after_execute(self, rule_id: str, action: str,
                                           result: Any, context: Dict[str, Any]) -> None:
        """Called after an automation rule executes."""
        ...
