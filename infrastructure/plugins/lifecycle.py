"""
Plugin lifecycle management.

Orchestrates the full lifecycle: discover → install → enable → disable → uninstall.
"""

from __future__ import annotations
import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path

from .types import PluginManifest, PluginMetadata, PluginState, PluginBase, PluginVersion
from .registry import PluginRegistry
from .loader import PluginLoader, PluginLoadError
from .context import PluginContext
from .dependencies import DependencyResolver, MissingDependencyError, VersionConflictError
from .config import PluginConfigManager
from .hook import HookSystem
from .capabilities import CapabilityRegistry

logger = logging.getLogger(__name__)


@dataclass
class LifecycleEvent:
    plugin_id: str
    action: str
    success: bool
    message: str = ""
    duration_ms: float = 0.0


class PluginLifecycleManager:
    """
    Manages the full plugin lifecycle.

    States: DISCOVERED → INSTALLED → ENABLED ⟷ DISABLED → UNINSTALLED
                                     ↓
                                   ERROR
    """

    def __init__(
        self,
        registry: PluginRegistry,
        loader: PluginLoader,
        hooks: HookSystem,
    ):
        self.registry = registry
        self.loader = loader
        self.hooks = hooks
        self._events: List[LifecycleEvent] = []
        self._lock = asyncio.Lock()

    async def discover(self, plugin_dirs: Optional[List[Path]] = None) -> List[PluginManifest]:
        """Discover plugins from directories."""
        if plugin_dirs:
            for d in plugin_dirs:
                self.loader.add_directory(d)

        discovered = self.loader.discover()
        manifests: List[PluginManifest] = []

        for manifest, error in discovered:
            if error:
                logger.warning(f"Plugin {manifest.id} discovery failed: {error}")
                continue
            try:
                self.registry.register(manifest)
                manifests.append(manifest)
            except ValueError as e:
                logger.warning(f"Plugin {manifest.id} registration failed: {e}")

        logger.info(f"Discovered {len(manifests)} plugins")
        return manifests

    async def install(self, plugin_id: str) -> LifecycleEvent:
        """Install a plugin: resolve deps, create context."""
        start = time.time()
        meta = self.registry.get(plugin_id)
        if not meta:
            return LifecycleEvent(plugin_id, "install", False, "Not found")

        try:
            missing = self.registry.dependency_resolver.get_missing_dependencies(meta.manifest)
            if missing:
                names = [d.plugin_id for d in missing]
                raise MissingDependencyError(f"Missing dependencies: {names}")

            conflicts = self.registry.dependency_resolver.get_version_conflicts(meta.manifest)
            if conflicts:
                msgs = [f"{d.plugin_id} needs {d.version}, got {v}" for d, v in conflicts]
                raise VersionConflictError("; ".join(msgs))

            self.registry.create_context(plugin_id)

            meta.config = self.registry.config_manager.load(plugin_id)
            self.registry.mark_installed(plugin_id)

            elapsed = (time.time() - start) * 1000
            event = LifecycleEvent(plugin_id, "install", True, duration_ms=elapsed)
            self._events.append(event)
            logger.info(f"Plugin installed: {plugin_id}")
            return event

        except Exception as e:
            self.registry.mark_error(plugin_id, str(e))
            elapsed = (time.time() - start) * 1000
            event = LifecycleEvent(plugin_id, "install", False, str(e), elapsed)
            self._events.append(event)
            return event

    async def enable(self, plugin_id: str) -> LifecycleEvent:
        """Enable a plugin: load code, register hooks, initialize."""
        start = time.time()
        meta = self.registry.get(plugin_id)
        if not meta:
            return LifecycleEvent(plugin_id, "enable", False, "Not found")

        if meta.state == PluginState.ENABLED:
            return LifecycleEvent(plugin_id, "enable", True, "Already enabled")

        try:
            instance = self.registry.get_instance(plugin_id)
            if not instance:
                loaded = self.loader.load_from_directory(plugin_id)
                if loaded:
                    manifest, instance = loaded
                else:
                    loaded_pkg = self.loader.load_from_package(plugin_id)
                    manifest, instance = loaded_pkg

                # Re-register with loaded manifest if discovered version was placeholder
                existing = self.registry.get(plugin_id)
                if existing and existing.manifest.version == PluginVersion(0, 0, 0):
                    self.registry.unregister(plugin_id)
                    self.registry.register(manifest, instance)
                else:
                    self.registry._instances[plugin_id] = instance

            ctx = self.registry.get_context(plugin_id)
            if not ctx:
                ctx = self.registry.create_context(plugin_id)
                if not ctx:
                    raise RuntimeError("Failed to create plugin context")

            async with self._lock:
                await instance.initialize(ctx)

                for hook in meta.manifest.hooks:
                    handler_name = f"on_{hook.value.replace(':', '_')}"
                    handler = getattr(instance, handler_name, None)
                    if handler:
                        self.hooks.register(plugin_id, hook, handler)

            self.registry.mark_enabled(plugin_id)
            elapsed = (time.time() - start) * 1000
            event = LifecycleEvent(plugin_id, "enable", True, duration_ms=elapsed)
            self._events.append(event)
            logger.info(f"Plugin enabled: {plugin_id}")
            return event

        except Exception as e:
            self.registry.mark_error(plugin_id, str(e))
            elapsed = (time.time() - start) * 1000
            event = LifecycleEvent(plugin_id, "enable", False, str(e), elapsed)
            self._events.append(event)
            return event

    async def disable(self, plugin_id: str) -> LifecycleEvent:
        """Disable a plugin: shutdown, unregister hooks."""
        start = time.time()
        meta = self.registry.get(plugin_id)
        if not meta:
            return LifecycleEvent(plugin_id, "disable", False, "Not found")

        try:
            instance = self.registry.get_instance(plugin_id)
            if instance:
                await instance.shutdown()

            self.hooks.clear_plugin(plugin_id)
            self.loader.unload_plugin(plugin_id)
            self.registry.mark_disabled(plugin_id)

            elapsed = (time.time() - start) * 1000
            event = LifecycleEvent(plugin_id, "disable", True, duration_ms=elapsed)
            self._events.append(event)
            logger.info(f"Plugin disabled: {plugin_id}")
            return event

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            event = LifecycleEvent(plugin_id, "disable", False, str(e), elapsed)
            self._events.append(event)
            return event

    async def uninstall(self, plugin_id: str) -> LifecycleEvent:
        """Uninstall a plugin completely."""
        if self.registry.get(plugin_id) and self.registry.get(plugin_id).is_enabled:
            await self.disable(plugin_id)

        self.registry.unregister(plugin_id)
        event = LifecycleEvent(plugin_id, "uninstall", True)
        self._events.append(event)
        logger.info(f"Plugin uninstalled: {plugin_id}")
        return event

    async def enable_all(self) -> List[LifecycleEvent]:
        """Discover, install, and enable all plugins."""
        results: List[LifecycleEvent] = []
        manifests = await self.discover()
        for m in manifests:
            install_result = await self.install(m.id)
            results.append(install_result)
            if install_result.success:
                enable_result = await self.enable(m.id)
                results.append(enable_result)
        return results

    async def health_check(self, plugin_id: str) -> Dict[str, Any]:
        meta = self.registry.get(plugin_id)
        if not meta:
            return {"id": plugin_id, "status": "not_found"}
        instance = self.registry.get_instance(plugin_id)
        if not instance:
            return {"id": plugin_id, "state": meta.state.value, "status": "no_instance"}
        try:
            health = await instance.health_check()
            return {"id": plugin_id, "state": meta.state.value, **health}
        except Exception as e:
            return {"id": plugin_id, "state": meta.state.value, "status": "error", "error": str(e)}

    def get_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [
            {
                "plugin_id": e.plugin_id,
                "action": e.action,
                "success": e.success,
                "message": e.message,
                "duration_ms": round(e.duration_ms, 2),
            }
            for e in self._events[-limit:]
        ]
