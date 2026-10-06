"""
Jarvis Plugin System.

Provides a complete plugin and extension architecture with:
  - Dynamic discovery and registration (file system + packages)
  - Isolated lifecycle management (discover → install → enable → disable → uninstall)
  - Secure execution boundaries (capability-gated PluginContext)
  - Granular permission model (16 permission types)
  - Event-driven hook system (22 standardized hooks across all subsystems)
  - Standardized subsystem interfaces (chat, agent, memory, voice, automation, API, webhook)
  - Per-plugin configuration with schema validation
  - Dependency resolution with version compatibility
  - Versioning and host compatibility checks
  - Decorators for easy plugin authoring
"""

from .types import (
    PluginBase, PluginManifest, PluginMetadata, PluginState,
    PluginVersion, PluginPermission, PluginHook, PluginDependency,
)
from .context import PluginContext as PluginExecContext
from .registry import PluginRegistry
from .loader import PluginLoader, PluginLoadError
from .lifecycle import PluginLifecycleManager, LifecycleEvent
from .context import PluginContext as PluginExecContext
from .hook import HookSystem, HookResult, HookRegistration
from .capabilities import CapabilityRegistry, CapabilityRegistration
from .config import PluginConfigManager, PluginConfigError
from .dependencies import DependencyResolver, DependencyError
from .decorators import plugin as plugin_decorator, hook as hook_decorator
from .interfaces import (
    ChatPluginInterface,
    AgentPluginInterface,
    MemoryPluginInterface,
    VoicePluginInterface,
    AutomationPluginInterface,
    ApiPluginInterface,
    WebhookPluginInterface,
)

__all__ = [
    "PluginBase", "PluginManifest", "PluginMetadata", "PluginState",
    "PluginVersion", "PluginPermission", "PluginHook", "PluginDependency",
    "PluginExecContext",
    "PluginRegistry", "PluginLoader", "PluginLoadError",
    "PluginLifecycleManager", "LifecycleEvent",
    "HookSystem", "HookResult", "HookRegistration",
    "CapabilityRegistry", "CapabilityRegistration",
    "PluginConfigManager", "PluginConfigError",
    "DependencyResolver", "DependencyError",
    "plugin_decorator", "hook_decorator",
    "ChatPluginInterface", "AgentPluginInterface",
    "MemoryPluginInterface", "VoicePluginInterface",
    "AutomationPluginInterface", "ApiPluginInterface",
    "WebhookPluginInterface",
]
