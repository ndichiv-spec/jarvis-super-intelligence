from __future__ import annotations

import sys
import time
from pathlib import Path
from types import ModuleType

from fastapi import FastAPI
from fastapi.testclient import TestClient

PLATFORM_ROOT = Path(__file__).resolve().parents[1] / "_tier1" / "canonical_repo" / "platform"
sys.path.insert(0, str(PLATFORM_ROOT))

# The package bootstrap is supplied by deployment tooling and is absent in
# this checkout; route tests exercise the API without starting external services.
try:
    import jarvis_runtime  # noqa: F401
except ModuleNotFoundError:
    runtime_bootstrap = ModuleType("jarvis_runtime")
    runtime_bootstrap.bootstrap_runtime = lambda: None
    sys.modules["jarvis_runtime"] = runtime_bootstrap
    _TEST_BOOTSTRAP_SHIM = True
else:
    _TEST_BOOTSTRAP_SHIM = False

from jarvis_backend.core import get_current_user
from jarvis_backend.routers import commands

if _TEST_BOOTSTRAP_SHIM:
    sys.modules.pop("jarvis_runtime", None)


class _MemoryStore:
    def __init__(self):
        self.value = {}

    def load(self):
        return self.value

    def save(self):
        pass


def test_authenticated_command_persists_events_and_waits_for_approval(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)
    store = _MemoryStore()
    store.value["stale-command"] = {
        "command_id": "stale-command",
        "user_id": "command-test-user",
        "status": "EXECUTING",
        "errors": [],
        "events": [],
    }
    monkeypatch.setattr(commands, "get_store", lambda _name: store)

    async def wait_for_authorization(command_id, user, autonomy):
        command = store.load()[command_id]
        command["status"] = "AWAITING_AUTHORIZATION"
        command["authorization"] = {
            "required": True,
            "capabilities": ["search_web"],
            "approved": None,
        }
        commands._append_event(
            command_id,
            "capability_authorization_required",
            capabilities=["search_web"],
        )
        await commands._authorization_events[command_id].wait()
        command["status"] = (
            "COMPLETED" if command["authorization"]["approved"] else "FAILED"
        )
        command["completed_at"] = time.time()
        commands._append_event(command_id, "command_finished")

    monkeypatch.setattr(commands, "_execute_command", wait_for_authorization)
    app = FastAPI()
    app.include_router(commands.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "command-test-user",
        "roles": [],
    }

    with TestClient(app) as client:
        interrupted = client.get("/api/v1/commands/stale-command").json()
        assert interrupted["status"] == "FAILED"
        assert interrupted["events"][0]["event"] == (
            "command_interrupted_without_execution_record"
        )

        payload = {
            "goal": "search for sources using API_KEY=sk-sensitive-test-value",
            "request_id": "cmd-request-1",
        }
        created = client.post("/api/v1/commands", json=payload)
        assert created.status_code == 202
        command_id = created.json()["command_id"]
        assert created.json()["status"] == "RECEIVED"
        assert "sk-sensitive-test-value" not in created.text
        duplicate = client.post("/api/v1/commands", json=payload)
        assert duplicate.status_code == 202
        assert duplicate.json()["command_id"] == command_id

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = client.get(f"/api/v1/commands/{command_id}").json()
            if snapshot["status"] == "AWAITING_AUTHORIZATION":
                break
            time.sleep(0.02)
        assert snapshot["status"] == "AWAITING_AUTHORIZATION"
        assert snapshot["events"][0]["event"] == "command_received"

        approved = client.post(
            f"/api/v1/commands/{command_id}/authorization",
            json={"approved": True},
        )
        assert approved.status_code == 200

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = client.get(f"/api/v1/commands/{command_id}").json()
            if snapshot["status"] == "COMPLETED":
                break
            time.sleep(0.02)
        assert snapshot["status"] == "COMPLETED"
        assert any(
            event["event"] == "authorization_granted"
            for event in snapshot["events"]
        )
        replay = client.get(
            f"/api/v1/commands/{command_id}/events?after_sequence=0",
        )
        assert replay.status_code == 200
        sequences = [event["sequence"] for event in replay.json()["events"]]
        assert sequences == sorted(set(sequences))

        app.dependency_overrides[get_current_user] = lambda: {
            "id": "another-user",
            "roles": [],
        }
        hidden = client.get(f"/api/v1/commands/{command_id}")
        assert hidden.status_code == 404
        hidden_events = client.get(f"/api/v1/commands/{command_id}/events")
        assert hidden_events.status_code == 404
        hidden_executions = client.get(
            f"/api/v1/commands/{command_id}/executions",
        )
        assert hidden_executions.status_code == 404
        hidden_plans = client.get(f"/api/v1/commands/{command_id}/plans")
        assert hidden_plans.status_code == 404
        commands._command_jobs.pop(command_id, None)
        commands._cancel_tokens.pop(command_id, None)
        commands._authorization_events.pop(command_id, None)


def test_command_controls_only_change_safe_execution_states(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JARVIS_DB_PATH", raising=False)
    store = _MemoryStore()
    monkeypatch.setattr(commands, "get_store", lambda _name: store)
    monkeypatch.setattr(commands, "_schedule_command", lambda *_args: None)

    app = FastAPI()
    app.include_router(commands.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "command-controls-user",
        "roles": [],
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/commands",
            json={"goal": "pause this queued operation"},
        ).json()
        command_id = created["command_id"]

        paused = client.post(f"/api/v1/commands/{command_id}/pause")
        assert paused.status_code == 200
        assert paused.json()["status"] == "PAUSED"
        resumed = client.post(f"/api/v1/commands/{command_id}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "RECEIVED"

        command = store.load()[command_id]
        execution_id = command["active_execution_id"]
        commands.jarvis_runtime.transition(
            execution_id, commands.ExecutionState.FAILED,
            error="worker failed before start",
        )
        command["status"] = "FAILED"
        store.save()
        retried = client.post(f"/api/v1/commands/{command_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["status"] == "QUEUED"
        assert commands.jarvis_runtime.get_execution(execution_id)["attempt"] == 2

        cancelled = client.post(f"/api/v1/commands/{command_id}/cancel")
        assert cancelled.status_code == 200
        assert commands.jarvis_runtime.get_execution(execution_id)["status"] == "CANCELLED"
