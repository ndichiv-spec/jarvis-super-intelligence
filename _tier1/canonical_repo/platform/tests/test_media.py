"""Hermetic tests for the provider-backed /api/v1/image/generate wiring
(Replicate + Stability + OpenAI) — the real-service path that replaced the old
empty stub. Keys are never materialized in the runner."""
from __future__ import annotations

import base64
import uuid

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
def test_image_unknown_provider_returns_501(client):
    r = client.post("/api/v1/image/generate", json={"prompt": "x", "provider": "aws"},
                    headers=_admin_headers())
    assert r.status_code == 501, r.text
    assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_image_generation_requires_authentication(client):
    response = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a cube", "provider": "replicate"},
    )
    assert response.status_code == 401


def test_image_provider_status_is_safe_and_explicit(client):
    response = client.get("/api/v1/image/providers", headers=_admin_headers())
    assert response.status_code == 200, response.text
    providers = response.json()["providers"]
    assert set(providers) == {"openai", "replicate", "stability"}
    assert all(
        not any(secret_field in key.lower() for key in value)
        for value in providers.values()
        for secret_field in ("api_key", "secret", "token")
    )
    assert all(value["availability"] in {
        "configured_unverified", "not_configured",
    } for value in providers.values())


def test_explicit_image_provider_selection_is_truthful_and_enforced(
    client, monkeypatch,
):
    monkeypatch.setenv("JARVIS_IMAGE_PROVIDER", "replicate")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-fixture")
    monkeypatch.delenv("REPLICATE_API_KEY", raising=False)

    headers = _admin_headers()
    status = client.get("/api/v1/image/providers", headers=headers)
    assert status.status_code == 200
    assert status.json()["selection_mode"] == "explicit"
    assert status.json()["selected_provider"] is None
    assert status.json()["providers"]["openai"]["selected"] is False

    unavailable = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a cube"},
        headers=headers,
    )
    assert unavailable.status_code == 503
    assert "openai-fixture" not in unavailable.text

    monkeypatch.setenv("REPLICATE_API_KEY", "replicate-fixture")
    status = client.get("/api/v1/image/providers", headers=headers)
    assert status.json()["selected_provider"] == "replicate"
    assert status.json()["selection_mode"] == "explicit"
    assert status.json()["providers"]["replicate"]["selected"] is True
    assert status.json()["providers"]["replicate"]["availability"] == (
        "configured_unverified"
    )


def test_selected_provider_uses_server_secret_file_without_exposing_key(
    client, monkeypatch, tmp_path,
):
    key_file = tmp_path / "replicate-api-key"
    key_file.write_text("replicate-file-fixture\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_IMAGE_PROVIDER", "replicate")
    monkeypatch.setenv("JARVIS_IMAGE_PROVIDER_API_KEY_FILE", str(key_file))
    for name in (
        "OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI",
        "REPLICATE_API_KEY", "STABILITY_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    response = client.get("/api/v1/image/providers", headers=_admin_headers())

    assert response.status_code == 200, response.text
    assert response.json()["selected_provider"] == "replicate"
    assert response.json()["providers"]["replicate"]["configured"] is True
    assert response.json()["providers"]["replicate"]["availability"] == (
        "configured_unverified"
    )
    assert "replicate-file-fixture" not in response.text


@pytest.mark.parametrize(
    ("provider", "credential", "response"),
    [
        ("openai", "OPENAI_API_KEY", (429, {}, b"", {})),
        ("replicate", "REPLICATE_API_KEY", (429, {}, b"", {})),
        ("stability", "STABILITY_API_KEY", (429, {}, b"", {})),
    ],
)
def test_image_provider_rate_limits_are_reported_without_success(
    client, monkeypatch, provider, credential, response,
):
    from jarvis_backend.routers import media

    monkeypatch.setenv(credential, "provider-fixture")
    monkeypatch.setattr(media._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [_Resp(*response)]

    result = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a small blue cube", "provider": provider},
        headers=_admin_headers(),
    )

    assert result.status_code == 503
    assert "provider-fixture" not in result.text


def test_replicate_requires_key(client):
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a cube", "provider": "replicate"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text
    status = client.get("/api/v1/image/providers", headers=_admin_headers())
    assert status.json()["providers"]["replicate"]["availability_reason"] == (
        "Configure REPLICATE_API_KEY on the server."
    )


def test_stability_requires_key(client):
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a cube", "provider": "stability"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text
    assert client.get(
        "/api/v1/image/providers", headers=_admin_headers(),
    ).json()["providers"]["stability"]["availability"] == "not_configured"


def test_openai_image_requires_key(client):
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a cube", "provider": "openai"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text
    assert client.get(
        "/api/v1/image/providers", headers=_admin_headers(),
    ).json()["providers"]["openai"]["availability"] == "not_configured"


def test_image_requires_prompt(client):
    # prompt is a required Pydantic field -> FastAPI body validation -> 422
    r = client.post("/api/v1/image/generate", json={"provider": "replicate"},
                    headers=_admin_headers())
    assert r.status_code == 422, r.text


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
    seq = []

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
    from jarvis_backend.routers import media as M
    monkeypatch.setenv("REPLICATE_API_KEY", "r8-test")
    monkeypatch.setattr(M._httpx, "AsyncClient", _FakeAsyncClient)
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
    assert body["images"][0]["media_ref"] == body["media_refs"][0]
    media_url = body["images"][0]["url"]
    assert media_url.startswith("/api/v1/media/")
    assert "replicate.delivery" not in media_url
    _FakeAsyncClient.seq = [
        _Resp(
            200,
            content=b"\x89PNG\r\n\x1a\nimage-data",
            headers={"content-type": "image/png"},
        ),
    ]
    delivered = client.get(media_url)
    assert delivered.status_code == 200
    assert delivered.content.startswith(b"\x89PNG\r\n\x1a\n")
    tampered = media_url.replace("signature=", "signature=0", 1)
    assert client.get(tampered).status_code == 404


def test_image_generation_uses_configured_provider_when_provider_is_omitted(
    client, monkeypatch, tmp_path,
):
    import jarvis_backend.media_storage as storage
    from jarvis_backend.routers import media as M

    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setattr(M._httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    encoded_png = base64.b64encode(
        b"\x89PNG\r\n\x1a\nfixture-image",
    ).decode("ascii")
    _FakeAsyncClient.seq = [
        _Resp(200, {"data": [{"b64_json": encoded_png}]}),
    ]

    response = client.post(
        "/api/v1/image/generate",
        json={"prompt": "a blue fox"},
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "openai"
    assert response.json()["images"][0]["url"].startswith("/api/v1/media/")


def test_replicate_bad_key_rejected_by_provider(client, monkeypatch):
    from jarvis_backend.routers import media as M
    monkeypatch.setenv("REPLICATE_API_KEY", "r8-bad")
    monkeypatch.setattr(M._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [_Resp(401, {"detail": "invalid API token"})]  # GET model 401
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a red cube", "provider": "replicate"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_stability_rejects_bad_key(client, monkeypatch):
    from jarvis_backend.routers import media as M
    monkeypatch.setenv("STABILITY_API_KEY", "sk-bad")
    monkeypatch.setattr(M._httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.seq = [_Resp(404, {"error": "not found"})]  # POST generation 404
    r = client.post("/api/v1/image/generate",
                    json={"prompt": "a red cube", "provider": "stability"},
                    headers=_admin_headers())
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "AUTHENTICATION_ERROR"
