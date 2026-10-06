"""
Tests for the durable Model Registry (Phase 1).

Verifies:
- Model storage and retrieval
- Lifecycle state transitions
- Search and discovery
- Idempotency of operations
"""

import pytest
import time

from infrastructure.model_registry import (
    ModelRegistry,
    ModelInfo,
    ModelLifecycleState,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry singleton before each test."""
    ModelRegistry.reset_instance()
    yield
    ModelRegistry.reset_instance()


class TestModelRegistry:
    """Test model registry operations."""
    
    def test_register_returns_persisted_model(self):
        """Registering a model should persist it."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="test-123",
            model_id="test/model",
            provider_id="test-provider",
            display_name="Test Model",
            description="A test model",
            lifecycle_type="jarvis_base",
            lifecycle_status="registered",
            capabilities=["text-generation", "chat"],
            context_window=8192,
            open_weights=True,
        )
        
        result = registry.register(model)
        
        assert result.model_id == "test/model"
        assert result.provider_id == "test-provider"
    
    def test_register_upserts_existing(self):
        """Registering an existing model_id should update it."""
        registry = ModelRegistry.get_instance()
        
        # Register first time
        model1 = ModelInfo(
            id="test-123",
            model_id="test/model",
            provider_id="test-provider",
            display_name="Test Model V1",
            description="Original description",
            lifecycle_status="registered",
        )
        registry.register(model1)
        
        # Update with same model_id
        model2 = ModelInfo(
            id="test-123",
            model_id="test/model",
            provider_id="test-provider",
            display_name="Test Model V2",
            description="Updated description",
            capabilities=["text-generation", "chat", "embedding"],
            lifecycle_status="registered",
        )
        registry.register(model2)
        
        # Verify update
        retrieved = registry.get("test/model")
        assert retrieved.display_name == "Test Model V2"
        assert "embedding" in retrieved.capabilities
    
    def test_get_by_model_id(self):
        """Should retrieve model by model_id."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="test-456",
            model_id="getbyid/model",
            provider_id="provider",
            lifecycle_status="registered",
        )
        registry.register(model)
        
        retrieved = registry.get("getbyid/model")
        assert retrieved is not None
        assert retrieved.id == "test-456"
    
    def test_get_by_internal_id(self):
        """Should retrieve model by internal id."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="internal-id-789",
            model_id="internal/model",
            provider_id="provider",
            lifecycle_status="registered",
        )
        registry.register(model)
        
        retrieved = registry.get_by_id("internal-id-789")
        assert retrieved is not None
        assert retrieved.model_id == "internal/model"
    
    def test_get_nonexistent_returns_none(self):
        """Should return None for nonexistent model."""
        registry = ModelRegistry.get_instance()
        
        assert registry.get("nonexistent/model") is None
        assert registry.get_by_id("nonexistent-id") is None
    
    def test_list_models_with_filters(self):
        """Should filter models correctly."""
        registry = ModelRegistry.get_instance()
        
        # Register multiple models
        models = [
            ModelInfo(
                id=f"model-{i}",
                model_id=f"provider/model-{i}",
                provider_id="provider-a",
                lifecycle_status="approved" if i < 2 else "evaluating",
                capabilities=["chat"] if i % 2 else ["embedding"],
            )
            for i in range(4)
        ]
        
        for m in models:
            registry.register(m)
        
        # Filter by provider
        by_provider = registry.list_models(provider_id="provider-a")
        assert len(by_provider) == 4
        
        # Filter by status
        by_status = registry.list_models(lifecycle_status="approved")
        assert len(by_status) == 2
        
        # Filter by capability
        by_cap = registry.list_models(capabilities=["chat"])
        assert len(by_cap) == 2


class TestLifecycleManagement:
    """Test lifecycle state transitions."""
    
    def test_update_lifecycle(self):
        """Should update lifecycle status."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="lifecycle-test",
            model_id="lifecycle/model",
            provider_id="provider",
            lifecycle_status="registered",
        )
        registry.register(model)
        
        result = registry.update_lifecycle("lifecycle/model", "evaluating", "Test transition")
        assert result is True
        
        updated = registry.get("lifecycle/model")
        assert updated.lifecycle_status == "evaluating"
    
    def test_update_lifecycle_nonexistent_model(self):
        """Should return False for nonexistent model."""
        registry = ModelRegistry.get_instance()
        
        result = registry.update_lifecycle("nonexistent", "approved")
        assert result is False
    
    def test_lifecycle_history_is_preserved(self):
        """Should maintain history of lifecycle changes."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="history-test",
            model_id="history/model",
            provider_id="provider",
            lifecycle_status="registered",
            history=[],
        )
        registry.register(model)
        
        registry.update_lifecycle("history/model", "evaluating", "First transition")
        registry.update_lifecycle("history/model", "approved", "Second transition")
        
        result = registry.get("history/model")
        assert len(result.history) == 2


