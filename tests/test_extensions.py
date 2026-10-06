"""Regression: the Extensions marketplace is browsable *without* auth and lists
the core integrations (Docker, GitHub, Claude, OpenCode, …), each exposing
capability tokens; install/enable/disable remain admin-gated and update the
audited capability surface."""
from __future__ import annotations

import uuid
import json
import os
from urllib.parse import unquote

import pytest
from fastapi import HTTPException

from jarvis_backend.core import create_token, get_store, hash_password, now_iso


REQUIRED = ["docker", "github", "claude", "opencode", "slack", "postgres"]
EXPECTED_CAPS = {
    "docker": ["docker.images", "docker.containers", "docker.build", "docker.push"],
    "claude": ["claude.chat", "claude.generate", "claude.analyze"],
    "opencode": ["opencode.run", "opencode.build", "opencode.test"],
    "slack": ["slack.send", "slack.receive"],
}


def _token(roles):
    # NOTE: get_store(...).load() returns the live cached reference (empty dict,
    # never None) for dict collections, so mutate-then-save() persists mutations.
    users = get_store("users").load()
    uid = str(uuid.uuid4())
    users[uid] = {
        "id": uid, "email": f"{uid[:8]}@test.local", "username": f"u_{uid[:6]}",
        "password_hash": hash_password("P@ss1word"), "full_name": "Test",
        "avatar_url": None, "status": "active", "tenant_id": None,
        "roles": roles, "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    return {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}


def test_marketplace_catalog_is_public_and_complete(client):
    # No Authorization header -> a marketplace catalog must still load.
    r = client.get("/api/v1/extensions")
    assert r.status_code == 200, r.text
    data = r.json()
    ids = {e["id"] for e in data["extensions"]}
    for must in REQUIRED:
        assert must in ids, f"missing extension: {must}"
    # every rendered extension exposes a caps list
    for e in data["extensions"]:
        assert isinstance(e["caps"], list) and e["caps"], f"{e['id']} has no caps"
    by_id = {e["id"]: e for e in data["extensions"]}
    for ext_id, caps in EXPECTED_CAPS.items():
        assert by_id[ext_id]["caps"] == caps


def test_install_enable_disable_is_admin_gated(client):
    body = {"extension_id": "github", "config": {}}
    # unauthenticated -> 401
    assert client.post("/api/v1/extensions/install", json=body).status_code == 401
    # authenticated but non-admin -> 403
    user_h = _token(["user"])
    assert client.post("/api/v1/extensions/install", json=body, headers=user_h).status_code == 403
    # admin -> install succeeds and the extension flips to installed+enabled
    admin_h = _token(["admin"])
    r = client.post("/api/v1/extensions/install", json=body, headers=admin_h)
    assert r.status_code == 200, r.text
    catalog = {e["id"]: e for e in client.get("/api/v1/extensions").json()["extensions"]}
    assert catalog["github"]["installed"] is True
    assert catalog["github"]["enabled"] is True

    # disable via PATCH (admin) -> capability surface drops
    r = client.patch("/api/v1/extensions/github", json={"enabled": False}, headers=admin_h)
    assert r.status_code == 200, r.text
    caps = client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]
    assert "github.read" not in caps  # disabling drops the capability surface
    # uninstall -> gone again
    r = client.post("/api/v1/extensions/uninstall", json={"extension_id": "github"}, headers=admin_h)
    assert r.status_code == 200, r.text
    catalog = {e["id"]: e for e in client.get("/api/v1/extensions").json()["extensions"]}
    assert catalog["github"]["installed"] is False


def test_capabilities_endpoint_reflects_state(client):
    # Public catalog has no github capability. Capabilities only go live once an
    # extension is installed + enabled AND connected — connecting is what makes
    # the effect positive on the entire platform.
    assert "github.read" not in client.get("/api/v1/extensions/capabilities").json()["capabilities"]
    admin_h = _token(["admin"])
    client.post("/api/v1/extensions/install", json={"extension_id": "github"}, headers=admin_h)
    # installed + enabled, but NOT yet connected -> capability still inactive
    caps = client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]
    assert "github.read" not in caps
    # Visiting the provider website is not proof of authorization.
    response = client.post("/api/v1/extensions/github/connect", headers=admin_h)
    assert response.status_code == 501
    assert "github.read" not in client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]
    # disabling it removes the capability
    client.patch("/api/v1/extensions/github", json={"enabled": False}, headers=admin_h)
    assert "github.read" not in client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]


