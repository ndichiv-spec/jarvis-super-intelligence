"""Hermetic tests for the provider-backed /api/v1/image/generate wiring
(Replicate + Stability + OpenAI) — the real-service path that replaced the old
empty stub. Keys are never materialized in the runner."""
from __future__ import annotations

import uuid
import base64
from typing import ClassVar

import pytest

from jarvis_backend.core import create_token, get_store, hash_password, now_iso


def _admin_headers():
    users = get_store("users").load()
    uid = str(uuid.uuid4())
    users[uid] = {
        "id": uid, "email": f"{uid[:8]}@test.local", "username": f"u_{uid[:6]}",
        "password_hash": hash_password("x"), "full_name": "Test", "avatar_url": None,
        "status": "active", "tenant_id": None, "roles": ["admin"],
        "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    return {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}",
            "Content-Type": "application/json"}


_PROVIDER_KEY_VARS = ("OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI", "ANTHROPIC_API_KEY",
                      "GOOGLE_API_KEY", "HF_TOKEN", "REPLICATE_API_KEY", "STABILITY_API_KEY")
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def _clear_provider_keys(monkeypatch):
    for v in _PROVIDER_KEY_VARS:
        monkeypatch.delenv(v, raising=False)
    yield


# --------------------------------------------------------------------------- #
# Dispatch + honest key guards (no provider call made)
# --------------------------------------------------------------------------- #
def test_image_generation_requires_auth(client):
    r = client.post("/api/v1/image/generate", json={"prompt": "a cube"})
    assert r.status_code == 401


def test_image_artifact_requires_auth(client):
    response = client.get("/api/v1/image/artifacts/artifact-id")
    assert response.status_code == 401


def test_image_provider_status_reports_backend_configuration_without_secrets(
    client,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "private-openai-test-key")
    monkeypatch.delenv("JARVIS_API_KEY_OPENAI", raising=False)
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)
    monkeypatch.setenv("REPLICATE_API_KEY", "private-replicate-test-key")

    response = client.get("/api/v1/image/providers", headers=_admin_headers())

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert providers["openai"] == {"configured": True, "status": "CONFIGURED"}
    assert providers["stability"] == {"configured": False, "status": "NOT_CONFIGURED"}
    assert providers["replicate"] == {"configured": True, "status": "CONFIGURED"}
    assert "private-openai-test-key" not in response.text
    assert "private-replicate-test-key" not in response.text


def test_image_unknown_provider_returns_501(client):
    r = client.post("/api/v1/image/generate", json={"prompt": "x", "provider": "aws"},
                    headers=_admin_headers())
    assert r.status_code == 501, r.text
    assert r.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"


def test_replicate_requires_key(client):
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a cube", "provider": "replicate"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text


def test_stability_requires_key(client):
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a cube", "provider": "stability"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text


def test_openai_image_requires_key(client):
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a cube", "provider": "openai"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text


def test_image_requires_prompt(client):
    # prompt is a required Pydantic field -> FastAPI body validation -> 422
    r = client.post("/api/v1/image/generate", json={"provider": "replicate"},
                    headers=_admin_headers())
    assert r.status_code == 422, r.text


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "cube", "provider": "openai", "size": "512x512"},
        {"prompt": "cube", "provider": "replicate", "size": "1792x1024"},
        {"prompt": "cube", "provider": "openai", "num_images": 2},
        {"prompt": "cube", "provider": "openai", "negative_prompt": "blur"},
    ],
)
def test_image_generation_rejects_provider_unsupported_options(client, payload):
    response = client.post(
        "/api/v1/image/generate",
        json=payload,
        headers=_admin_headers(),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [
    {"prompt": "   "},
    {"prompt": "cube", "size": "99999x1"},
    {"prompt": "cube", "size": "not-a-size"},
    {"prompt": "cube", "num_images": 0},
    {"prompt": "cube", "num_images": 5},
])
def test_image_generation_validates_bounds(client, payload):
    r = client.post("/api/v1/image/generate", json=payload, headers=_admin_headers())
    assert r.status_code == 422, r.text


def test_image_generation_rate_limited_per_user(client, monkeypatch):
    from jarvis_backend.routers import media

    monkeypatch.setattr(media, "_IMAGE_LIMIT_PER_USER", 1)
    user_headers = _admin_headers()
    first = client.post("/api/v1/image/generate",
                        json={"prompt": "a cube", "provider": "unimplemented"},
                        headers=user_headers)
    second = client.post("/api/v1/image/generate",
                         json={"prompt": "a cube", "provider": "unimplemented"},
                         headers=user_headers)
    another_user = client.post("/api/v1/image/generate",
                               json={"prompt": "a cube", "provider": "unimplemented"},
                               headers=_admin_headers())
    assert first.status_code == 501
    assert second.status_code == 429
    assert another_user.status_code == 501


