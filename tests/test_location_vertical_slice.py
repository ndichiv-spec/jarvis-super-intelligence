import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from jarvis_backend.capability import CapabilityRegistry, ExecutionContext, Orchestrator
from jarvis_backend.capabilities.location import LocationCurrentCapability
from jarvis_backend.chat_service import ChatService
from jarvis_backend.core import create_token, get_store
from jarvis_backend.presentation.context import presentation_context_service
from jarvis_backend.presentation.location_data import ephemeral_location_data
from jarvis_backend.presentation.schemas import PresentationCapabilities
from jarvis_backend.runtime_events import RuntimeEventType, runtime_event_service


def _map_client() -> PresentationCapabilities:
    return PresentationCapabilities.model_validate({
        "clientId": "jarvis-web",
        "platform": "web",
        "surfaces": ["web"],
        "renderers": ["map.renderer", "text.renderer", "status.renderer"],
        "environments": ["conversation", "geospatial"],
        "primitives": ["text", "status", "map", "marker", "control"],
        "input": ["text", "zoom", "pan", "recenter"],
        "output": ["text"],
    })


@pytest.mark.asyncio
async def test_location_capability_requires_permission_and_rejects_stale_input():
    registry = CapabilityRegistry()
    capability = LocationCurrentCapability()
    registry.register(capability)
    now = datetime.now(UTC)

    denied = await capability.execute(
        {
            "latitude": 42.3,
            "longitude": -71.1,
            "captured_at": now.isoformat(),
        },
        ExecutionContext(user_id="user-a", session_id="session-a"),
    )
    assert denied.success is False
    assert denied.error_type == "PERMISSION_DENIED"

    stale = await capability.execute(
        {
            "latitude": 42.3,
            "longitude": -71.1,
            "captured_at": (now - timedelta(minutes=3)).isoformat(),
        },
        ExecutionContext(
            user_id="user-a",
            session_id="session-a",
            correlation_id="REQ-stale",
            permissions=["location:read"],
        ),
    )
    assert stale.success is False
    assert stale.error_type == "STALE_LOCATION"

    invalid = await capability.execute(
        {
            "latitude": 91,
            "longitude": -71.1,
            "captured_at": now.isoformat(),
        },
        ExecutionContext(
            user_id="user-a",
            session_id="session-a",
            correlation_id="REQ-invalid",
            permissions=["location:read"],
        ),
    )
    assert invalid.success is False
    assert invalid.error_type == "INVALID_LOCATION"

    fresh = await capability.execute(
        {
            "latitude": 42.3,
            "longitude": -71.1,
            "accuracy_meters": 8.5,
            "captured_at": now.isoformat(),
        },
        ExecutionContext(
            user_id="user-a",
            session_id="session-a",
            correlation_id="REQ-fresh",
            permissions=["location:read"],
        ),
    )
    assert fresh.success is True
    assert fresh.data["source"] == "browser_geolocation"
    assert fresh.data["accuracyMeters"] == 8.5
    assert fresh.data["freshness"]["ageSeconds"] >= 0
    assert "altitudeMeters" not in fresh.data

    recorded_events = registry.event_bus.get_events()
    assert all(
        "latitude" not in json.dumps(event["payload"])
        and "longitude" not in json.dumps(event["payload"])
        for event in recorded_events
    )


