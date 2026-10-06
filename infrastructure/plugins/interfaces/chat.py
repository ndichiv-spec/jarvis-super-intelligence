"""
Chat subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ChatPluginInterface(ABC):
    """Interface for plugins that extend chat capabilities."""

    @abstractmethod
    async def on_chat_before_response(self, conversation_id: str, message: str,
                                       context: Dict[str, Any]) -> Optional[str]:
        """Called before the AI generates a response. Return modified message or None."""
        ...

    @abstractmethod
    async def on_chat_after_response(self, conversation_id: str, message: str,
                                      response: str, context: Dict[str, Any]) -> None:
        """Called after a response is generated."""
        ...

    @abstractmethod
    async def on_chat_message_filter(self, message: str) -> str:
        """Filter or transform a message before processing."""
        ...