class TestEvaluationRecording:
    """Test evaluation result recording."""
    
    def test_record_evaluation(self):
        """Should record evaluation results."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="eval-test",
            model_id="eval/model",
            provider_id="provider",
            lifecycle_status="candidate",
        )
        registry.register(model)
        
        results = {
            "accuracy": 0.95,
            "latency_ms": 120,
            "tokens_per_second": 85.5,
        }
        
        registry.record_evaluation("eval/model", results, "test_evaluator")
        
        updated = registry.get("eval/model")
        assert "test_evaluator" in updated.evaluation_results
        assert updated.evaluation_results["test_evaluator"]["results"]["accuracy"] == 0.95
    
    def test_record_evaluation_multiple_evaluators(self):
        """Should handle multiple evaluation entries."""
        registry = ModelRegistry.get_instance()
        
        model = ModelInfo(
            id="multi-eval",
            model_id="multi/model",
            provider_id="provider",
            lifecycle_status="evaluating",
        )
        registry.register(model)
        
        registry.record_evaluation("multi/model", {"test": 1}, "evaluator_a")
        registry.record_evaluation("multi/model", {"test": 2}, "evaluator_b")
        
        updated = registry.get("multi/model")
        assert "evaluator_a" in updated.evaluation_results
        assert "evaluator_b" in updated.evaluation_results


class TestSearch:
    """Test model search functionality."""
    
    def test_search_by_model_id(self):
        """Should search by model_id."""
        registry = ModelRegistry.get_instance()
        
        registry.register(ModelInfo(
            id="search-1",
            model_id="openai/gpt-4",
            provider_id="openai",
            lifecycle_status="approved",
        ))
        
        results = registry.search("gpt-4")
        assert len(results) >= 1
        assert any(r.model_id == "openai/gpt-4" for r in results)
    
    def test_search_by_display_name(self):
        """Should search by display_name."""
        registry = ModelRegistry.get_instance()
        
        registry.register(ModelInfo(
            id="search-2",
            model_id="provider/model-x",
            provider_id="provider",
            display_name="My Special Model",
            lifecycle_status="registered",
        ))
        
        results = registry.search("Special")
        assert len(results) >= 1
    
    def test_search_limit_respected(self):
        """Should respect search limit."""
        registry = ModelRegistry.get_instance()
        
        # Register multiple models
        for i in range(10):
            registry.register(ModelInfo(
                id=f"search-limit-{i}",
                model_id=f"provider/model-{i}",
                provider_id="provider",
                lifecycle_status="registered",
            ))
        
        results = registry.search("model", limit=5)
        assert len(results) <= 5


class TestModelInfoDataclass:
    """Test ModelInfo dataclass."""
    
    def test_from_record(self):
        """Should create ModelInfo from record."""
        from infrastructure.model_registry import ModelRecord
        from sqlalchemy import String, Column
        from sqlalchemy.orm import declarative_base
        from dataclasses import dataclass
        
        # Create a proper dataclass that mimics ModelRecord
        @dataclass
        class FakeRecord:
            id: str = "test-id"
            model_id: str = "test/model-id"
            provider_id: str = "test-provider"
            display_name: str = "Display"
            description: str = "Description"
            lifecycle_type: str = "jarvis_base"
            lifecycle_status: str = "approved"
            model_family: str = "test-family"
            parent_model_id: str = None
            revision: str = None
            capabilities: list = None
            modalities: list = None
            context_window: int = 0
            max_output_tokens: int = 0
            architecture: str = ""
            parameters: int = None
            open_weights: bool = False
            deployment_type: str = "local"
            endpoint_reference: str = ""
            artifact_reference: str = ""
            checksum: str = ""
            source: str = ""
            training_run_id: str = ""
            dataset_id: str = ""
            evaluation_results: dict = None
            model_data: dict = None
            provenance_chain: dict = None
            history: list = None
            created_at: float = 0.0
            updated_at: float = 0.0
            
            def __post_init__(self):
                if self.capabilities is None:
                    self.capabilities = []
                if self.modalities is None:
                    self.modalities = ["text"]
                if self.evaluation_results is None:
                    self.evaluation_results = {}
                if self.model_data is None:
                    self.model_data = {}
                if self.provenance_chain is None:
                    self.provenance_chain = {}
                if self.history is None:
                    self.history = []
        
        info = ModelInfo.from_record(FakeRecord())
        
        assert info.id == "test-id"
        assert info.model_id == "test/model-id"
        assert info.capabilities == []
        assert info.metadata == {}


class TestLifecycleStates:
    """Test lifecycle state enumeration."""
    
    def test_all_states_exist(self):
        """All lifecycle states should be defined."""
        states = [s.value for s in ModelLifecycleState]
        
        assert "discovered" in states
        assert "registered" in states
        assert "candidate" in states
        assert "evaluating" in states
        assert "approved" in states
        assert "deployed" in states
        assert "deprecated" in states
        assert "retired" in states