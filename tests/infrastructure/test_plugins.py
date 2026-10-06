"""Tests for infrastructure.plugins — registry, lifecycle, hooks, context, loader, etc."""

from __future__ import annotations
import pytest
from typing import Dict, Any
from infrastructure.plugins.types import (
    PluginManifest, PluginPermission, PluginHook, PluginVersion,
    PluginDependency, PluginBase,
)


class TestPluginTypes:
    def test_manifest_creation(self):
        manifest = PluginManifest(
            id="test-plugin",
            name="Test Plugin",
            version="1.0.0",
            description="A test plugin",
            author="Tester",
            permissions=[PluginPermission.KNOWLEDGE_READ],
            hooks=[PluginHook.CHAT_BEFORE_RESPOND],
        )
        assert manifest.id == "test-plugin"
        assert manifest.version == "1.0.0"

    def test_manifest_memory_permission(self):
        manifest = PluginManifest(
            id="mem-plugin", name="Mem Plugin", version="1.0.0",
            permissions=[PluginPermission.MEMORY_READ, PluginPermission.MEMORY_WRITE],
            hooks=[PluginHook.MEMORY_BEFORE_RETRIEVE],
        )
        assert PluginPermission.MEMORY_READ in manifest.permissions
        assert PluginPermission.MEMORY_WRITE in manifest.permissions

    def test_plugin_version_parsing(self):
        v = PluginVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_plugin_version_comparison(self):
        v1 = PluginVersion.parse("1.0.0")
        v2 = PluginVersion.parse("2.0.0")
        assert v1 < v2

    def test_plugin_version_str(self):
        v = PluginVersion.parse("1.2.3")
        assert str(v) == "1.2.3"

    def test_plugin_base_class(self):
        class MyPlugin(PluginBase):
            pass
        instance = MyPlugin()
        assert instance is not None
        assert instance.name == "MyPlugin"

    def test_dependency_creation(self):
        dep = PluginDependency(plugin_id="dep-plugin", version=">=1.0.0")
        assert dep.plugin_id == "dep-plugin"
        assert dep.version == ">=1.0.0"


