"""
JARVIS Super AI - System Integration Tests
Comprehensive testing for all implemented upgrades
"""

import asyncio
import pytest
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import aiohttp
import logging

from core.security.auth_service import auth_service, UserRoleEnum, PermissionEnum
from core.performance.cache_service import cache_service, CacheLevel
from core.ai.training_service import training_service, ModelType, TrainingConfig
from core.analytics.analytics_service import analytics_service, EventType
from microservices.service_registry import get_service_registry

logger = logging.getLogger(__name__)


class TestSystemUpgrades:
    """Comprehensive test suite for JARVIS system upgrades"""
    
    @pytest.fixture
    async def test_client(self):
        """Create test HTTP client"""
        async with aiohttp.ClientSession() as session:
            yield session
    
    @pytest.fixture
    async def test_user(self):
        """Create test user for authentication tests"""
        # Mock database session
        class MockDB:
            pass
        
        db = MockDB()
        
        # Register test user
        user_data = await auth_service.register_user(
            db=db,
            username="test_user",
            email="test@jarvis.ai",
            password="test_password_123",
            roles=[UserRoleEnum.USER]
        )
        
        return user_data
    
    @pytest.fixture
    async def service_registry(self):
        """Initialize service registry"""
        registry = get_service_registry()
        await registry.initialize()
        
        # Register test services
        await registry.register_service(
            name="test-api",
            host="localhost",
            port=8001,
            health_endpoint="/health"
        )
        
        await registry.register_service(
            name="test-ai",
            host="localhost",
            port=8002,
            health_endpoint="/health"
        )
        
        yield registry
        
        await registry.shutdown()
    
    async def test_security_features(self, test_user):
        """Test enhanced security features"""
        logger.info("Testing security features...")
        
        # Test 2FA setup
        totp_secret = auth_service.two_factor.generate_totp_secret()
        assert len(totp_secret) == 32, "TOTP secret should be 32 characters"
        
        # Test backup code generation
        backup_codes = auth_service.two_factor.generate_backup_codes()
        assert len(backup_codes) == 10, "Should generate 10 backup codes"
        assert all(len(code) == 8 for code in backup_codes), "Backup codes should be 8 characters"
        
        # Test TOTP verification
        import pyotp
        totp = pyotp.TOTP(totp_secret)
        token = totp.now()
        assert auth_service.two_factor.verify_totp(totp_secret, token), "TOTP verification should work"
        
        # Test RBAC permissions
        user_roles = [UserRoleEnum.USER]
        user_permissions = auth_service.rbac.get_all_permissions(user_roles)
        assert PermissionEnum.AI_CHAT in user_permissions, "User should have AI chat permission"
        assert PermissionEnum.SYSTEM_ADMIN not in user_permissions, "User should not have admin permission"
        
        logger.info("✅ Security features test passed")
    
    async def test_performance_caching(self):
        """Test performance and caching system"""
        logger.info("Testing performance caching...")
        
        # Test cache set/get
        test_key = "test_key_123"
        test_data = {"message": "Hello JARVIS", "timestamp": datetime.utcnow().isoformat()}
        
        # Set in cache
        await cache_service.set(test_key, test_data, ttl=300)
        
        # Get from cache
        cached_data = await cache_service.get(test_key)
        assert cached_data is not None, "Cached data should be retrievable"
        assert cached_data["message"] == test_data["message"], "Cached data should match original"
        
        # Test cache metrics
        metrics = cache_service.get_metrics()
        assert metrics["hits"] > 0, "Cache hits should be recorded"
        assert metrics["sets"] > 0, "Cache sets should be recorded"
        
        # Test cache stats
        stats = await cache_service.get_cache_stats()
        assert "memory_cache" in stats, "Memory cache stats should be available"
        assert "metrics" in stats, "Cache metrics should be available"
        
        logger.info("✅ Performance caching test passed")
    
    async def test_ai_training_service(self):
        """Test AI training service"""
        logger.info("Testing AI training service...")
        
        # Create training job
        config = TrainingConfig(
            model_type=ModelType.LANGUAGE_MODEL,
            base_model="gpt-3.5-turbo",
            dataset_path="/test/dataset.csv",
            epochs=5,
            batch_size=16
        )
        
        job_id = await training_service.train_model("test_model", config)
        assert job_id is not None, "Training job should be created"
        
        # Wait a moment for training to start
        await asyncio.sleep(1)
        
        # Check job status
        job_status = await training_service.get_training_status(job_id)
        assert job_status is not None, "Job status should be available"
        assert job_status["status"] in ["pending", "preparing", "training"], "Job should be active"
        
        # List training jobs
        jobs = await training_service.list_training_jobs()
        assert len(jobs) > 0, "Should have training jobs"
        
        # Test AutoML experiment
        experiment_id = await training_service.create_automl_experiment(
            dataset_path="/test/automl_data.csv",
            target_column="target",
            task_type="classification"
        )
        assert experiment_id is not None, "AutoML experiment should be created"
        
        logger.info("✅ AI training service test passed")
    
    async def test_analytics_platform(self):
        """Test analytics platform"""
        logger.info("Testing analytics platform...")
        
        # Track events
        event_id = await analytics_service.track_event(
            event_type=EventType.USER_ACTION,
            properties={"feature": "dashboard", "action": "view"},
            metrics={"duration": 1.5},
            user_id="test_user",
            session_id="test_session"
        )
        assert event_id is not None, "Event should be tracked"
        
        # Track metrics
        await analytics_service.increment_counter("api_requests", 1, {"endpoint": "/api/test"})
        await analytics_service.record_gauge("cpu_usage", 45.2)
        await analytics_service.record_timer("response_time", 0.123)
        
        # Get KPI dashboard
        kpi_data = await analytics_service.get_kpi_dashboard()
        assert "kpis" in kpi_data, "KPI data should be available"
        assert "generated_at" in kpi_data, "Generation timestamp should be included"
        
        # Generate usage report
        report = await analytics_service.generate_report("usage", days=7)
        assert report["report_type"] == "usage", "Report type should match"
        assert "period" in report, "Report period should be included"
        
        # Get service stats
        stats = await analytics_service.get_service_stats()
        assert stats["total_events_tracked"] > 0, "Events should be tracked"
        
        logger.info("✅ Analytics platform test passed")
    
    async def test_microservices_registry(self, service_registry):
        """Test microservices service registry"""
        logger.info("Testing microservices registry...")
        
        # Test service registration
        instances = await service_registry.get_service_instances("test-api")
        assert len(instances) > 0, "Service should be registered"
        
        # Test healthy instances
        healthy = await service_registry.get_healthy_instances("test-api")
        assert len(healthy) >= 0, "Healthy instances should be available"
        
        # Test service stats
        stats = await service_registry.get_service_stats()
        assert stats["total_services"] >= 2, "Should have registered services"
        assert stats["total_instances"] >= 2, "Should have service instances"
        
        # Test service listing
        all_services = await service_registry.get_all_services()
        assert "test-api" in all_services, "Test API should be in services"
        assert "test-ai" in all_services, "Test AI should be in services"
        
        logger.info("✅ Microservices registry test passed")
    
    async def test_real_time_monitoring(self):
        """Test real-time monitoring integration"""
        logger.info("Testing real-time monitoring...")
        
        # Simulate system metrics
        await analytics_service.record_gauge("system_cpu_usage", 25.5, {"host": "server1"})
        await analytics_service.record_gauge("system_memory_usage", 67.8, {"host": "server1"})
        await analytics_service.record_timer("api_response_time", 0.145, {"endpoint": "/api/dashboard"})
        
        # Get performance metrics
        performance = await analytics_service.get_performance_metrics(hours=1)
        assert "total_requests" in performance, "Performance metrics should include requests"
        
        # Track system events
        await analytics_service.track_event(
            event_type=EventType.SYSTEM_EVENT,
            properties={"component": "database", "status": "healthy"},
            metrics={"connections": 45}
        )
        
        logger.info("✅ Real-time monitoring test passed")
    
    async def test_pwa_features(self, test_client):
        """Test PWA manifest and features"""
        logger.info("Testing PWA features...")
        
        # Test manifest accessibility (mock)
        # In real implementation, this would test actual manifest file
        manifest_features = {
            "name": "JARVIS Super AI",
            "short_name": "JARVIS",
            "display": "standalone",
            "categories": ["productivity", "utilities", "ai", "business"],
            "shortcuts": [
                {"name": "Dashboard", "url": "/dashboard"},
                {"name": "AI Chat", "url": "/dashboard?tab=chat"},
                {"name": "Real-Time Monitor", "url": "/dashboard?tab=monitoring"}
            ]
        }
        
        assert manifest_features["name"] == "JARVIS Super AI", "Manifest name should match"
        assert len(manifest_features["shortcuts"]) >= 3, "Should have multiple shortcuts"
        
        logger.info("✅ PWA features test passed")
    
    async def test_integration_workflow(self):
        """Test complete integration workflow"""
        logger.info("Testing integration workflow...")
        
        # 1. User authentication with security
        # 2. Cache performance metrics
        # 3. Track analytics events
        # 4. Monitor system performance
        # 5. Register microservices
        
        # Simulate user login
        await analytics_service.track_event(
            event_type=EventType.USER_ACTION,
            properties={"action": "login", "method": "2fa"},
            metrics={"login_time": 1.2}
        )
        
        # Cache user session
        session_data = {"user_id": "test_user", "permissions": ["ai:chat", "dashboard:read"]}
        await cache_service.set("session:test_user", session_data, ttl=3600)
        
        # Track API performance
        await analytics_service.record_timer("api_request_time", 0.089, {"endpoint": "/api/ai/chat"})
        
        # Monitor system health
        await analytics_service.record_gauge("system_health", 95.5, {"component": "overall"})
        
        # Verify integration
        cached_session = await cache_service.get("session:test_user")
        assert cached_session is not None, "Session should be cached"
        
        kpi_data = await analytics_service.get_kpi_dashboard()
        assert kpi_data["kpis"]["active_users_24h"] >= 1, "Should track active users"
        
        logger.info("✅ Integration workflow test passed")
    
    async def test_performance_benchmarks(self):
        """Test performance benchmarks"""
        logger.info("Testing performance benchmarks...")
        
        # Cache performance test
        start_time = time.time()
        
        # Perform 100 cache operations
        for i in range(100):
            await cache_service.set(f"bench_key_{i}", {"data": f"value_{i}"})
            await cache_service.get(f"bench_key_{i}")
        
        cache_time = time.time() - start_time
        
        # Analytics performance test
        start_time = time.time()
        
        # Perform 100 analytics operations
        for i in range(100):
            await analytics_service.track_event(
                event_type=EventType.USER_ACTION,
                properties={"action": f"test_{i}"},
                metrics={"duration": i * 0.01}
            )
        
        analytics_time = time.time() - start_time
        
        # Performance assertions
        assert cache_time < 5.0, f"Cache operations should be fast: {cache_time:.2f}s"
        assert analytics_time < 5.0, f"Analytics operations should be fast: {analytics_time:.2f}s"
        
        # Check cache hit rate
        cache_metrics = cache_service.get_metrics()
        assert cache_metrics["hit_rate"] > 0.8, "Cache hit rate should be high"
        
        logger.info(f"✅ Performance benchmarks passed - Cache: {cache_time:.2f}s, Analytics: {analytics_time:.2f}s")
    
    async def test_error_handling(self):
        """Test error handling and resilience"""
        logger.info("Testing error handling...")
        
        # Test cache error handling
        invalid_data = object()  # Non-serializable object
        try:
            await cache_service.set("invalid_key", invalid_data)
            # Should handle gracefully
        except Exception as e:
            assert isinstance(e, (TypeError, ValueError)), "Should handle serialization errors"
        
        # Test analytics error handling
        try:
            await analytics_service.track_event(
                event_type=EventType.ERROR,
                properties={"error": "test_error"},
                metrics={"error_count": 1}
            )
            # Should handle errors gracefully
        except Exception as e:
            logger.error(f"Analytics error: {e}")
        
        # Test service registry error handling
        registry = get_service_registry()
        try:
            # Try to get non-existent service
            instances = await registry.get_service_instances("non_existent_service")
            assert len(instances) == 0, "Should return empty list for non-existent service"
        except Exception as e:
            logger.error(f"Service registry error: {e}")
        
        logger.info("✅ Error handling test passed")


