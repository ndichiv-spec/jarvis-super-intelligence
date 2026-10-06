from __future__ import annotations

import time
import uuid

import pytest

from jarvis_backend.core import create_token
from jarvis_backend.routers import commands as command_router


def _headers_for_user(user_id: str = "testuser"):
    token = create_token({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_command_runtime_creates_and_lists_commands(client):
    response = client.post(
        "/api/v1/commands",
        json={"goal": "Check provider status", "conversation_id": "conv-1", "capabilities": ["provider.status"]},
        headers=_headers_for_user(),
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["command_id"]
    assert body["goal"] == "Check provider status"
    command_id = body["command_id"]

    for _ in range(30):
        result = client.get(f"/api/v1/commands/{command_id}", headers=_headers_for_user())
        if result.status_code == 200 and result.json().get("status") not in {"RECEIVED", "PLANNING"}:
            break
        time.sleep(0.2)

    item = client.get(f"/api/v1/commands/{command_id}", headers=_headers_for_user()).json()
    assert item["user_id"] == "testuser"
    assert item["status"] in {"READY", "EXECUTING", "COMPLETED", "FAILED", "PARTIAL", "AWAITING_AUTHORIZATION"}

    listing = client.get("/api/v1/commands", headers=_headers_for_user())
    assert listing.status_code == 200
    assert any(entry["command_id"] == command_id for entry in listing.json()["commands"])


def test_command_runtime_requires_approval_for_risky_capability(client):
    response = client.post(
        "/api/v1/commands",
        json={"goal": "Inspect github repo", "conversation_id": "conv-approve", "capabilities": ["github.inspect"]},
        headers=_headers_for_user(),
    )
    assert response.status_code == 202, response.text
    command_id = response.json()["command_id"]

    for _ in range(30):
        current = client.get(f"/api/v1/commands/{command_id}", headers=_headers_for_user())
        if current.status_code == 200 and current.json().get("status") == "AWAITING_AUTHORIZATION":
            break
        time.sleep(0.2)

    current = client.get(f"/api/v1/commands/{command_id}", headers=_headers_for_user()).json()
    assert current["status"] in {"AWAITING_AUTHORIZATION", "READY", "EXECUTING", "COMPLETED", "PARTIAL"}

    if current["status"] == "AWAITING_AUTHORIZATION":
        approve = client.post(
            f"/api/v1/commands/{command_id}/authorization",
            json={"approved": True},
            headers=_headers_for_user(),
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == "READY"

        final = client.get(f"/api/v1/commands/{command_id}", headers=_headers_for_user())
        assert final.status_code == 200
        assert final.json()["status"] in {"READY", "EXECUTING", "COMPLETED", "FAILED", "PARTIAL"}


def test_command_events_and_metrics_are_exposed(client):
    response = client.post(
        "/api/v1/commands",
        json={"goal": "Check provider status", "conversation_id": "conv-metrics", "capabilities": ["provider.status"]},
        headers=_headers_for_user(),
    )
    command_id = response.json()["command_id"]

    events = client.get(f"/api/v1/commands/{command_id}/events", headers=_headers_for_user())
    assert events.status_code == 200
    assert events.json()["command_id"] == command_id
    assert isinstance(events.json()["events"], list)

    metrics = client.get("/api/v1/commands/metrics", headers=_headers_for_user())
    assert metrics.status_code == 200
    assert metrics.json()["total_commands"] >= 1


def test_production_command_dispatch_is_durable_and_idempotent(client, monkeypatch):
    from jarvis_backend import celery_tasks

    dispatched = []
    monkeypatch.setattr(command_router, "is_production", lambda: True)
    monkeypatch.setattr(
        celery_tasks,
        "enqueue_command",
        lambda **kwargs: dispatched.append(kwargs) or "celery-task-1",
    )
    headers = _headers_for_user()
    payload = {
        "goal": "Check provider status",
        "conversation_id": "durable-command",
        "request_id": "durable-command-request-1",
        "capabilities": ["provider.status"],
    }

    first = client.post("/api/v1/commands", json=payload, headers=headers)
    second = client.post("/api/v1/commands", json=payload, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["command_id"] == second.json()["command_id"]
    assert first.json()["status"] == "QUEUED"
    assert first.json()["worker_task_id"] == "celery-task-1"
    assert len(dispatched) == 1
    assert dispatched[0]["command_id"] == first.json()["command_id"]

    conflicting = client.post(
        "/api/v1/commands",
        json={**payload, "goal": "A different command"},
        headers=headers,
    )
    assert conflicting.status_code == 409


def test_record_save_does_not_replace_other_worker_records():
    from jarvis_backend.core import Store
    from jarvis_backend.db import kv_delete, kv_insert_if_absent, kv_load

    store_name = f"command-record-isolation-{uuid.uuid4()}"
    left = Store(store_name)
    right = Store(store_name)
    left.load()
    assert kv_insert_if_absent(store_name, "command-a", {"status": "QUEUED"})
    right.reload()
    right.save_key("command-b", {"status": "QUEUED"})
    left.save_key("command-c", {"status": "QUEUED"})

    assert kv_load(store_name) == {
        "command-a": {"status": "QUEUED"},
        "command-b": {"status": "QUEUED"},
        "command-c": {"status": "QUEUED"},
    }
    assert not kv_insert_if_absent(store_name, "command-a", {"status": "FAILED"})
    kv_delete(store_name, "command-a")
    kv_delete(store_name, "command-b")
    kv_delete(store_name, "command-c")


def test_worker_command_claim_is_atomic_and_duplicate_safe(monkeypatch):
    record = {"command_id": "command-claim", "status": "QUEUED", "worker_attempts": 0}

    class Store:
        def update_key(self, key, transform):
            assert key == "command-claim"
            updated = transform(record.copy())
            record.update(updated)
            return record.copy()

    monkeypatch.setattr(command_router, "_commands_store", Store)

    claimed = command_router._claim_command_for_worker(
        "command-claim",
        "worker-task-1",
        "worker-1",
        resume=False,
        redelivered=False,
    )
    duplicate = command_router._claim_command_for_worker(
        "command-claim",
        "worker-task-2",
        "worker-2",
        resume=False,
        redelivered=False,
    )

    assert claimed is not None
    assert claimed["status"] == "RECEIVED"
    assert claimed["worker_task_id"] == "worker-task-1"
    assert claimed["worker_id"] == "worker-1"
    assert duplicate is None
    assert record["worker_attempts"] == 1


def test_expired_worker_lease_requeues_persisted_checkpoint(monkeypatch):
    record = {
        "command_id": "command-crashed",
        "user_id": "owner-1",
        "goal": "Continue task",
        "autonomy": "SUPERVISED",
        "task_id": "execution-checkpoint",
        "status": "EXECUTING",
        "lease_expires_at": 5.0,
        "events": [],
    }

    class Store:
        def load(self):
            return {"command-crashed": record}

        def update_key(self, key, transform):
            assert key == "command-crashed"
            updated = transform(record.copy())
            record.clear()
            record.update(updated)
            return record.copy()

    enqueued = []
    monkeypatch.setattr(command_router, "_commands_store", Store)
    from jarvis_backend import celery_tasks

    monkeypatch.setattr(
        celery_tasks,
        "enqueue_command",
        lambda **kwargs: enqueued.append(kwargs) or "recovery-task-1",
    )

    result = command_router._recover_expired_commands(now=100.0)

    assert result == {"recovered": 1, "enqueue_failures": 0}
    assert record["status"] == "QUEUED"
    assert record["worker_task_id"] == "recovery-task-1"
    assert enqueued[0]["resume"] is True
    assert enqueued[0]["command_id"] == "command-crashed"
    assert record["events"][-1]["event"] == "worker_lease_expired"


@pytest.mark.asyncio
async def test_rejected_command_authorization_is_terminal(monkeypatch):
    command = {
        "command_id": "command-1",
        "user_id": "owner-1",
        "status": "AWAITING_AUTHORIZATION",
        "authorization": {"required": True},
    }

    class Store:
        def load(self):
            return {"command-1": command}

        def save(self):
            return None

    monkeypatch.setattr(command_router, "_commands_store", Store)
    monkeypatch.setattr(command_router, "_append_event", lambda *args, **kwargs: None)
    response = await command_router.authorize_command(
        "command-1",
        command_router.CommandAuthorization(approved=False),
        {"id": "owner-1"},
    )

    assert response["status"] == "CANCELLED"
    assert response["authorization"]["approved"] is False
    assert "rejected" in response["errors"][0].lower()


@pytest.mark.asyncio
async def test_command_metrics_only_include_authenticated_owner(monkeypatch):
    class Store:
        def load(self):
            return {
                "mine": {"user_id": "owner-1", "status": "COMPLETED"},
                "theirs": {"user_id": "owner-2", "status": "FAILED"},
            }

    monkeypatch.setattr(command_router, "_commands_store", Store)
    metrics = await command_router.get_command_metrics({"id": "owner-1"})

    assert metrics["total_commands"] == 1
    assert metrics["by_status"]["COMPLETED"] == 1
    assert metrics["by_status"]["FAILED"] == 0
