from __future__ import annotations

import asyncio

class _AudioResponse:
    def __init__(self, status_code=200, payload=None, content=b"audio"):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload


class _FakeAudioClient:
    calls = []
    response = _AudioResponse()

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_voice_provider_status_is_explicitly_unconfigured(client, monkeypatch):
    from jarvis_backend.routers import voice

    monkeypatch.setattr(voice, "_openai_audio_key", lambda: None)
    result = asyncio.run(voice.voice_status())
    assert result["status"] == "DEGRADED"
    assert result["asr_status"] == "NOT_CONFIGURED"
    assert result["asr_available"] is False


def test_openai_speech_generation_returns_real_audio_not_a_success_placeholder(
    client, auth_headers, monkeypatch,
):
    from jarvis_backend.routers import voice

    monkeypatch.setattr(voice, "_openai_audio_key", lambda: "test-only-key")
    monkeypatch.setattr(voice.httpx, "AsyncClient", _FakeAudioClient)
    _FakeAudioClient.calls = []
    _FakeAudioClient.response = _AudioResponse(content=b"ID3-real-audio-bytes")

    response = client.post(
        "/api/v1/voice/speak",
        headers=auth_headers,
        json={"text": "Hello from the same assistant."},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3-real-audio-bytes"
    assert _FakeAudioClient.calls[0][0].endswith("/speech")
    assert _FakeAudioClient.calls[0][1]["json"]["input"] == (
        "Hello from the same assistant."
    )
    assert client.post(
        "/api/v1/voice/speak",
        json={"text": "unauthenticated"},
    ).status_code == 401


def test_transcription_posts_audio_to_provider_and_uses_owned_conversation(
    client, auth_headers, monkeypatch,
):
    from jarvis_backend import chat_service
    from jarvis_backend.routers import voice

    monkeypatch.setattr(voice, "_openai_audio_key", lambda: "test-only-key")
    monkeypatch.setattr(voice.httpx, "AsyncClient", _FakeAudioClient)
    _FakeAudioClient.calls = []
    _FakeAudioClient.response = _AudioResponse(
        payload={"text": "Turn left at the next street."},
    )
    captured = {}

    class _ChatService:
        def get_session(self, user_id, session_id):
            assert user_id == "testuser"
            assert session_id == "existing-conversation"
            return {"id": session_id}

        async def send_message(self, user_id, session_id, content, **kwargs):
            captured.update(
                user_id=user_id,
                session_id=session_id,
                content=content,
                kwargs=kwargs,
            )
            return {"status": "COMPLETED", "message": "Route received."}

    monkeypatch.setattr(chat_service, "chat_service", _ChatService())
    response = client.post(
        "/api/v1/voice/transcribe?session_id=existing-conversation",
        headers=auth_headers,
        files={"file": ("sample.wav", b"valid-test-audio", "audio/wav")},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["transcript"] == "Turn left at the next street."
    assert result["session_id"] == "existing-conversation"
    assert captured["content"] == result["transcript"]
    assert captured["session_id"] == "existing-conversation"
    assert captured["kwargs"]["client_message_id"].startswith("voice-")
    assert _FakeAudioClient.calls[0][0].endswith("/transcriptions")


def test_transcription_honestly_reports_missing_provider_credentials(
    client, auth_headers, monkeypatch,
):
    from jarvis_backend.routers import voice

    monkeypatch.setattr(voice, "_openai_audio_key", lambda: None)
    response = client.post(
        "/api/v1/voice/transcribe",
        headers=auth_headers,
        files={"file": ("sample.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 503
    status = client.get("/api/v1/voice/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["asr_availability_reason"] == (
        "Configure OPENAI_API_KEY for the speech transcription provider."
    )


def test_transcription_refuses_audio_that_exceeds_size_limit(
    client, auth_headers, monkeypatch,
):
    from jarvis_backend.routers import voice

    monkeypatch.setattr(voice, "MAX_AUDIO_UPLOAD_BYTES", 4)
    response = client.post(
        "/api/v1/voice/transcribe",
        headers=auth_headers,
        files={"file": ("sample.wav", b"12345", "audio/wav")},
    )
    assert response.status_code == 413
