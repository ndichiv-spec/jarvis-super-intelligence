"""
Tests for Memory and Knowledge Systems
======================================
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock


class TestMemorySystem:
    """Test memory system module."""

    def test_memory_system_import(self):
        """Test memory system can be imported."""
        from core.memory_system import UserMemory, MemoryEntry

        assert UserMemory is not None
        assert MemoryEntry is not None

    def test_persistent_memory_import(self):
        """Test persistent memory can be imported."""
        from core import persistent_memory

        assert persistent_memory is not None

    def test_memory_manager_import(self):
        """Test memory manager can be imported."""
        from core.memory_manager import MemoryManager

        manager = MemoryManager()
        assert manager is not None

    def test_advanced_memory_import(self):
        """Test advanced memory can be imported."""
        from core import advanced_memory

        assert advanced_memory is not None


class TestKnowledgeSystem:
    """Test knowledge system module."""

    def test_knowledge_base_import(self):
        """Test knowledge base can be imported."""
        from core.knowledge_base import KnowledgeBase

        kb = KnowledgeBase()
        assert kb is not None

    def test_knowledge_graph_import(self):
        """Test knowledge graph can be imported."""
        from core.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()
        assert kg is not None

    def test_embeddings_import(self):
        """Test embeddings can be imported."""
        from core import embeddings

        assert embeddings is not None

    def test_global_knowledge_import(self):
        """Test global knowledge can be imported."""
        from core import global_knowledge

        assert global_knowledge is not None


class TestKnowledgeAPI:
    """Test knowledge API endpoints."""

    @pytest.mark.asyncio
    async def test_get_all_knowledge(self, test_client):
        """Test getting all knowledge."""
        response = await test_client.get("/api/v1/knowledge")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_knowledge(self, test_client):
        """Test searching knowledge."""
        response = await test_client.get("/api/v1/knowledge/search?q=test")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_add_knowledge(self, test_client, auth_headers):
        """Test adding knowledge."""
        payload = {
            "key": "test_key",
            "value": "test_value",
            "category": "test",
            "tags": ["test"],
        }
        response = await test_client.post(
            "/api/v1/knowledge",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code in [200, 201]


class TestMemoryAPI:
    """Test memory API endpoints."""

    @pytest.mark.asyncio
    async def test_get_memory_stats(self, test_client, auth_headers):
        """Test getting memory stats."""
        response = await test_client.get("/api/v1/memory/stats", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_memory_sessions(self, test_client):
        """Test getting memory sessions."""
        response = await test_client.get("/api/v1/memory/sessions")
        assert response.status_code == 200
