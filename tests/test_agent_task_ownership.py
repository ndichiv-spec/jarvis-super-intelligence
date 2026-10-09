"""Agent task records and executions are isolated to their creator."""

import uuid

from jarvis_backend.core import create_token, get_store


def _headers_for(user_id: str) -> dict[str, str]:
    get_store("users").save_key(
        user_id,
        {
            "id": user_id,
            "email": f"{user_id}@example.test",
            "roles": ["user"],
            "is_active": True,
        },
    )
    return {"Authorization": f"Bearer {create_token({'sub': user_id})}"}


def test_agent_task_read_and_mutations_are_owner_scoped(client, auth_headers):
    created = client.post(
        "/api/v1/agents/task",
        headers=auth_headers,
        json={"name": "private task", "description": "private task description"},
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    other_headers = _headers_for(f"other-{uuid.uuid4().hex}")
    assert client.get("/api/v1/agents/tasks", headers=other_headers).json()["total"] == 0
    assert client.get("/api/v1/agents/executions", headers=other_headers).json()["total"] == 0

    assert client.post(
        f"/api/v1/agents/tasks/{task_id}/toggle",
        headers=other_headers,
        json={"enabled": False},
    ).status_code == 404
    assert client.post(
        f"/api/v1/agents/tasks/{task_id}/run",
        headers=other_headers,
    ).status_code == 404
    assert client.delete(
        f"/api/v1/agents/tasks/{task_id}",
        headers=other_headers,
    ).status_code == 404

    owner_tasks = client.get("/api/v1/agents/tasks", headers=auth_headers).json()
    assert [task["id"] for task in owner_tasks["tasks"]] == [task_id]
    assert client.delete(
        f"/api/v1/agents/tasks/{task_id}",
        headers=auth_headers,
    ).status_code == 200


def test_collaboration_tasks_are_owner_scoped(client, auth_headers):
    created = client.post(
        "/api/v1/agents/collaboration/task/create",
        headers=auth_headers,
        json={"description": "private collaboration"},
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    other_headers = _headers_for(f"other-{uuid.uuid4().hex}")
    assert client.get(
        "/api/v1/agents/collaboration/tasks/list",
        headers=other_headers,
    ).json()["total"] == 0
    assert client.post(
        "/api/v1/agents/collaboration/task/execute",
        headers=other_headers,
        json={"task_id": task_id},
    ).status_code == 404


def test_unconfigured_agent_scheduler_does_not_claim_to_be_running(client, auth_headers):
    status = client.get("/api/v1/agents/scheduler/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["running"] is False
    assert status.json()["status"] == "NOT_CONFIGURED"

    toggled = client.post(
        "/api/v1/agents/scheduler/toggle",
        headers=auth_headers,
        json={"running": True},
    )
    assert toggled.status_code == 501
    assert toggled.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"

    scheduled = client.post(
        "/api/v1/agents/tasks",
        headers=auth_headers,
        json={
            "name": "scheduled task",
            "description": "execute on a schedule",
            "schedule_type": "interval",
            "schedule_value": "60",
        },
    )
    assert scheduled.status_code == 501
    assert scheduled.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"