def test_catalog_carries_real_logos(client):
    catalog = {e["id"]: e for e in client.get("/api/v1/extensions").json()["extensions"]}
    # every entry carries a logo field (URL, or empty string for Jarvis-internal ones)
    for ext_id, e in catalog.items():
        assert "logo" in e, f"{ext_id} missing logo"
    # the headline integrations carry real logo URLs; the emoji stays as fallback
    for ext_id in ("github", "docker", "claude", "opencode", "slack", "aws"):
        assert catalog[ext_id]["logo"], f"{ext_id} missing a logo URL"
        assert catalog[ext_id]["logo"].startswith("http"), catalog[ext_id]["logo"]
        assert catalog[ext_id]["icon"], f"{ext_id} lost its emoji icon"


def test_install_launch_connect_flow_is_admin_gated(client):
    admin_h = _token(["admin"])
    body = {"extension_id": "docker", "config": {"driver": "unix:///var/run/docker.sock"}}

    # unauthenticated / non-admin cannot install or connect
    assert client.post("/api/v1/extensions/install", json=body).status_code == 401
    user_h = _token(["user"])
    assert client.post("/api/v1/extensions/install", json=body, headers=user_h).status_code == 403

    # admin installs -> a pending connection is recorded in Jarvis KV storage
    r = client.post("/api/v1/extensions/install", json=body, headers=admin_h)
    assert r.status_code == 200, r.text
    ext = client.get("/api/v1/extensions/docker").json()
    assert ext["installed"] is True and ext["enabled"] is True
    assert ext["connected"] is False and ext["status"] == "needs_connection"
    assert ext["launch_url"] and ext["launch_url"].startswith("http")
    assert "connect=" not in ext["launch_url"]  # real app URL, not a settings deep-link

    # launch (returns the authorize/configure URL) is admin-gated
    assert client.post("/api/v1/extensions/docker/launch").status_code == 401
    assert client.post("/api/v1/extensions/docker/launch", headers=user_h).status_code == 403
    r = client.post("/api/v1/extensions/docker/launch", headers=admin_h)
    assert r.status_code == 200, r.text
    assert r.json()["launch_url"].startswith("http")  # opens docker's own app, not settings
    assert "connect=" not in r.json()["launch_url"]

    # Opening Docker Hub does not prove Docker access; no fake connect is allowed.
    r = client.post("/api/v1/extensions/docker/connect", headers=admin_h)
    assert r.status_code == 501, r.text
    ext = client.get("/api/v1/extensions/docker").json()
    assert ext["connected"] is False and ext["status"] == "needs_connection"
    # /installed retains the pending state without claiming an active connection.
    inst = {x["id"]: x for x in
            client.get("/api/v1/extensions/installed", headers=admin_h).json()["installed"]}
    assert inst["docker"]["connected"] is False
    caps = client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]
    assert "docker.images" not in caps and "docker.build" not in caps

    # cleanup
    client.post("/api/v1/extensions/uninstall", json={"extension_id": "docker"}, headers=admin_h)
    assert client.get("/api/v1/extensions/docker").json()["installed"] is False


# ---------------------------------------------------------------------------
# OAuth handoff layer (secret-free config; verified in-process, no network)
# ---------------------------------------------------------------------------
_GITHUB_OAUTH_CFG = json.dumps({
    "github": {
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scope": "repo,user:email",
    }
})


