"""Fixtures for infrastructure subsystem tests."""

from __future__ import annotations
import pytest
from typing import Dict, List, Optional, Any, AsyncGenerator

from tests.utils.mocks import (
    MockAIProvider, MockEmbeddingProvider, MockLLMProvider, MockPluginContext,
)


# ── Mock Provider Fixtures ─────────────────────────────────

@pytest.fixture
def mock_ai_provider() -> MockAIProvider:
    return MockAIProvider()


@pytest.fixture
def mock_ai_provider_slow() -> MockAIProvider:
    return MockAIProvider(latency=0.05)


@pytest.fixture
def mock_ai_provider_failing() -> MockAIProvider:
    return MockAIProvider(fail_on=["trigger_error"])


@pytest.fixture
def mock_embedding_provider() -> MockEmbeddingProvider:
    return MockEmbeddingProvider(dimension=384)


@pytest.fixture
def mock_llm_provider() -> MockLLMProvider:
    return MockLLMProvider(
        responses={
            "hello": "Hello! How can I help you?",
            "capital of France": "The capital of France is Paris.",
        },
        default_response="I don't have a specific answer for that.",
    )


@pytest.fixture
def mock_plugin_context() -> MockPluginContext:
    return MockPluginContext(plugin_id="test-plugin")


# ── Knowledge Store Fixtures ───────────────────────────────

@pytest.fixture
def empty_knowledge_store():
    from infrastructure.knowledge import KnowledgeStore
    return KnowledgeStore(namespace="test")


@pytest.fixture
def populated_knowledge_store(empty_knowledge_store):
    """Store with pre-loaded documents and chunks."""
    store = empty_knowledge_store
    doc1 = store.create_document(
        "The quick brown fox jumps over the lazy dog.",
        status=KnowledgeStatus.ACTIVE,  # noqa: F821
    )
    doc2 = store.create_document(
        "Machine learning is a subset of artificial intelligence.",
        status=KnowledgeStatus.ACTIVE,
    )
    doc3 = store.create_document(
        "Python is a popular programming language for data science.",
        status=KnowledgeStatus.ACTIVE,
    )

    from infrastructure.knowledge import KnowledgeIngestor, ChunkConfig
    from infrastructure.knowledge.types import ChunkingStrategy
    ingestor = KnowledgeIngestor(
        ChunkConfig(chunk_size=100, min_chunk_size=10, strategy=ChunkingStrategy.FIXED_SIZE)
    )
    for doc in [doc1, doc2, doc3]:
        chunks = ingestor.ingest(doc.content).chunks
        for c in chunks:
            c.document_id = doc.id
            store.add_chunk(c)
    return store


@pytest.fixture
def knowledge_ingestor():
    from infrastructure.knowledge import KnowledgeIngestor, ChunkConfig
    from infrastructure.knowledge.types import ChunkingStrategy
    return KnowledgeIngestor(
        ChunkConfig(chunk_size=100, min_chunk_size=10, strategy=ChunkingStrategy.FIXED_SIZE)
    )


@pytest.fixture
def knowledge_retriever(populated_knowledge_store):
    from infrastructure.knowledge import KnowledgeRetriever, RetrievalConfig
    return KnowledgeRetriever(
        populated_knowledge_store,
        config=RetrievalConfig(top_k=5, min_score=0.0),
    )


@pytest.fixture
def context_manager():
    from infrastructure.knowledge import ContextManager, ContextWindowConfig
    return ContextManager(ContextWindowConfig(max_tokens=2000, max_turns=20))


@pytest.fixture
def rag_pipeline(knowledge_retriever, context_manager):
    from infrastructure.knowledge import RAGPipeline
    return RAGPipeline(knowledge_retriever, context_manager)


@pytest.fixture
def learning_controller(populated_knowledge_store):
    from infrastructure.knowledge import LearningController, LearningConfig
    return LearningController(populated_knowledge_store, LearningConfig(require_approval=True))


@pytest.fixture
def retention_manager(populated_knowledge_store):
    from infrastructure.knowledge import RetentionManager
    return RetentionManager(populated_knowledge_store)


