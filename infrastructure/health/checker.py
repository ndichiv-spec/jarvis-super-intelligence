"""
Health monitoring and diagnostics system.

Provides:
  - Component-level health checks
  - Readiness, liveness, and startup probes
  - Dependency health validation
  - Metrics collection
  - Diagnostics reports
"""

import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ComponentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    NOT_CHECKED = "not_checked"


@dataclass
class HealthComponent:
    """Represents a single health-checkable component."""
    name: str
    status: ComponentStatus = ComponentStatus.NOT_CHECKED
    message: str = ""
    response_time_ms: float = 0.0
    last_checked: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class HealthStatus:
    """Aggregated health status."""
    status: ComponentStatus
    summary: str
    timestamp: str
    version: str
    app_name: str
    environment: str
    uptime_seconds: float
    components: Dict[str, HealthComponent] = field(default_factory=dict)


HealthCheckFunc = Callable[[], Awaitable[HealthComponent]]


class HealthCheck:
    """Registers a health check function for a component."""

    def __init__(
        self,
        name: str,
        check_fn: HealthCheckFunc,
        dependencies: Optional[List[str]] = None,
        timeout: float = 10.0,
        critical: bool = True,
    ):
        self.name = name
        self.check_fn = check_fn
        self.dependencies = dependencies or []
        self.timeout = timeout
        self.critical = critical


class HealthChecker:
    """
    Runs health checks against all registered components.

    Supports three probe types:
      - startup:  Checks if the service has started successfully
      - readiness: Checks if the service is ready to handle requests
      - liveness:  Checks if the service is still alive
    """

    def __init__(self, app_name: str = "jarvis", version: str = "3.0.0", environment: str = "development"):
        self.app_name = app_name
        self.version = version
        self.environment = environment
        self.checks: Dict[str, HealthCheck] = {}
        self.cached_status: Dict[str, HealthComponent] = {}
        self.start_time = time.time()

    def register(self, check: HealthCheck):
        """Register a health check."""
        self.checks[check.name] = check
        self.cached_status[check.name] = HealthComponent(
            name=check.name,
            status=ComponentStatus.NOT_CHECKED,
            dependencies=check.dependencies,
        )

    def register_func(self, name: str, fn: HealthCheckFunc, **kwargs):
        """Register a health check from a function."""
        self.register(HealthCheck(name=name, check_fn=fn, **kwargs))

    async def run_check(self, name: str) -> HealthComponent:
        """Run a single health check."""
        check = self.checks.get(name)
        if not check:
            return HealthComponent(name=name, status=ComponentStatus.NOT_CHECKED, message="No check registered")

        start = time.time()
        try:
            result = await asyncio.wait_for(check.check_fn(), timeout=check.timeout)
            result.response_time_ms = (time.time() - start) * 1000
            result.last_checked = datetime.now(timezone.utc).isoformat()
            self.cached_status[name] = result
            return result
        except asyncio.TimeoutError:
            component = HealthComponent(
                name=name,
                status=ComponentStatus.UNHEALTHY,
                message=f"Health check timed out after {check.timeout}s",
                response_time_ms=(time.time() - start) * 1000,
                last_checked=datetime.now(timezone.utc).isoformat(),
            )
            self.cached_status[name] = component
            return component
        except Exception as e:
            component = HealthComponent(
                name=name,
                status=ComponentStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=(time.time() - start) * 1000,
                last_checked=datetime.now(timezone.utc).isoformat(),
            )
            self.cached_status[name] = component
            return component

    async def run_all(self) -> Dict[str, HealthComponent]:
        """Run all registered health checks."""
        results: Dict[str, HealthComponent] = {}
        for name in self.checks:
            results[name] = await self.run_check(name)
        return results

    async def get_status(
        self,
        probe: str = "readiness",
        check_names: Optional[List[str]] = None,
    ) -> HealthStatus:
        """Get the overall health status for a specific probe type."""
        names = check_names or list(self.checks.keys())
        components: Dict[str, HealthComponent] = {}

        for name in names:
            if name in self.checks:
                components[name] = await self.run_check(name)

        overall = self._aggregate(components)
        return HealthStatus(
            status=overall,
            summary=self._summary(overall, probe),
            timestamp=datetime.now(timezone.utc).isoformat(),
            version=self.version,
            app_name=self.app_name,
            environment=self.environment,
            uptime_seconds=time.time() - self.start_time,
            components=components,
        )

    def _aggregate(self, components: Dict[str, HealthComponent]) -> ComponentStatus:
        """Aggregate component statuses into an overall status."""
        if not components:
            return ComponentStatus.NOT_CHECKED
        if any(c.status == ComponentStatus.UNHEALTHY for c in components.values()):
            return ComponentStatus.UNHEALTHY
        if any(c.status == ComponentStatus.DEGRADED for c in components.values()):
            return ComponentStatus.DEGRADED
        if any(c.status == ComponentStatus.NOT_CHECKED for c in components.values()):
            return ComponentStatus.DEGRADED
        return ComponentStatus.HEALTHY

    def _summary(self, status: ComponentStatus, probe: str) -> str:
        """Generate a human-readable summary."""
        summaries = {
            ComponentStatus.HEALTHY: f"{probe.capitalize()} probe passed - all components healthy",
            ComponentStatus.DEGRADED: f"{probe.capitalize()} probe degraded - some components unhealthy",
            ComponentStatus.UNHEALTHY: f"{probe.capitalize()} probe failed - critical components unhealthy",
            ComponentStatus.NOT_CHECKED: f"{probe.capitalize()} probe not yet run",
        }
        return summaries.get(status, "Unknown status")


_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get the global health checker singleton."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


def reset_health_checker():
    """Reset the health checker singleton (useful for testing)."""
    global _health_checker
    _health_checker = None
