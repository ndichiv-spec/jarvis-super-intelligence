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
