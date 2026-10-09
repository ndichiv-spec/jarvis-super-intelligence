import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from jarvis_backend.capability import CapabilityEvent
from jarvis_backend.capability import EventBus as CapabilityEventBus
from jarvis_backend.chat_service import ChatService
from jarvis_backend.core import create_token, get_store
from jarvis_backend import db
from jarvis_backend.event_fabric import Event, EventBus, get_event_bus
from jarvis_backend.runtime_events import (
    EventRetention,
    EventSensitivity,
    RuntimeEvent,
    RuntimeEventSource,
    RuntimeEventType,
    RuntimeState,
    runtime_event_service,
)


def test_runtime_journal_is_shared_across_process_restart(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'runtime-shared.db').as_posix()}"
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment.pop("JARVIS_TEST_MODE", None)

    writer = (
        "from jarvis_backend.runtime_events import RuntimeEventSource, "
        "RuntimeEventType, runtime_event_service; "
        f"event = runtime_event_service.emit(event_type=RuntimeEventType.REQUEST_CREATED, "
        f"user_id={user_id!r}, session_id={session_id!r}, "
        "source=RuntimeEventSource.CHAT); "
        "print(event.sequence)"
    )
    written = subprocess.run(
        [sys.executable, "-c", writer],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert written.stdout.strip() == "1"

    reader = (
        "from jarvis_backend.runtime_events import runtime_event_service; "
        f"events = runtime_event_service.replay({user_id!r}, {session_id!r}); "
        "print(events[0].sequence, events[0].session_id)"
    )
    replayed = subprocess.run(
        [sys.executable, "-c", reader],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert replayed.stdout.strip() == f"1 {session_id}"


def test_conversation_created_by_one_process_is_visible_to_another(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'conversation-shared.db').as_posix()}"
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment.pop("JARVIS_TEST_MODE", None)
    created = subprocess.run(
        [
            sys.executable,
            "-c",
            "from jarvis_backend.chat_service import chat_service; "
            f"session = chat_service.create_session({user_id!r}, {session_id!r}, 'shared'); "
            "print(session['id'])",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert created.stdout.strip() == session_id

    restored = subprocess.run(
        [
            sys.executable,
            "-c",
            "from jarvis_backend.chat_service import chat_service; "
            f"session = chat_service.get_session({user_id!r}, {session_id!r}); "
            "print(session['user_id'], session['title'])",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert restored.stdout.strip() == f"{user_id} shared"


def test_concurrent_processes_allocate_one_shared_sequence(tmp_path):
    from sqlalchemy import create_engine

    from jarvis_backend import db

    database_url = f"sqlite:///{(tmp_path / 'runtime-concurrent.db').as_posix()}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    db.metadata.create_all(engine)
    engine.dispose()
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment.pop("JARVIS_TEST_MODE", None)

    def publish(index):
        code = (
            "from jarvis_backend.runtime_events import RuntimeEventSource, "
            "RuntimeEventType, runtime_event_service; "
            f"event = runtime_event_service.emit(event_type=RuntimeEventType.REQUEST_CREATED, "
            f"user_id={user_id!r}, session_id={session_id!r}, "
            f"source=RuntimeEventSource.CHAT, data={{'worker': {index}}}); "
            "print(event.sequence)"
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()

    with ThreadPoolExecutor(max_workers=2) as pool:
        sequences = list(pool.map(publish, (1, 2)))

    assert sorted(map(int, sequences)) == [1, 2]
    reader = (
        "from jarvis_backend.runtime_events import runtime_event_service; "
        f"events = runtime_event_service.replay({user_id!r}, {session_id!r}); "
        "print(','.join(str(event.sequence) for event in events))"
    )
    replayed = subprocess.run(
        [sys.executable, "-c", reader],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert replayed.stdout.strip() == "1,2"


def test_runtime_journal_deduplicates_and_marks_expired_history_for_resync():
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"

    def build_event(sequence, snapshot):
        return (
            {"id": "durable-event", "sequence": sequence},
            snapshot or {"sequence": 0},
        )

    original, created = db.append_runtime_event(
        user_id,
        session_id,
        "durable-event",
        "session",
        build_event,
    )
    duplicate, duplicate_created = db.append_runtime_event(
        user_id,
        session_id,
        "durable-event",
        "session",
        build_event,
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate == original

    expired_id = "expired-event"
    db.append_runtime_event(
        user_id,
        session_id,
        expired_id,
        "session",
        lambda sequence, snapshot: (
            {"id": expired_id, "sequence": sequence},
            snapshot or {"sequence": 0},
        ),
        session_retention_days=0,
    )
    stream = db.read_runtime_stream(user_id, session_id, after=0)
    assert stream["resync_required"] is True
    assert stream["retention_floor"] == 2
    assert [event["sequence"] for event in stream["events"]] == [1]


def test_runtime_event_contract_validates_semantic_type_and_hides_principal():
    event = RuntimeEvent.model_validate({
        "id": "event-1",
        "protocolVersion": "1.0",
        "type": "request_created",
        "timestamp": "2026-10-08T10:00:00Z",
        "requestId": "request-1",
        "sessionId": "session-1",
        "source": "chat",
        "sequence": 1,
        "state": "waiting",
        "security": {
            "retention": "session",
            "sensitivity": "user",
            "principalId": "private-user-id",
        },
    })

    serialized = event.sse_data()
    assert event.event_id == "event-1"
    assert '"protocolVersion":"1.0"' in serialized
    assert '"correlation":{}' in serialized
    assert '"principalId"' not in serialized
    assert "private-user-id" not in serialized
    with pytest.raises(ValidationError):
        RuntimeEvent.model_validate({
            "id": "event-2",
            "type": "invented_event",
            "timestamp": "2026-10-08T10:00:00Z",
            "sessionId": "session-1",
            "source": "chat",
            "sequence": 1,
            "security": {"principalId": "user"},
        })


def test_runtime_event_journal_replay_snapshot_and_secret_redaction():
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    request_id = str(uuid.uuid4())
    start = runtime_event_service.emit(
        event_type=RuntimeEventType.REQUEST_CREATED,
        user_id=user_id,
        session_id=session_id,
        source=RuntimeEventSource.CHAT,
        request_id=request_id,
        conversation_id=session_id,
        capability_id="chat.respond",
        presentation_id="presentation-1",
        presentation={"kind": "text"},
        correlation={"requestId": "client-forged"},
        state=RuntimeState.WAITING,
        data={"api_key": "should-not-leak", "message": "Bearer abc.def.ghi"},
    )
    running = runtime_event_service.emit(
        event_type=RuntimeEventType.MODEL_STARTED,
        user_id=user_id,
        session_id=session_id,
        source=RuntimeEventSource.MODEL_RUNTIME,
        request_id=request_id,
        execution_id="exec-1",
        state=RuntimeState.THINKING,
    )

    assert (start.sequence, running.sequence) == (1, 2)
    assert start.event_id == start.id
    assert start.correlation["requestId"] == request_id
    assert start.presentation == {"kind": "text"}
    assert runtime_event_service.replay(user_id, session_id, after=1) == [running]
    assert start.data == {"message": "Bearer [REDACTED]"}
    assert "should-not-leak" not in json.dumps(runtime_event_service.snapshot(user_id, session_id))
    assert runtime_event_service.snapshot(user_id, session_id)["activeExecutions"] == [{
        "executionId": "exec-1",
        "requestId": request_id,
        "capabilityId": None,
        "state": "thinking",
    }]
    assert runtime_event_service.replay(f"{user_id}-other", session_id) == []


@pytest.mark.asyncio
async def test_runtime_event_subscriber_replays_retained_scoped_events():
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    saved = runtime_event_service.emit(
        event_type=RuntimeEventType.REQUEST_ACCEPTED,
        user_id=user_id,
        session_id=session_id,
        source=RuntimeEventSource.CHAT,
        request_id="req-replay",
        state=RuntimeState.THINKING,
    )

    subscription = runtime_event_service.subscribe(user_id, session_id, after=0)
    assert await anext(subscription) == saved
    await subscription.aclose()


def test_ephemeral_events_are_delivered_to_subscribers_but_not_replayed():
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    event = runtime_event_service.emit(
        event_type=RuntimeEventType.MODEL_TOKEN,
        user_id=user_id,
        session_id=session_id,
        source=RuntimeEventSource.MODEL_RUNTIME,
        request_id="request-ephemeral",
        data={"token": "private response fragment"},
        retention=EventRetention.EPHEMERAL,
        sensitivity=EventSensitivity.PRIVATE,
    )

    assert runtime_event_service.replay(user_id, session_id) == []
    assert event.security.retention == EventRetention.EPHEMERAL
    resume = runtime_event_service.resume(user_id, session_id, after=0)
    assert resume["resyncRequired"] is True
    assert resume["highWaterSequence"] == event.sequence
    assert resume["events"] == []


def test_ephemeral_fabric_events_are_not_retained_but_reach_subscribers():
    bus = EventBus(max_events=2)
    received = []
    bus.subscribe("*", received.append)
    event = Event.create(
        event_type="model.token",
        source="model_runtime",
        session_id="session-ephemeral",
        user_id="user-ephemeral",
        payload={
            "runtime_protocol": "1.0",
            "retention": "ephemeral",
            "token": "private response fragment",
        },
    )

    bus.emit(event_type=event.event_type, event=event)

    assert received == [event]
    assert bus.get_events() == []


def test_canonical_runtime_events_are_not_duplicated_in_process_local_history():
    bus = EventBus(max_events=2)
    received = []
    bus.subscribe("*", received.append)
    event = Event.create(
        event_type="request.created",
        source="chat",
        session_id="session-durable",
        user_id="user-durable",
        payload={"runtime_protocol": "1.0", "retention": "session"},
    )

    bus.emit(event_type=event.event_type, event=event)

    assert received == [event]
    assert bus.get_events() == []


def test_capability_lifecycle_is_bridged_into_the_canonical_runtime_stream():
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    request_id = str(uuid.uuid4())
    execution_id = f"exec-{uuid.uuid4()}"
    capability_bus = CapabilityEventBus()

    capability_bus.emit(CapabilityEvent(
        event_type="example.execution.started",
        source="orchestrator",
        capability="example",
        correlation_id=request_id,
        execution_id=execution_id,
        session_id=session_id,
        user_id=user_id,
        status="started",
    ))
    capability_bus.emit(CapabilityEvent(
        event_type="example.execution.completed",
        source="orchestrator",
        capability="example",
        correlation_id=request_id,
        execution_id=execution_id,
        session_id=session_id,
        user_id=user_id,
        status="failed",
    ))

    events = runtime_event_service.replay(user_id, session_id)
    assert [event.type for event in events] == [
        RuntimeEventType.CAPABILITY_STARTED,
        RuntimeEventType.CAPABILITY_FAILED,
    ]
    assert all(event.request_id == request_id for event in events)
    assert all(event.execution_id == execution_id for event in events)
    assert runtime_event_service.snapshot(user_id, session_id)["activeExecutions"] == []


def test_image_generation_failure_and_artifact_references_are_projected_truthfully():
    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    execution_id = f"exec-{uuid.uuid4()}"
    failure = Event.create(
        event_type="image.generation.failed",
        source="image.generate",
        capability="image.generate",
        correlation_id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        status="failed",
        payload={
            "execution_id": execution_id,
            "success": False,
            "artifact_count": 0,
            "prompt": "must not appear in runtime data",
        },
    )
    get_event_bus().emit(event_type=failure.event_type, event=failure)
    completed = Event.create(
        event_type="image.generation.completed",
        source="image.generate",
        capability="image.generate",
        correlation_id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        status="completed",
        payload={
            "execution_id": execution_id,
            "artifact_count": 1,
            "artifact_ids": ["authorized-artifact-ref"],
        },
    )
    get_event_bus().emit(event_type=completed.event_type, event=completed)

    events = runtime_event_service.replay(user_id, session_id)
    assert [event.type for event in events] == [
        RuntimeEventType.IMAGE_GENERATION_FAILED,
        RuntimeEventType.IMAGE_GENERATION_COMPLETED,
    ]
    assert events[0].state == RuntimeState.FAILED
    assert "prompt" not in events[0].data
    assert events[1].data["artifactIds"] == ["authorized-artifact-ref"]
    assert events[1].execution_id == execution_id


@pytest.mark.asyncio
async def test_chat_runtime_events_share_request_identity_and_complete_lifecycle():
    class Gateway:
        timeout = 1

        async def chat(self, *args, **kwargs):
            return {
                "content": "A real response from the test provider.",
                "provider": "test-provider",
                "model": "test-model",
                "usage": {},
            }

    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    service = ChatService(gateway=Gateway())
    service._plan_presentation = lambda *_args, **_kwargs: None
    service.create_session(user_id, session_id, "runtime event test")

    result = await service.send_message(user_id, session_id, "Hello, JARVIS")
    emitted = runtime_event_service.replay(user_id, session_id)
    created = next(
        event for event in emitted
        if event.type == RuntimeEventType.REQUEST_CREATED
        and event.message_id == result["message_id"]
    )
    request_events = [event for event in emitted if event.request_id == created.request_id]

    assert result["status"] == "COMPLETED"
    assert request_events
    assert {event.type for event in request_events} >= {
        RuntimeEventType.REQUEST_CREATED,
        RuntimeEventType.REQUEST_ACCEPTED,
        RuntimeEventType.MODEL_STARTED,
        RuntimeEventType.MODEL_COMPLETED,
        RuntimeEventType.MESSAGE_COMPLETED,
        RuntimeEventType.REQUEST_COMPLETED,
    }
    model_started = next(
        event for event in request_events
        if event.type == RuntimeEventType.MODEL_STARTED
    )
    assert model_started.execution_id
    assert len({event.id for event in request_events}) == len(request_events)


@pytest.mark.asyncio
async def test_stream_fallback_preserves_canonical_request_id():
    class Gateway:
        timeout = 1

        async def chat(self, *args, **kwargs):
            return {
                "content": "A buffered response from the test provider.",
                "provider": "test-provider",
                "model": "test-model",
                "usage": {},
            }

        async def stream_chat(self, **kwargs):
            if False:
                yield {}

    user_id = f"user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    service = ChatService(gateway=Gateway())
    service._plan_presentation = lambda *_args, **_kwargs: None
    service.create_session(user_id, session_id, "stream fallback test")

    frames = [
        frame async for frame in service.stream_message(
            user_id, session_id, "Hello, JARVIS"
        )
    ]
    emitted = runtime_event_service.replay(user_id, session_id)
    created = next(
        event for event in emitted
        if event.type == RuntimeEventType.REQUEST_CREATED
    )
    request_events = [event for event in emitted if event.request_id == created.request_id]
    model_starts = [
        event for event in request_events
        if event.type == RuntimeEventType.MODEL_STARTED
    ]

    assert frames[-1]["type"] == "complete"
    assert frames[-1]["request_id"] == created.request_id
    assert len(model_starts) == 2
    assert all(event.execution_id for event in model_starts)
    assert any(event.type == RuntimeEventType.REQUEST_COMPLETED for event in request_events)


def test_runtime_snapshot_is_not_visible_to_another_authenticated_user(
    client, auth_headers,
):
    from jarvis_backend.chat_service import chat_service

    session_id = f"session-{uuid.uuid4()}"
    chat_service.create_session("testuser", session_id, "private session")
    owned = client.get(
        f"/api/v1/runtime/snapshot/{session_id}",
        headers=auth_headers,
    )
    assert owned.status_code == 200
    assert owned.json()["sessionId"] == session_id

    get_store("users").save_key("other-runtime-user", {
        "id": "other-runtime-user",
        "email": "other-runtime-user@jarvis.local",
        "display_name": "Other User",
        "is_active": True,
        "roles": ["user"],
    })
    other_token = create_token({"sub": "other-runtime-user"})
    other = client.get(
        f"/api/v1/runtime/snapshot/{session_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other.status_code == 403
    other_stream = client.get(
        "/api/v1/runtime/events",
        params={"session_id": session_id},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_stream.status_code == 403
    other_replay = client.get(
        f"/api/v1/runtime/resume/{session_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_replay.status_code == 403


@pytest.mark.asyncio
async def test_authenticated_runtime_snapshot_and_sse_replay(client, auth_headers):
    from starlette.requests import Request

    from jarvis_backend.chat_service import chat_service
    from jarvis_backend.routers.runtime_events import runtime_events as runtime_events_endpoint

    user_id = "testuser"
    session_id = f"session-{uuid.uuid4()}"
    request_id = str(uuid.uuid4())
    chat_service.create_session(user_id, session_id, "runtime stream test")
    emitted = runtime_event_service.emit(
        event_type=RuntimeEventType.REQUEST_ACCEPTED,
        user_id=user_id,
        session_id=session_id,
        source=RuntimeEventSource.CHAT,
        request_id=request_id,
        state=RuntimeState.THINKING,
    )

    snapshot = client.get(
        f"/api/v1/runtime/snapshot/{session_id}",
        headers=auth_headers,
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["sequence"] == emitted.sequence
    assert snapshot.json()["assistantState"] == "thinking"
    resumed = client.get(
        f"/api/v1/runtime/resume/{session_id}",
        params={"after": 0},
        headers=auth_headers,
    )
    assert resumed.status_code == 200
    assert resumed.json()["events"][0]["id"] == emitted.id
    assert "principalId" not in json.dumps(resumed.json())

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/runtime/events",
        "headers": [
            (b"authorization", auth_headers["Authorization"].encode("latin-1")),
        ],
        "query_string": b"",
    }, receive=receive)
    response = await runtime_events_endpoint(
        request,
        session_id=session_id,
        after=0,
        last_event_id=None,
    )
    assert response.status_code == 200
    frame = await anext(response.body_iterator)
    assert frame.startswith(f"id: {emitted.sequence}\nevent: request_accepted\n")
    assert f'"requestId":"{request_id}"' in frame
    await response.body_iterator.aclose()


def test_http_request_id_is_canonical_for_chat_provider_and_runtime(
    client, auth_headers, monkeypatch,
):
    from jarvis_backend.chat_service import chat_service
    from jarvis_backend.observability import request_id_var

    class Gateway:
        timeout = 1
        observed_request_id = None

        async def chat(self, *args, **kwargs):
            self.observed_request_id = request_id_var.get()
            return {
                "content": "A correlated response.",
                "provider": "test-provider",
                "model": "test-model",
                "usage": {},
            }

    gateway = Gateway()
    monkeypatch.setattr(chat_service, "gateway", gateway)
    monkeypatch.setattr(
        chat_service,
        "_plan_presentation",
        lambda *_args, **_kwargs: None,
    )
    session_id = f"session-{uuid.uuid4()}"
    request_id = str(uuid.uuid4())

    response = client.post(
        "/api/chat",
        json={"message": "Correlate this request", "session_id": session_id},
        headers={**auth_headers, "X-Request-ID": request_id},
    )

    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.headers["X-Request-ID"] == request_id
    assert gateway.observed_request_id == request_id
    events = runtime_event_service.replay("testuser", session_id)
    assert events
    assert {event.request_id for event in events} == {request_id}
