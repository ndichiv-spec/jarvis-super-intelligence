"""Unit tests for the n8n-backed automation router.

Offline by design: n8n HTTP calls are mocked so tests never touch the live
n8n instance. They cover task merging, webhook extraction, authorization,
truthful run failures, and the plain-text webhook response path.
"""

from __future__ import annotations

import json

import pytest

from jarvis_backend import core
from jarvis_backend.routers import automation as mod


@pytest.fixture(autouse=True)
def _isolate_store():
    yield
    core.data.clear()


class FakeResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, status_code=200, text="allIncomingItems", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        if isinstance(self._json, BaseException):
            raise self._json
        if self._json is None:
            raise ValueError("Response content isn't valid JSON")
        return json.loads(json.dumps(self._json))


class FakeClient:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("get", url))
        return self.response

    async def post(self, url, **kwargs):
        self.calls.append(("post", url))
        return self.response


def _n8n_webhook_workflow(path: str, active: bool = True, nid: str = "1") -> dict:
    return {
        "id": nid,
        "publicId": f"pub-{nid}",
        "name": f"n8n-{path}",
        "active": active,
        "type": "workflow",
        "nodes": [{
            "type": "n8n-nodes-base.webhook",
            "parameters": {"path": path, "httpMethod": "POST"},
        }],
        "connections": {},
        "updatedAt": "2026-09-15T00:00:00.000Z",
        "createdAt": "2026-09-01T00:00:00.000Z",
    }


def _auth_headers(roles: list[str]) -> dict[str, str]:
    import uuid

    from jarvis_backend.core import create_token

    uid = str(uuid.uuid4())
    users = core.get_store("users").load()
    users[uid] = {
        "id": uid,
        "email": f"{uid}@example.com",
        "username": f"u_{uid[:8]}",
        "status": "active",
        "roles": roles,
    }
    core.get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    return {"Authorization": f"Bearer {token}"}


def test_extract_webhook_path():
    assert mod._extract_webhook_path(_n8n_webhook_workflow("wf-cleanup")) == "wf-cleanup"
    assert mod._extract_webhook_path({"nodes": [{"type": "n8n-nodes-base.httpRequest"}]}) is None
    assert mod._extract_webhook_path({}) is None


def test_parse_run_response_plain_text():
    r = FakeResponse(status_code=200, text="allIncomingItems")
    import asyncio
    parsed = asyncio.run(mod._parse_run_response(r))
    assert isinstance(parsed, dict)
    assert parsed["message"] == "allIncomingItems"
    assert parsed["status_code"] == 200


def test_parse_run_response_json():
    r = FakeResponse(status_code=200, json_data={"ok": True})
    import asyncio
    parsed = asyncio.run(mod._parse_run_response(r))
    assert parsed == {"ok": True}


def test_default_task_shape():
    t = mod._default_task(mod._DEFAULT_WORKFLOWS[0])
    assert t["id"] == "wf-nightly-report"
    assert t["engine"] == "local"
    assert t["trigger_type"] == "schedule"
    assert "trigger_config" in t


def test_list_automation_local_only(client, monkeypatch):
    async def fake_list():
        return []
    monkeypatch.setattr(mod, "_n8n_list_workflows", fake_list)
    r = client.get("/api/v1/automation")
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "local"
    ids = {t["id"] for t in body["tasks"]}
    assert "wf-nightly-report" in ids and "wf-knowledge-digest" in ids and "wf-cleanup" in ids
    engines = {task["id"]: task["engine"] for task in body["tasks"]}
    assert engines["wf-nightly-report"] == "local"
    assert engines["wf-knowledge-digest"] == "local"
    assert engines["wf-cleanup"] == "n8n"


def test_list_automation_merges_n8n(client, monkeypatch):
    n8n_wf = _n8n_webhook_workflow("wf-cleanup", nid="42")
    async def fake_list():
        return [n8n_wf]
    monkeypatch.setattr(mod, "_n8n_list_workflows", fake_list)
    r = client.get("/api/v1/automation")
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "n8n"
    by_id = {t["id"]: t for t in body["tasks"]}
    assert "42" in by_id
    assert by_id["42"]["engine"] == "n8n"
    assert by_id["42"]["webhook_path"] == "wf-cleanup"
    assert by_id["42"]["trigger_type"] == "webhook"
    # n8n id mirror persisted to the store
    mirrored = core.get_store("misc").load().get("n8n_workflows", {})
    assert "42" in mirrored