def test_oauth_launch_builds_authorize_url_when_configured(client, monkeypatch):
    # With a JARVIS_OAUTH_CLIENTS entry, /launch must return the provider's
    # authorize URL (state-signed by JARVIS) instead of the plain app URL.
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", _GITHUB_OAUTH_CFG)
    monkeypatch.setenv("JARVIS_SECRET_KEY", "extensions-oauth-test-secret")
    admin_h = _token(["admin"])
    client.post("/api/v1/extensions/install", json={"extension_id": "github"}, headers=admin_h)
    r = client.post("/api/v1/extensions/github/launch", headers=admin_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorize_url"].startswith("https://github.com/login/oauth/authorize")
    assert "client_id=test-client-id" in body["authorize_url"]
    # redirect_uri is url-encoded in the authorize URL; decode to assert the path
    assert "/api/v1/extensions/oauth/callback/github" in unquote(body["authorize_url"])
    assert "response_type=code" in body["authorize_url"]
    assert "state=" in body["authorize_url"]
    assert "scope=repo" in body["authorize_url"]
    assert body["launch_url"] == body["authorize_url"]

    # OAuth consent belongs to each authenticated account; it does not require
    # an administrator once the extension and OAuth application are configured.
    user_h = _token(["user"])
    user_launch = client.post("/api/v1/extensions/github/launch", headers=user_h)
    assert user_launch.status_code == 200, user_launch.text
    connection = client.get("/api/v1/extensions/connections", headers=user_h)
    assert connection.status_code == 200
    github = next(item for item in connection.json()["connections"] if item["id"] == "github")
    assert github["connected"] is False
    assert github["authorization_type"] == "oauth2"
    assert "client_secret" not in github and "access_token" not in github


def test_oauth_launch_falls_back_to_app_url_without_config(client, monkeypatch):
    # No OAuth config -> external URLs are informational; they cannot activate a connection.
    monkeypatch.delenv("JARVIS_OAUTH_CLIENTS", raising=False)
    admin_h = _token(["admin"])
    client.post("/api/v1/extensions/install", json={"extension_id": "docker"}, headers=admin_h)
    r = client.post("/api/v1/extensions/docker/launch", headers=admin_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorize_url"] is None
    assert body["launch_url"] == "https://hub.docker.com/"
    assert body["connect_type"] == "unsupported"


def test_oauth_callback_requires_code_and_state(client, monkeypatch):
    # Config present, but no code/state yet -> 400 (no network exchange happens).
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", _GITHUB_OAUTH_CFG)
    r = client.get("/api/v1/extensions/oauth/callback/github")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_encrypts_tokens_and_binds_extension_owner(monkeypatch):
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", _GITHUB_OAUTH_CFG)
    monkeypatch.setenv("JARVIS_SECRET_KEY", "extensions-oauth-test-secret")
    from jarvis_backend.connectors import oauth as oauth_store
    from jarvis_backend.routers import extensions

    data = extensions._extensions_store()
    data["installed"]["github"] = {
        "id": "github",
        "enabled": True,
        "connected": False,
        "status": "needs_connection",
    }
    get_store("extensions").save()

    class Response:
        status_code = 200
        headers = {"X-OAuth-Scopes": "repo,user:email"}

        def json(self):
            return {
                "access_token": "github-access-token",
                "refresh_token": "github-refresh-token",
                "expires_in": 3600,
                "scope": "repo",
            }

    class ProfileResponse:
        status_code = 200
        headers = {"X-OAuth-Scopes": "repo,user:email"}

        def json(self):
            return {"login": "connected-github-user"}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return Response()

        async def get(self, *args, **kwargs):
            return ProfileResponse()

    monkeypatch.setattr(extensions.httpx, "AsyncClient", Client)
    state = oauth_store.make_state("github", "oauth-owner")
    response = await extensions.oauth_callback("github", "test-code", state)

    assert response.status_code == 303
    token_record = get_store("oauth_tokens").load()["github:oauth-owner"]
    assert token_record["access_token"].startswith("fernet:")
    assert token_record["refresh_token"].startswith("fernet:")
    assert oauth_store.load_tokens("github", "oauth-owner")["account"] == "connected-github-user"
    assert oauth_store.load_tokens("github", "oauth-owner")["scope"] == "repo,user:email"
    install = get_store("extensions").load()["installed"]["github"]
    assert "connected_by" not in install
    assert "oauth_token" not in install
    assert "github-access-token" not in json.dumps(install)
    connections = await extensions.list_user_connections({"id": "oauth-owner"})
    github = next(item for item in connections["connections"] if item["id"] == "github")
    assert github["connected"] is True
    assert github["account"] == "connected-github-user"
    assert github["scopes"] == "repo,user:email"
    assert "access_token" not in github and "refresh_token" not in github

    verified = await extensions.verify_extension_connection(
        "github",
        {"id": "oauth-owner"},
    )
    assert verified["authenticated"] is True
    assert verified["account"] == "connected-github-user"
    assert verified["scopes"] == "repo,user:email"

    class RepositoryResponse:
        status_code = 200

        def json(self):
            return [{
                "name": "sample",
                "full_name": "connected-github-user/sample",
                "description": "Authorized test repository",
                "private": True,
                "stargazers_count": 0,
                "language": "Python",
            }]

    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: RepositoryResponse())
    repository_list = await extensions.invoke_extension(
        "github",
        extensions.ExtensionInvokeIn(capability="github.repositories.list"),
        {"id": "oauth-owner"},
    )
    assert repository_list["result"]["repos"][0]["full_name"] == "connected-github-user/sample"

    write_body = extensions.ExtensionInvokeIn(
        capability="github.files.write",
        params={
            "owner": "connected-github-user",
            "repo": "sample",
            "path": "README.md",
            "content": "approved change",
            "message": "Update README",
        },
    )
    with pytest.raises(HTTPException) as confirmation:
        await extensions.invoke_extension("github", write_body, {"id": "oauth-owner"})
    assert confirmation.value.status_code == 409

    class CurrentFileResponse:
        status_code = 200

        def json(self):
            return {"sha": "current-sha"}

    class UpdatedFileResponse:
        status_code = 200

        def json(self):
            return {
                "content": {"path": "README.md", "sha": "new-sha"},
                "commit": {"sha": "commit-sha"},
            }

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: CurrentFileResponse())
    monkeypatch.setattr(requests, "put", lambda *args, **kwargs: UpdatedFileResponse())
    write_body.confirmed = True
    updated = await extensions.invoke_extension(
        "github",
        write_body,
        {"id": "oauth-owner"},
    )
    assert updated["result"]["commit_sha"] == "commit-sha"

    with pytest.raises(HTTPException) as denied:
        await extensions.invoke_extension(
            "github",
            extensions.ExtensionInvokeIn(capability="github.repositories.list"),
            {"id": "different-user"},
        )
    assert denied.value.status_code == 403

    disconnected = await extensions.disconnect_extension_connection(
        "github",
        {"id": "oauth-owner"},
    )
    assert disconnected["connected"] is False
    assert oauth_store.load_tokens("github", "oauth-owner") is None


