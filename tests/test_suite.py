#!/usr/bin/env python3
"""
JARVIS Automated Testing Suite
==============================
Comprehensive testing suite for JARVIS system components.
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import JARVIS components
from core.agents.advanced_agent_orchestration import (
    advanced_orchestrator,
    AgentProfile,
    AgentCapability,
    AgentPriority,
    TaskContext
)
from auth import (
    create_user,
    authenticate_user,
    create_access_token,
    decode_token,
    get_password_hash,
    verify_password
)
from rate_limiter import RateLimiter, RateLimitStats
from monitoring import MonitoringSystem, LogLevel

# Test fixtures
@pytest.fixture
def sample_agent():
    """Create a sample agent for testing"""
    return AgentProfile(
        id="test_agent",
        name="Test Agent",
        capabilities={AgentCapability.QUANTUM_REASONING, AgentCapability.NEURAL_SYNTHESIS},
        priority=AgentPriority.HIGH,
        knowledge_domains={"physics", "mathematics"}
    )

@pytest.fixture
def sample_task():
    """Create a sample task for testing"""
    return TaskContext(
        id="test_task",
        description="Test task description",
        required_capabilities={AgentCapability.QUANTUM_REASONING},
        priority=AgentPriority.MEDIUM,
        complexity=0.5,
        metadata={"test": True}
    )

@pytest.fixture
def monitoring_system():
    """Create a monitoring system instance"""
    return MonitoringSystem()

# Agent Orchestration Tests
class TestAgentOrchestration:
    """Test agent orchestration system"""
    
    @pytest.mark.asyncio
    async def test_register_agent(self, sample_agent):
        """Test agent registration"""
        agent_id = await advanced_orchestrator.register_agent(sample_agent)
        assert agent_id == "test_agent"
        assert agent_id in advanced_orchestrator.agents
    
    @pytest.mark.asyncio
    async def test_get_agent(self, sample_agent):
        """Test getting an agent"""
        await advanced_orchestrator.register_agent(sample_agent)
        agent = advanced_orchestrator.agents.get("test_agent")
        assert agent is not None
        assert agent.name == "Test Agent"
    
    @pytest.mark.asyncio
    async def test_assign_task(self, sample_agent, sample_task):
        """Test task assignment"""
        await advanced_orchestrator.register_agent(sample_agent)
        result = await advanced_orchestrator.assign_task(sample_task)
        assert result is not None
        assert "assigned_agent" in result or "status" in result
    
    @pytest.mark.asyncio
    async def test_system_status(self):
        """Test system status retrieval"""
        status = await advanced_orchestrator.get_system_status()
        assert status is not None
        assert "total_agents" in status
        assert "active_agents" in status

# Authentication Tests
class TestAuthentication:
    """Test authentication system"""
    
    def test_password_hashing(self):
        """Test password hashing"""
        password = "test_password"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)
    
    def test_user_creation(self):
        """Test user creation"""
        from auth import UserCreate
        user_data = UserCreate(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        user = create_user(user_data)
        assert user["username"] == "testuser"
        assert user["email"] == "test@example.com"
        assert user["is_active"] is True
    
    def test_user_authentication(self):
        """Test user authentication"""
        from auth import UserCreate
        user_data = UserCreate(
            username="authuser",
            email="auth@example.com",
            password="authpass123"
        )
        create_user(user_data)
        
        # Test successful authentication
        authenticated = authenticate_user("authuser", "authpass123")
        assert authenticated is not None
        assert authenticated["username"] == "authuser"
        
        # Test failed authentication
        failed = authenticate_user("authuser", "wrongpassword")
        assert failed is None
    
    def test_token_creation(self):
        """Test JWT token creation"""
        token = create_access_token(
            data={"sub": "testuser", "scopes": ["read", "write"]}
        )
        assert token is not None
        assert isinstance(token, str)
    
    def test_token_decoding(self):
        """Test JWT token decoding"""
        token = create_access_token(
            data={"sub": "testuser", "scopes": ["read", "write"]}
        )
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["sub"] == "testuser"
        assert "read" in decoded["scopes"]

# Rate Limiting Tests
class TestRateLimiting:
    """Test rate limiting system"""
    
    def test_rate_limiter_creation(self):
        """Test rate limiter creation"""
        limiter = RateLimiter(
            requests_per_minute=10,
            requests_per_hour=100,
            requests_per_day=1000
        )
        assert limiter.requests_per_minute == 10
        assert limiter.requests_per_hour == 100
        assert limiter.requests_per_day == 1000
    
    def test_rate_limit_check(self):
        """Test rate limit checking"""
        limiter = RateLimiter(requests_per_minute=5)
        
        # First 5 requests should be allowed
        for i in range(5):
            allowed, message = limiter.check_rate_limit("test_client")
            assert allowed is True
        
        # 6th request should be blocked
        allowed, message = limiter.check_rate_limit("test_client")
        assert allowed is False
        assert "Rate limit exceeded" in message
    
    def test_rate_limit_stats(self):
        """Test rate limit statistics"""
        limiter = RateLimiter(requests_per_minute=5)
        
        # Make some requests
        for i in range(3):
            limiter.check_rate_limit("stats_client")
        
        stats = RateLimitStats.get_client_stats("stats_client")
        assert stats["total_requests"] == 3
        assert stats["requests_per_minute"] == 3

# Monitoring Tests
class TestMonitoring:
    """Test monitoring system"""
    
    def test_logger_creation(self, monitoring_system):
        """Test logger creation"""
        assert monitoring_system.logger is not None
        assert monitoring_system.logger.name == "jarvis"
    
    def test_logging(self, monitoring_system):
        """Test logging functionality"""
        monitoring_system.logger.info("TestComponent", "Test message")
        logs = monitoring_system.logger.get_logs(limit=10)
        assert len(logs) > 0
        assert logs[-1]["message"] == "Test message"
    
    def test_metric_recording(self, monitoring_system):
        """Test metric recording"""
        monitoring_system.metrics.record_metric("test_metric", 42.0, "units")
        metric = monitoring_system.metrics.get_latest_metric("test_metric")
        assert metric is not None
        assert metric["value"] == 42.0
        assert metric["unit"] == "units"
    
    def test_alert_creation(self, monitoring_system):
        """Test alert creation"""
        from monitoring import AlertLevel
        alert = monitoring_system.alerts.create_alert(
            level=AlertLevel.WARNING,
            title="Test Alert",
            message="This is a test alert"
        )
        assert alert is not None
        assert alert.title == "Test Alert"
        assert alert.resolved is False
    
    def test_system_status(self, monitoring_system):
        """Test system status retrieval"""
        monitoring_system.log_system_metrics(
            cpu_usage=50.0,
            memory_usage=60.0,
            disk_usage=40.0
        )
        status = monitoring_system.get_system_status()
        assert status is not None
        assert "status" in status
        assert "metrics" in status

# Integration Tests
class TestIntegration:
    """Integration tests for JARVIS system"""
    
    @pytest.mark.asyncio
    async def test_full_agent_workflow(self):
        """Test complete agent workflow"""
        # Create agent
        agent = AgentProfile(
            id="integration_agent",
            name="Integration Test Agent",
            capabilities={AgentCapability.QUANTUM_REASONING},
            priority=AgentPriority.HIGH,
            knowledge_domains={"physics"}
        )
        
        agent_id = await advanced_orchestrator.register_agent(agent)
        assert agent_id == "integration_agent"
        
        # Create and assign task
        task = TaskContext(
            id="integration_task",
            description="Integration test task",
            required_capabilities={AgentCapability.QUANTUM_REASONING},
            priority=AgentPriority.MEDIUM,
            complexity=0.5
        )
        
        result = await advanced_orchestrator.assign_task(task)
        assert result is not None
        
        # Check system status
        status = await advanced_orchestrator.get_system_status()
        assert status["total_agents"] >= 1
    
    def test_monitoring_with_metrics(self, monitoring_system):
        """Test monitoring with metric recording"""
        # Record metrics
        monitoring_system.log_system_metrics(
            cpu_usage=75.0,
            memory_usage=80.0,
            disk_usage=45.0,
            error_rate=0.05
        )
        
        # Check dashboard
        dashboard = monitoring_system.get_monitoring_dashboard()
        assert dashboard is not None
        assert "system_status" in dashboard
        assert "metrics" in dashboard

# Performance Tests
class TestPerformance:
    """Performance tests for JARVIS system"""
    
    @pytest.mark.asyncio
    async def test_agent_registration_performance(self):
        """Test agent registration performance"""
        import time
        
        start_time = time.time()
        
        for i in range(10):
            agent = AgentProfile(
                id=f"perf_agent_{i}",
                name=f"Performance Agent {i}",
                capabilities={AgentCapability.QUANTUM_REASONING},
                priority=AgentPriority.MEDIUM,
                knowledge_domains={"test"}
            )
            await advanced_orchestrator.register_agent(agent)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete 10 registrations in less than 1 second
        assert duration < 1.0
    
    def test_rate_limiting_performance(self):
        """Test rate limiting performance"""
        import time
        
        limiter = RateLimiter(requests_per_minute=1000)
        
        start_time = time.time()
        
        for i in range(100):
            limiter.check_rate_limit(f"client_{i % 10}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete 100 checks in less than 0.1 seconds
        assert duration < 0.1

# Test runner
def run_tests():
    """Run all tests"""
    print("Running JARVIS Automated Test Suite...")
    print("=" * 60)
    
    # Run pytest
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--color=yes"
    ])
    
    print("=" * 60)
    if exit_code == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    
    return exit_code

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
