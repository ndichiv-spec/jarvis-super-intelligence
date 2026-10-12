"""Sandbox execution API tests (spec #17, #16).

Covers the audited Silverwing sandbox endpoint on the JARVIS API plus the Coder
agent `act` path that now executes generated code inside the sandbox.
"""
from __future__ import annotations

import copy

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


def test_sandbox_policy_reports_memory_enforcement_availability(client, monkeypatch):
    from jarvis_backend.routers import sandbox

    monkeypatch.setattr(sandbox, "_memory_enforcement_available", lambda: False)
    response = client.get("/api/v1/sandbox/policy")
    assert response.status_code == 200
    assert response.json()["controls"]["memory_enforcement"] is False


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
    assert body["request_id"]


def test_sandbox_run_alias_is_rate_limited(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import sandbox

    monkeypatch.setattr(sandbox, "_rate_allowed", lambda _user_id: False)
    response = client.post("/api/v1/sandbox/run", json={"code": "print(1)"}, headers=auth_headers)
    assert response.status_code == 429


def test_sandbox_run_history_is_private(client, admin_headers, auth_headers):
    created = client.post("/api/v1/sandbox/run", json={"code": "print(1)"}, headers=admin_headers)
    assert created.status_code == 200
    run_id = created.json()["request_id"]

    own_run = client.get(f"/api/v1/sandbox/runs/{run_id}", headers=admin_headers)
    other_user = client.get(f"/api/v1/sandbox/runs/{run_id}", headers=auth_headers)
    assert own_run.status_code == 200
    assert other_user.status_code == 404


def test_mounted_silverwing_tool_invocation_uses_jarvis_auth(client, admin_headers):
    from jarvis_backend.core import create_token, get_store

    endpoint = "/silverwing/api/tools/invoke"
    payload = {"tool": "code_executor", "input": {"code": "print(42)"}}
    assert client.post(endpoint, json=payload).status_code == 401
    assert client.post(endpoint, json=payload, headers=admin_headers).status_code == 403

    user_id = "test-silverwing-code-execution"
    users = get_store("users")
    records = users.load()
    previous = copy.deepcopy(records.get(user_id))
    records[user_id] = {
        "id": user_id,
        "email": "silverwing-code-execution@test.local",
        "is_active": True,
        "roles": ["admin"],
        "capabilities": ["code_execution"],
    }
    users.save()
    headers = {"Authorization": f"Bearer {create_token({'sub': user_id})}"}
    try:
        response = client.post(endpoint, json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["output_data"]["stdout"].strip() == "42"
    finally:
        records = users.load()
        if previous is None:
            records.pop(user_id, None)
        else:
            records[user_id] = previous
        users.save()


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


def test_coder_agent_has_execute_capability(client, auth_headers):
    response = client.get("/api/v1/agents/coder", headers=auth_headers)
    assert response.status_code == 200
    agent = response.json()
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
