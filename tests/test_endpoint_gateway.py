import uuid

import pytest

from jarvis_backend.chat_service import chat_service
from jarvis_backend.core import create_token, get_store
from jarvis_backend.runtime_events import RuntimeEventType, runtime_event_service


def _registration_payload(session_id: str, device_identity: str) -> dict:
    return {
        "deviceIdentity": device_identity,
        "runtimeVersion": "1.0",
        "sessionId": session_id,
        "capabilities": {
            "clientId": "jarvis-web",
            "runtimeVersion": "1.0",
            "platform": "web",
            "surfaces": ["web"],
            "renderers": ["text.renderer", "status.renderer", "map.renderer"],
            "environments": ["conversation", "geospatial"],
            "primitives": ["text", "status", "map", "marker", "control"],
            "media": [],
            "spatial": [],
            "input": ["text", "zoom", "pan", "recenter"],
            "output": ["text"],
        },
    }


def test_endpoint_registration_requires_authenticated_identity(client):
    response = client.post(
        "/api/v1/endpoints/register",
        json=_registration_payload("session-missing", str(uuid.uuid4())),
    )

    assert response.status_code == 401


def test_endpoint_registration_is_persistent_scoped_and_attaches_session(
    client, auth_headers,
):
    session_id = f"session-{uuid.uuid4()}"
    device_identity = str(uuid.uuid4())
    chat_service.create_session("testuser", session_id, "endpoint test")
    payload = _registration_payload(session_id, device_identity)

    registered = client.post(
        "/api/v1/endpoints/register",
        json=payload,
        headers=auth_headers,
    )
    assert registered.status_code == 200
    data = registered.json()
    endpoint_id = data["endpoint"]["endpointId"]
    endpoint_token = data["endpointToken"]
    assert endpoint_token.startswith(f"jep_{endpoint_id}.")
    assert data["endpoint"]["securityState"] == "authenticated"
    assert data["endpoint"]["state"] == "registered"
    assert data["endpoint"]["activeSessions"] == []
    assert data["runtimeCapabilities"]["renderers"]
    persisted_record = next(
        record for record in get_store("endpoints").reload().values()
        if record["endpoint_id"] == endpoint_id
    )
    assert endpoint_token not in str(persisted_record)
    assert persisted_record["credentials"][0]["hash"]
    assert runtime_event_service.replay("testuser", session_id)[-1].type == (
        RuntimeEventType.DEVICE_DISCOVERED
    )
    from sqlalchemy import select

    from infrastructure.audit_events import AuditEventRecord
    from jarvis_backend.db import get_engine

    with get_engine().connect() as connection:
        registration_audits = connection.execute(
            select(
                AuditEventRecord.__table__.c.request_id,
                AuditEventRecord.__table__.c.event_metadata,
            ).where(
                AuditEventRecord.user_id == "testuser",
                AuditEventRecord.resource_type == "endpoint",
                AuditEventRecord.resource_id == endpoint_id,
                AuditEventRecord.event_type == "endpoint.registered",
            )
        ).mappings().all()
    assert len(registration_audits) == 1
    registration_audit = registration_audits[0]
    registration_event = runtime_event_service.replay("testuser", session_id)[-1]
    assert registration_audit["request_id"] == registration_event.request_id
    assert endpoint_token not in str(registration_audit["event_metadata"])

    reconnected = client.post(
        "/api/v1/endpoints/register",
        json=payload,
        headers=auth_headers,
    )
    assert reconnected.status_code == 200
    assert reconnected.json()["endpoint"]["endpointId"] == endpoint_id
    assert reconnected.json()["endpointToken"] != endpoint_token

    listed = client.get("/api/v1/endpoints", headers=auth_headers)
    assert listed.status_code == 200
    assert [item["endpointId"] for item in listed.json()["endpoints"]] == [endpoint_id]
    persisted = get_store("endpoints").reload()
    assert any(record["endpoint_id"] == endpoint_id for record in persisted.values())


