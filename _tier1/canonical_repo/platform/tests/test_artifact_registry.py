"""
Tests for the durable Artifact Registry (Phase 2).

Verifies:
- Artifact metadata storage and retrieval
- Artifact type tracking
- Provenance chain preservation
- Usage tracking for artifacts
"""

import pytest
import time

from infrastructure.artifact_registry import (
    ArtifactRegistry,
    ArtifactInfo,
    ArtifactType,
    ArtifactStatus,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry singleton before each test."""
    ArtifactRegistry.reset_instance()
    yield
    ArtifactRegistry.reset_instance()


class TestArtifactRegistry:
    """Test artifact registry operations."""
    
    def test_register_artifact(self):
        """Registering an artifact should persist it."""
        registry = ArtifactRegistry.get_instance()
        
        artifact = ArtifactInfo(
            id="test-artifact-123",
            artifact_id="model-weights-v1",
            artifact_type="model_weights",
            storage_uri="s3://bucket/weights/v1.bin",
            size_bytes=1024 * 1024 * 1024,  # 1GB
            checksum_sha256="abc123",
        )
        
        result = registry.register(artifact)
        
        assert result.artifact_id == "model-weights-v1"
        assert result.artifact_type == "model_weights"
        assert result.size_bytes == 1024 * 1024 * 1024
    
    def test_get_artifact(self):
        """Should retrieve artifact by artifact_id."""
        registry = ArtifactRegistry.get_instance()
        
        artifact = ArtifactInfo(
            id="test-artifact-456",
            artifact_id="lora-adapter-v2",
            artifact_type="lora_adapter",
            storage_uri="/local/path/adapter.bin",
            parent_artifact_id="base-model-v1",
        )
        registry.register(artifact)
        
        retrieved = registry.get("lora-adapter-v2")
        assert retrieved is not None
        assert retrieved.id == "test-artifact-456"
        assert retrieved.parent_artifact_id == "base-model-v1"
    
    def test_record_access(self):
        """Should record artifact access."""
        registry = ArtifactRegistry.get_instance()
        
        artifact = ArtifactInfo(
            id="test-artifact-access",
            artifact_id="model-to-track",
            artifact_type="model_weights",
            storage_uri="s3://bucket/model.bin",
        )
        registry.register(artifact)
        
        result = registry.record_access("model-to-track")
        assert result is True
        
        updated = registry.get("model-to-track")
        assert updated.access_count >= 1
    
    def test_update_status(self):
        """Should update artifact status."""
        registry = ArtifactRegistry.get_instance()
        
        artifact = ArtifactInfo(
            id="test-artifact-status",
            artifact_id="model-with-status",
            artifact_type="model_weights",
            storage_uri="s3://bucket/model.bin",
            status="available",
        )
        registry.register(artifact)
        
        result = registry.update_status("model-with-status", "verified")
        assert result is True
        
        updated = registry.get("model-with-status")
        assert updated.status == "verified"
    
    def test_link_to_model(self):
        """Should link artifact to a model deployment."""
        registry = ArtifactRegistry.get_instance()
        
        artifact = ArtifactInfo(
            id="test-artifact-link",
            artifact_id="weights-for-deployment",
            artifact_type="model_weights",
            storage_uri="s3://bucket/model.bin",
        )
        registry.register(artifact)
        
        result = registry.link_to_model("weights-for-deployment", "gpt-4-turbo")
        assert result is True
        
        linked = registry.get("weights-for-deployment")
        assert linked.deployed_model_id == "gpt-4-turbo"
    
    def test_list_artifacts_by_model(self):
        """Should list artifacts for a specific model."""
        registry = ArtifactRegistry.get_instance()
        
        artifacts = [
            ArtifactInfo(
                id=f"artifact-{i}",
                artifact_id=f"artifacts-for-model-{i}",
                artifact_type="model_weights",
                storage_uri=f"s3://bucket/model-{i}.bin",
                source_model_id="gpt-4-turbo",
            )
            for i in range(3)
        ]
        
        for a in artifacts:
            registry.register(a)
        
        results = registry.get_artifacts_by_model("gpt-4-turbo")
        assert len(results) == 3
    
    def test_get_parent_chain(self):
        """Should retrieve parent chain for artifacts."""
        registry = ArtifactRegistry.get_instance()
        
        # Base model
        base = ArtifactInfo(
            id="base-model",
            artifact_id="base-model-v1",
            artifact_type="model_weights",
            storage_uri="s3://bucket/base.bin",
        )
        registry.register(base)
        
        # LoRA adapter that depends on base
        lora = ArtifactInfo(
            id="lora-adapter",
            artifact_id="lora-sft-adapter",
            artifact_type="lora_adapter",
            storage_uri="s3://bucket/lora.bin",
            parent_artifact_id="base-model-v1",
        )
        registry.register(lora)
        
        chain = registry.get_parent_chain("lora-sft-adapter")
        
        assert len(chain) == 2
        assert chain[0].artifact_id == "lora-sft-adapter"
        assert chain[1].artifact_id == "base-model-v1"


class TestArtifactTypes:
    """Test artifact type enumeration."""
    
    def test_all_types_exist(self):
        """All artifact types should be defined."""
        types = [t.value for t in ArtifactType]
        
        assert "model_weights" in types
        assert "lora_adapter" in types
        assert "checkpoint" in types
        assert "train_dataset" in types  # Note: enum uses 'train_dataset', not 'training_dataset'


class TestArtifactDataclass:
    """Test ArtifactInfo dataclass."""
    
    def test_from_record(self):
        """Should create ArtifactInfo from record."""
        from infrastructure.artifact_registry import ArtifactRecord
        
        class FakeRecord:
            id = "test-artifact-id"
            artifact_id = "test-artifact"
            artifact_type = "model_weights"
            status = "available"
            parent_artifact_id = None
            base_model_id = None
            source_model_id = "test-model"
            training_run_id = ""
            dataset_id = ""
            storage_uri = "s3://test.bin"
            storage_type = "s3"
            size_bytes = 1024
            checksum_sha256 = "abc123"
            checksum_type = "sha256"
            name = "Test Artifact"
            description = "A test artifact"
            version = "1.0"
            revision = ""
            architecture = "transformer"
            parameters = 1000000000
            context_window = 8192
            open_weights = True
            training_args = {}
            training_output = {}
            evaluation_results = {}
            access_count = 5
            first_accessed = time.time()
            last_accessed = time.time()
            deployed_model_id = ""
            deployment_time = None
            artifact_data = {}
            provenance_chain = []
            created_at = time.time()
            updated_at = time.time()
        
        info = ArtifactInfo.from_record(FakeRecord())
        
        assert info.id == "test-artifact-id"
        assert info.artifact_id == "test-artifact"
        assert info.artifact_type == "model_weights"
        assert info.access_count == 5