"""Permission-bound knowledge retrieval tests for the supported backend."""

from jarvis_backend.core import get_store


def test_cognitive_knowledge_search_requires_authentication(client):
    response = client.get(
        "/api/v1/cognitive/knowledge/search",
        params={"query": "owner-specific"},
    )

    assert response.status_code == 401


def test_cognitive_knowledge_search_is_scoped_to_the_caller(client, admin_headers):
    store = get_store("knowledge")
    items = store.load()
    items.update(
        {
            "caller-item": {
                "key": "owner-specific-caller",
                "value": "visible",
                "user_id": "test-admin",
            },
            "other-item": {
                "key": "owner-specific-other",
                "value": "must-not-leak",
                "user_id": "another-user",
            },
        }
    )
    store.save()

    response = client.get(
        "/api/v1/cognitive/knowledge/search",
        params={"query": "owner-specific"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["user_id"] == "test-admin"
    assert "must-not-leak" not in response.text
