from __future__ import annotations

import base64
import json
import struct
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis_backend.core import get_current_user
from jarvis_backend.errors import ChatError, ErrorCategory
from jarvis_backend.routers import openai_compat


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(openai_compat.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "api-user",
        "roles": ["user"],
    }
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_chat_completion_returns_openai_shape_and_real_usage(client, monkeypatch):
    class Gateway:
        async def chat(self, messages, model=None):
            assert messages[-1]["content"] == "hello"
            assert model == "jarvis-test"
            return {
                "content": "hello back",
                "model": "jarvis-test",
                "usage": {"input_tokens": 3, "output_tokens": 2},
            }

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "hello"}],
        },
        headers={"X-Request-ID": "request-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"] == {
        "role": "assistant",
        "content": "hello back",
    }
    assert body["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert response.headers["Jarvis-Version"] == "1"
    assert response.headers["X-Request-ID"] == "request-123"


def test_chat_stream_forwards_genuine_provider_deltas(client, monkeypatch):
    class Gateway:
        async def stream_chat(self, **kwargs):
            yield {"type": "delta", "text": "first "}
            yield {"type": "delta", "text": "second"}
            yield {"type": "done", "streamed": True, "model": "jarvis-test"}

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    assert [event["choices"][0]["delta"].get("content") for event in events[1:3]] == [
        "first ",
        "second",
    ]
    assert events[-1]["choices"][0]["finish_reason"] == "stop"
    assert "data: [DONE]" in response.text


def test_streaming_buffered_provider_is_not_split_into_fake_deltas(client, monkeypatch):
    class Gateway:
        async def stream_chat(self, **kwargs):
            yield {
                "type": "done",
                "streamed": False,
                "content": "complete response",
            }

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.text.count('"content":"complete response"') == 1


def test_provider_errors_use_openai_error_envelope(client, monkeypatch):
    class Gateway:
        async def chat(self, messages, model=None):
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "No model provider is available.",
            )

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["type"] == "server_error"
    assert response.json()["error"]["message"] == "No model provider is available."


def test_unsupported_generation_options_are_rejected(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert "temperature" in response.json()["error"]["message"]


def test_invalid_request_uses_openai_error_envelope(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "jarvis-test", "messages": []},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert "messages" in response.json()["error"]["message"]
    assert response.headers["Jarvis-Version"] == "1"


def test_embedding_response_supports_float_and_base64(client, monkeypatch):
    vector = [0.25] * 384
    monkeypatch.setattr(openai_compat, "embed_text", lambda *_: vector)
    monkeypatch.setattr(openai_compat, "_tokenize", lambda *_: ["token", "count"])

    response = client.post(
        "/v1/embeddings",
        json={"model": "jarvis-embedding-v1", "input": ["first", "second"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["index"] == 0
    assert body["data"][0]["embedding"] == vector
    assert body["usage"] == {"prompt_tokens": 4, "total_tokens": 4}

    encoded = client.post(
        "/v1/embeddings",
        json={
            "model": "jarvis-embedding-v1",
            "input": "first",
            "encoding_format": "base64",
        },
    ).json()["data"][0]["embedding"]
    decoded = base64.b64decode(encoded)
    assert len(decoded) == 384 * 4
    assert struct.unpack("<f", decoded[:4])[0] == pytest.approx(0.25)


def test_embedding_rejects_alias_that_would_misstate_model_identity(client):
    response = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": "text"},
    )

    assert response.status_code == 400
    assert "jarvis-embedding-v1" in response.json()["error"]["message"]


def test_embedding_rejects_text_without_supported_tokens(client, monkeypatch):
    monkeypatch.setattr(openai_compat, "_tokenize", lambda *_: [])
    response = client.post(
        "/v1/embeddings",
        json={"model": "jarvis-embedding-v1", "input": "..."},
    )

    assert response.status_code == 400
    assert "supported token" in response.json()["error"]["message"]


def test_models_routes_expose_only_public_model_fields(client, monkeypatch):
    model = SimpleNamespace(
        model_id="provider:model-1",
        provider_id="provider",
        created_at=1_700_000_000.9,
        checksum="private-checksum",
    )

    class Registry:
        def list_models(self, lifecycle_status):
            return [model] if lifecycle_status == "approved" else []

    monkeypatch.setattr(openai_compat, "model_registry", Registry())
    response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.json()["data"][0] == {
        "id": "provider:model-1",
        "object": "model",
        "created": 1_700_000_000,
        "owned_by": "provider",
    }
    assert response.json()["data"][-1]["id"] == "jarvis-embedding-v1"
    assert "checksum" not in response.text


def test_openai_compat_router_requires_authentication():
    app = FastAPI()
    app.include_router(openai_compat.router)
    response = TestClient(app, raise_server_exceptions=False).get("/v1/models")

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"


def test_json_schema_response_is_validated_before_success(client, monkeypatch):
    class Gateway:
        async def chat(self, messages, model=None, system=None):
            assert "JSON Schema" in system
            return {"content": '{"answer":42}', "model": model}

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "answer"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "integer"}},
                        "required": ["answer"],
                        "additionalProperties": False,
                    },
                },
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == '{"answer":42}'


