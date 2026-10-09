from __future__ import annotations

import uuid
import asyncio

import pytest

from jarvis_backend.presentation_contract import build_conversation_presentation
from jarvis_backend.runtime import (
    JarvisRuntime,
    PresentationRevisionConflictError,
)


class _SuccessfulGateway:
    timeout = 1
    max_retries = 0

    async def chat(self, messages, model=None, system=None, timeout=None):
        return {
            "content": "Persisted chat answer.",
            "model": "configured-test",
            "provider": "test",
            "latency_ms": 1,
            "usage": {},
        }


def _record(runtime, *, task_id, owner_id, request_id, idempotency_key,
            expected_revision, command_id=None):
    presentation = build_conversation_presentation(
        "A durable answer.",
        request_id=request_id,
        session_id="conversation-1",
        conversation_id="conversation-1",
    )
    return runtime.create_presentation_revision(
        task_id=task_id,
        owner_id=owner_id,
        request_id=request_id,
        conversation_id="conversation-1",
        command_id=command_id,
        presentation=presentation,
        expected_revision=expected_revision,
        idempotency_key=idempotency_key,
        compatibility={"decision": "text"},
    )


def test_presentation_revisions_are_idempotent_durable_and_owner_scoped():
    first_runtime = JarvisRuntime()
    task_id = str(uuid.uuid4())
    first = _record(
        first_runtime,
        task_id=task_id,
        owner_id="presentation-owner",
        request_id="request-1",
        idempotency_key="presentation-1",
        expected_revision=0,
    )
    repeated = _record(
        JarvisRuntime(),
        task_id=task_id,
        owner_id="presentation-owner",
        request_id="request-1",
        idempotency_key="presentation-1",
        expected_revision=0,
    )

    assert first["revision"] == 1
    assert repeated["revision_id"] == first["revision_id"]
    assert JarvisRuntime().get_presentation_revision(
        first["revision_id"], owner_id="presentation-owner",
    )["presentation"]["correlation"]["request_id"] == "request-1"
    assert JarvisRuntime().get_presentation_revision(
        first["revision_id"], owner_id="other-owner",
    ) is None
    with pytest.raises(PermissionError, match="owner"):
        _record(
            JarvisRuntime(),
            task_id=task_id,
            owner_id="other-owner",
            request_id="request-other",
            idempotency_key="presentation-other",
            expected_revision=0,
        )


def test_presentation_revisions_use_optimistic_concurrency_and_event_replay():
    runtime = JarvisRuntime()
    task_id = str(uuid.uuid4())
    command_id = str(uuid.uuid4())
    first = _record(
        runtime,
        task_id=task_id,
        owner_id="presentation-owner",
        request_id="request-1",
        idempotency_key="presentation-1",
        expected_revision=0,
        command_id=command_id,
    )
    with pytest.raises(PresentationRevisionConflictError, match="expected revision"):
        _record(
            JarvisRuntime(),
            task_id=task_id,
            owner_id="presentation-owner",
            request_id="request-2",
            idempotency_key="presentation-2",
            expected_revision=0,
        )
    second = _record(
        JarvisRuntime(),
        task_id=task_id,
        owner_id="presentation-owner",
        request_id="request-2",
        idempotency_key="presentation-2",
        expected_revision=first["revision"],
        command_id=command_id,
    )

    assert second["revision"] == 2
    assert [row["revision"] for row in JarvisRuntime().list_presentation_revisions(
        task_id, owner_id="presentation-owner",
    )] == [1, 2]
    events = runtime.replay_events(command_id)
    assert [event["type"] for event in events] == [
        "presentation.revision.created",
        "presentation.revision.created",
    ]


def test_chat_persists_presentation_and_idempotent_resend_does_not_duplicate():
    from jarvis_backend.chat_service import ChatService

    service = ChatService(gateway=_SuccessfulGateway())
    service.create_session("chat-owner", "chat-session", "Chat")
    first = asyncio.run(service.send_message(
        "chat-owner", "chat-session", "hello",
        client_message_id="client-message-1",
    ))
    resumed = asyncio.run(service.send_message(
        "chat-owner", "chat-session", "hello",
        client_message_id="client-message-1",
    ))

    assert first["status"] == "COMPLETED"
    assert first["canonical_task_id"]
    assert first["presentation_revision_id"]
    assert resumed["resumed"] is True
    assert resumed["presentation_revision_id"] == first["presentation_revision_id"]
    assert len(JarvisRuntime().list_presentation_revisions(
        first["canonical_task_id"], owner_id="chat-owner",
    )) == 1


def test_endpoint_recovery_creates_text_fallback_revision_without_losing_map_data(
    client, auth_headers,
):
    import json

    from jarvis_backend.presentation_contract import build_execution_presentation

    task_id = str(uuid.uuid4())
    contract = build_execution_presentation(
        operation="geography.coordinates.map",
        success=True,
        message="Validated user-supplied coordinates.",
        artifacts=[],
        tool_result=json.dumps({
            "result_available": True,
            "latitude": 47.6062,
            "longitude": -122.3321,
            "units": {
                "latitude": "degrees_north",
                "longitude": "degrees_east",
            },
        }),
        request_id="map-request",
        session_id="map-conversation",
        conversation_id="map-conversation",
        command_id=task_id,
        execution_id=str(uuid.uuid4()),
    )
    data_refs = {item["id"] for item in contract["data_refs"]}
    runtime = JarvisRuntime()
    runtime.create_presentation_revision(
        task_id=task_id,
        owner_id="testuser",
        request_id="map-request",
        conversation_id="map-conversation",
        command_id=task_id,
        presentation=contract,
        expected_revision=0,
        idempotency_key="map-original",
    )
    endpoint_response = client.post(
        "/api/v1/endpoints/register",
        headers=auth_headers,
        json={
            "supported_modalities": ["text"],
            "presentation_contract_versions": ["1.0"],
        },
    )
    assert endpoint_response.status_code == 200, endpoint_response.text
    endpoint_id = endpoint_response.json()["endpoint"]["endpoint_id"]
    negotiated = client.post(
        f"/api/v1/endpoints/{endpoint_id}/negotiate",
        headers=auth_headers,
        json={},
    )
    assert negotiated.status_code == 200

    recovery = client.post(
        f"/api/v1/presentations/{task_id}/recover",
        headers=auth_headers,
        json={
            "endpoint_id": endpoint_id,
            "idempotency_key": "map-recovery",
        },
    )
    assert recovery.status_code == 200, recovery.text
    revision = recovery.json()["revision"]
    assert revision["revision"] == 2
    assert revision["presentation"]["contract_version"] == "1.0"
    text = revision["presentation"]["components"][0]["text"]
    assert "47.60620, -122.33210" in text
    assert "user_provided_coordinates observed at" in text
    assert revision["presentation"]["data_refs"] == []
    assert runtime.list_presentation_revisions(
        task_id, owner_id="testuser",
    )[0]["presentation"]["data_refs"][0]["id"] in data_refs
    assert recovery.json()["compatibility"]["authorization_granted"] is False

    repeated = client.post(
        f"/api/v1/presentations/{task_id}/recover",
        headers=auth_headers,
        json={
            "endpoint_id": endpoint_id,
            "idempotency_key": "map-recovery",
        },
    )
    assert repeated.json()["revision"]["revision_id"] == revision["revision_id"]
    assert len(client.get(
        f"/api/v1/presentations/{task_id}/revisions",
        headers=auth_headers,
    ).json()["revisions"]) == 2
