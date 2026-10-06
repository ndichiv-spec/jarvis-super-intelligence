"""
Standardized plugin interfaces for each Jarvis subsystem.

Each interface defines the contract a plugin must implement to integrate
with that subsystem. Plugins declare which interfaces they support in
their manifest.
"""

from .chat import ChatPluginInterface
from .agent import AgentPluginInterface
from .memory import MemoryPluginInterface
from .voice import VoicePluginInterface
from .automation import AutomationPluginInterface
from .api import ApiPluginInterface
from .webhook import WebhookPluginInterface

__all__ = [
    "ChatPluginInterface",
    "AgentPluginInterface",
    "MemoryPluginInterface",
    "VoicePluginInterface",
    "AutomationPluginInterface",
    "ApiPluginInterface",
    "WebhookPluginInterface",
]