def test_endpoint_access_is_owner_scoped_and_disconnect_is_truthful(
    client, auth_headers,
):
    session_id = f"session-{uuid.uuid4()}"
    device_identity = str(uuid.uuid4())
    chat_service.create_session("testuser", session_id, "endpoint ownership")
    registered = client.post(
        "/api/v1/endpoints/register",
        json=_registration_payload(session_id, device_identity),
        headers=auth_headers,
    )
    endpoint_id = registered.json()["endpoint"]["endpointId"]
    endpoint_token = registered.json()["endpointToken"]
    heartbeat = client.post(
        f"/api/v1/endpoints/{endpoint_id}/heartbeat",
        json={},
        headers={"Authorization": f"Bearer {endpoint_token}"},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["endpoint"]["connectivity"] == "connected"

    second_session_id = f"session-{uuid.uuid4()}"
    chat_service.create_session("testuser", second_session_id, "handoff target")
    attached = client.post(
        f"/api/v1/endpoints/{endpoint_id}/sessions/{second_session_id}",
        headers={"Authorization": f"Bearer {endpoint_token}"},
    )
    assert attached.status_code == 200
    assert second_session_id in attached.json()["endpoint"]["activeSessions"]
    endpoint_headers = {"Authorization": f"Bearer {endpoint_token}"}
    own_resume = client.get(
        f"/api/v1/runtime/resume/{second_session_id}",
        headers=endpoint_headers,
    )
    assert own_resume.status_code == 200
    assert any(
        event["type"] == RuntimeEventType.DEVICE_STATE_UPDATED.value
        for event in own_resume.json()["events"]
    )

    unattached_session_id = f"session-{uuid.uuid4()}"
    chat_service.create_session("testuser", unattached_session_id, "not attached")
    denied_resume = client.get(
        f"/api/v1/runtime/resume/{unattached_session_id}",
        headers=endpoint_headers,
    )
    assert denied_resume.status_code == 403

    get_store("users").save_key("another-endpoint-user", {
        "id": "another-endpoint-user",
        "email": "another-endpoint-user@jarvis.local",
        "display_name": "Other User",
        "is_active": True,
        "roles": ["user"],
    })
    other_token = create_token({"sub": "another-endpoint-user"})
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert client.get("/api/v1/endpoints", headers=other_headers).json()["endpoints"] == []
    assert client.post(
        f"/api/v1/endpoints/{endpoint_id}/heartbeat",
        json={},
        headers=other_headers,
    ).status_code == 401

    readiness_before_disconnect = client.get("/health/ready")
    disconnected = client.delete(
        f"/api/v1/endpoints/{endpoint_id}",
        headers=auth_headers,
    )
    assert disconnected.status_code == 200
    endpoint = client.get("/api/v1/endpoints", headers=auth_headers).json()["endpoints"][0]
    assert endpoint["connectivity"] == "disconnected"
    assert endpoint["state"] == "disconnected"
    assert runtime_event_service.snapshot("testuser", session_id)["assistantState"] == "idle"
    readiness_after_disconnect = client.get("/health/ready")
    assert readiness_after_disconnect.status_code == readiness_before_disconnect.status_code
    assert (
        readiness_after_disconnect.json()["service_readiness"]
        == readiness_before_disconnect.json()["service_readiness"]
    )

    resumed_registration = client.post(
        "/api/v1/endpoints/register",
        json=_registration_payload(session_id, device_identity),
        headers=auth_headers,
    )
    assert resumed_registration.status_code == 200
    new_endpoint_id = resumed_registration.json()["endpoint"]["endpointId"]
    assert new_endpoint_id == endpoint_id
    new_endpoint_token = resumed_registration.json()["endpointToken"]
    assert client.post(
        f"/api/v1/endpoints/{new_endpoint_id}/heartbeat",
        json={},
        headers={"Authorization": f"Bearer {new_endpoint_token}"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/endpoints/{new_endpoint_id}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {new_endpoint_token}"},
    ).status_code == 200
    snapshot = client.get(
        f"/api/v1/runtime/snapshot/{session_id}",
        headers={"Authorization": f"Bearer {new_endpoint_token}"},
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["sequence"] >= 1


def test_endpoint_cannot_attach_another_owners_session(client, auth_headers):
    session_id = f"session-{uuid.uuid4()}"
    chat_service.create_session("testuser", session_id, "endpoint session")
    registered = client.post(
        "/api/v1/endpoints/register",
        json=_registration_payload(session_id, str(uuid.uuid4())),
        headers=auth_headers,
    )
    endpoint_id = registered.json()["endpoint"]["endpointId"]
    endpoint_token = registered.json()["endpointToken"]
    other_session_id = f"session-{uuid.uuid4()}"
    chat_service.create_session("another-endpoint-user", other_session_id, "private")

    response = client.post(
        f"/api/v1/endpoints/{endpoint_id}/sessions/{other_session_id}",
        headers={"Authorization": f"Bearer {endpoint_token}"},
    )

    assert response.status_code == 403


def test_ownerless_legacy_session_cannot_be_claimed_by_endpoint():
    from jarvis_backend.errors import ChatError

    session_id = f"legacy-session-{uuid.uuid4()}"
    get_store("chat_sessions").save_key(session_id, {
        "id": session_id,
        "title": "legacy ownerless",
        "messages": [],
    })
    with pytest.raises(ChatError) as error:
        chat_service.get_session("testuser", session_id)
    assert error.value.status_code == 403
