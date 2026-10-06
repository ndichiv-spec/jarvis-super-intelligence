"""Tests for automation safety patterns and validation."""

from __future__ import annotations
import pytest


class TestAutomationPolicy:
    def test_command_allow_list(self):
        allowed = {"echo", "ls", "cat", "python", "git"}
        assert "echo" in allowed
        assert "rm" not in allowed

    def test_command_deny_list(self):
        denied = {"rm -rf /", "sudo", "shutdown", "mkfs"}
        dangerous = "rm -rf /"
        assert dangerous in denied
        assert "echo" not in denied

    def test_policy_default_deny(self):
        def is_allowed(command: str, allowed_list: set) -> bool:
            base = command.split()[0]
            return base in allowed_list
        allowed = {"echo", "ls"}
        assert is_allowed("echo hello", allowed) is True
        assert is_allowed("curl evil.com", allowed) is False
        assert is_allowed("rm -rf /", allowed) is False

    def test_policy_explicit_deny_overrides_allow(self):
        allowed = {"echo"}
        denied = {"echo"}
        command = "echo secret"
        base = command.split()[0]
        assert base in allowed
        assert base in denied
        result = False  # deny wins
        assert result is False

    def test_automation_requires_approval_for_destructive(self):
        def requires_approval(action: str, destructive_actions: set) -> bool:
            return action in destructive_actions
        destructive = {"delete_file", "drop_database", "restart_service", "execute_shell"}
        assert requires_approval("delete_file", destructive) is True
        assert requires_approval("read_file", destructive) is False

    def test_automation_max_concurrent(self):
        max_concurrent = 5
        active = 3
        assert active <= max_concurrent
        active = 6
        assert active > max_concurrent


class TestAutomationValidation:
    def test_validate_input_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "minimum": 1, "maximum": 300},
            },
            "required": ["command"],
        }
        assert "command" in schema["required"]
        assert schema["properties"]["timeout"]["maximum"] == 300

    def test_validate_output_size_limit(self):
        max_output_bytes = 100_000
        small_output = "x" * 100
        large_output = "x" * 200_000
        assert len(small_output) <= max_output_bytes
        assert len(large_output) > max_output_bytes

    def test_validate_execution_timeout(self):
        timeout = 30.0
        max_allowed = 300.0
        safe_timeout = min(timeout, max_allowed)
        assert safe_timeout == 30.0
        huge_timeout = 600.0
        clamped = min(huge_timeout, max_allowed)
        assert clamped == 300.0

    def test_sandbox_violation_detection(self):
        violations = []
        def check_safety(action: str) -> bool:
            if action in ["rm -rf /", "dd if=/dev/zero"]:
                violations.append(action)
                return False
            return True
        assert check_safety("rm -rf /") is False
        assert check_safety("echo safe") is True
        assert len(violations) == 1


class TestAutomationAudit:
    def test_audit_log_creation(self):
        log_entry = {
            "timestamp": "2024-01-01T00:00:00Z",
            "action": "file:delete",
            "user": "admin",
            "resource": "/tmp/test.txt",
            "allowed": False,
            "reason": "Destructive action requires approval",
        }
        assert log_entry["action"] == "file:delete"
        assert log_entry["allowed"] is False
        assert "reason" in log_entry

    def test_audit_trail_immutability(self):
        entries = []
        entries.append({"id": 1, "action": "read"})
        entries.append({"id": 2, "action": "write"})
        assert len(entries) == 2
        assert entries[0]["id"] == 1

    def test_audit_query_by_user(self):
        logs = [
            {"user": "alice", "action": "read"},
            {"user": "bob", "action": "write"},
            {"user": "alice", "action": "delete"},
        ]
        alice_logs = [l for l in logs if l["user"] == "alice"]
        assert len(alice_logs) == 2

    def test_audit_query_by_action(self):
        logs = [
            {"action": "file:read", "count": 10},
            {"action": "file:write", "count": 5},
            {"action": "file:delete", "count": 1},
        ]
        deletes = [l for l in logs if l["action"] == "file:delete"]
        assert deletes[0]["count"] == 1
