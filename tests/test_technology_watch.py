from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis_backend.core import get_current_user
from jarvis_backend.research import technology_watch as watch
from jarvis_backend.routers import global_knowledge


class MemoryStore:
    def __init__(self):
        self.data = {}
        self.saves = 0

    def load(self):
        return self.data

    def save(self):
        self.saves += 1


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, *, fail_repository=None, **kwargs):
        self.fail_repository = fail_repository
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, **kwargs):
        self.requested_urls.append(url)
        repository = url.removeprefix("https://api.github.com/repos/").removesuffix("/releases")
        if repository == self.fail_repository:
            raise httpx.ConnectError("source unavailable")
        return FakeResponse([{
            "tag_name": "v1.2.3",
            "name": "Release 1.2.3",
            "html_url": f"https://github.com/{repository}/releases/tag/v1.2.3",
            "published_at": "2026-09-30T12:00:00Z",
            "body": "Release notes are external text.",
        }])


def test_release_normalization_rejects_untrusted_urls_and_prereleases():
    source = watch.SOURCES[0]
    base = {
        "tag_name": "v1.0.0",
        "html_url": f"https://github.com/{source['repository']}/releases/tag/v1.0.0",
        "body": "release body",
    }

    assert watch._normalize_release(source, {**base, "html_url": "https://evil.test/release"}) is None
    assert watch._normalize_release(source, {**base, "prerelease": True}) is None
    item = watch._normalize_release(source, base)
    assert item is not None
    assert item["content_trust"] == "external_release_notes_untrusted"
    assert item["repository"] == source["repository"]


@pytest.mark.asyncio
async def test_refresh_reads_only_pinned_sources_and_keeps_partial_failures(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(watch, "get_store", lambda _name: store)
    clients = []

    def client_factory(**kwargs):
        client = FakeClient(fail_repository="vllm-project/vllm", **kwargs)
        clients.append(client)
        return client

    result = await watch.refresh_watch(client_factory=client_factory, force=True)

    assert result["status"] == "partial"
    assert result["new_items"] == len(watch.SOURCES) - 1
    assert len(result["items"]) == len(watch.SOURCES) - 1
    assert result["last_errors"][0]["source_id"] == "vllm"
    assert len(clients[0].requested_urls) == len(watch.SOURCES)
    assert all(url.startswith("https://api.github.com/repos/") for url in clients[0].requested_urls)
    assert all(item["content_trust"] == "external_release_notes_untrusted" for item in result["items"])
    assert store.saves == 2

    repeated = await watch.refresh_watch(client_factory=client_factory, force=True)
    assert repeated["new_items"] == 0


@pytest.mark.asyncio
async def test_refresh_cooldown_returns_cached_results_without_network(monkeypatch):
    store = MemoryStore()
    store.data["last_attempt_at"] = datetime.now(UTC).isoformat()
    store.data["items"] = [{"id": "cached"}]
    monkeypatch.setattr(watch, "get_store", lambda _name: store)

    def should_not_connect(**kwargs):
        raise AssertionError("cooldown must not make network requests")

    result = await watch.refresh_watch(client_factory=should_not_connect)

    assert result["status"] == "throttled"
    assert result["items"] == [{"id": "cached"}]
    assert result["new_items"] == 0


def test_watch_routes_require_auth_and_legacy_rss_does_not_claim_success(monkeypatch):
    app = FastAPI()
    app.include_router(global_knowledge.router)
    client = TestClient(app)

    assert client.get("/api/v1/global/technology/updates").status_code == 401
    assert client.post("/api/v1/global/technology/refresh").status_code == 401
    response = client.post("/api/v1/global/rss/refresh")
    assert response.status_code == 501
    assert "no refresh was performed" in response.json()["detail"]

    app.dependency_overrides[get_current_user] = lambda: {"roles": ["user"]}
    assert client.post("/api/v1/global/technology/refresh").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: {"is_admin": True}
    response = client.get("/api/v1/global/technology/updates")
    assert response.status_code == 200
    assert response.json()["automatic_refresh"] is False

    audit_store = MemoryStore()
    audit_store.data = []
    monkeypatch.setattr(global_knowledge, "get_store", lambda _name: audit_store)

    async def fake_refresh():
        return {"status": "partial", "new_items": 3}

    monkeypatch.setattr(global_knowledge, "refresh_watch", fake_refresh)
    response = client.post("/api/v1/global/technology/refresh")
    assert response.status_code == 200
    assert audit_store.data[0]["kind"] == "technology_watch"
    assert audit_store.data[0]["meta"] == {"status": "partial", "new_items": 3}
