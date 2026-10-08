from __future__ import annotations

import json
import uuid

from mcp.types import LATEST_PROTOCOL_VERSION

from jarvis_backend.core import create_token, get_store
from jarvis_backend.runtime import runtime


def _mcp_post(client, method: str, params: dict, token: str, request_id: int = 1):
    return client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        },
    )


def _add_user(user_id: str) -> str:
    users = get_store("users").load()
    users[user_id] = {"id": user_id, "status": "active"}
    get_store("users").save()
    return create_token({"sub": user_id})


def test_authenticated_mcp_protocol_discovers_and_executes_real_capabilities(client):
    user_id = str(uuid.uuid4())
    token = _add_user(user_id)

    initialized = _mcp_post(
        client,
        "initialize",
        {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "jarvis-test-client", "version": "1"},
        },
        token,
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "jarvis"

    listed = _mcp_post(client, "tools/list", {}, token, request_id=2)
    tools = listed.json()["result"]["tools"]
    assert listed.status_code == 200
    assert any(tool["name"] == "project.test_status" for tool in tools)
    assert any(tool["name"] == "jarvis_command_events" for tool in tools)

    executed = _mcp_post(
        client,
        "tools/call",
        {"name": "project.test_status", "arguments": {}},
        token,
        request_id=3,
    )
    assert executed.status_code == 200
    tool_result = executed.json()["result"]
    assert tool_result["isError"] is False
    capability_output = json.loads(tool_result["content"][0]["text"])
    assert capability_output["tool"] == "project.test_status"
    assert capability_output["success"] is True

    resource = _mcp_post(
        client,
        "resources/read",
        {"uri": "jarvis://runtime/status"},
        token,
        request_id=4,
    )
    assert resource.status_code == 200
    resource_state = json.loads(resource.json()["result"]["contents"][0]["text"])
    assert resource_state["runtime"] == "ALIVE"
    assert resource_state["database"] == "AVAILABLE"
    assert resource_state["mcp"]["events_replay"] is True

    mcp_status = client.get(
        "/api/v1/mcp/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mcp_status.status_code == 200
    assert mcp_status.json()["status"] == "AVAILABLE"
    assert mcp_status.json()["executable"] is True

    snapshot = client.get(
        "/api/v1/runtime",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshot.status_code == 200
    runtime_state = snapshot.json()["runtime"]
    assert runtime_state["status"] == "ALIVE"
    assert runtime_state["service_readiness"] == "READY"
    assert snapshot.json()["mcp"]["status"] == "AVAILABLE"

    readiness = client.get("/health/ready")
    assert readiness.status_code == 200
    readiness_state = readiness.json()
    assert readiness_state["alive"] is True
    assert readiness_state["service_readiness"] == "ready"
    assert readiness_state["ai_execution_readiness"] in {"ready", "degraded"}


def test_mcp_requires_authentication_and_command_event_access_is_owner_scoped(client):
    owner_id, other_id, command_id = (
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
    )
    owner_token = _add_user(owner_id)
    other_token = _add_user(other_id)

    commands = get_store("commands").load()
    commands[command_id] = {
        "command_id": command_id,
        "user_id": owner_id,
        "status": "COMPLETED",
        "events": [],
    }
    get_store("commands").save()
    runtime.append_event(
        command_id=command_id,
        event_type="command.completed",
        payload={"verified": True},
    )

    unauthenticated = client.post(
        "/mcp/",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"

    owner_result = _mcp_post(
        client,
        "tools/call",
        {
            "name": "jarvis_command_events",
            "arguments": {"command_id": command_id, "after_sequence": 0},
        },
        owner_token,
    ).json()["result"]
    assert owner_result["isError"] is False
    assert json.loads(owner_result["content"][0]["text"])[0]["type"] == "command.completed"

    other_result = _mcp_post(
        client,
        "tools/call",
        {
            "name": "jarvis_command_events",
            "arguments": {"command_id": command_id, "after_sequence": 0},
        },
        other_token,
        request_id=2,
    ).json()["result"]
    assert other_result["isError"] is True
    assert "Command not found" in other_result["content"][0]["text"]
