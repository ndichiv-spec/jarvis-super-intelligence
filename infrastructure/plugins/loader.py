"""
Dynamic plugin loader.

Discovers and imports plugins from:
  - File system directories
  - Python packages (installed via pip)
  - Configuration-defined paths
"""

from __future__ import annotations
import os
import sys
import json
import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .types import PluginManifest, PluginBase, PluginVersion

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    pass


class PluginLoader:
    """
    Loads plugins from disk.

    Plugin structure expected:
        plugins/my-plugin/
            manifest.json
            main.py          (entrypoint)
            requirements.txt (optional)

    manifest.json format:
        {
            "id": "my-plugin",
            "name": "My Plugin",
            "version": "1.0.0",
            "entrypoint": "main:Plugin",
            "permissions": ["network:http"],
            "hooks": ["chat:before_response"],
            ...
        }
    """

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        self.plugin_dirs = plugin_dirs or []
        self._loaded_modules: Dict[str, object] = {}

    def add_directory(self, path: Path):
        if path not in self.plugin_dirs:
            self.plugin_dirs.append(path)

    def discover(self) -> List[Tuple[PluginManifest, Optional[str]]]:
        """
        Scan all plugin directories for valid plugins.

        Returns list of (manifest, error_or_None) tuples.
        """
        results: List[Tuple[PluginManifest, Optional[str]]] = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue

            for entry in sorted(plugin_dir.iterdir()):
                if not entry.is_dir():
                    continue

                manifest_file = entry / "manifest.json"
                if not manifest_file.exists():
                    continue

                try:
                    with open(manifest_file, "r") as f:
                        data = json.load(f)
                    manifest = PluginManifest.from_dict(data)
                    results.append((manifest, None))
                except Exception as e:
                    logger.warning(f"Failed to load manifest from {manifest_file}: {e}")
                    # Create minimal manifest for error reporting
                    results.append((
                        PluginManifest(
                            id=entry.name,
                            name=entry.name,
                            version=PluginVersion(0, 0, 0),
                        ),
                        str(e),
                    ))

        return results

    def load_plugin(self, manifest: PluginManifest, plugin_dir: Path) -> PluginBase:
        """
        Dynamically import and instantiate a plugin from its entrypoint.

        Entrypoint format: "module:ClassName"
        Example: "main:Plugin"
        """
        entrypoint = manifest.entrypoint or "main:Plugin"
        module_name, _, class_name = entrypoint.partition(":")

        module_path = plugin_dir / f"{module_name}.py"
        if not module_path.exists():
            raise PluginLoadError(f"Entrypoint not found: {module_path}")

        spec = importlib.util.spec_from_file_location(
            f"jarvis_plugin_{manifest.id}",
            str(module_path),
        )
        if not spec or not spec.loader:
            raise PluginLoadError(f"Failed to create spec for {module_path}")

        module = importlib.util.module_from_spec(spec)
        self._loaded_modules[manifest.id] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin module '{manifest.id}': {e}") from e

        plugin_class = getattr(module, class_name, None)
        if not plugin_class:
            raise PluginLoadError(
                f"Plugin '{manifest.id}': class '{class_name}' not found in {module_path}"
            )

        try:
            instance = plugin_class()
        except Exception as e:
            raise PluginLoadError(
                f"Failed to instantiate plugin '{manifest.id}': {e}"
            ) from e

        if not isinstance(instance, PluginBase):
            raise PluginLoadError(
                f"Plugin '{manifest.id}' must inherit from PluginBase"
            )

        return instance

    def load_from_directory(self, plugin_id: str) -> Optional[Tuple[PluginManifest, PluginBase]]:
        """Find and load a specific plugin by ID from registered directories."""
        for plugin_dir in self.plugin_dirs:
            candidate = plugin_dir / plugin_id
            manifest_file = candidate / "manifest.json"
            if manifest_file.exists():
                with open(manifest_file, "r") as f:
                    data = json.load(f)
                manifest = PluginManifest.from_dict(data)
                instance = self.load_plugin(manifest, candidate)
                return manifest, instance
        return None

    def load_from_package(self, package_name: str) -> Tuple[PluginManifest, PluginBase]:
        """Load a plugin installed as a Python package."""
        try:
            module = importlib.import_module(package_name)
        except ImportError as e:
            raise PluginLoadError(f"Package '{package_name}' not installed: {e}") from e

        manifest_data = getattr(module, "__plugin_manifest__", None)
        if not manifest_data:
            raise PluginLoadError(f"Package '{package_name}' has no __plugin_manifest__")

        manifest = PluginManifest.from_dict(manifest_data)
        plugin_class = getattr(module, "Plugin", None)
        if not plugin_class:
            raise PluginLoadError(f"Package '{package_name}' has no Plugin class")

        instance = plugin_class()
        if not isinstance(instance, PluginBase):
            raise PluginLoadError(f"Plugin in '{package_name}' must inherit from PluginBase")

        self._loaded_modules[manifest.id] = module
        return manifest, instance

    def unload_plugin(self, plugin_id: str):
        """Remove a loaded plugin module from sys.modules."""
        module = self._loaded_modules.pop(plugin_id, None)
        if module:
            key = f"jarvis_plugin_{plugin_id}"
            sys.modules.pop(key, None)