class TestPluginRegistry:
    def test_register_and_get(self, plugin_registry):
        manifest = PluginManifest(
            id="reg-test", name="Reg Test", version="1.0.0",
            permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        retrieved = plugin_registry.get("reg-test")
        assert retrieved is not None
        assert retrieved.id == "reg-test"

    def test_register_duplicate_raises(self, plugin_registry):
        manifest = PluginManifest(
            id="dup", name="Dup", version="1.0.0", permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        with pytest.raises(Exception):
            plugin_registry.register(manifest)

    def test_unregister(self, plugin_registry):
        manifest = PluginManifest(
            id="unreg", name="Unreg", version="1.0.0", permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        plugin_registry.unregister("unreg")
        assert plugin_registry.get("unreg") is None

    def test_list_plugins(self, plugin_registry):
        for i in range(3):
            plugin_registry.register(PluginManifest(
                id=f"p{i}", name=f"P{i}", version="1.0.0", permissions=[], hooks=[],
            ))
        assert len(plugin_registry.list()) == 3

    def test_find_by_hook(self, plugin_registry):
        manifest = PluginManifest(
            id="hook-test", name="Hook Test", version="1.0.0",
            permissions=[], hooks=[PluginHook.CHAT_BEFORE_RESPOND],
        )
        plugin_registry.register(manifest)
        results = plugin_registry.find_by_hook(PluginHook.CHAT_BEFORE_RESPOND)
        assert len(results) == 1
        assert results[0].id == "hook-test"

    def test_find_by_permission(self, plugin_registry):
        manifest = PluginManifest(
            id="perm-test", name="Perm Test", version="1.0.0",
            permissions=[PluginPermission.KNOWLEDGE_WRITE], hooks=[],
        )
        plugin_registry.register(manifest)
        results = plugin_registry.find_by_permission(PluginPermission.KNOWLEDGE_WRITE)
        assert len(results) == 1

    def test_find_by_tag(self, plugin_registry):
        manifest = PluginManifest(
            id="tag-test", name="Tag Test", version="1.0.0",
            tags=["utility", "test"], permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        results = plugin_registry.find_by_tag("utility")
        assert len(results) == 1


class TestHookSystem:
    def test_emit_with_no_handlers(self, hook_system):
        results = hook_system.emit(PluginHook.CHAT_BEFORE_RESPOND, {"text": "hello"})
        assert results == []

    def test_register_and_emit(self, hook_system):
        received = []
        def handler(event):
            received.append(event)
        hook_system.register(PluginHook.CHAT_BEFORE_RESPOND, handler)
        results = hook_system.emit(PluginHook.CHAT_BEFORE_RESPOND, {"text": "hello"})
        assert len(received) == 1
        assert received[0]["text"] == "hello"

    def test_emit_filter_transforms(self, hook_system):
        def upper_filter(event):
            event["text"] = event["text"].upper()
            return event
        hook_system.register(PluginHook.CHAT_BEFORE_RESPOND, upper_filter)
        results = hook_system.emit_filter(PluginHook.CHAT_BEFORE_RESPOND, {"text": "hello"})
        assert results[0]["text"] == "HELLO"

    def test_multiple_handlers_in_order(self, hook_system):
        order = []
        hook_system.register(PluginHook.CHAT_BEFORE_RESPOND, lambda e: order.append(1), priority=10)
        hook_system.register(PluginHook.CHAT_BEFORE_RESPOND, lambda e: order.append(2), priority=5)
        hook_system.emit(PluginHook.CHAT_BEFORE_RESPOND, {})
        assert order == [2, 1]

    def test_unregister_handler(self, hook_system):
        def handler(e):
            pass
        hook_system.register(PluginHook.CHAT_BEFORE_RESPOND, handler)
        hook_system.unregister(PluginHook.CHAT_BEFORE_RESPOND, handler)
        results = hook_system.emit(PluginHook.CHAT_BEFORE_RESPOND, {})
        assert len(results) == 0


class TestPluginContext:
    def test_has_permission_granted(self, mock_plugin_context):
        assert mock_plugin_context.has_permission("knowledge:read") is True

    def test_has_permission_denied(self, mock_plugin_context):
        assert mock_plugin_context.has_permission("admin:*") is False

    def test_assert_permission_passes(self, mock_plugin_context):
        mock_plugin_context.assert_permission("knowledge:read")

    def test_assert_permission_raises(self, mock_plugin_context):
        with pytest.raises(PermissionError):
            mock_plugin_context.assert_permission("admin:*")

    def test_get_config(self, mock_plugin_context):
        assert mock_plugin_context.get_config("nonexistent", "default") == "default"

    def test_http_request_tracked(self, mock_plugin_context):
        import asyncio
        asyncio.run(mock_plugin_context.http_request("GET", "https://example.com"))
        assert len(mock_plugin_context.calls) == 1

    def test_emit_event(self, mock_plugin_context):
        import asyncio
        asyncio.run(mock_plugin_context.emit_event("test.event", {"key": "val"}))
        assert len(mock_plugin_context._events_emitted) == 1


class TestPluginLifecycleManager:
    def test_state_transitions(self, plugin_lifecycle):
        plugin_lifecycle.register("p1")
        assert plugin_lifecycle.get_state("p1") == "registered"

    def test_enable(self, plugin_lifecycle):
        plugin_lifecycle.register("p1")
        plugin_lifecycle.enable("p1")
        assert plugin_lifecycle.get_state("p1") == "enabled"

    def test_disable(self, plugin_lifecycle):
        plugin_lifecycle.register("p1")
        plugin_lifecycle.enable("p1")
        plugin_lifecycle.disable("p1")
        assert plugin_lifecycle.get_state("p1") == "disabled"

    def test_uninstall(self, plugin_lifecycle):
        plugin_lifecycle.register("p1")
        plugin_lifecycle.uninstall("p1")
        assert plugin_lifecycle.get_state("p1") is None

    def test_list_enabled(self, plugin_lifecycle):
        plugin_lifecycle.register("a")
        plugin_lifecycle.register("b")
        plugin_lifecycle.enable("a")
        enabled = plugin_lifecycle.list_state("enabled")
        assert "a" in enabled
        assert "b" not in enabled

    def test_enable_nonexistent_raises(self, plugin_lifecycle):
        with pytest.raises(Exception):
            plugin_lifecycle.enable("nonexistent")


class TestDependencyResolver:
    def test_no_dependencies(self, dependency_resolver):
        result = dependency_resolver.resolve([])
        assert result == []

    def test_missing_dependency_detected(self, dependency_resolver):
        from infrastructure.plugins.types import PluginDependency
        deps = [PluginDependency(plugin_id="missing-dep", version=">=1.0.0")]
        with pytest.raises(Exception):
            dependency_resolver.resolve(deps)

    def test_version_conflict(self, dependency_resolver):
        from infrastructure.plugins.types import PluginDependency, PluginManifest
        dep = PluginDependency(plugin_id="base", version=">=2.0.0")
        dependency_resolver.register_available(
            PluginManifest(id="base", name="Base", version="1.0.0", permissions=[], hooks=[])
        )
        with pytest.raises(Exception):
            dependency_resolver.resolve([dep])


class TestPluginLoader:
    def test_discover_no_plugins(self, plugin_loader):
        plugins = plugin_loader.discover()
        assert plugins == []

    def test_scan_directory(self, plugin_loader, tmp_path):
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text('{"id":"test","version":"1.0.0"}')
        found = plugin_loader.scan_directory(str(plugin_dir))
        assert len(found) >= 1
