"""
Startup performance optimization for Jarvis.

Provides lazy initialization, parallel dependency resolution,
async startup with readiness tracking, and component warmup.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, List, Optional, Set,
    Awaitable, TypeVar, Tuple,
)

from performance.concurrency import AtomicCounter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class InitStatus(Enum):
    PENDING = auto()
    INITIALIZING = auto()
    READY = auto()
    FAILED = auto()
    SKIPPED = auto()


@dataclass
class InitComponent:
    """A component that needs initialization."""
    name: str
    init_fn: Callable[[], Awaitable[Any]]
    dependencies: List[str] = field(default_factory=list)
    status: InitStatus = InitStatus.PENDING
    error: Optional[str] = None
    start_time: float = 0.0
    duration: float = 0.0
    critical: bool = True
    warmup_fn: Optional[Callable[[], Awaitable[None]]] = None


class StartupOptimizer:
    """
    Optimizes application startup through lazy loading and parallel init.

    Features:
    - Dependency-aware parallel initialization
    - Lazy loading (components initialized on first use)
    - Warmup phase for cache priming
    - Readiness tracking per component
    - Graceful degradation on non-critical failures
    - Startup time measurement and reporting

    Usage:
        optimizer = StartupOptimizer()

        @optimizer.register("database", depends_on=["config"])
        async def init_db():
            ...

        await optimizer.initialize()
        await optimizer.warmup()
    """

    def __init__(self):
        self._components: Dict[str, InitComponent] = {}
        self._lazy_registry: Dict[str, InitComponent] = {}
        self._start_time: float = 0.0
        self._total_duration: float = 0.0
        self._ready = False

    def register(
        self,
        name: str,
        depends_on: Optional[List[str]] = None,
        critical: bool = True,
        lazy: bool = False,
    ):
        """
        Decorator to register an initialization function.

        Args:
            name: Component name
            depends_on: List of component names this depends on
            critical: If True, startup fails when this component fails
            lazy: If True, init is deferred until first access
        """
        def decorator(fn: Callable[[], Awaitable[T]]) -> Callable[[], Awaitable[T]]:
            component = InitComponent(
                name=name,
                init_fn=fn,
                dependencies=depends_on or [],
                critical=critical,
            )
            if lazy:
                self._lazy_registry[name] = component
            else:
                self._components[name] = component
            return fn
        return decorator

    async def initialize(self) -> Dict[str, InitStatus]:
        """
        Initialize all registered components.

        Respects dependency ordering and runs independent
        components in parallel.
        """
        self._start_time = time.time()
        results = {}

        ordered = self._resolve_order()
        batches = self._batched(ordered)

        for batch in batches:
            tasks = {
                name: asyncio.create_task(self._init_component(name))
                for name in batch
            }
            for name, task in tasks.items():
                try:
                    await task
                except Exception as e:
                    component = self._components[name]
                    component.status = InitStatus.FAILED
                    component.error = str(e)
                    if component.critical:
                        raise StartupError(f"Critical component '{name}' failed: {e}")

        self._total_duration = time.time() - self._start_time
        self._ready = True

        for name in self._components:
            results[name] = self._components[name].status

        logger.info(
            "Startup completed in %.2fs: %d components, %d failed",
            self._total_duration,
            len(self._components),
            sum(1 for c in self._components.values() if c.status == InitStatus.FAILED),
        )

        return results

    async def warmup(self):
        """
        Run warmup functions for all initialized components.

        This primes caches, establishes connections, and prepares
        resources before accepting traffic.
        """
        warmup_tasks = []
        for component in self._components.values():
            if component.status == InitStatus.READY and component.warmup_fn:
                warmup_tasks.append(component.warmup_fn())

        if warmup_tasks:
            await asyncio.gather(*warmup_tasks, return_exceptions=True)
            logger.info("Warmup completed for %d components", len(warmup_tasks))

    async def get_or_init(self, name: str) -> Any:
        """
        Get a lazy component, initializing it if necessary.
        """
        component = self._lazy_registry.get(name)
        if component is None:
            component = self._components.get(name)

        if component is None:
            raise KeyError(f"Component '{name}' not registered")

        if component.status == InitStatus.PENDING:
            await self._init_component(name)

        if component.status == InitStatus.FAILED:
            raise RuntimeError(f"Component '{name}' failed: {component.error}")

        return component

    def is_ready(self, name: str) -> bool:
        component = self._components.get(name)
        return component.status == InitStatus.READY if component else False

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_duration": self._total_duration,
            "components": {
                name: {
                    "status": comp.status.name,
                    "duration": comp.duration,
                    "critical": comp.critical,
                    "error": comp.error,
                }
                for name, comp in self._components.items()
            },
            "ready": self._ready,
        }

    async def _init_component(self, name: str) -> None:
        """Initialize a single component."""
        component = self._components[name]
        component.status = InitStatus.INITIALIZING
        component.start_time = time.time()

        try:
            result = await component.init_fn()
            component.duration = time.time() - component.start_time
            component.status = InitStatus.READY
            logger.info(
                "Component '%s' initialized in %.2fs",
                name, component.duration,
            )
            return result
        except Exception as e:
            component.duration = time.time() - component.start_time
            component.status = InitStatus.FAILED
            component.error = str(e)
            if component.critical:
                raise
            logger.warning("Component '%s' failed (non-critical): %s", name, e)

    def _resolve_order(self) -> List[str]:
        """Topological sort of components by dependency."""
        graph = {name: set(comp.dependencies) for name, comp in self._components.items()}

        for name, deps in graph.items():
            for dep in deps:
                if dep not in self._components:
                    raise StartupError(f"Component '{name}' depends on unknown '{dep}'")

        visited: Set[str] = set()
        result: List[str] = []

        def dfs(node: str, path: Set[str]):
            if node in path:
                cycle = " -> ".join(list(path) + [node])
                raise StartupError(f"Dependency cycle detected: {cycle}")
            if node in visited:
                return
            path.add(node)
            for dep in graph.get(node, set()):
                dfs(dep, path.copy())
            path.discard(node)
            visited.add(node)
            result.append(node)

        for name in self._components:
            if name not in visited:
                dfs(name, set())

        return result

    def _batched(self, ordered: List[str]) -> List[List[str]]:
        """Group components into parallel batches based on dependencies."""
        levels: Dict[str, int] = {}
        for name in ordered:
            comp = self._components[name]
            if not comp.dependencies:
                levels[name] = 0
            else:
                levels[name] = max(levels.get(d, 0) for d in comp.dependencies) + 1

        max_level = max(levels.values()) if levels else 0
        batches: List[List[str]] = [[] for _ in range(max_level + 1)]
        for name, level in levels.items():
            batches[level].append(name)

        return batches


class StartupError(Exception):
    """Raised when a critical startup component fails."""


class LazyLoader:
    """
    Proxy that defers object creation until first access.

    Usage:
        loader = LazyLoader(ExpensiveObject, arg1="hello")
        obj = await loader.get()  # Created here
    """

    def __init__(self, factory: Callable[..., T], *args, **kwargs):
        self._factory = factory
        self._args = args
        self._kwargs = kwargs
        self._instance: Optional[T] = None
        self._lock = asyncio.Lock()

    async def get(self) -> T:
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    result = self._factory(*self._args, **self._kwargs)
                    if asyncio.iscoroutine(result):
                        self._instance = await result
                    else:
                        self._instance = result
        return self._instance
