"""
Plugin registry: central directory of all known plugins.

Handles discovery, registration, lookup, and state tracking.
"""

from __future__ import annotations
import time
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from .types import (
    PluginManifest, PluginMetadata, PluginState, PluginVersion, PluginBase,
)
from .context import PluginContext
from .capabilities import CapabilityRegistry
from .hook import HookSystem
from .config import PluginConfigManager
from .dependencies import DependencyResolver

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Central directory of all known plugins.

    Maintains:
      - Registered plugin metadata
      - State machine (discovered -> installed -> enabled -> disabled)
      - Lookup by ID, interface, hook, tag, permission
    """

    def __init__(
        self,
        capabilities: Optional[CapabilityRegistry] = None,
        hooks: Optional[HookSystem] = None,
        config_manager: Optional[PluginConfigManager] = None,
    ):
        self._plugins: Dict[str, PluginMetadata] = {}
        self._instances: Dict[str, PluginBase] = {}
        self._contexts: Dict[str, PluginContext] = {}
        self.capabilities = capabilities or CapabilityRegistry.default_registry()
        self.hooks = hooks or HookSystem()
        self.config_manager = config_manager or PluginConfigManager()
        self.dependency_resolver = DependencyResolver()

    # ── Registration ────────────────────────────────────────

    def register(self, manifest: PluginManifest, instance: Optional[PluginBase] = None) -> PluginMetadata:
        if manifest.id in self._plugins:
            existing = self._plugins[manifest.id].manifest.version
            if manifest.version > existing:
                logger.info(f"Upgrading plugin '{manifest.id}': {existing} -> {manifest.version}")
            else:
                raise ValueError(f"Plugin '{manifest.id}' version {manifest.version} already registered")

        metadata = PluginMetadata(manifest=manifest)
        self._plugins[manifest.id] = metadata

        if instance:
            self._instances[manifest.id] = instance

        logger.info(f"Plugin registered: {manifest.id} v{manifest.version}")
        return metadata

    def unregister(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            self._instances.pop(plugin_id, None)
            self._contexts.pop(plugin_id, None)
            self.hooks.clear_plugin(plugin_id)
            logger.info(f"Plugin unregistered: {plugin_id}")
            return True
        return False

    # ── Lookup ──────────────────────────────────────────────

    def get(self, plugin_id: str) -> Optional[PluginMetadata]:
        return self._plugins.get(plugin_id)

    def get_instance(self, plugin_id: str) -> Optional[PluginBase]:
        return self._instances.get(plugin_id)

    def get_context(self, plugin_id: str) -> Optional[PluginContext]:
        return self._contexts.get(plugin_id)

    def list(self, state: Optional[PluginState] = None, include_error: bool = True) -> List[PluginMetadata]:
        plugins = list(self._plugins.values())
        if state:
            plugins = [p for p in plugins if p.state == state]
        if not include_error:
            plugins = [p for p in plugins if p.state != PluginState.ERROR]
        return plugins

    def find_by_hook(self, hook: str) -> List[PluginMetadata]:
        return [
            p for p in self._plugins.values()
            if p.is_enabled and any(h.value == hook for h in p.manifest.hooks)
        ]

    def find_by_interface(self, interface: str) -> List[PluginMetadata]:
        return [
            p for p in self._plugins.values()
            if interface in p.manifest.interfaces
        ]

    def find_by_tag(self, tag: str) -> List[PluginMetadata]:
        return [
            p for p in self._plugins.values()
            if tag in p.manifest.tags
        ]

    def find_by_permission(self, permission: str) -> List[PluginMetadata]:
        return [
            p for p in self._plugins.values()
            if any(perm.value == permission for perm in p.manifest.permissions)
        ]

    # ── State machine ───────────────────────────────────────

    def _transition(self, plugin_id: str, target: PluginState) -> Optional[PluginMetadata]:
        meta = self._plugins.get(plugin_id)
        if not meta:
            return None
        meta.state = target
        return meta

    def mark_installed(self, plugin_id: str) -> Optional[PluginMetadata]:
        meta = self._transition(plugin_id, PluginState.INSTALLED)
        if meta:
            meta.installed_at = time.time()
        return meta

    def mark_enabled(self, plugin_id: str) -> Optional[PluginMetadata]:
        meta = self._transition(plugin_id, PluginState.ENABLED)
        if meta:
            meta.enabled_at = time.time()
        return meta

    def mark_disabled(self, plugin_id: str) -> Optional[PluginMetadata]:
        return self._transition(plugin_id, PluginState.DISABLED)

    def mark_error(self, plugin_id: str, error: str) -> Optional[PluginMetadata]:
        meta = self._transition(plugin_id, PluginState.ERROR)
        if meta:
            meta.last_error = error
            meta.error_count += 1
        return meta

    # ── Context management ──────────────────────────────────

    def create_context(self, plugin_id: str) -> Optional[PluginContext]:
        meta = self._plugins.get(plugin_id)
        if not meta:
            return None

        import logging as _logging
        ctx = PluginContext(
            plugin_id=plugin_id,
            manifest=meta.manifest,
            config=meta.config,
            logger=_logging.getLogger(f"jarvis.plugin.{plugin_id}"),
            data_dir=f"data/plugins/{plugin_id}",
        )
        self.capabilities.bind_for_plugin(meta.manifest, ctx)
        self._contexts[plugin_id] = ctx
        return ctx

    # ── Snapshot ────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        return {
            "total": len(self._plugins),
            "enabled": sum(1 for p in self._plugins.values() if p.is_enabled),
            "disabled": sum(1 for p in self._plugins.values() if p.state == PluginState.DISABLED),
            "error": sum(1 for p in self._plugins.values() if p.state == PluginState.ERROR),
            "plugins": [m.to_dict() for m in self._plugins.values()],
        }
