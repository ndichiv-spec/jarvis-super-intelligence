"""Tests for infrastructure.startup — StartupValidator."""

from __future__ import annotations
import os
import sys
import pytest
from tests.utils.helpers import temp_env_vars
from infrastructure.startup.validator import (
    StartupValidator, CheckResult, CheckSeverity, StartupCheck,
    check_env_var, check_disk_space, check_directory_writable,
)


class TestStartupValidator:
    @pytest.mark.asyncio
    async def test_empty_validator(self, startup_validator):
        report = await startup_validator.assert_can_start()
        assert report["all_passed"] is True
        assert report["total"] == 0

    @pytest.mark.asyncio
    async def test_register_check_via_decorator(self):
        validator = StartupValidator(app_name="test")
        @validator.check("always_ok")
        async def ok_check():
            return CheckResult(name="always_ok", passed=True)
        results = await validator.run()
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_register_check_via_register(self):
        validator = StartupValidator()
        check = StartupCheck(name="manual", check_fn=lambda: _async_result(True, "manual"))
        validator.register(check)
        results = await validator.run()
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_check_fails(self):
        validator = StartupValidator()
        @validator.check("failing")
        async def fail():
            return CheckResult(name="failing", passed=False, message="Boom")
        results = await validator.run()
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_check_exception_handled(self):
        validator = StartupValidator()
        @validator.check("exploder")
        async def explode():
            raise RuntimeError("Kaboom")
        results = await validator.run()
        assert results[0].passed is False
        assert "Kaboom" in results[0].message

    @pytest.mark.asyncio
    async def test_has_failures_with_critical(self):
        validator = StartupValidator()
        @validator.check("critical_fail", severity=CheckSeverity.CRITICAL)
        async def fail():
            return CheckResult(name="critical_fail", passed=False, severity=CheckSeverity.CRITICAL)
        await validator.run()
        assert validator.has_failures() is True

    @pytest.mark.asyncio
    async def test_has_failures_with_warning_only(self):
        validator = StartupValidator()
        @validator.check("warn", severity=CheckSeverity.WARNING)
        async def warn():
            return CheckResult(name="warn", passed=False, severity=CheckSeverity.WARNING)
        await validator.run()
        assert validator.has_failures() is False

    @pytest.mark.asyncio
    async def test_report_structure(self):
        validator = StartupValidator(app_name="test-app")
        results = await validator.run()
        report = validator.report(results)
        assert report["app"] == "test-app"
        assert "timestamp" in report
        assert "checks" in report
        assert "all_passed" in report
        assert "can_start" in report

    @pytest.mark.asyncio
    async def test_assert_can_start_raises_on_critical(self):
        validator = StartupValidator()
        @validator.check("critical", severity=CheckSeverity.CRITICAL)
        async def fail():
            return CheckResult(name="critical", passed=False, severity=CheckSeverity.CRITICAL)
        with pytest.raises(RuntimeError, match="critical"):
            await validator.assert_can_start()

    @pytest.mark.asyncio
    async def test_run_specific_checks(self):
        validator = StartupValidator()
        @validator.check("a")
        async def check_a():
            return CheckResult(name="a", passed=True)
        @validator.check("b")
        async def check_b():
            return CheckResult(name="b", passed=True)
        results = await validator.run(checks=["a"])
        assert len(results) == 1
        assert results[0].name == "a"


class TestBuiltinChecks:
    @pytest.mark.asyncio
    async def test_check_env_var_present(self):
        with temp_env_vars({"STARTUP_TEST_VAR": "present_value"}):
            check = check_env_var("STARTUP_TEST_VAR")
            result = await check.check_fn()
            assert result.passed is True

    @pytest.mark.asyncio
    async def test_check_env_var_missing(self):
        check = check_env_var("MISSING_STARTUP_VAR_XYZ")
        result = await check.check_fn()
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_check_disk_space(self):
        check = check_disk_space(min_gb=0.001)
        result = await check.check_fn()
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_check_disk_space_impossible(self):
        check = check_disk_space(min_gb=999_999)
        result = await check.check_fn()
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_check_directory_writable(self, tmp_path):
        d = tmp_path / "writable_check"
        d.mkdir()
        check = check_directory_writable(str(d))
        result = await check.check_fn()
        assert result.passed is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows does not enforce chmod write permission the same way")
    async def test_check_directory_not_writable(self, tmp_path):
        import stat
        import sys
        d = tmp_path / "readonly_check"
        d.mkdir()
        os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
        check = check_directory_writable(str(d))
        result = await check.check_fn()
        assert result.passed is False


async def _async_result(passed: bool, message: str = ""):
    return CheckResult(name="test", passed=passed, message=message)