def test_run_builtin_local_report(client, monkeypatch):
    async def fake_list():
        return []
    monkeypatch.setattr(mod, "_n8n_list_workflows", fake_list)
    def no_n8n(**_kwargs):
        raise AssertionError("built-in report must not depend on n8n")
    monkeypatch.setattr(mod.httpx, "AsyncClient", no_n8n)
    headers = _auth_headers(["admin"])
    r = client.post(
        "/api/v1/automation/task/wf-nightly-report/run",
        json={},
        headers=headers,
    )
    assert r.status_code == 200
    execution = r.json()["execution"]
    assert execution["status"] == "completed"
    assert execution["engine"] == "local"
    assert execution["result"]["scope"] == "current_backend_process"
    assert "capabilities" in execution["result"]
    assert core.get_store("executions").load()[-1]["id"] == execution["id"]
    workflow = core.get_store("misc").load()["workflows"]["wf-nightly-report"]
    assert workflow["last_run_status"] == "completed"
    audit = core.get_store("audit_logs").load()[-1]
    assert audit["ok"] is True
    assert audit["meta"]["status"] == "completed"
    history = client.get("/api/v1/automation/executions", headers=headers)
    assert history.status_code == 200
    assert history.json()["executions"][0]["id"] == execution["id"]


def test_task_run_requires_admin(client):
    url = "/api/v1/automation/task/wf-nightly-report/run"
    assert client.post(url, json={}).status_code == 401
    assert client.post(url, json={}, headers=_auth_headers(["user"])).status_code == 403
    assert client.get("/api/v1/automation/executions").status_code == 401


def test_run_n8n_webhook(client, monkeypatch):
    core.get_store("misc").load().setdefault("n8n_workflows", {})["42"] = (
        _n8n_webhook_workflow("wf-cleanup", nid="42")
    )
    core.get_store("misc").save()
    monkeypatch.setattr(
        mod.httpx, "AsyncClient",
        lambda **_kwargs: FakeClient(FakeResponse(status_code=200)),
    )
    r = client.post(
        "/api/v1/automation/task/42/run",
        json={"data": {"x": 1}},
        headers=_auth_headers(["developer"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["execution"]["engine"] == "n8n"
    assert body["execution"]["status"] == "accepted"
    assert body["execution"]["run"]["message"] == "allIncomingItems"
    assert core.get_store("executions").load()[-1]["status"] == "accepted"
    assert "run" not in core.get_store("executions").load()[-1]


def test_knowledge_digest_is_user_scoped():
    from jarvis_backend.automation_runners import knowledge_digest

    entries = core.get_store("knowledge").load()
    entries.update({
        "one": {"key": "owned", "category": "research", "user_id": "user-one"},
        "two": {"key": "other", "category": "secret", "user_id": "user-two"},
        "three": {"key": "shared", "category": "public", "user_id": "system"},
    })
    core.get_store("knowledge").save()

    result = knowledge_digest("user-one", {})

    assert result["entry_count"] == 2
    assert result["owned_entry_count"] == 1
    assert result["categories"] == {"research": 1, "public": 1}


def test_unimplemented_local_task_does_not_claim_success(client, monkeypatch):
    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient(FakeResponse(status_code=404)),
    )
    r = client.post(
        "/api/v1/automation/task/wf-cleanup/run",
        json={},
        headers=_auth_headers(["admin"]),
    )
    assert r.status_code == 502
    workflow = core.get_store("misc").load()["workflows"]["wf-cleanup"]
    assert workflow["last_run_status"] == "failed"
    assert core.get_store("executions").load()[-1]["status"] == "failed"


def test_n8n_endpoints_require_admin(client):
    import uuid

    from jarvis_backend.core import create_token, hash_password, now_iso
    users = core.get_store("users").load()
    uid = str(uuid.uuid4())
    user = {
        "id": uid, "email": f"{uid}@example.com", "username": f"u_{uid[:8]}",
        "password_hash": hash_password("S3cret!pass"), "full_name": "T",
        "status": "active", "roles": ["user"],
        "created_at": now_iso(),
    }
    users[uid] = user
    core.get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/automation/n8n/status", headers=headers).status_code == 403
    assert client.get("/api/v1/automation/n8n/workflows", headers=headers).status_code == 403
    assert client.post("/api/v1/automation/n8n/workflows/run",
                    json={"workflow_id": "1"}, headers=headers).status_code == 403


def test_n8n_status_up(client, monkeypatch):
    import uuid

    from jarvis_backend.core import create_token, hash_password, now_iso
    users = core.get_store("users").load()
    uid = str(uuid.uuid4())
    user = {
        "id": uid, "email": f"{uid}@example.com", "username": f"u_{uid[:8]}",
        "password_hash": hash_password("S3cret!pass"), "full_name": "T",
        "status": "active", "roles": ["admin"],
        "created_at": now_iso(),
    }
    users[uid] = user
    core.get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    monkeypatch.setattr(
        mod.httpx, "AsyncClient",
        lambda **_kwargs: FakeClient(FakeResponse(status_code=200, json_data={"version": "2.8.4"})),
    )
    r = client.get("/api/v1/automation/n8n/status",
                headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "n8n"
    assert body["status"] == "UP"
    assert body["version"] == "2.8.4"
