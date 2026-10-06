"""
API subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ApiPluginInterface(ABC):
    """Interface for plugins that extend API capabilities."""

    @abstractmethod
    async def on_api_before_request(self, method: str, path: str,
                                     headers: Dict[str, str],
                                     body: Any) -> Optional[Dict[str, Any]]:
        """Called before an API request is processed. Return modified request or None."""
        ...

    @abstractmethod
    async def on_api_after_response(self, method: str, path: str,
                                     status_code: int, body: Any) -> None:
        """Called after an API response is sent."""
        ...