def test_image_generation_hides_provider_exception(client, monkeypatch):
    from jarvis_backend.routers import media

    async def _raise_secret(*_args, **_kwargs):
        raise media._httpx.ConnectError("provider key leaked")

    monkeypatch.setattr(media, "_generate_replicate", _raise_secret)
    r = client.post("/api/v1/image/generate", json={"prompt": "a cube"},
                    headers=_admin_headers())
    assert r.status_code == 502
    assert "provider key" not in r.text


# --------------------------------------------------------------------------- #
# Real provider call path (hermetic fake httpx client; key is a throwaway token)
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, status, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload or {}
        self._content = content
        self.headers = headers or {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return ""

    @property
    def content(self):
        return self._content


class _FakeAsyncClient:
    """FIFO fake for the async httpx client used by media.py provider helpers."""
    seq: ClassVar[list] = []
    calls: ClassVar[list] = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, **k):
        return _FakeAsyncClient.seq.pop(0)

    async def post(self, url, headers=None, json=None, files=None, data=None, **k):
        _FakeAsyncClient.calls.append({"url": url, "json": json})
        return _FakeAsyncClient.seq.pop(0)


def test_replicate_generates_image(client, monkeypatch, tmp_path):
    from jarvis_backend.routers import media
    from pathlib import Path

    monkeypatch.setenv("REPLICATE_API_KEY", "r8-test")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(media, "DATA_DIR", tmp_path)
    stored = []
    monkeypatch.setattr(
        media.ArtifactRepository,
        "store_artifact",
        lambda **artifact: stored.append(artifact) or "artifact-test-id",
    )

    async def download_image(_url):
        return _PNG_BYTES, "image/png"

    monkeypatch.setattr(media, "_download_provider_image", download_image)
    # GET model (latest_version.id) -> POST prediction (id+urls.get) -> GET poll (succeeded+url)
    _FakeAsyncClient.seq = [
        _Resp(200, {"latest_version": {"id": "ver-123"}}),
        _Resp(201, {"id": "pred-1",
                    "urls": {"get": "https://api.replicate.com/v1/predictions/pred-1"}}),
        _Resp(200, {"status": "succeeded",
                    "output": ["https://replicate.delivery/img/x.png"]}),
    ]
    headers = _admin_headers()
    session_response = client.post("/api/chat/sessions", headers=headers)
    assert session_response.status_code == 200, session_response.text
    session_id = session_response.json()["id"]
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a red cube on a white table",
                          "provider": "replicate", "num_images": 1,
                          "session_id": session_id},
                    headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "replicate"
    assert body["count"] == 1
    assert body["images"][0]["artifact_id"] == "artifact-test-id"
    assert body["images"][0]["url"] == "/api/v1/image/artifacts/artifact-test-id"
    assert body["images"][0]["width"] == 1024
    assert stored[0]["metadata"]["owner_id"]
    assert stored[0]["session_id"] == session_id
    assert Path(stored[0]["file_path"]).read_bytes() == _PNG_BYTES
    assert len(body["conversation_messages"]) == 2
    assert body["conversation_messages"][0]["role"] == "user"
    assert body["conversation_messages"][0]["content"] == "a red cube on a white table"
    assert body["conversation_messages"][1]["metadata"]["artifacts"][0]["artifact_id"] == "artifact-test-id"
    history = client.get(f"/api/chat/history/{session_id}", headers=headers)
    assert history.status_code == 200
    prompt_message, attached_message = history.json()["messages"][-2:]
    assert prompt_message["content"] == "a red cube on a white table"
    assert attached_message["content"] == "Generated 1 image."
    assert attached_message["metadata"]["artifacts"][0]["url"] == body["images"][0]["url"]


def test_image_generation_rejects_another_users_conversation(client):
    owner_headers = _admin_headers()
    other_headers = _admin_headers()
    session = client.post("/api/chat/sessions", headers=owner_headers)
    assert session.status_code == 200, session.text

    response = client.post(
        "/api/v1/image/generate",
        json={
            "prompt": "a cube",
            "provider": "replicate",
            "session_id": session.json()["id"],
        },
        headers=other_headers,
    )

    assert response.status_code == 403