def test_oauth_callback_404_without_config(client, monkeypatch):
    monkeypatch.delenv("JARVIS_OAUTH_CLIENTS", raising=False)
    r = client.get("/api/v1/extensions/oauth/callback/github?code=x&state=y")
    assert r.status_code == 404




# ---------------------------------------------------------------------------
# API-key connect flow (OpenAI, Claude, Gemini, Hugging Face, CodeMuse)
# ---------------------------------------------------------------------------
# External services whose connection is an API key issued from the service's own
# console. /launch advertises connect_type="api_key" + the key-creation console
# URL; /connect accepts a key (or auto-detects it from env), VALIDATES it live,
# and only then flips the extension live -- so the capabilities go real on the
# platform immediately, with no demo confirm-gate state.
_APIKEY_PROVIDERS = ["openai", "claude", "gemini", "nvidia", "whisper", "stablediffusion", "codemuse"]
_SUPPORTED_APIKEY_PROVIDERS = {"openai", "claude", "gemini", "nvidia"}


@pytest.fixture(autouse=True)
def _isolate_api_key_env(monkeypatch):
    """These tests must not depend on / leak real provider keys in the runner."""
    monkeypatch.setenv("JARVIS_SECRET_KEY", "extensions-test-signing-key")
    for v in ("OPENAI_API_KEY", "JARVIS_API_KEY_OPENAI", "ANTHROPIC_API_KEY",
              "JARVIS_API_KEY_CLAUDE", "GOOGLE_API_KEY", "JARVIS_API_KEY_GEMINI",
              "HF_TOKEN", "JARVIS_API_KEY_WHISPER", "JARVIS_API_KEY_STABLEDIFFUSION",
              "JARVIS_API_KEY_CODEMUSE"):
        monkeypatch.delenv(v, raising=False)
    yield


def _admin_headers():
    return _token(["admin"])


def _error_message(response):
    payload = response.json()
    return payload.get("detail") or payload.get("error", {}).get("message", "")


