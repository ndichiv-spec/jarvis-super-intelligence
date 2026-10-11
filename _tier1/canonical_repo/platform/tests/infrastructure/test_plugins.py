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
            version=PluginVersion.parse("1.0.0"),
            description="A test plugin",
            author="Tester",
            permissions=[PluginPermission.MEMORY_READ],
            hooks=[PluginHook.CHAT_BEFORE_RESPONSE],
        )
        assert manifest.id == "test-plugin"
        assert str(manifest.version) == "1.0.0"

    def test_manifest_memory_permission(self):
        manifest = PluginManifest(
            id="mem-plugin", name="Mem Plugin", version=PluginVersion.parse("1.0.0"),
            permissions=[PluginPermission.MEMORY_READ, PluginPermission.MEMORY_WRITE],
            hooks=[PluginHook.MEMORY_AFTER_RETRIEVE],
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
        assert callable(instance.initialize)
        assert callable(instance.shutdown)

    def test_dependency_creation(self):
        dep = PluginDependency(plugin_id="dep-plugin", version=">=1.0.0")
        assert dep.plugin_id == "dep-plugin"
        assert dep.version == ">=1.0.0"


class TestPluginRegistry:
    def test_register_and_get(self, plugin_registry):
        manifest = PluginManifest(
            id="reg-test", name="Reg Test", version=PluginVersion.parse("1.0.0"),
            permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        retrieved = plugin_registry.get("reg-test")
        assert retrieved is not None
        assert retrieved.manifest.id == "reg-test"

    def test_register_duplicate_raises(self, plugin_registry):
        manifest = PluginManifest(
            id="dup", name="Dup", version=PluginVersion.parse("1.0.0"), permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        with pytest.raises(Exception):
            plugin_registry.register(manifest)

    def test_unregister(self, plugin_registry):
        manifest = PluginManifest(
            id="unreg", name="Unreg", version=PluginVersion.parse("1.0.0"), permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        plugin_registry.unregister("unreg")
        assert plugin_registry.get("unreg") is None

    def test_list_plugins(self, plugin_registry):
        for i in range(3):
            plugin_registry.register(PluginManifest(
                id=f"p{i}", name=f"P{i}", version=PluginVersion.parse("1.0.0"), permissions=[], hooks=[],
            ))
        assert len(plugin_registry.list()) == 3

    def test_find_by_hook(self, plugin_registry):
        manifest = PluginManifest(
            id="hook-test", name="Hook Test", version=PluginVersion.parse("1.0.0"),
            permissions=[], hooks=[PluginHook.CHAT_BEFORE_RESPONSE],
        )
        plugin_registry.register(manifest)
        plugin_registry.mark_enabled("hook-test")
        results = plugin_registry.find_by_hook(PluginHook.CHAT_BEFORE_RESPONSE.value)
        assert len(results) == 1
        assert results[0].manifest.id == "hook-test"

    def test_find_by_permission(self, plugin_registry):
        manifest = PluginManifest(
            id="perm-test", name="Perm Test", version=PluginVersion.parse("1.0.0"),
            permissions=[PluginPermission.MEMORY_WRITE], hooks=[],
        )
        plugin_registry.register(manifest)
        results = plugin_registry.find_by_permission(PluginPermission.MEMORY_WRITE.value)
        assert len(results) == 1

    def test_find_by_tag(self, plugin_registry):
        manifest = PluginManifest(
            id="tag-test", name="Tag Test", version=PluginVersion.parse("1.0.0"),
            tags=["utility", "test"], permissions=[], hooks=[],
        )
        plugin_registry.register(manifest)
        results = plugin_registry.find_by_tag("utility")
        assert len(results) == 1


class TestHookSystem:
    @pytest.mark.asyncio
    async def test_emit_with_no_handlers(self, hook_system):
        result = await hook_system.emit(PluginHook.CHAT_BEFORE_RESPONSE, {"text": "hello"})
        assert result.results == []

    @pytest.mark.asyncio
    async def test_register_and_emit(self, hook_system):
        received = []
        async def handler(event):
            received.append(event)
        hook_system.register("test-plugin", PluginHook.CHAT_BEFORE_RESPONSE, handler)
        result = await hook_system.emit(PluginHook.CHAT_BEFORE_RESPONSE, {"text": "hello"})
        assert len(received) == 1
        assert received[0]["text"] == "hello"
        assert result.results == [None]

    @pytest.mark.asyncio
    async def test_emit_filter_transforms(self, hook_system):
        async def upper_filter(event):
            event["text"] = event["text"].upper()
            return event
        hook_system.register("test-plugin", PluginHook.CHAT_BEFORE_RESPONSE, upper_filter)
        result = await hook_system.emit_filter(
            PluginHook.CHAT_BEFORE_RESPONSE,
            {"text": "hello"},
        )
        assert result["text"] == "HELLO"

    @pytest.mark.asyncio
    async def test_multiple_handlers_in_order(self, hook_system):
        order = []
        async def first_handler(_event):
            order.append(1)
        async def second_handler(_event):
            order.append(2)
        hook_system.register(
            "test-plugin",
            PluginHook.CHAT_BEFORE_RESPONSE,
            first_handler,
            priority=10,
        )
        hook_system.register(
            "test-plugin",
            PluginHook.CHAT_BEFORE_RESPONSE,
            second_handler,
            priority=5,
        )
        await hook_system.emit(PluginHook.CHAT_BEFORE_RESPONSE, {})
        assert order == [1, 2]

    @pytest.mark.asyncio
    async def test_unregister_handler(self, hook_system):
        async def handler(_event):
            pass
        hook_system.register("test-plugin", PluginHook.CHAT_BEFORE_RESPONSE, handler)
        hook_system.unregister("test-plugin", PluginHook.CHAT_BEFORE_RESPONSE)
        result = await hook_system.emit(PluginHook.CHAT_BEFORE_RESPONSE, {})
        assert result.results == []


class TestPluginContext:
    def test_has_permission_granted(self, mock_plugin_context):
        assert mock_plugin_context.has_permission("memory:read") is True

    def test_has_permission_denied(self, mock_plugin_context):
        assert mock_plugin_context.has_permission("admin:*") is False

    def test_assert_permission_passes(self, mock_plugin_context):
        mock_plugin_context.assert_permission("memory:read")

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
    @staticmethod
    def register_plugin(plugin_lifecycle, plugin_id):
        manifest = PluginManifest(
            id=plugin_id,
            name=plugin_id,
            version=PluginVersion.parse("1.0.0"),
            permissions=[],
            hooks=[],
        )
        plugin_lifecycle.registry.register(manifest, PluginBase())

    def test_state_transitions(self, plugin_lifecycle):
        self.register_plugin(plugin_lifecycle, "p1")
        metadata = plugin_lifecycle.registry.get("p1")
        assert metadata.state.value == "discovered"

    @pytest.mark.asyncio
    async def test_enable(self, plugin_lifecycle):
        self.register_plugin(plugin_lifecycle, "p1")
        result = await plugin_lifecycle.enable("p1")
        assert result.success is True
        assert plugin_lifecycle.registry.get("p1").state.value == "enabled"

    @pytest.mark.asyncio
    async def test_disable(self, plugin_lifecycle):
        self.register_plugin(plugin_lifecycle, "p1")
        await plugin_lifecycle.enable("p1")
        result = await plugin_lifecycle.disable("p1")
        assert result.success is True
        assert plugin_lifecycle.registry.get("p1").state.value == "disabled"

    @pytest.mark.asyncio
    async def test_uninstall(self, plugin_lifecycle):
        self.register_plugin(plugin_lifecycle, "p1")
        result = await plugin_lifecycle.uninstall("p1")
        assert result.success is True
        assert plugin_lifecycle.registry.get("p1") is None

    @pytest.mark.asyncio
    async def test_list_enabled(self, plugin_lifecycle):
        self.register_plugin(plugin_lifecycle, "a")
        self.register_plugin(plugin_lifecycle, "b")
        await plugin_lifecycle.enable("a")
        enabled = plugin_lifecycle.registry.list(
            state=plugin_lifecycle.registry.get("a").state,
        )
        assert [plugin.manifest.id for plugin in enabled] == ["a"]

    @pytest.mark.asyncio
    async def test_enable_nonexistent_returns_failure(self, plugin_lifecycle):
        result = await plugin_lifecycle.enable("nonexistent")
        assert result.success is False


class TestDependencyResolver:
    def test_no_dependencies(self, dependency_resolver):
        manifest = PluginManifest(
            id="independent",
            version=PluginVersion.parse("1.0.0"),
        )
        assert dependency_resolver.validate(manifest) == []

    def test_missing_dependency_detected(self, dependency_resolver):
        from infrastructure.plugins.types import PluginDependency
        manifest = PluginManifest(
            id="dependent",
            version=PluginVersion.parse("1.0.0"),
            dependencies=[PluginDependency(plugin_id="missing-dep", version=">=1.0.0")],
        )
        assert dependency_resolver.validate(manifest) == [
            "Missing dependency: missing-dep",
        ]

    def test_version_conflict(self, dependency_resolver):
        from infrastructure.plugins.types import PluginDependency, PluginManifest
        dependency_resolver.add_plugin(
            PluginManifest(
                id="base",
                name="Base",
                version=PluginVersion.parse("1.0.0"),
                permissions=[],
                hooks=[],
            )
        )
        dependent = PluginManifest(
            id="dependent",
            version=PluginVersion.parse("1.0.0"),
            dependencies=[PluginDependency(plugin_id="base", version=">=2.0.0")],
        )
        assert dependency_resolver.validate(dependent) == [
            "Version conflict: base requires >=2.0.0, installed 1.0.0",
        ]


class TestPluginLoader:
    def test_discover_no_plugins(self, plugin_loader):
        plugins = plugin_loader.discover()
        assert plugins == []

    def test_scan_directory(self, plugin_loader, tmp_path):
        plugin_dir = tmp_path / "plugins" / "test"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "manifest.json").write_text(
            '{"id":"test","version":"1.0.0"}',
            encoding="utf-8",
        )
        found = plugin_loader.discover()
        assert len(found) == 1
        assert found[0][0].id == "test"
        assert found[0][1] is None
