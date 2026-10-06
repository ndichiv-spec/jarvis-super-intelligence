"""
Webhook subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class WebhookPluginInterface(ABC):
    """Interface for plugins that receive webhooks."""

    @abstractmethod
    async def on_webhook_received(self, source: str, event: str,
                                   payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called when a webhook is received. Return response data or None."""
        ...

    @abstractmethod
    async def on_observability_metric(self, name: str, value: float,
                                       labels: Dict[str, str]) -> None:
        """Called when a custom metric is emitted."""
        ...

    @abstractmethod
    async def on_observability_log(self, level: str, message: str,
                                    context: Dict[str, Any]) -> None:
        """Called when an observability log is emitted."""
        ...
