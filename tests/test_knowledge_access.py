"""Authenticated, user-scoped knowledge workspace API behavior."""

import uuid

import pytest

from jarvis_backend.core import create_token, get_store


def _user_headers(user_id: str, email: str) -> dict[str, str]:
    users = get_store("users")
    records = users.load()
    records[user_id] = {
        "id": user_id,
        "email": email,
        "display_name": user_id,
        "is_active": True,
        "roles": ["user"],
    }
    users.save()
    token = create_token({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_knowledge_reads_require_authentication(client):
    assert client.get("/api/v1/knowledge").status_code == 401
    assert client.get("/api/v1/knowledge/search?q=jarvis").status_code == 401
    assert client.get("/api/v1/knowledge/patterns").status_code == 401
    assert client.get("/api/v1/cognitive/knowledge/search").status_code == 401


def test_knowledge_entries_are_isolated_per_user(client, auth_headers):
    key = f"isolation_{uuid.uuid4().hex}"
    created = client.post(
        "/api/v1/knowledge",
        headers=auth_headers,
        json={"key": key, "value": "Private knowledge content", "category": "general"},
    )
    assert created.status_code == 200

    other_user_id = f"knowledge-reader-{uuid.uuid4().hex}"
    other_headers = _user_headers(other_user_id, f"{other_user_id}@jarvis.local")
    other_entries = client.get("/api/v1/knowledge", headers=other_headers).json()["entries"]
    assert all(entry["key"] != key for entry in other_entries)

    forbidden_delete = client.delete(
        "/api/v1/knowledge",
        params={"key": key},
        headers=other_headers,
    )
    assert forbidden_delete.status_code == 404

    own_entries = client.get("/api/v1/knowledge", headers=auth_headers).json()["entries"]
    assert any(entry["key"] == key for entry in own_entries)


def test_knowledge_upsert_and_patterns_return_renderable_entries(client, auth_headers):
    label = uuid.uuid4().hex
    key = f"pattern:remember_{label}"
    first = client.post(
        "/api/v1/knowledge",
        headers=auth_headers,
        json={"key": key, "value": "First response", "category": "pattern", "tags": ["learned"]},
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    updated = client.post(
        "/api/v1/knowledge",
        headers=auth_headers,
        json={"key": key, "value": "Updated response", "category": "pattern", "tags": ["learned"]},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == first_id
    assert updated.json()["value"] == "Updated response"

    patterns = client.get("/api/v1/knowledge/patterns", headers=auth_headers)
    assert patterns.status_code == 200
    assert {
        "pattern": f"remember_{label}",
        "response": "Updated response",
        "category": "pattern",
    } in patterns.json()["patterns"]


def test_cognitive_knowledge_search_and_chat_context_are_user_scoped(
    client, auth_headers
):
    owner_id = "testuser"
    private_key = f"private_{uuid.uuid4().hex}"
    other_key = f"other_{uuid.uuid4().hex}"
    global_key = f"global_{uuid.uuid4().hex}"
    knowledge = get_store("knowledge").load()
    knowledge.update({
        f"{owner_id}::{private_key}": {
            "key": private_key,
            "value": "owner privateproof",
            "category": "private",
            "user_id": owner_id,
        },
        f"other-user::{other_key}": {
            "key": other_key,
            "value": "other privateproof",
            "category": "private",
            "user_id": "other-user",
        },
        f"system::{global_key}": {
            "key": global_key,
            "value": "shared sharedproof",
            "category": "shared",
            "user_id": "system",
        },
        "legacy-unowned": {
            "key": "legacy-private",
            "value": "legacy legacyproof",
            "user_id": None,
        },
        "explicit-public": {
            "key": "public-marker",
            "value": "approved publicproof",
            "user_id": None,
            "visibility": "public",
        },
    })
    get_store("knowledge").save()

    results = client.get(
        "/api/v1/cognitive/knowledge/search",
        params={"query": "privateproof"},
        headers=auth_headers,
    )
    assert results.status_code == 200
    visible_keys = {item["key"] for item in results.json()["results"]}
    assert private_key in visible_keys
    assert other_key not in visible_keys
    assert global_key not in visible_keys
    assert "legacy-private" not in visible_keys

    visible_public = client.get(
        "/api/v1/cognitive/knowledge/search",
        params={"query": "approved publicproof"},
        headers=auth_headers,
    ).json()["results"]
    assert [entry["key"] for entry in visible_public] == ["public-marker"]

    from jarvis_backend.chat_service import chat_service

    own_context = chat_service._recall_context(owner_id, "privateproof")
    assert private_key in own_context
    assert other_key not in own_context
    assert global_key not in own_context
    assert "legacy legacyproof" not in own_context

    shared_context = chat_service._recall_context(owner_id, "sharedproof")
    assert global_key in shared_context
