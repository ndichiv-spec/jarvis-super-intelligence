"""Hermetic tests for the provider-backed /api/v1/image/generate wiring
(Replicate + Stability + OpenAI) — the real-service path that replaced the old
empty stub. Keys are never materialized in the runner."""
from __future__ import annotations

import uuid
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


def test_image_unknown_provider_returns_501(client):
    r = client.post("/api/v1/image/generate", json={"prompt": "x", "provider": "aws"},
                    headers=_admin_headers())
    assert r.status_code == 501, r.text
    assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


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

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, **k):
        return _FakeAsyncClient.seq.pop(0)

    async def post(self, url, headers=None, json=None, files=None, data=None, **k):
        return _FakeAsyncClient.seq.pop(0)


def test_replicate_generates_image(client, monkeypatch):
    from jarvis_backend.routers import media
    monkeypatch.setenv("REPLICATE_API_KEY", "r8-test")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    # GET model (latest_version.id) -> POST prediction (id+urls.get) -> GET poll (succeeded+url)
    _FakeAsyncClient.seq = [
        _Resp(200, {"latest_version": {"id": "ver-123"}}),
        _Resp(201, {"id": "pred-1",
                    "urls": {"get": "https://api.replicate.com/v1/predictions/pred-1"}}),
        _Resp(200, {"status": "succeeded",
                    "output": ["https://replicate.delivery/img/x.png"]}),
    ]
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a red cube on a white table",
                          "provider": "replicate", "num_images": 1},
                    headers=_admin_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "replicate"
    assert body["count"] == 1
    assert body["images"][0]["url"] == "https://replicate.delivery/img/x.png"


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
