"""
Event-driven hook system for plugin extension points.

Subsystems emit events at key boundaries; plugins register handlers
to intercept or observe those events.
"""

from __future__ import annotations
import asyncio
import time
import logging
from typing import Dict, List, Callable, Any, Awaitable, Optional, Tuple
from dataclasses import dataclass, field

from .types import PluginHook, PluginManifest
from .capabilities import HOOK_PERMISSION_MAP

logger = logging.getLogger(__name__)

HookHandler = Callable[..., Awaitable[Any]]


@dataclass
class HookRegistration:
    plugin_id: str
    hook: PluginHook
    handler: HookHandler
    priority: int = 0
    created_at: float = field(default_factory=time.time)


class HookResult:
    """
    Result of a hook execution chain.

    Collects all handler responses, errors, and timing.
    """

    def __init__(self, hook: str):
        self.hook = hook
        self.results: List[Any] = []
        self.errors: List[Tuple[str, str]] = []
        self.duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hook": self.hook,
            "handler_count": len(self.results) + len(self.errors),
            "error_count": len(self.errors),
            "duration_ms": round(self.duration_ms, 2),
        }


class HookSystem:
    """
    Central hub for hook registration and emission.

    Usage (subsystem emits):
        hook_result = await hooks.emit(PluginHook.CHAT_BEFORE_RESPONSE, message=msg)

    Usage (plugin registers):
        @hooks.on(PluginHook.CHAT_BEFORE_RESPONSE)
        async def my_handler(message): ...
    """

    def __init__(self):
        self._handlers: Dict[PluginHook, List[HookRegistration]] = {}
        self._lock = asyncio.Lock()

    def on(self, hook: PluginHook, priority: int = 0):
        """Decorator to register a hook handler."""
        def decorator(fn: HookHandler):
            self.register("__system__", hook, fn, priority)
            return fn
        return decorator

    def register(self, plugin_id: str, hook: PluginHook, handler: HookHandler,
                 priority: int = 0):
        if hook not in self._handlers:
            self._handlers[hook] = []
        self._handlers[hook].append(HookRegistration(
            plugin_id=plugin_id, hook=hook, handler=handler, priority=priority,
        ))
        self._handlers[hook].sort(key=lambda r: r.priority, reverse=True)
        logger.debug(f"Handler registered: {plugin_id} @ {hook.value}")

    def unregister(self, plugin_id: str, hook: Optional[PluginHook] = None):
        """Remove all handlers for a plugin, optionally for a specific hook."""
        for h in list(self._handlers.keys()):
            if hook and h != hook:
                continue
            self._handlers[h] = [
                r for r in self._handlers[h] if r.plugin_id != plugin_id
            ]

    def handlers_for(self, hook: PluginHook) -> List[HookRegistration]:
        return list(self._handlers.get(hook, []))

    async def emit(self, hook: PluginHook, *args, **kwargs) -> HookResult:
        """
        Emit an event to all registered hook handlers.

        Handlers with higher priority run first. If a handler raises,
        subsequent handlers still run. All results and errors are collected.
        """
        result = HookResult(hook.value)
        handlers = self._handlers.get(hook, [])
        if not handlers:
            return result

        start = time.time()
        for registration in handlers:
            try:
                handler_result = await registration.handler(*args, **kwargs)
                result.results.append(handler_result)
            except Exception as e:
                logger.warning(f"Hook handler '{registration.plugin_id}@{hook.value}' failed: {e}")
                result.errors.append((registration.plugin_id, str(e)))

        result.duration_ms = (time.time() - start) * 1000
        return result

    async def emit_filter(self, hook: PluginHook, value: Any, *args, **kwargs) -> Any:
        """
        Emit a filter hook where each handler can modify a value.

        The value is passed through each handler sequentially.
        Useful for hooks like chat:message_filter.
        """
        handlers = self._handlers.get(hook, [])
        if not handlers:
            return value

        current = value
        for registration in handlers:
            try:
                current = await registration.handler(current, *args, **kwargs)
            except Exception as e:
                logger.warning(f"Filter handler '{registration.plugin_id}@{hook.value}' failed: {e}")
        return current

    def hook_count(self) -> Dict[str, int]:
        return {h.value: len(r) for h, r in self._handlers.items()}

    def snapshot(self) -> Dict[str, Any]:
        return {
            "total_hooks": len(self._handlers),
            "total_handlers": sum(len(r) for r in self._handlers.values()),
            "by_hook": self.hook_count(),
        }

    def clear_plugin(self, plugin_id: str):
        self.unregister(plugin_id)