def test_api_key_launch_advertises_connect_type(client, _isolate_api_key_env):
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": "openai"}, headers=admin_h)
    r = client.post("/api/v1/extensions/openai/launch", headers=admin_h)
    assert r.status_code == 200, r.text
    body = r.json()
    # Real OpenAI API-key service: console URL, no OAuth authorize URL
    assert body["connect_type"] == "api_key"
    assert body["authorize_url"] is None
    assert body["launch_url"] == "https://platform.openai.com/api-keys"
    assert body["key_env"] == "OPENAI_API_KEY"


@pytest.mark.parametrize("ext", _APIKEY_PROVIDERS)
def test_api_key_launch_for_all_providers(client, ext, _isolate_api_key_env):
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": ext}, headers=admin_h)
    r = client.post(f"/api/v1/extensions/{ext}/launch", headers=admin_h)
    assert r.status_code == 200, r.text
    expected_type = "api_key" if ext in _SUPPORTED_APIKEY_PROVIDERS else "unsupported"
    assert r.json()["connect_type"] == expected_type
    assert r.json()["authorize_url"] is None
    # the public catalog also exposes the connect contract
    cat = {e["id"]: e for e in client.get("/api/v1/extensions").json()["extensions"]}
    assert cat[ext]["connect_type"] == expected_type
    assert cat[ext]["key_env"] is not None


def test_api_key_connect_requires_a_key(client, _isolate_api_key_env):
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": "openai"}, headers=admin_h)
    # No key in body and none in env -> 400 (the demo confirm-gate is gone:
    # an API key is mandatory to flip OpenAI connected)
    r = client.post("/api/v1/extensions/openai/connect", headers=admin_h)
    assert r.status_code == 400, r.text
    assert "API key" in _error_message(r)


def test_api_key_connect_rejects_invalid_key(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": "openai"}, headers=admin_h)
    validation_calls = []
    # Validation explicitly fails -> 401. A bad key is REJECTED, not silently
    # accepted (this is the real validation gate, not a confirm-gate).
    monkeypatch.setattr("jarvis_backend.routers.extensions._validate_api_key",
                        lambda ext_id, key: (validation_calls.append((ext_id, key)) or
                                             (False, "invalid OpenAI API key")))
    r = client.post("/api/v1/extensions/openai/connect", json={"api_key": "sk-bad"}, headers=admin_h)
    assert r.status_code == 401, r.text
    assert validation_calls == [("openai", "sk-bad")]
    # the extension stays disconnected
    ext = client.get("/api/v1/extensions/openai").json()
    assert ext["connected"] is False


def test_api_key_connect_with_validated_key_goes_live(client, _isolate_api_key_env, monkeypatch):
    monkeypatch.setenv("JARVIS_SECRET_KEY", "extensions-api-key-test-secret")
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": "openai"}, headers=admin_h)
    # capabilities dormant before connect
    caps = client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]
    assert "openai.chat" not in caps
    # validator confirms the key -> connected + capabilities live immediately
    monkeypatch.setattr("jarvis_backend.routers.extensions._validate_api_key",
                        lambda ext_id, key: (True, None))
    r = client.post("/api/v1/extensions/openai/connect", json={"api_key": "sk-valid"}, headers=admin_h)
    assert r.status_code == 200, r.text
    assert r.json()["validation"] == "verified"
    # /capabilities now exposes openai.* across the entire platform
    caps = client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]
    assert "openai.chat" in caps and "openai.images" in caps
    # /installed reflects the validated connection metadata (no raw secret)
    inst = {x["id"]: x for x in
            client.get("/api/v1/extensions/installed", headers=admin_h).json()["installed"]}
    assert inst["openai"]["connected"] is True
    assert inst["openai"]["connected_by"] != "api_key"
    assert inst["openai"]["validation"] == "verified"
    assert inst["openai"]["key_env"] == "OPENAI_API_KEY"
    assert "api_key" not in inst["openai"]  # raw secret never persisted
    token_store = get_store("oauth_tokens").load()
    stored = token_store[f"openai:{inst['openai']['connected_by']}"]
    assert stored["access_token"].startswith("fernet:")


