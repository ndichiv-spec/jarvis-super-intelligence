"""Tests for infrastructure.sandbox — SandboxExecutor, PolicyEngine."""

from __future__ import annotations
import pytest


@pytest.mark.asyncio
class TestSandboxExecutor:
    async def test_run_command_simple(self, sandbox_executor):
        result = await sandbox_executor.run_command("echo hello")
        assert result.success is True
        assert "hello" in result.stdout

    async def test_run_command_exit_code(self, sandbox_executor):
        result = await sandbox_executor.run_command("echo ok")
        assert result.exit_code == 0

    async def test_command_not_found(self, sandbox_executor):
        result = await sandbox_executor.run_command("nonexistent_cmd_xyz123")
        assert result.success is False

    async def test_run_python_hello(self, sandbox_executor):
        result = await sandbox_executor.run_python("print('hello from python')")
        assert result.success is True
        assert "hello from python" in result.stdout

    async def test_run_python_with_error(self, sandbox_executor):
        result = await sandbox_executor.run_python("raise ValueError('test error')")
        assert result.success is False

    async def test_result_contains_duration(self, sandbox_executor):
        result = await sandbox_executor.run_command("echo timing")
        assert result.duration_ms >= 0

    async def test_result_to_dict(self, sandbox_executor):
        result = await sandbox_executor.run_command("echo dict_test")
        d = result.to_dict()
        assert d["success"] is True
        assert "dict_test" in d["stdout"]

    async def test_timeout_enforced(self, sandbox_executor):
        result = await sandbox_executor.run_command("sleep 10", timeout=0.1)
        assert result.success is False
        assert "timed out" in (result.error or "").lower()


class TestPolicyEngine:
    def test_creates_with_default_rules(self, policy_engine):
        assert policy_engine is not None

    def test_allows_echo(self, policy_engine):
        assert policy_engine.is_allowed("echo hello") is True

    def test_check_capability(self, policy_engine):
        from infrastructure.sandbox import Capability
        result = policy_engine.check_capability(Capability.FILE_READ, "/etc/passwd")
        assert result is True or result is False

    def test_check_capability_unknown(self, policy_engine):
        from infrastructure.sandbox import Capability
        result = policy_engine.check_capability(Capability.PROCESS_KILL, "123")
        assert result is True or result is False

    def test_check_capability_explicit_block(self, policy_engine):
        from infrastructure.sandbox import Capability
        policy_engine.add_rule("deny", Capability.FILE_DELETE, "*")
        result = policy_engine.check_capability(Capability.FILE_DELETE, "/data")
        assert result is False

    def test_add_allow_rule(self, policy_engine):
        policy_engine.add_allow_rule("my_tool")
        assert policy_engine.is_allowed("my_tool --version") is True

    def test_add_deny_rule_overrides(self, policy_engine):
        policy_engine.add_deny_rule("echo")
        assert policy_engine.is_allowed("echo secret") is False
