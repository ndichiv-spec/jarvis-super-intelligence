"""
Plugin dependency resolution and version compatibility checking.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field

from .types import PluginVersion, PluginDependency, PluginManifest

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    pass


class VersionConflictError(DependencyError):
    pass


class MissingDependencyError(DependencyError):
    pass


class CircularDependencyError(DependencyError):
    pass


@dataclass
class DependencyGraph:
    nodes: Dict[str, PluginManifest] = field(default_factory=dict)
    edges: Dict[str, List[str]] = field(default_factory=dict)

    def add(self, manifest: PluginManifest):
        self.nodes[manifest.id] = manifest
        self.edges[manifest.id] = [d.plugin_id for d in manifest.dependencies if not d.optional]


class DependencyResolver:
    """
    Resolves plugin dependencies and validates version compatibility.

    Handles:
      - Required vs. optional dependencies
      - Version constraint checking
      - Circular dependency detection
      - Dependency ordering for initialization
    """

    def __init__(self):
        self._graph = DependencyGraph()

    def add_plugin(self, manifest: PluginManifest):
        self._graph.add(manifest)

    def remove_plugin(self, plugin_id: str):
        self._graph.nodes.pop(plugin_id, None)
        self._graph.edges.pop(plugin_id, None)

    def get_missing_dependencies(self, manifest: PluginManifest) -> List[PluginDependency]:
        """Return dependencies that are not registered."""
        missing: List[PluginDependency] = []
        for dep in manifest.dependencies:
            if dep.optional:
                continue
            if dep.plugin_id not in self._graph.nodes:
                missing.append(dep)
        return missing

    def get_version_conflicts(self, manifest: PluginManifest) -> List[Tuple[PluginDependency, PluginVersion]]:
        """Return dependencies with version mismatches."""
        conflicts: List[Tuple[PluginDependency, PluginVersion]] = []
        for dep in manifest.dependencies:
            if dep.optional:
                continue
            provider = self._graph.nodes.get(dep.plugin_id)
            if provider and dep.version:
                if not dep.satisfied_by(provider.version):
                    conflicts.append((dep, provider.version))
        return conflicts

    def validate(self, manifest: PluginManifest) -> List[str]:
        """Validate all dependencies. Returns list of error messages."""
        errors: List[str] = []
        for dep in manifest.dependencies:
            if dep.optional:
                continue
            provider = self._graph.nodes.get(dep.plugin_id)
            if not provider:
                errors.append(f"Missing dependency: {dep.plugin_id}")
                continue
            if dep.version and not dep.satisfied_by(provider.version):
                errors.append(
                    f"Version conflict: {dep.plugin_id} requires {dep.version}, "
                    f"installed {provider.version}"
                )
        return errors

    def check_circular(self) -> List[str]:
        """Detect circular dependencies. Returns list of involved plugin IDs."""
        visited: Set[str] = set()
        path: Set[str] = set()
        circular: List[str] = []

        def dfs(node: str):
            if node in path:
                cycle = list(path)
                circular.append(" -> ".join(cycle + [node]))
                return
            if node in visited:
                return
            visited.add(node)
            path.add(node)
            for neighbor in self._graph.edges.get(node, []):
                dfs(neighbor)
            path.remove(node)

        for node in self._graph.nodes:
            dfs(node)

        return circular

    def get_initialization_order(self) -> List[str]:
        """Topological sort for initialization order."""
        visited: Set[str] = set()
        order: List[str] = []

        def dfs(node: str):
            if node in visited:
                return
            visited.add(node)
            for neighbor in self._graph.edges.get(node, []):
                dfs(neighbor)
            order.append(node)

        for node in self._graph.nodes:
            dfs(node)

        return order

    def host_compatible(self, manifest: PluginManifest, host_version: str) -> bool:
        """Check if plugin is compatible with the host version."""
        if not manifest.min_host_version:
            return True
        host = PluginVersion.parse(host_version)
        minimum = PluginVersion.parse(manifest.min_host_version)
        return host >= minimum
