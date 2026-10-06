"""
Voice subsystem plugin interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class VoicePluginInterface(ABC):
    """Interface for plugins that extend voice capabilities."""

    @abstractmethod
    async def on_voice_before_synthesis(self, text: str, voice: str,
                                         params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called before TTS synthesis. Return modified params or None."""
        ...

    @abstractmethod
    async def on_voice_after_recognition(self, audio: bytes, text: str,
                                          confidence: float) -> None:
        """Called after speech recognition completes."""
        ...