@pytest.mark.asyncio
async def test_chat_location_flow_is_private_correlated_and_plans_map(monkeypatch):
    user_id = f"location-user-{uuid.uuid4()}"
    session_id = f"location-session-{uuid.uuid4()}"
    request_id = f"REQ-{uuid.uuid4()}"
    location = {
        "latitude": 42.3,
        "longitude": -71.1,
        "accuracy_meters": 8.5,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    registry = CapabilityRegistry()
    registry.register(LocationCurrentCapability())
    orchestrator = Orchestrator(registry)
    monkeypatch.setattr(
        "jarvis_backend.capability.get_orchestrator",
        lambda: orchestrator,
    )
    presentation_context_service.save_client_capabilities(user_id, _map_client())

    service = ChatService()
    service.create_session(user_id, session_id)
    response = await service.send_message(
        user_id,
        session_id,
        "Where am I?",
        request_id=request_id,
        principal={"id": user_id, "roles": ["user"]},
        location=location,
    )

    assert response["status"] == "COMPLETED"
    assert response["request_id"] == request_id
    assert "map" in response["message"].lower()
    intent = response["presentation"]["intent"]
    assert intent["environment"]["type"] == "geospatial"
    assert intent["visualizations"][0]["type"] == "map"
    assert intent["visualizations"][0]["data"]["resource"].endswith(intent["id"])

    session = service.get_session(user_id, session_id)
    serialized_session = json.dumps(session)
    assert str(location["latitude"]) not in serialized_session
    assert str(location["longitude"]) not in serialized_session
    assert str(location["latitude"]) not in json.dumps(response["runtime_events"])

    events = runtime_event_service.replay(user_id, session_id)
    request_events = [event for event in events if event.request_id == request_id]
    assert RuntimeEventType.LOCATION_REQUESTED in {event.type for event in request_events}
    assert RuntimeEventType.LOCATION_RECEIVED in {event.type for event in request_events}
    assert RuntimeEventType.PRESENTATION_CREATED in {event.type for event in request_events}
    location_events = [
        event for event in request_events
        if event.type in {RuntimeEventType.LOCATION_REQUESTED, RuntimeEventType.LOCATION_RECEIVED}
    ]
    assert location_events
    assert len({event.execution_id for event in location_events}) == 1
    assert all(event.security.sensitivity == "sensitive" for event in location_events)
    assert str(location["longitude"]) not in json.dumps([event.model_dump(mode="json") for event in events])

    reference = ephemeral_location_data.get_for_presentation(
        intent["id"],
        user_id=user_id,
    )
    assert reference is not None
    assert reference["session_id"] == session_id
    assert reference["value"]["longitude"] == location["longitude"]


@pytest.mark.asyncio
async def test_chat_location_denial_does_not_execute_capability(monkeypatch):
    user_id = f"location-viewer-{uuid.uuid4()}"
    session_id = f"location-denied-session-{uuid.uuid4()}"

    def forbidden_orchestrator():
        raise AssertionError("Unauthorized location must not access the capability runtime.")

    monkeypatch.setattr(
        "jarvis_backend.capability.get_orchestrator",
        forbidden_orchestrator,
    )
    action = await ChatService()._execute_conversation_action(
        "Where am I?",
        user_id,
        session_id,
        f"REQ-{uuid.uuid4()}",
        principal={"id": user_id, "roles": ["viewer"]},
        location={
            "latitude": 42.3,
            "longitude": -71.1,
            "captured_at": datetime.now(UTC).isoformat(),
        },
    )

    assert action is not None
    assert action["success"] is False
    assert action["error_type"] == "PERMISSION_DENIED"
    assert "authorized" in action["message"]


@pytest.mark.asyncio
async def test_location_presentation_routes_enforce_auth_and_owner_scope(test_client, auth_headers):
    session_id = f"protected-location-session-{uuid.uuid4()}"
    presentation_id = f"presentation-{uuid.uuid4()}"
    request_id = f"REQ-{uuid.uuid4()}"
    execution_id = f"exec-{uuid.uuid4()}"
    user_id = "testuser"
    ChatService().create_session(user_id, session_id)
    reference = ephemeral_location_data.create(
        user_id,
        session_id,
        request_id,
        execution_id,
        {
            "latitude": 42.3,
            "longitude": -71.1,
            "accuracyMeters": 8.0,
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "browser_geolocation",
            "freshness": {"capturedAt": datetime.now(UTC).isoformat(), "ageSeconds": 0},
        },
    )
    ephemeral_location_data.attach_presentation(reference, presentation_id)

    unauthenticated = await test_client.get(
        f"/api/v1/presentation/location/{presentation_id}",
    )
    assert unauthenticated.status_code in {401, 403}
    authorized = await test_client.get(
        "/api/v1/presentation/location/authorization",
        headers=auth_headers,
    )
    assert authorized.json() == {"authorized": True}

    current_user_data = await test_client.get(
        f"/api/v1/presentation/location/{presentation_id}",
        headers=auth_headers,
    )
    assert current_user_data.status_code == 200
    assert current_user_data.json()["longitude"] == -71.1

    users = get_store("users")
    users.save_key("location-viewer", {
        "id": "location-viewer",
        "email": "location-viewer@jarvis.local",
        "is_active": True,
        "roles": ["viewer"],
    })
    viewer_headers = {
        "Authorization": f"Bearer {create_token({'sub': 'location-viewer'})}",
    }
    viewer_permission = await test_client.get(
        "/api/v1/presentation/location/authorization",
        headers=viewer_headers,
    )
    assert viewer_permission.json() == {"authorized": False}
    viewer_data = await test_client.get(
        f"/api/v1/presentation/location/{presentation_id}",
        headers=viewer_headers,
    )
    assert viewer_data.status_code == 403

    premature_interaction = await test_client.post(
        f"/api/v1/presentation/location/{presentation_id}/interactions",
        headers=auth_headers,
        json={"action": "zoom"},
    )
    assert premature_interaction.status_code == 409
    rendered = await test_client.post(
        f"/api/v1/presentation/location/{presentation_id}/rendered",
        headers=auth_headers,
        json={},
    )
    assert rendered.status_code == 200
    events = runtime_event_service.replay(user_id, session_id)
    map_event = next(event for event in events if event.type == RuntimeEventType.MAP_CREATED)
    assert map_event.request_id == request_id
    assert map_event.execution_id == execution_id
    assert str(42.3) not in json.dumps(map_event.model_dump(mode="json"))

    interaction = await test_client.post(
        f"/api/v1/presentation/location/{presentation_id}/interactions",
        headers=auth_headers,
        json={"action": "zoom"},
    )
    assert interaction.status_code == 200
    events = runtime_event_service.replay(user_id, session_id)
    updated_map = next(event for event in events if event.type == RuntimeEventType.MAP_UPDATED)
    assert updated_map.request_id == request_id
    assert updated_map.execution_id == execution_id
    assert updated_map.data == {"interaction": "zoom"}