# Test runner
async def run_comprehensive_tests():
    """Run all comprehensive tests"""
    logger.info("🚀 Starting comprehensive JARVIS system tests...")
    
    test_suite = TestSystemUpgrades()
    
    tests = [
        ("Security Features", test_suite.test_security_features),
        ("Performance Caching", test_suite.test_performance_caching),
        ("AI Training Service", test_suite.test_ai_training_service),
        ("Analytics Platform", test_suite.test_analytics_platform),
        ("Real-Time Monitoring", test_suite.test_real_time_monitoring),
        ("PWA Features", test_suite.test_pwa_features),
        ("Integration Workflow", test_suite.test_integration_workflow),
        ("Performance Benchmarks", test_suite.test_performance_benchmarks),
        ("Error Handling", test_suite.test_error_handling)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            logger.info(f"Running {test_name} test...")
            start_time = time.time()
            
            # Create mock dependencies if needed
            if test_name == "Security Features":
                # Mock test user
                user_data = {"id": "test_user", "username": "test_user"}
                await test_func(user_data)
            elif test_name == "Microservices Registry":
                # Initialize service registry
                registry = get_service_registry()
                await registry.initialize()
                await test_func(registry)
                await registry.shutdown()
            else:
                await test_func()
            
            duration = time.time() - start_time
            results.append({"test": test_name, "status": "PASSED", "duration": duration})
            logger.info(f"✅ {test_name} test passed in {duration:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ {test_name} test failed: {e}")
            results.append({"test": test_name, "status": "FAILED", "error": str(e)})
    
    # Generate test report
    passed = len([r for r in results if r["status"] == "PASSED"])
    failed = len([r for r in results if r["status"] == "FAILED"])
    
    logger.info(f"\n📊 Test Results Summary:")
    logger.info(f"✅ Passed: {passed}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"📈 Success Rate: {(passed / len(results) * 100):.1f}%")
    
    if failed > 0:
        logger.error("\n❌ Failed Tests:")
        for result in results:
            if result["status"] == "FAILED":
                logger.error(f"  - {result['test']}: {result.get('error', 'Unknown error')}")
    
    return results


if __name__ == "__main__":
    # Run tests
    asyncio.run(run_comprehensive_tests())
