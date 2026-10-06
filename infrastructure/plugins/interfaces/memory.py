"""
Memory subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class MemoryPluginInterface(ABC):
    """Interface for plugins that extend memory capabilities."""

    @abstractmethod
    async def on_memory_before_store(self, namespace: str, key: str,
                                      value: Any, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called before storing to memory. Return modified data or None."""
        ...

    @abstractmethod
    async def on_memory_after_retrieve(self, namespace: str, key: str,
                                        value: Any) -> None:
        """Called after retrieving from memory."""
        ...

    @abstractmethod
    async def on_memory_before_search(self, namespace: str, query: str,
                                       limit: int) -> Optional[Dict[str, Any]]:
        """Called before searching memory. Return modified query params or None."""
        ...
