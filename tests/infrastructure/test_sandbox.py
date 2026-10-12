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
        from infrastructure.sandbox import SandboxViolation
        with pytest.raises(SandboxViolation, match="not in the allowed list"):
            await sandbox_executor.run_command("nonexistent_cmd_xyz123")

    async def test_run_python_hello(self, sandbox_executor):
        result = await sandbox_executor.run_python("print('hello from python')")
        assert result.success is True
        assert "hello from python" in result.stdout

    async def test_run_python_temp_path_does_not_match_denied_substring(
        self, sandbox_executor, monkeypatch, tmp_path,
    ):
        import tempfile

        temp_dir = tmp_path / "tmp4su"
        temp_dir.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
        result = await sandbox_executor.run_python("print('safe')")
        assert result.success is True
        assert result.stdout.strip() == "safe"

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
        result = await sandbox_executor.run_python(
            "import time; time.sleep(1)", timeout=0.1,
        )
        assert result.success is False
        assert "timed out" in (result.error or "").lower()


class TestPolicyEngine:
    def test_creates_with_default_rules(self, policy_engine):
        assert policy_engine is not None

    def test_allows_configured_shell_action(self, policy_engine):
        from infrastructure.sandbox import Capability
        policy_engine.allow(Capability.EXECUTE_SHELL, "echo.*")
        assert policy_engine.is_allowed(Capability.EXECUTE_SHELL, "echo hello") is True

    def test_default_policy_denies_unconfigured_capability(self, policy_engine):
        from infrastructure.sandbox import Capability
        assert policy_engine.is_allowed(Capability.FILE_READ, "/etc/passwd") is False

    def test_check_capability_unknown(self, policy_engine):
        from infrastructure.sandbox import Capability
        assert policy_engine.is_allowed(Capability.PROCESS_KILL, "123") is False

    def test_check_capability_explicit_block(self, policy_engine):
        from infrastructure.sandbox import Capability, PolicyRule, RuleAction
        policy_engine.allow(Capability.FILE_DELETE, "/data.*")
        policy_engine.add_rule(PolicyRule(
            RuleAction.DENY, Capability.FILE_DELETE, "/data.*", priority=10,
        ))
        assert policy_engine.is_allowed(Capability.FILE_DELETE, "/data/file") is False

    def test_add_allow_rule(self, policy_engine):
        from infrastructure.sandbox import Capability
        policy_engine.allow(Capability.EXECUTE_CODE)
        assert policy_engine.is_allowed(Capability.EXECUTE_CODE) is True

    def test_add_deny_rule_overrides(self, policy_engine):
        from infrastructure.sandbox import Capability, PolicyRule, RuleAction
        policy_engine.allow(Capability.EXECUTE_SHELL, "echo.*")
        policy_engine.add_rule(PolicyRule(
            RuleAction.DENY, Capability.EXECUTE_SHELL, "echo.*", priority=10,
        ))
        assert policy_engine.is_allowed(Capability.EXECUTE_SHELL, "echo command") is False