def test_api_key_connect_env_autodetects_key(client, _isolate_api_key_env, monkeypatch):
    monkeypatch.setenv("JARVIS_SECRET_KEY", "extensions-api-key-test-secret")
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": "openai"}, headers=admin_h)
    # Self-resilient: user set the key once in env, no re-paste needed
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setattr("jarvis_backend.routers.extensions._validate_api_key",
                        lambda ext_id, key: (True, None))
    # POST /connect with NO body -> backend auto-detects env key + validates it
    r = client.post("/api/v1/extensions/openai/connect", headers=admin_h)
    assert r.status_code == 200, r.text
    assert r.json()["validation"] == "verified"
    assert "openai.chat" in client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]


def test_api_key_connect_without_supported_invoker_is_not_marked_connected(client, _isolate_api_key_env):
    admin_h = _admin_headers()
    # No invocation handler means an API key cannot activate this extension yet.
    client.post("/api/v1/extensions/install", json={"extension_id": "codemuse"}, headers=admin_h)
    r = client.post("/api/v1/extensions/codemuse/connect", json={"api_key": "cm-key"}, headers=admin_h)
    assert r.status_code == 501, r.text
    assert "codemuse.chat" not in client.get("/api/v1/extensions/capabilities", headers=admin_h).json()["capabilities"]


def test_list_installed_never_leaks_oauth_token(client, _isolate_api_key_env):
    admin_h = _admin_headers()
    client.post("/api/v1/extensions/install", json={"extension_id": "github"}, headers=admin_h)
    # Simulate a persisted OAuth token (as oauth_callback would store)
    from jarvis_backend.core import get_store
    data = get_store("extensions").load()
    data["installed"]["github"]["oauth_token"] = {"access_token": "super-secret-tok"}
    data["installed"]["github"]["api_key"] = "super-secret-key"
    get_store("extensions").save()
    r = client.get("/api/v1/extensions/installed", headers=admin_h)
    assert r.status_code == 200
    body = r.json()
    for entry in body["installed"]:
        assert "oauth_token" not in entry
        assert "api_key" not in entry
    assert "super-secret-tok" not in json.dumps(body)
    assert "super-secret-key" not in json.dumps(body)
# ---------------------------------------------------------------------------
# Extension service invocation: Jarvis USES a connected extension's REAL service
# (opt-in: an admin explicitly POSTs /invoke; no /api/chat autowire).
# ---------------------------------------------------------------------------
from jarvis_backend.routers import extensions as _ext_mod


class _FakeHttpResp:
    """Stand-in for an httpx.Response so invoke tests stay hermetic."""
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            raise httpx.HTTPStatusError("err", request=req, response=self)


def _ext(client, admin_h, ext="openai"):
    client.post("/api/v1/extensions/install", json={"extension_id": ext}, headers=admin_h)


