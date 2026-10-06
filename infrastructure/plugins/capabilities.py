"""
Plugin capability and permission registry.

Maps declared PluginPermissions to actual system functions.
Controls what a plugin is allowed to do at runtime.
"""

from __future__ import annotations
import logging
from typing import Dict, Set, Callable, Any, Optional
from dataclasses import dataclass, field

from .types import PluginPermission, PluginManifest
from .context import PluginContext

logger = logging.getLogger(__name__)


@dataclass
class CapabilityRegistration:
    permission: PluginPermission
    name: str
    fn: Callable
    description: str = ""


class CapabilityRegistry:
    """
    Maps PluginPermission enums to implementor functions.

    When a plugin declares a permission in its manifest, the corresponding
    capabilities are bound into its PluginContext at activation time.
    """

    def __init__(self):
        self._registrations: Dict[PluginPermission, CapabilityRegistration] = {}

    def register(self, permission: PluginPermission, name: str, fn: Callable,
                 description: str = ""):
        self._registrations[permission] = CapabilityRegistration(
            permission=permission, name=name, fn=fn, description=description,
        )

    def get(self, permission: PluginPermission) -> Optional[CapabilityRegistration]:
        return self._registrations.get(permission)

    def bind_for_plugin(self, manifest: PluginManifest, context: PluginContext):
        """Bind all declared permissions as callable capabilities in context."""
        for perm in manifest.permissions:
            reg = self._registrations.get(perm)
            if reg:
                context.bind_capability(reg.name, reg.fn)
                logger.debug(f"Bound '{reg.name}' for plugin '{manifest.id}'")
            else:
                logger.warning(f"Permission '{perm.value}' requested by '{manifest.id}' has no registered handler")

    def list_permissions(self) -> Dict[str, str]:
        return {p.value: reg.description for p, reg in self._registrations.items()}

    @classmethod
    def default_registry(cls) -> CapabilityRegistry:
        """Create a registry with all standard capabilities."""
        reg = cls()

        reg.register(PluginPermission.NETWORK_HTTP, "http_request",
                     lambda *a, **kw: None,  # stub - real impl in infrastructure.resilience
                     description="Make HTTP requests to external services")

        reg.register(PluginPermission.FILE_READ, "file_read",
                     lambda *a, **kw: None,
                     description="Read files from plugin data directory")

        reg.register(PluginPermission.FILE_WRITE, "file_write",
                     lambda *a, **kw: None,
                     description="Write files to plugin data directory")

        reg.register(PluginPermission.DATABASE_READ, "db_query",
                     lambda *a, **kw: None,
                     description="Read from the database")

        reg.register(PluginPermission.DATABASE_WRITE, "db_execute",
                     lambda *a, **kw: None,
                     description="Write to the database")

        reg.register(PluginPermission.AI_INFERENCE, "ai_infer",
                     lambda *a, **kw: None,
                     description="Call AI models for inference")

        reg.register(PluginPermission.OBSERVABILITY_EMIT, "emit_metric",
                     lambda *a, **kw: None,
                     description="Emit custom metrics to observability system")

        reg.register(PluginPermission.MEMORY_READ, "memory_search",
                     lambda *a, **kw: None,
                     description="Search Jarvis memory stores")

        reg.register(PluginPermission.MEMORY_WRITE, "memory_store",
                     lambda *a, **kw: None,
                     description="Write to Jarvis memory stores")

        return reg


# Default capability permission mapping for each hook
HOOK_PERMISSION_MAP: Dict[str, PluginPermission] = {
    "chat:before_response": PluginPermission.AI_INFERENCE,
    "chat:after_response": PluginPermission.AI_INFERENCE,
    "chat:message_filter": PluginPermission.AI_INFERENCE,
    "agent:before_execute": PluginPermission.EXECUTE_CODE,
    "agent:after_execute": PluginPermission.EXECUTE_CODE,
    "agent:tool_invoke": PluginPermission.EXECUTE_CODE,
    "memory:before_store": PluginPermission.MEMORY_WRITE,
    "memory:after_retrieve": PluginPermission.MEMORY_READ,
    "memory:before_search": PluginPermission.MEMORY_READ,
    "voice:before_synthesis": PluginPermission.AI_INFERENCE,
    "voice:after_recognition": PluginPermission.AI_INFERENCE,
    "automation:before_execute": PluginPermission.EXECUTE_CODE,
    "automation:after_execute": PluginPermission.EXECUTE_CODE,
    "api:before_request": PluginPermission.API_CALL,
    "api:after_response": PluginPermission.API_CALL,
    "system:startup": PluginPermission.SYSTEM_CONFIG,
    "system:shutdown": PluginPermission.SYSTEM_CONFIG,
    "system:health_check": PluginPermission.SYSTEM_CONFIG,
    "webhook:received": PluginPermission.WEBHOOK_RECEIVE,
    "observability:metric": PluginPermission.OBSERVABILITY_EMIT,
    "observability:log": PluginPermission.OBSERVABILITY_EMIT,
}
