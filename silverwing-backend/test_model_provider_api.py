"""Integration tests for the /api/models/* endpoints + model_provider tool.

Run with:  python -m pytest test_model_provider_api.py -q
Hermetic: uses the always-on LocalProvider fallback (no model SDK/key needed).
"""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _chat(model=None, messages=None):
    body = {"messages": messages or [{"role": "user", "content": "ping"}]}
    if model:
        body["model"] = model
    return client.post("/api/models/chat", json=body)


class TestModelProviderAPI:
    def test_list(self):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        names = {p["name"] for p in data["providers"]}
        assert {"local", "openai", "anthropic", "google", "groq", "ollama",
                "deepseek", "bedrock", "vertex", "llamacpp"} <= names
        assert data["default"] == "local-rule"

    def test_catalog(self):
        resp = client.get("/api/models/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "models" in data
        assert len(data["models"]) > 10
        # Spot-check key entries
        model_keys = {m["key"] for m in data["models"]}
        assert "openai:gpt-5.6-sol" in model_keys
        assert "anthropic:claude-opus-5" in model_keys
        assert "google:gemini-2.5-pro" in model_keys
        assert "bedrock:anthropic.claude-opus-5" in model_keys
        assert "vertex:gemini-2.5-pro" in model_keys
        assert "deepseek:deepseek-v4-pro" in model_keys
        # Open-weights models should be present
        assert any(m["open_weights"] for m in data["models"])

    def test_catalog_by_family(self):
        resp = client.get("/api/models/catalog/families")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "families" in data
        assert len(data["families"]) > 5

    def test_catalog_open_weights(self):
        resp = client.get("/api/models/catalog/open-weights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["models"]) >= 3

    def test_chat_falls_back_for_new_providers(self):
        # deepseek, bedrock, vertex have no keys/creds in test env -> local
        for ref, payload in [
            ("deepseek:deepseek-v4-pro", "ds-fallback"),
            ("bedrock:anthropic.claude-opus-5", "bedrock-fb"),
            ("vertex:gemini-2.5-pro", "vertex-fb"),
        ]:
            resp = _chat(model=ref, messages=[{"role": "user", "content": payload}])
            assert resp.status_code == 200
            d = resp.json()
            assert d["provider"] == "local"
            assert f"[local] {payload}" in d["content"]

    def test_default(self):
        resp = client.get("/api/models/default")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["default"] == "local-rule"

    def test_chat_local_echo(self):
        resp = _chat(messages=[{"role": "user", "content": "hello"}])
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["provider"] == "local"
        assert "[local] hello" in data["content"]
        assert data["finish_reason"] == "stop"

    def test_chat_falls_back_when_provider_unavailable(self):
        # openai has no key/sdk in the test env -> LocalProvider fallback
        resp = _chat(model="openai:gpt-5.6-sol",
                     messages=[{"role": "user", "content": "fallback"}])
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "local"
        assert "[local] fallback" in data["content"]

    def test_set_default(self):
        resp = client.post("/api/models/default", json={"model": "anthropic:claude-fable-5"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "anthropic" in resp.json()["default"]
        # reflected on subsequent default read
        assert "anthropic" in client.get("/api/models/default").json()["default"]
        # restore for any later tests that depend on the default
        client.post("/api/models/default", json={"model": "local-rule"})

    def test_chat_no_user_message(self):
        resp = _chat(messages=[{"role": "assistant", "content": "hi"}])
        assert resp.status_code == 200
        assert "no user message" in resp.json()["content"]

    def test_model_provider_tool_dispatch(self):
        # Exercise the agent tool surface (mirrors _dispatch_tool usage).
        from main import _tool_model_provider
        import asyncio
        out = asyncio.run(_tool_model_provider({"action": "list"}))
        assert out["status"] == "ok"
        assert isinstance(out["providers"], list)
        out2 = asyncio.run(_tool_model_provider({
            "action": "chat",
            "model": "local-rule",
            "messages": [{"role": "user", "content": "tool-ok"}],
        }))
        assert out2["status"] == "ok"
        assert "[local] tool-ok" in out2["content"]