def test_invoke_openai_chat_returns_provider_response(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    _ext(client, admin_h)
    fake = _FakeHttpResp(200, {"choices": [{"message": {"content": "hi from openai"}}],
                               "model": "gpt-4o-mini", "usage": {"total_tokens": 3}})
    monkeypatch.setattr(_ext_mod.httpx, "post", lambda *a, **k: fake)
    r = client.post("/api/v1/extensions/openai/invoke",
                    json={"capability": "openai.chat", "api_key": "sk-test",
                          "params": {"messages": [{"role": "user", "content": "hello"}]}},
                    headers=admin_h)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["extension"] == "openai"
    assert res["result"]["provider"] == "openai"
    assert res["result"]["content"] == "hi from openai"


def test_invoke_openai_image_generation(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    _ext(client, admin_h)
    fake = _FakeHttpResp(200, {"data": [{"url": "https://oaidallec.com/i/x.png"}]})
    monkeypatch.setattr(_ext_mod.httpx, "post", lambda *a, **k: fake)
    r = client.post("/api/v1/extensions/openai/invoke",
                    json={"capability": "openai.images", "api_key": "sk-test",
                          "params": {"prompt": "a red square"}}, headers=admin_h)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["images"] == ["https://oaidallec.com/i/x.png"]


def test_invoke_requires_api_key(client, _isolate_api_key_env):
    admin_h = _admin_headers()
    _ext(client, admin_h)
    # No key in body, none in env -> 400 (no demo; a real key is required)
    r = client.post("/api/v1/extensions/openai/invoke",
                    json={"capability": "openai.chat", "params": {"messages": []}}, headers=admin_h)
    assert r.status_code == 400, r.text
    assert "API key" in _error_message(r)


def test_invoke_bad_key_rejected_by_provider(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    _ext(client, admin_h)
    # Provider itself returns 401 -> invoke propagates it (real validation gate)
    provider_calls = []
    monkeypatch.setattr(_ext_mod.httpx, "post",
                        lambda *a, **k: (provider_calls.append((a, k)) or
                                         _FakeHttpResp(401, text="invalid")))
    r = client.post("/api/v1/extensions/openai/invoke",
                    json={"capability": "openai.chat", "api_key": "sk-bad",
                          "params": {"messages": [{"role": "user", "content": "hi"}]}}, headers=admin_h)
    assert r.status_code == 401, r.text
    assert provider_calls


def test_invoke_not_implemented_for_confirm_service(client, _isolate_api_key_env):
    # docker is a confirm-gate service (no API key); invocation isn't wired yet
    admin_h = _admin_headers()
    _ext(client, admin_h, ext="docker")
    r = client.post("/api/v1/extensions/docker/invoke",
                    json={"capability": "docker.containers"}, headers=admin_h)
    assert r.status_code == 501, r.text


def test_invoke_not_installed(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    monkeypatch.setattr(_ext_mod, "_extensions_store", lambda: {"installed": {}})
    r = client.post("/api/v1/extensions/openai/invoke",
                    json={"capability": "openai.chat", "api_key": "sk-x"}, headers=admin_h)
    assert r.status_code == 404, r.text



def test_invoke_claude_chat_returns_provider_response(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    _ext(client, admin_h, ext="claude")
    fake = _FakeHttpResp(200, {"content": [{"text": "hi from claude"}],
                               "model": "claude-3-5-sonnet", "usage": {"output_tokens": 3}})
    monkeypatch.setattr(_ext_mod.httpx, "post", lambda *a, **k: fake)
    r = client.post("/api/v1/extensions/claude/invoke",
                    json={"capability": "claude.chat", "api_key": "sk-test",
                          "params": {"messages": [{"role": "user", "content": "hello"}]}},
                    headers=admin_h)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["extension"] == "claude"
    assert res["result"]["provider"] == "claude"
    assert res["result"]["content"] == "hi from claude"


def test_invoke_claude_bad_key_rejected(client, _isolate_api_key_env, monkeypatch):
    # Provider returns 401 -> invoke propagates it (real validation gate)
    admin_h = _admin_headers()
    _ext(client, admin_h, ext="claude")
    provider_calls = []
    monkeypatch.setattr(_ext_mod.httpx, "post",
                        lambda *a, **k: (provider_calls.append((a, k)) or
                                         _FakeHttpResp(401, text="invalid")))
    r = client.post("/api/v1/extensions/claude/invoke",
                    json={"capability": "claude.chat", "api_key": "bad-key",
                          "params": {"messages": [{"role": "user", "content": "hi"}]}}, headers=admin_h)
    assert r.status_code == 401, r.text
    assert provider_calls


def test_invoke_gemini_chat_returns_provider_response(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    _ext(client, admin_h, ext="gemini")
    fake = _FakeHttpResp(200, {"candidates": [{"content": {"parts": [{"text": "hi from gemini"}]}}],
                               "usageMetadata": {"totalTokens": "5"}})
    monkeypatch.setattr(_ext_mod.httpx, "post", lambda *a, **k: fake)
    r = client.post("/api/v1/extensions/gemini/invoke",
                    json={"capability": "gemini.chat", "api_key": "test-gem",
                          "params": {"messages": [{"role": "user", "content": "hello"}]}},
                    headers=admin_h)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["extension"] == "gemini"
    assert res["result"]["provider"] == "gemini"
    assert res["result"]["content"] == "hi from gemini"


def test_invoke_gemini_bad_key_rejected(client, _isolate_api_key_env, monkeypatch):
    admin_h = _admin_headers()
    _ext(client, admin_h, ext="gemini")
    provider_calls = []
    monkeypatch.setattr(_ext_mod.httpx, "post",
                        lambda *a, **k: (provider_calls.append((a, k)) or
                                         _FakeHttpResp(401, text="invalid")))
    r = client.post("/api/v1/extensions/gemini/invoke",
                    json={"capability": "gemini.chat", "api_key": "bad-key",
                          "params": {"messages": [{"role": "user", "content": "hi"}]}}, headers=admin_h)
    assert r.status_code == 401, r.text
    assert provider_calls
