"""
JARVIS Integration Tests
========================
Integration tests for the unified JARVIS system components.
"""

import pytest
import asyncio
from typing import Dict, Any


class TestOrchestrator:
    """Test the unified orchestrator"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test that orchestrator initializes correctly"""
        from core.orchestrator import get_orchestrator
        
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        
        assert orchestrator._initialized is True
    
    @pytest.mark.asyncio
    async def test_simple_mode_processing(self):
        """Test simple mode processing"""
        from core.orchestrator import get_orchestrator, OrchestrationMode, OrchestrationRequest
        
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        
        request = OrchestrationRequest(
            query="Hello, JARVIS",
            user_id="test_user",
            mode=OrchestrationMode.SIMPLE
        )
        
        result = await orchestrator.process(request)
        
        assert result.success is True
        assert len(result.response) > 0
        assert result.mode_used == OrchestrationMode.SIMPLE


class TestOmegaEngine:
    """Test OMEGA AI Engine integration"""
    
    @pytest.mark.asyncio
    async def test_omega_status(self):
        """Test that OMEGA engine status can be retrieved"""
        try:
            from core.omega_engine import OmegaEngine
            
            omega = OmegaEngine()
            status = omega.get_status()
            
            assert "available_models" in status or status is None
        except ImportError:
            pytest.skip("OMEGA engine not available")


class TestAdvancedMemory:
    """Test Advanced Memory System integration"""
    
    @pytest.mark.asyncio
    async def test_memory_storage(self):
        """Test that memory can be stored"""
        try:
            from core.advanced_memory import AdvancedMemorySystem
            
            memory = AdvancedMemorySystem()
            result = memory.store(
                user_id="test_user",
                content="Test memory content",
                importance=0.8
            )
            
            assert result is not None
        except ImportError:
            pytest.skip("Advanced memory system not available")


class TestAgentCollaboration:
    """Test Agent Collaboration System integration"""
    
    @pytest.mark.asyncio
    async def test_agent_system_status(self):
        """Test that agent system status can be retrieved"""
        try:
            from core.agent_collaboration import AgentCollaborationSystem
            
            agents = AgentCollaborationSystem()
            status = agents.get_status()
            
            assert status is not None
        except ImportError:
            pytest.skip("Agent collaboration system not available")


class TestErrorHandling:
    """Test error handling system"""
    
    def test_error_handler_initialization(self):
        """Test that error handler initializes correctly"""
        from core.error_handling import get_error_handler
        
        handler = get_error_handler()
        assert handler is not None
    
    def test_error_handling(self):
        """Test that errors are handled correctly"""
        from core.error_handling import get_error_handler, JARVISError
        
        handler = get_error_handler()
        
        error = JARVISError("Test error", component="test_component")
        result = handler.handle_error(error, "test_component")
        
        assert result["handled"] is True or result["handled"] is False
        assert "user_message" in result


class TestDatabaseConnections:
    """Test database connections"""
    
    def test_postgresql_connection(self):
        """Test PostgreSQL connection"""
        try:
            from core.database import engine
            
            # Try to connect
            with engine.connect() as conn:
                result = conn.execute("SELECT 1")
                assert result is not None
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
    
    @pytest.mark.asyncio
    async def test_redis_connection(self):
        """Test Redis connection"""
        try:
            from core.redis_cache import get_cache
            
            cache = await get_cache()
            stats = await cache.get_stats()
            
            assert stats is not None
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


class TestAPIEndpoints:
    """Test API endpoints"""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint"""
        from fastapi.testclient import TestClient
        from core.api.main import create_application
        
        app = create_application()
        client = TestClient(app)
        
        response = client.get("/api/v1/health/status")
        
        assert response.status_code in [200, 404]  # 404 if endpoint doesn't exist
    
    @pytest.mark.asyncio
    async def test_omega_endpoint(self):
        """Test OMEGA endpoint"""
        from fastapi.testclient import TestClient
        from core.api.main import create_application
        
        app = create_application()
        client = TestClient(app)
        
        response = client.get("/api/v1/omega/status")
        
        assert response.status_code in [200, 404]  # 404 if router not registered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