def test_json_schema_mismatch_is_not_returned_as_success(client, monkeypatch):
    class Gateway:
        async def chat(self, messages, model=None, system=None):
            return {"content": '{"answer":"wrong"}', "model": model}

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "jarvis-test",
            "messages": [{"role": "user", "content": "answer"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "integer"}},
                        "required": ["answer"],
                    },
                },
            },
        },
    )

    assert response.status_code == 502
    assert "did not match" in response.json()["error"]["message"]


def test_legacy_completion_has_text_completion_response_shape(client, monkeypatch):
    class Gateway:
        async def chat(self, messages, model=None):
            return {"content": "completion text", "model": model}

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/completions",
        json={"model": "jarvis-test", "prompt": "finish this"},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "text_completion"
    assert response.json()["choices"][0]["text"] == "completion text"
    assert "message" not in response.json()["choices"][0]


def test_legacy_completion_stream_uses_text_choice_chunks(client, monkeypatch):
    class Gateway:
        async def stream_chat(self, **kwargs):
            yield {"type": "delta", "text": "text "}
            yield {"type": "delta", "text": "chunk"}
            yield {"type": "done", "streamed": True}

    monkeypatch.setattr(openai_compat, "provider_gateway", Gateway())
    response = client.post(
        "/v1/completions",
        json={"model": "jarvis-test", "prompt": "finish this", "stream": True},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    assert all(event["object"] == "text_completion" for event in events)
    assert [event["choices"][0]["text"] for event in events if event["choices"]] == [
        "text ",
        "chunk",
        "",
    ]


def test_compat_file_storage_is_owner_scoped_and_downloadable(client, monkeypatch, tmp_path):
    stores = {}

    class Store:
        def __init__(self):
            self.value = {}

        def load(self):
            return self.value

        def save(self):
            return None

    def get_store(name):
        stores.setdefault(name, Store())
        return stores[name]

    monkeypatch.setattr(openai_compat, "get_store", get_store)
    monkeypatch.setattr(openai_compat, "UPLOADS_DIR", tmp_path)
    response = client.post(
        "/v1/files",
        data={"purpose": "user_data"},
        files={"file": ("notes.txt", b"private notes", "text/plain")},
    )

    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "uploaded"
    assert "path" not in response.text
    file_id = created["id"]
    download = client.get(f"/v1/files/{file_id}/content")
    assert download.content == b"private notes"
    assert download.headers["Jarvis-Version"] == "1"

    client.app.dependency_overrides[get_current_user] = lambda: {
        "id": "another-user",
        "roles": ["user"],
    }
    assert client.get(f"/v1/files/{file_id}").status_code == 404


def test_anthropic_token_count_uses_authenticated_shared_tokenizer(client, monkeypatch):
    monkeypatch.setattr(openai_compat, "find_api_key", lambda *_: {"owner": "api-user"})
    monkeypatch.setattr(openai_compat, "is_api_key_expired", lambda *_: False)
    monkeypatch.setattr(openai_compat, "_api_key_principal", lambda record: {"id": record["owner"]})
    response = client.post(
        "/v1/messages/count_tokens",
        headers={"x-api-key": "jarvis_test_key"},
        json={
            "model": "claude-3-5-sonnet-latest",
            "system": "Be concise.",
            "messages": [{"role": "user", "content": "Count these tokens."}],
        },
    )

    assert response.status_code == 200
    assert response.json()["input_tokens"] > 0
    assert set(response.json()) == {"input_tokens"}


def test_audio_transcription_and_speech_use_voice_capability(client, monkeypatch):
    class Voice:
        async def execute(self, request, context):
            if request["action"] == "transcribe":
                assert request["audio_data"]["filename"] == "sample.wav"
                return SimpleNamespace(success=True, data={"text": "recognized words"})
            assert request["voice"] == "alloy"
            return SimpleNamespace(
                success=True,
                data={"audio_data": base64.b64encode(b"mp3 bytes").decode("ascii")},
            )

    monkeypatch.setattr(openai_compat, "VoiceCapability", Voice)
    transcription = client.post(
        "/v1/audio/transcriptions",
        data={"model": "whisper-1", "response_format": "text"},
        files={"file": ("sample.wav", b"wav bytes", "audio/wav")},
    )
    speech = client.post(
        "/v1/audio/speech",
        json={"model": "tts-1", "input": "hello", "voice": "alloy"},
    )

    assert transcription.status_code == 200
    assert transcription.text == "recognized words"
    assert speech.status_code == 200
    assert speech.content == b"mp3 bytes"
    assert speech.headers["content-type"] == "audio/mpeg"


def test_image_generation_returns_owner_scoped_url_for_base64_provider(
    client, monkeypatch, tmp_path
):
    image_data = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode("ascii")

    async def fake_image_generate(body, user):
        return {"images": [{"base64": image_data}], "count": 1}

    stores = {}

    class Store:
        def __init__(self):
            self.value = {}

        def load(self):
            return self.value

        def save(self):
            return None

    monkeypatch.setattr(openai_compat, "image_generate", fake_image_generate)
    monkeypatch.setattr(openai_compat, "get_store", lambda name: stores.setdefault(name, Store()))
    monkeypatch.setattr(openai_compat, "UPLOADS_DIR", tmp_path)
    response = client.post("/v1/images/generations", json={"prompt": "a blue square"})

    assert response.status_code == 200
    image_url = response.json()["data"][0]["url"]
    fetched = client.get(image_url.replace("http://testserver", ""))
    assert fetched.content == b"\x89PNG\r\n\x1a\nimage"
