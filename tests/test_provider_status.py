"""Tests for the provider-capability discovery endpoint (spec sections 9/17/41).

These assert the *honest* matrix behaviour: the endpoint must NEVER claim a
provider is connected/healthy unless its real configured capability was
exercised, must never leak secret values, and must report the audited
NOT_IMPLEMENTED gaps (Microsoft 365 Copilot, Vertex AI).
"""
from __future__ import annotations

import pytest

# Provider API-key env vars the fabric reads. Tests scrub them to assert the
# NOT_CONFIGURED state deterministically (the .env loaded by main.py sets
# OPENAI_API_KEY, so we delenv it per-test).
_PROVIDER_KEY_ENVS = [
    "OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI",
    "ANTHROPIC_API_KEY", "JARVIS_API_KEY_CLAUDE",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY", "JARVIS_API_KEY_GEMINI",
    "HF_TOKEN", "JARVIS_API_KEY_WHISPER", "JARVIS_API_KEY_STABLEDIFFUSION",
    "JARVIS_API_KEY_CODEMUSE",
    "JARVIS_OAUTH_CLIENTS",
]


@pytest.fixture
def admin_headers():
    from jarvis_backend.core import hash_password, create_token, get_store, now_iso
    import uuid
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid, "email": "admin@test.local", "username": "admin",
        "password_hash": hash_password("pw"), "full_name": "Admin",
        "is_admin": True, "roles": ["admin"], "status": "active",
        "tenant_id": None, "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    return {"Authorization": f"Bearer {create_token({'sub': uid})}"}


def _scrub(monkeypatch):
    for k in _PROVIDER_KEY_ENVS:
        monkeypatch.delenv(k, raising=False)


def _get(client, headers, **qs):
    url = "/api/v1/integrations/providers"
    if qs:
        url += "?" + "&".join(f"{k}={v}" for k, v in qs.items())
    return client.get(url, headers=headers)