def test_openai_options_are_sent_and_artifact_is_persisted(client, monkeypatch, tmp_path):
    from jarvis_backend.routers import media

    image_data = base64.b64encode(_PNG_BYTES).decode("ascii")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(media, "DATA_DIR", tmp_path)
    stored = []
    monkeypatch.setattr(
        media.ArtifactRepository,
        "store_artifact",
        lambda **artifact: stored.append(artifact) or "openai-artifact",
    )
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.seq = [_Resp(200, {"data": [{"b64_json": image_data}]})]

    response = client.post(
        "/api/v1/image/generate",
        json={
            "prompt": "a red cube",
            "provider": "openai",
            "size": "1792x1024",
            "quality": "hd",
            "style": "vivid",
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.text
    assert _FakeAsyncClient.calls[0]["json"]["quality"] == "hd"
    assert _FakeAsyncClient.calls[0]["json"]["style"] == "vivid"
    assert response.json()["images"][0]["artifact_id"] == "openai-artifact"
    assert stored[0]["metadata"]["width"] == 1792
    assert stored[0]["metadata"]["height"] == 1024


def test_replicate_rejects_untrusted_prediction_poll_url(client, monkeypatch):
    from jarvis_backend.routers import media

    monkeypatch.setenv("REPLICATE_API_KEY", "r8-test")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [
        _Resp(200, {"latest_version": {"id": "ver-123"}}),
        _Resp(201, {"id": "pred-1", "urls": {"get": "https://attacker.invalid/poll"}}),
    ]

    response = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a cube", "provider": "replicate"},
        headers=_admin_headers(),
    )
    assert response.status_code == 502
    assert "attacker.invalid" not in response.text
    assert _FakeAsyncClient.seq == []


@pytest.mark.asyncio
async def test_image_artifact_is_only_retrievable_by_owning_user(monkeypatch, tmp_path):
    from jarvis_backend.routers import media

    monkeypatch.setattr(media, "DATA_DIR", tmp_path)
    image_path = media._user_image_directory("owner").resolve() / "image.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"owned-image")
    monkeypatch.setattr(
        media.ArtifactRepository,
        "get_artifact",
        lambda _artifact_id: {
            "capability": "image.generate",
            "artifact_type": "image.generated",
            "file_path": str(image_path),
            "mime_type": "image/png",
            "metadata_json": '{"owner_id":"owner"}',
        },
    )

    response = await media.get_image_artifact(
        "artifact-id",
        user={"id": "owner"},
    )
    assert response.path == image_path

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await media.get_image_artifact("artifact-id", user={"id": "another-user"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_image_artifact_download_rejects_untrusted_provider_host():
    from fastapi import HTTPException
    from jarvis_backend.routers import media

    with pytest.raises(HTTPException) as exc:
        await media._download_provider_image("https://attacker.invalid/image.png")
    assert exc.value.status_code == 502


def test_replicate_bad_key_rejected_by_provider(client, monkeypatch):
    from jarvis_backend.routers import media
    monkeypatch.setenv("REPLICATE_API_KEY", "r8-bad")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [_Resp(401, {"detail": "invalid API token"})]  # GET model 401
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a red cube", "provider": "replicate"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text


def test_stability_rejects_bad_key(client, monkeypatch):
    from jarvis_backend.routers import media
    monkeypatch.setenv("STABILITY_API_KEY", "sk-bad")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [_Resp(404, {"error": "not found"})]  # POST generation 404
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a red cube", "provider": "stability"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text


def test_stability_malformed_json_is_not_reported_as_an_image(client, monkeypatch):
    from jarvis_backend.routers import media

    class _MalformedJsonResponse(_Resp):
        def json(self):
            raise ValueError("invalid provider JSON")

    monkeypatch.setenv("STABILITY_API_KEY", "sk-test")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [
        _MalformedJsonResponse(
            200,
            content=b'{"error":',
            headers={"content-type": "application/json"},
        )
    ]

    response = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a cube", "provider": "stability"},
        headers=_admin_headers(),
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "REQUEST_ERROR"
    assert response.json().get("success") is not True


def test_image_provider_bytes_must_match_declared_image_type(client, monkeypatch):
    from jarvis_backend.routers import media

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [
        _Resp(200, {"data": [{"b64_json": base64.b64encode(b"not-an-image").decode()}]})
    ]

    response = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a cube", "provider": "openai"},
        headers=_admin_headers(),
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "REQUEST_ERROR"
    assert response.json().get("success") is not True
