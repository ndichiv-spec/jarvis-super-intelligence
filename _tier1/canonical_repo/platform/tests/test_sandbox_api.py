"""Sandbox execution API tests (spec #17, #16).

Covers the audited Silverwing sandbox endpoint on the JARVIS API plus the Coder
agent `act` path that now executes generated code inside the sandbox.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_backend.core import DATA_DIR

AUDIT_JSONL = DATA_DIR / "audit" / "sandbox.jsonl"


def _count_audit_lines() -> int:
    if not AUDIT_JSONL.exists():
        return 0
    before = len(AUDIT_JSONL.read_text(encoding="utf-8").splitlines())
    return before


def test_sandbox_policy_is_public(client):
    r = client.get("/api/v1/sandbox/policy")
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "python"
    assert body["controls"]["ast_allowlist"] is True
    assert body["controls"]["network_blocked"] is True
    assert len(body["honest_limits"]) >= 1


def test_sandbox_python_requires_auth(client):
    r = client.post("/api/v1/sandbox/python", json={"code": "print(1)"})
    assert r.status_code == 401


def test_sandbox_python_runs_sandboxed(client, auth_headers):
    r = client.post("/api/v1/sandbox/python",
                    json={"code": "print(sum(range(100)))", "timeout": 3},
                    headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stdout"].strip() == "4950"
    assert body["memory_enforced"] is True


def test_sandbox_blocks_dangerous_import(client, auth_headers):
    r = client.post("/api/v1/sandbox/python",
                    json={"code": "import os", "timeout": 3},
                    headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "violation" in (body["error"] or "")


def test_sandbox_enforces_timeout(client, auth_headers):
    r = client.post("/api/v1/sandbox/python",
                    json={"code": "while True: pass", "timeout": 1.2},
                    headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["signal"] == "timeout"
    assert "Timeout" in (body["error"] or "")


def test_sandbox_enforces_memory_cap(client, auth_headers):
    oom_code = "buf=[]\nwhile True:\n    buf.append(b' ' * 1_000_000)"
    r = client.post("/api/v1/sandbox/python",
                    json={"code": oom_code, "timeout": 10, "memory_limit_mb": 64},
                    headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["signal"] == "killed"
    assert "Memory limit" in (body["error"] or "")


def test_sandbox_writes_audit_trail(client, auth_headers):
    before = _count_audit_lines()
    client.post("/api/v1/sandbox/python",
                json={"code": "print(2 + 2)", "timeout": 3},
                headers=auth_headers)
    after = _count_audit_lines()
    assert after == before + 1


def test_coder_agent_has_execute_capability(client):
    agent = client.get("/api/v1/agents/coder").json()
    assert "execute" in agent.get("capabilities", [])


def test_coder_agent_can_act_via_sandbox(client, auth_headers):
    r = client.post("/api/v1/agents/coder/act", json={
        "action": "run_code",
        "code": "print(21 * 2)",
        "timeout": 3,
        "memory_limit_mb": 128,
    }, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["agent_id"] == "coder"
    assert body["ok"] is True
    assert body["stdout"].strip() == "42"
    assert body["memory_enforced"] is True


def test_coder_agent_rejects_unsupported_action(client, auth_headers):
    r = client.post("/api/v1/agents/coder/act", json={
        "action": "create_file",
        "code": "x = 1",
    }, headers=auth_headers)
    assert r.status_code == 400


def test_coder_agent_rejects_non_python(client, auth_headers):
    r = client.post("/api/v1/agents/coder/act", json={
        "action": "run_code",
        "language": "bash",
        "code": "echo hi",
    }, headers=auth_headers)
    assert r.status_code == 400