@pytest.fixture
def memory_bridge(populated_knowledge_store):
    from infrastructure.knowledge import MemoryBridge
    return MemoryBridge(populated_knowledge_store)


# ── Plugin Fixtures ────────────────────────────────────────

@pytest.fixture
def plugin_registry():
    from infrastructure.plugins import PluginRegistry
    return PluginRegistry()


@pytest.fixture
def plugin_lifecycle():
    from infrastructure.plugins import PluginLifecycleManager
    return PluginLifecycleManager()


@pytest.fixture
def hook_system():
    from infrastructure.plugins import HookSystem
    return HookSystem()


@pytest.fixture
def dependency_resolver():
    from infrastructure.plugins import DependencyResolver
    return DependencyResolver()


@pytest.fixture
def plugin_loader(tmp_path):
    from infrastructure.plugins import PluginLoader
    return PluginLoader(plugin_dir=str(tmp_path / "plugins"))


# ── Security Fixtures ──────────────────────────────────────

@pytest.fixture
def jwt_authenticator():
    from infrastructure.security import JWTAuthenticator
    return JWTAuthenticator(secret_key="test-secret-key-32-chars-long-for-hmac!")


@pytest.fixture
def rate_limiter():
    from infrastructure.security import RateLimiter
    return RateLimiter()


@pytest.fixture
def api_key_manager():
    from infrastructure.security import ApiKeyManager
    return ApiKeyManager()


# ── Resilience Fixtures ────────────────────────────────────

@pytest.fixture
def circuit_breaker():
    from infrastructure.resilience import CircuitBreaker
    return CircuitBreaker(name="test-breaker", failure_threshold=3, recovery_timeout=0.5)


@pytest.fixture
def retry_strategy():
    from infrastructure.resilience import RetryStrategy
    return RetryStrategy(max_retries=3, base_delay=0.01, max_delay=0.1)


@pytest.fixture
def fallback_chain():
    from infrastructure.resilience import FallbackChain
    return FallbackChain()


# ── Error Handler Fixtures ─────────────────────────────────

@pytest.fixture
def error_tracker():
    from infrastructure.errors import ErrorTracker
    return ErrorTracker()


# ── Sandbox Fixtures ───────────────────────────────────────

@pytest.fixture
def sandbox_executor():
    from infrastructure.sandbox import SandboxExecutor, ExecutionPolicy
    policy = ExecutionPolicy(default_timeout=5.0, allowed_commands=["echo", "python", "python3", "ls"])
    return SandboxExecutor(policy=policy)


@pytest.fixture
def policy_engine():
    from infrastructure.sandbox import PolicyEngine
    return PolicyEngine()


# ── Observability Fixtures ─────────────────────────────────

@pytest.fixture
def metrics_collector():
    from infrastructure.observability import MetricsCollector
    return MetricsCollector()


@pytest.fixture
def tracer():
    from infrastructure.observability import Tracer
    return Tracer(service_name="test-service")


# ── Logging Fixtures ───────────────────────────────────────

@pytest.fixture
def structured_logger():
    from infrastructure.logsys import StructuredLogger
    return StructuredLogger(name="test-logger")


# ── Config Fixtures ────────────────────────────────────────

@pytest.fixture
def config_loader():
    from infrastructure.config import ConfigLoader
    return ConfigLoader()


# ── Vault Fixtures ─────────────────────────────────────────

@pytest.fixture
def secrets_manager():
    from infrastructure.vault import SecretsManager
    from infrastructure.vault.manager import EnvBackend
    return SecretsManager(backends=[EnvBackend(prefix="TEST_")])


# ── Health Fixtures ────────────────────────────────────────

@pytest.fixture
def health_checker():
    from infrastructure.health import HealthChecker
    return HealthChecker(app_name="test-app", version="1.0.0", environment="test")


# ── Startup Fixtures ───────────────────────────────────────

@pytest.fixture
def startup_validator():
    from infrastructure.startup import StartupValidator
    return StartupValidator()

# Import KnowledgeStatus for fixtures above
from infrastructure.knowledge.types import KnowledgeStatus
