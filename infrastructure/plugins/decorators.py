"""
Decorators for easy plugin authoring.

Provides @plugin and @hook decorators that simplify creating plugins.
"""

from __future__ import annotations
import functools
from typing import Dict, List, Optional, Any, Callable, Type
from dataclasses import dataclass

from .types import PluginBase, PluginManifest, PluginVersion, PluginHook, PluginPermission
from .context import PluginContext


class plugin:
    """
    Class decorator for defining a plugin.

    Usage:
        @plugin(
            id="my-plugin",
            name="My Plugin",
            version="1.0.0",
            permissions=["network:http"],
            hooks=["chat:before_response"],
        )
        class MyPlugin(PluginBase):
            async def initialize(self, ctx):
                ...

            async def on_chat_before_response(self, message):
                ...
    """

    def __init__(
        self,
        id: str,
        name: Optional[str] = None,
        version: str = "1.0.0",
        description: str = "",
        author: str = "",
        permissions: Optional[List[str]] = None,
        hooks: Optional[List[str]] = None,
        interfaces: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        **kwargs,
    ):
        self._manifest_data = {
            "id": id,
            "name": name or id,
            "version": version,
            "description": description,
            "author": author,
            "permissions": permissions or [],
            "hooks": hooks or [],
            "interfaces": interfaces or [],
            "tags": tags or [],
            **kwargs,
        }

    def __call__(self, cls: Type[PluginBase]) -> Type[PluginBase]:
        manifest = PluginManifest.from_dict(self._manifest_data)
        cls.__plugin_manifest__ = manifest

        original_init = getattr(cls, "initialize", None)

        if original_init:
            @functools.wraps(original_init)
            async def wrapped_init(self, ctx):
                self.metadata.manifest = manifest
                self.context = ctx
                return await original_init(self, ctx)
            cls.initialize = wrapped_init

        return cls


def hook(event: str):
    """
    Method decorator for hook handlers.

    Usage:
        @hook("chat:before_response")
        async def my_handler(self, message):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        fn.__hook_event__ = event
        return fn
    return decorator


def _collect_hooks(instance: PluginBase) -> Dict[str, Callable]:
    """Utility to collect hook-annotated methods from a plugin instance."""
    hooks: Dict[str, Callable] = {}
    for name in dir(instance):
        attr = getattr(instance, name, None)
        if attr and hasattr(attr, "__hook_event__"):
            event = attr.__hook_event__
            hook_method = f"on_{event.replace(':', '_')}"
            hooks[event] = attr
            setattr(instance, hook_method, attr)
    return hooks
