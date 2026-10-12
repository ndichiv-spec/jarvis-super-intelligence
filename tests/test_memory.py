"""Tests for the supported knowledge and cognitive-memory API surfaces."""


class TestKnowledgeAPI:
    """Test knowledge API endpoints."""

    def test_get_all_knowledge(self, client, auth_headers):
        """Test getting all knowledge."""
        response = client.get("/api/v1/knowledge", headers=auth_headers)
        assert response.status_code == 200

    def test_search_knowledge(self, client, auth_headers):
        """Test searching knowledge."""
        response = client.get("/api/v1/knowledge/search?q=test", headers=auth_headers)
        assert response.status_code == 200

    def test_add_knowledge(self, client, auth_headers):
        """Test adding knowledge."""
        payload = {
            "key": "test_key",
            "value": "test_value",
            "category": "test",
            "tags": ["test"],
        }
        response = client.post(
            "/api/v1/knowledge",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]


class TestMemoryAPI:
    """Test memory API endpoints."""

    def test_get_memory_stats(self, client, auth_headers):
        response = client.get("/api/v1/cognitive/memory/stats", headers=auth_headers)
        assert response.status_code == 200

    def test_get_memory_stats_requires_authentication(self, client):
        response = client.get("/api/v1/cognitive/memory/stats")
        assert response.status_code == 401
