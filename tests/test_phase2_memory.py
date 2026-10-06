"""Phase 2.3 — memory / knowledge integration tests.

Verifies that recalled memories and knowledge items are injected into the
system prompt that is sent to the provider gateway, that the injection is
ownership-safe (one user's memories never leak into another user's context),
and that the absence of memories leaves the base system prompt untouched.
"""
from __future__ import annotations

from jarvis_backend import chat_service as cs
from jarvis_backend.core import _SYSTEM_PROMPT, get_store, now_iso


class CapturingGateway:
    """Fake provider gateway that records the ``system`` prompt it receives."""

    def __init__(self, content="Hello from the model."):
        self.content = content
        self.timeout = 30.0
        self.max_retries = 0
        self.calls = 0
        self.system = None
        self.messages = None

    async def chat(self, messages, model=None, system=None, timeout=None):
        self.calls += 1
        self.system = system
        self.messages = messages
        return {
            "content": self.content,
            "model": "fake:mem",
            "provider": "fake",
            "latency_ms": 3,
            "usage": {},
        }


def _seed_user_memory(user_id: str, content: str, importance: float = 0.9):
    mem = get_store("memory").load()
    mid = "mem-" + content[:8]
    mem[mid] = {
        "id": mid,
        "content": content,
        "layer": "short_term",
        "importance": importance,
        "user_id": user_id,
        "created_at": now_iso(),
    }
    get_store("memory").save()
    return mem[mid]


def _seed_knowledge(key: str, value: str):
    kb = get_store("knowledge").load()
    kb[key] = {"key": key, "value": value, "category": "system", "tags": ["system"]}
    get_store("knowledge").save()


def test_memory_and_knowledge_recall_injected_into_system_prompt(
    client, auth_user, monkeypatch
):
    user_id = auth_user["user"]["id"]
    _seed_user_memory(user_id, "The user's pet is a cat named Whiskers.")
    _seed_knowledge("jarvis_version", "JARVIS version 3.0.0")

    fake = CapturingGateway()
    monkeypatch.setattr(cs.chat_service, "gateway", fake)

    prompt = "what version is Jarvis and tell me about Whiskers"
    resp = client.post(
        "/api/chat",
        json={"message": prompt},
        headers=auth_user["headers"],
    )
    assert resp.status_code == 200
    assert fake.calls == 1

    system = fake.system or ""
    # Base system prompt is preserved...
    assert _SYSTEM_PROMPT in system
    # ...recalled memory is appended (lowercased by the recall scorer)...
    assert "whiskers" in system.lower()
    # ...and matching knowledge items are injected.
    assert "jarvis version 3.0.0" in system.lower()


def test_system_prompt_without_memory_is_unchanged(client, auth_user, monkeypatch):
    fake = CapturingGateway()
    monkeypatch.setattr(cs.chat_service, "gateway", fake)

    resp = client.post(
        "/api/chat",
        json={"message": "hello"},
        headers=auth_user["headers"],
    )
    assert resp.status_code == 200
    assert fake.system == _SYSTEM_PROMPT


def test_memory_isolation_between_users(client, auth_user, monkeypatch):
    """A memory owned by a *different* user must never reach this user's prompt."""
    user_id = auth_user["user"]["id"]
    _seed_user_memory("some-other-user", "SECRET_TOKEN_987654")

    fake = CapturingGateway()
    monkeypatch.setattr(cs.chat_service, "gateway", fake)

    resp = client.post(
        "/api/chat",
        json={"message": "hello there"},
        headers=auth_user["headers"],
    )
    assert resp.status_code == 200
    assert "secret_token_987654" not in (fake.system or "").lower()
