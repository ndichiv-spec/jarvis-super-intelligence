import json
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect


@pytest.mark.parametrize(
    ("path", "method", "kwargs"),
    [
        ("/api/v1/voice/speak", "post", {"json": {"text": "hello"}}),
        ("/api/v1/voice/listen", "post", {"json": {}}),
        (
            "/api/v1/voice/transcribe",
            "post",
            {"files": {"file": ("voice.wav", b"audio", "audio/wav")}},
        ),
        ("/api/v1/voice/voices", "get", {}),
    ],
)
def test_voice_execution_endpoints_require_authentication(client, path, method, kwargs):
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401


def test_transcription_rejects_unsupported_files_before_provider_use(client, auth_headers):
    response = client.post(
        "/api/v1/voice/transcribe",
        headers=auth_headers,
        files={"file": ("payload.exe", b"not audio", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "INVALID_AUDIO_TYPE" in response.json()["error"]["message"]


def test_transcription_uses_voice_capability_with_authenticated_identity(
    client, auth_headers, monkeypatch
):
    calls = []

    class VoiceCapabilityStub:
        async def execute(self, request, context):
            calls.append((request, context))
            return SimpleNamespace(
                success=True,
                data={"text": "Check my schedule", "provider": "test-stt", "confidence": 0.9},
                error=None,
            )

    monkeypatch.setattr("jarvis_backend.routers.voice.VoiceCapability", VoiceCapabilityStub)
    response = client.post(
        "/api/v1/voice/transcribe",
        headers=auth_headers,
        files={"file": ("recording.wav", b"audio-bytes", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "text": "Check my schedule",
        "provider": "test-stt",
        "confidence": 0.9,
    }
    request, context = calls[0]
    assert request["action"] == "transcribe"
    assert request["audio_data"]["data"] == b"audio-bytes"
    assert context.user_id == "testuser"


def test_voice_websocket_reports_unavailable_instead_of_acknowledging_fake_transcription(
    client, monkeypatch
):
    async def allow_test_ticket(_ws):
        return True

    monkeypatch.setattr("jarvis_backend.websocket._require_websocket_ticket", allow_test_ticket)

    with client.websocket_connect("/api/v1/voice/ws/chat") as websocket:
        message = json.loads(websocket.receive_text())
        assert message["code"] == "CAPABILITY_NOT_CONFIGURED"
        assert message["status"] == "error"
        assert "authenticated chat" in message["message"]
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()