def _matrix(client, headers, monkeypatch):
    _scrub(monkeypatch)
    resp = _get(client, headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_endpoint_is_admin_gated_401_without_auth(client):
    resp = client.get("/api/v1/integrations/providers")
    assert resp.status_code == 401


def test_endpoint_rejects_non_admin(client, auth_headers):
    # The shared test identity is a normal user (roles=["user"]).
    resp = client.get(
        "/api/v1/integrations/providers",
        headers=auth_headers,
    )
    assert resp.status_code == 403


def test_matrix_reports_real_state_when_nothing_configured(client, admin_headers, monkeypatch):
    body = _matrix(client, admin_headers, monkeypatch)
    by_id = {p["id"]: p for p in body["providers"]}

    # All API-key providers are NOT_CONFIGURED (no keys in env).
    for ext_id in ("openai", "claude", "gemini", "whisper", "stablediffusion", "codemuse"):
        assert by_id[ext_id]["status"] == "NOT_CONFIGURED", ext_id
        assert by_id[ext_id]["configured"] is False
        assert by_id[ext_id]["code_present"] is True

    # OAuth mail connectors have no registered client -> AUTHENTICATION_REQUIRED.
    for kind in ("gmail", "outlook"):
        assert by_id[kind]["connect_type"] == "oauth"
        assert by_id[kind]["status"] == "AUTHENTICATION_REQUIRED", kind
        assert by_id[kind]["configured"] is False

    # Audited capability gaps are reported as NOT_IMPLEMENTED (never faked up).
    assert by_id["microsoft_copilot"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["microsoft_copilot"]["license_required"] is True
    assert by_id["google_vertexai"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["azure_ai"]["status"] == "NOT_IMPLEMENTED"
    assert by_id["github_copilot"]["status"] == "NOT_IMPLEMENTED"


def test_matrix_marks_openai_configured_when_key_present(client, admin_headers, monkeypatch):
    _scrub(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    resp = _get(client, admin_headers)
    assert resp.status_code == 200
    by_id = {p["id"]: p for p in resp.json()["providers"]}
    assert by_id["openai"]["configured"] is True
    assert by_id["openai"]["connected"] is False
    assert by_id["openai"]["status"] == "CONFIGURED"  # probe=false -> no live call
    # Others remain NOT_CONFIGURED.
    assert by_id["gemini"]["status"] == "NOT_CONFIGURED"


def test_matrix_live_probe_reports_invalid_key_without_network(client, admin_headers, monkeypatch):
    _scrub(monkeypatch)
    from jarvis_backend.routers import extensions as ext
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    # Bypass the real HTTP probe to stay deterministic + network-free.
    monkeypatch.setattr(ext, "_validate_api_key", lambda ext_id, key: (False, "invalid key"))
    resp = _get(client, admin_headers, probe=True)
    assert resp.status_code == 200
    by_id = {p["id"]: p for p in resp.json()["providers"]}
    assert by_id["openai"]["status"] == "INVALID_KEY"
    assert by_id["openai"]["connected"] is False
    assert by_id["openai"]["validator_result"]["verified"] is False


def test_matrix_never_leaks_secret_values(client, admin_headers, monkeypatch):
    _scrub(monkeypatch)
    secret_value = "test-secret-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret_value)
    resp = client.get("/api/v1/integrations/providers", headers=admin_headers)
    text = resp.text
    # Env var NAMES are fine to expose; VALUES must never appear.
    assert secret_value not in text
    assert "Bearer " not in text
    # The redacted placeholder from .env must not leak if a real key were present.
    by_id = {p["id"]: p for p in resp.json()["providers"]}
    for p in by_id.values():
        vr = p.get("validator_result")
        if vr:
            assert secret_value not in str(vr)


def test_matrix_covers_expected_providers(client, admin_headers, monkeypatch):
    body = _matrix(client, admin_headers, monkeypatch)
    ids = {p["id"] for p in body["providers"]}
    # Fabric API-key providers + OAuth mail + audited gaps.
    assert {"openai", "claude", "gemini", "whisper", "stablediffusion", "codemuse",
            "gmail", "outlook", "microsoft_copilot", "google_vertexai"} <= ids
    for p in body["providers"]:
        assert "config" not in {k.lower() for k in p.keys()}  # no raw config blob
        assert "secret" not in p.get("name", "").lower()


def test_canonical_backend_base_no_localhost_fragmentation(monkeypatch):
    # spec sections 23/24/54: the backend must advertise 127.0.0.1:8000 as the
    # canonical API base (no 'localhost:' defaults that break OAuth redirect-URI
    # matching) and APP_URL=127.0.0.1:3000.
    from jarvis_backend.connectors import oauth as oauth_store
    from jarvis_backend.routers import extensions as ext
    import inspect as _inspect

    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000")
    assert oauth_store._backend_base() == "http://127.0.0.1:8000"
    assert "localhost" not in oauth_store._backend_base()
    # code default (no env override) must also be canonical 127.0.0.1
    monkeypatch.delenv("NEXT_PUBLIC_API_URL", raising=False)
    assert oauth_store._backend_base() == "http://127.0.0.1:8000"
    # The OAuth authorize-URL builder (the redirect-URI source of truth) must
    # advertise the canonical base, never a localhost default.
    src = _inspect.getsource(ext._oauth_authorize_url)
    assert "http://127.0.0.1:8000" in src
    assert "http://localhost:8000" not in src


def test_openai_healthy_when_key_present_and_validator_passes(client, admin_headers, monkeypatch):
    # spec section 62: a provider is HEALTHY only when its real capability was
    # exercised -- i.e. the live validator returned verified=True. probe=true
    # triggers the validator; here we drive it deterministically (no network).
    _scrub(monkeypatch)
    from jarvis_backend.routers import extensions as ext
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(ext, "_validate_api_key", lambda ext_id, key: (True, None))
    resp = _get(client, admin_headers, probe=True)
    assert resp.status_code == 200
    by_id = {p["id"]: p for p in resp.json()["providers"]}
    assert by_id["openai"]["status"] == "HEALTHY"
    assert by_id["openai"]["connected"] is True
    assert by_id["openai"]["validator_result"]["verified"] is True
    # Gemini is still NOT_CONFIGURED here (no google key present).
    assert by_id["gemini"]["status"] == "NOT_CONFIGURED"


def test_gemini_recognizes_all_canonical_key_names(client, admin_headers, monkeypatch):
    # §54 fragmentation repair: any canonical Gemini key name activates the
    # provider (CONFIGURED at probe=false). We never fake a key -- we only
    # assert the alias set the fabric actually reads.
    from jarvis_backend.routers import extensions as ext
    expected_aliases = {"GOOGLE_API_KEY", "JARVIS_API_KEY_GEMINI",
                        "GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY"}
    assert set(ext._API_KEY_PROVIDERS["gemini"]["key_env"]) == expected_aliases
    for alias in ("GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY"):
        _scrub(monkeypatch)
        monkeypatch.setenv(alias, "fake-key-only-for-presence-test")
        resp = _get(client, admin_headers)
        by_id = {p["id"]: p for p in resp.json()["providers"]}
        assert by_id["gemini"]["configured"] is True, alias
        assert by_id["gemini"]["status"] == "CONFIGURED", alias
    # And with none present, it stays NOT_CONFIGURED (honest).
    _scrub(monkeypatch)
    resp = _get(client, admin_headers)
    by_id = {p["id"]: p for p in resp.json()["providers"]}
    assert by_id["gemini"]["status"] == "NOT_CONFIGURED"


def test_ai_status_does_not_treat_provider_configuration_as_available(
    client, monkeypatch
):
    from jarvis_backend.routers import ai

    async def catalog():
        return {
            "providers": [{
                "provider": "google",
                "configured": True,
                "available": False,
                "inference_verified": False,
            }],
        }

    async def unavailable(*args, **kwargs):
        return False

    monkeypatch.setattr(ai, "_provider_catalog", catalog)
    monkeypatch.setattr(ai, "_probe_endpoint", unavailable)
    monkeypatch.setattr(ai, "_probe_silverwing_chat", unavailable)
    monkeypatch.delenv("SILVERWING_ENDPOINT", raising=False)
    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)

    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["status"] == "degraded"
    assert body["configured_provider_count"] == 1
    assert body["providers"][0]["status"] == "CONFIGURED"
    assert body["providers"][0]["inference_verified"] is False
    assert "127.0.0.1" not in response.text


def test_ai_status_requires_verified_inference_for_online_state(client, monkeypatch):
    from jarvis_backend.routers import ai

    async def catalog():
        return {
            "providers": [{
                "provider": "google",
                "configured": True,
                "available": True,
                "inference_verified": True,
            }],
        }

    async def unavailable(*args, **kwargs):
        return False

    monkeypatch.setattr(ai, "_provider_catalog", catalog)
    monkeypatch.setattr(ai, "_probe_endpoint", unavailable)
    monkeypatch.setattr(ai, "_probe_silverwing_chat", unavailable)
    monkeypatch.delenv("SILVERWING_ENDPOINT", raising=False)
    monkeypatch.delenv("JARVIS_BRAIN_ENDPOINT", raising=False)

    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["provider"] == "google"
    assert body["status"] == "ready"


def test_openai_invoke_runs_real_provider_path(client, admin_headers, monkeypatch):
    # Proves the Browser-AI path actually reaches the provider's real API:
    # install+enable OpenAI (admin), resolve the key from env, and exercise the
    # chat handler. The network call is swapped for a deterministic fake so the
    # test stays hermetic while asserting the REAL routing shape:
    # api.openai.com -> choices[0].message.content.
    _scrub(monkeypatch)
    from jarvis_backend.routers import extensions as ext
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    # 1) Install + enable the OpenAI extension (admin-only).
    r = client.post("/api/v1/extensions/install",
                         headers=admin_headers, json={"extension_id": "openai"})
    assert r.status_code == 200, r.text

    # 2) Swap the live OpenAI HTTP post for a fake provider response.
    def _fake_openai_json_post(url, payload, key):
        # Mirrors the real /v1/chat/completions response shape.
        assert url == "https://api.openai.com/v1/chat/completions"
        assert payload["model"] == "gpt-4o-mini"
        assert payload["messages"][0]["role"] == "user"
        return {
            "choices": [{"message": {"content": "summarized page content"}}],
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }
    monkeypatch.setattr(ext, "_openai_json_post", _fake_openai_json_post)

    # 3) Invoke openai.chat -- the exact capability the Browser routes to.
    resp = client.post(
        "/api/v1/extensions/openai/invoke",
        headers=admin_headers,
        json={"capability": "openai.chat",
              "params": {"messages": [{"role": "user", "content": "summarize this page"}]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["extension"] == "openai"
    assert body["capability"] == "openai.chat"
    # The provider-shaped result the Browser/AI layer consumes:
    assert body["result"]["provider"] == "openai"
    assert body["result"]["content"] == "summarized page content"
    assert body["result"]["model"] == "gpt-4o-mini"


def test_gemini_invoke_not_configured_without_key(client, admin_headers, monkeypatch):
    # §62: never reach the provider without a configured key. Gemini's invoke
    # must be rejected (400) when no GOOGLE_API_KEY / alias is present.
    _scrub(monkeypatch)
    r = client.post("/api/v1/extensions/install",
                         headers=admin_headers, json={"extension_id": "gemini"})
    assert r.status_code == 200, r.text
    resp = client.post(
        "/api/v1/extensions/gemini/invoke",
        headers=admin_headers,
        json={"capability": "gemini.chat", "params": {"messages": []}},
    )
    assert resp.status_code == 400
    assert "API key" in resp.json()["error"]["message"]
