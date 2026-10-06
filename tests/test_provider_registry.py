"""
Tests for the durable Provider Registry (Phase 2).

Verifies:
- Provider metadata storage and retrieval
- Health state tracking
- Supported models tracking
- Provider enable/disable functionality
"""

import pytest
import time

from infrastructure.provider_registry import (
    ProviderRegistry,
    ProviderInfo,
    ProviderHealthState,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry singleton before each test."""
    ProviderRegistry.reset_instance()
    yield
    ProviderRegistry.reset_instance()


class TestProviderRegistry:
    """Test provider registry operations."""
    
    def test_register_provider(self):
        """Registering a provider should persist it."""
        registry = ProviderRegistry.get_instance()
        
        provider = ProviderInfo(
            id="test-provider-123",
            provider_id="test-provider",
            provider_name="Test Provider",
            adapter="test",
            capabilities=["chat", "completion"],
            enabled=True,
        )
        
        result = registry.register(provider)
        
        assert result.provider_id == "test-provider"
        assert result.provider_name == "Test Provider"
    
    def test_get_provider(self):
        """Should retrieve provider by provider_id."""
        registry = ProviderRegistry.get_instance()
        
        provider = ProviderInfo(
            id="test-provider-456",
            provider_id="test-provider-get",
            provider_name="Test Provider Get",
            adapter="test",
            capabilities=["chat"],
        )
        registry.register(provider)
        
        retrieved = registry.get("test-provider-get")
        assert retrieved is not None
        assert retrieved.id == "test-provider-456"
    
    def test_update_health(self):
        """Should update provider health state."""
        registry = ProviderRegistry.get_instance()
        
        provider = ProviderInfo(
            id="test-provider-789",
            provider_id="test-provider-health",
            provider_name="Test Provider Health",
            adapter="test",
            enabled=True,
            health_state="healthy",
        )
        registry.register(provider)
        
        result = registry.update_health(
            "test-provider-health",
            "offline",
            "Connection timeout",
        )
        assert result is True
        
        updated = registry.get("test-provider-health")
        assert updated.health_state == "offline"
        assert "timeout" in updated.health_check_message.lower()
    
    def test_enable_disable_provider(self):
        """Should enable/disable providers."""
        registry = ProviderRegistry.get_instance()
        
        provider = ProviderInfo(
            id="test-provider-disable",
            provider_id="test-provider-disable",
            provider_name="Test Provider Disable",
            adapter="test",
            enabled=True,
        )
        registry.register(provider)
        
        # Disable
        result = registry.disable_provider("test-provider-disable", "Testing disable")
        assert result is True
        
        updated = registry.get("test-provider-disable")
        assert updated.enabled is False
        
        # Re-enable
        result = registry.enable_provider("test-provider-disable")
        assert result is True
        
        enabled = registry.get("test-provider-disable")
        assert enabled.enabled is True
    
    def test_list_with_filters(self):
        """Should filter providers correctly."""
        registry = ProviderRegistry.get_instance()
        
        # Register multiple providers
        providers = [
            ProviderInfo(
                id=f"provider-{i}",
                provider_id=f"test-provider-{i}",
                provider_name=f"Test Provider {i}",
                adapter="test",
                enabled=i % 2 == 0,  # Half enabled
                health_state="healthy" if i < 2 else "offline",
                capabilities=["chat"] if i % 2 == 0 else [],
            )
            for i in range(4)
        ]
        
        for p in providers:
            registry.register(p)
        
        # Filter by enabled
        enabled = registry.list_providers(enabled=True)
        assert len(enabled) == 2
        
        # Filter by health state
        healthy = registry.list_providers(health_state="healthy")
        assert len(healthy) == 2
    
    def test_add_supported_model(self):
        """Should add models to supported list."""
        registry = ProviderRegistry.get_instance()
        
        provider = ProviderInfo(
            id="test-provider-models",
            provider_id="test-provider-models",
            provider_name="Test Provider Models",
            adapter="test",
            enabled=True,
            supported_models=[],
        )
        registry.register(provider)
        
        result = registry.add_supported_model("test-provider-models", "model-1")
        assert result is True
        
        updated = registry.get("test-provider-models")
        assert "model-1" in updated.supported_models


class TestProviderInfoDataclass:
    """Test ProviderInfo dataclass."""
    
    def test_from_record(self):
        """Should create ProviderInfo from record."""
        from infrastructure.provider_registry import ProviderRecord
        
        class FakeRecord:
            id = "test-provider-id"
            provider_id = "test-provider"
            provider_name = "Test Provider"
            adapter = "test"
            enabled = True
            capabilities = ["chat"]
            supported_modalities = ["text"]
            environment = "development"
            endpoint_type = "api"
            endpoint_url = "https://example.com"
            region = "us-east-1"
            version = "1.0"
            health_state = "healthy"
            last_health_check = time.time()
            health_check_message = "All good"
            verification_enabled = True
            verification_state = "verified"
            last_verification = time.time()
            verification_results = {}
            supported_models = ["model-1"]
            provider_data = {"key": "value"}
            created_at = time.time()
            updated_at = time.time()
        
        info = ProviderInfo.from_record(FakeRecord())
        
        assert info.id == "test-provider-id"
        assert info.provider_id == "test-provider"
        assert info.capabilities == ["chat"]
        assert info.enabled is True


class TestBootstrapProviders:
    """Test provider bootstrap functionality."""
    
    def test_bootstrap_creates_known_providers(self):
        """Bootstrap should create default providers."""
        from infrastructure.provider_registry import bootstrap_providers
        
        providers = bootstrap_providers()
        
        assert "openai" in providers
        assert "anthropic" in providers
        assert "google" in providers
        assert "silverwing" in providers


class TestProviderHealthStates:
    """Test provider health state enumeration."""
    
    def test_all_states_exist(self):
        """All health states should be defined."""
        states = [s.value for s in ProviderHealthState]
        
        assert "unknown" in states
        assert "healthy" in states
        assert "degraded" in states
        assert "offline" in states
        assert "rate_limited" in states
        assert "auth_error" in states
        assert "temporarily_disabled" in states