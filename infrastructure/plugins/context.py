"""
Plugin execution context.

Provides an isolated sandbox for each plugin with:
  - Capability-gated access to system resources
  - Restricted API surface
  - Logging with plugin identity
  - Config access
  - Hook emission
"""

from __future__ import annotations
import logging
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass, field

from .types import PluginManifest, PluginPermission


@dataclass
class PluginContext:
    """
    Execution context injected into every plugin.

    Plugins interact with Jarvis ONLY through this context.
    No direct access to core systems.
    """

    plugin_id: str
    manifest: PluginManifest
    config: Dict[str, Any] = field(default_factory=dict)
    logger: Optional[logging.Logger] = None
    data_dir: str = ""
    _capabilities: Dict[str, Callable] = field(default_factory=dict)

    def has_permission(self, permission: PluginPermission) -> bool:
        return permission in self.manifest.permissions

    def require_permission(self, permission: PluginPermission):
        if not self.has_permission(permission):
            raise PermissionError(
                f"Plugin '{self.plugin_id}' does not have permission: {permission.value}"
            )

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set_config(self, key: str, value: Any):
        self.config[key] = self.config.get("__internal__", {})
        self.config[key] = value

    def log_info(self, message: str, **kwargs):
        if self.logger:
            self.logger.info(f"[plugin:{self.plugin_id}] {message}", extra=kwargs)

    def log_warning(self, message: str, **kwargs):
        if self.logger:
            self.logger.warning(f"[plugin:{self.plugin_id}] {message}", extra=kwargs)

    def log_error(self, message: str, **kwargs):
        if self.logger:
            self.logger.error(f"[plugin:{self.plugin_id}] {message}", extra=kwargs)

    def call(self, capability: str, *args, **kwargs) -> Any:
        fn = self._capabilities.get(capability)
        if not fn:
            raise RuntimeError(f"Capability '{capability}' not available")
        return fn(*args, **kwargs)

    def bind_capability(self, name: str, fn: Callable):
        self._capabilities[name] = fn

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "permissions": [p.value for p in self.manifest.permissions],
            "config_keys": list(self.config.keys()),
        }
