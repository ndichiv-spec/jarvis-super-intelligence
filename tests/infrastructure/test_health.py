"""Tests for infrastructure.health — HealthChecker."""

from __future__ import annotations
import pytest
from infrastructure.health.checker import (
    HealthChecker, HealthCheck, HealthComponent, ComponentStatus,
)


class TestHealthChecker:
    @pytest.mark.asyncio
    async def test_empty_checker_not_checked(self, health_checker):
        status = await health_checker.get_status()
        assert status.status == ComponentStatus.NOT_CHECKED

    @pytest.mark.asyncio
    async def test_register_check(self, health_checker):
        async def ok_check() -> HealthComponent:
            return HealthComponent(name="db", status=ComponentStatus.HEALTHY)
        health_checker.register(HealthCheck(name="db", check_fn=ok_check))
        result = await health_checker.run_check("db")
        assert result.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_register_func(self, health_checker):
        async def ok_check() -> HealthComponent:
            return HealthComponent(name="cache", status=ComponentStatus.HEALTHY)
        health_checker.register_func("cache", ok_check)
        result = await health_checker.run_check("cache")
        assert result.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_report_unhealthy(self, health_checker):
        async def fail_check() -> HealthComponent:
            return HealthComponent(name="db", status=ComponentStatus.UNHEALTHY, message="Connection refused")
        health_checker.register(HealthCheck(name="db", check_fn=fail_check))
        status = await health_checker.get_status()
        assert status.status == ComponentStatus.UNHEALTHY
        assert status.components["db"].message == "Connection refused"

    @pytest.mark.asyncio
    async def test_overall_unhealthy_when_critical_fails(self, health_checker):
        async def ok() -> HealthComponent:
            return HealthComponent(name="web", status=ComponentStatus.HEALTHY)
        async def fail() -> HealthComponent:
            return HealthComponent(name="db", status=ComponentStatus.UNHEALTHY)
        health_checker.register_func("web", ok)
        health_checker.register_func("db", fail)
        status = await health_checker.get_status()
        assert status.status == ComponentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_all_healthy(self, health_checker):
        async def ok(name):
            async def _check() -> HealthComponent:
                return HealthComponent(name=name, status=ComponentStatus.HEALTHY)
            return _check
        health_checker.register_func("db", await ok("db"))
        health_checker.register_func("cache", await ok("cache"))
        status = await health_checker.get_status()
        assert status.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_liveness_probe(self, health_checker):
        status = await health_checker.get_status(probe="liveness")
        assert "liveness" in status.summary.lower()

    @pytest.mark.asyncio
    async def test_readiness_probe(self, health_checker):
        status = await health_checker.get_status(probe="readiness")
        assert "readiness" in status.summary.lower()

    @pytest.mark.asyncio
    async def test_startup_probe(self, health_checker):
        status = await health_checker.get_status(probe="startup")
        assert "startup" in status.summary.lower()

    @pytest.mark.asyncio
    async def test_status_contains_metadata(self, health_checker):
        status = await health_checker.get_status()
        assert status.app_name == "test-app"
        assert status.version == "1.0.0"
        assert status.environment == "test"
        assert status.timestamp is not None
        assert status.uptime_seconds >= 0

    @pytest.mark.asyncio
    async def test_run_all_returns_all(self, health_checker):
        async def a() -> HealthComponent:
            return HealthComponent(name="a", status=ComponentStatus.HEALTHY)
        async def b() -> HealthComponent:
            return HealthComponent(name="b", status=ComponentStatus.HEALTHY)
        health_checker.register_func("a", a)
        health_checker.register_func("b", b)
        results = await health_checker.run_all()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_component_has_response_time(self, health_checker):
        async def ok() -> HealthComponent:
            return HealthComponent(name="fast", status=ComponentStatus.HEALTHY)
        health_checker.register_func("fast", ok)
        result = await health_checker.run_check("fast")
        assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_unregistered_check_returns_not_checked(self, health_checker):
        result = await health_checker.run_check("nonexistent")
        assert result.status == ComponentStatus.NOT_CHECKED

    @pytest.mark.asyncio
    async def test_check_exception_handling(self, health_checker):
        async def explode() -> HealthComponent:
            raise RuntimeError("Kaboom")
        health_checker.register_func("exploder", explode)
        result = await health_checker.run_check("exploder")
        assert result.status == ComponentStatus.UNHEALTHY
        assert "Kaboom" in result.message
