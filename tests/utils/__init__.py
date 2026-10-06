"""Testing utilities, mocks, factories, and helpers for Jarvis."""

from .mocks import (
    MockAIProvider,
    MockEmbeddingProvider,
    MockLLMProvider,
    MockPluginContext,
    MockAsyncBackend,
    FakeResponse,
)
from .factories import (
    DocumentFactory,
    ChunkFactory,
    PluginManifestFactory,
    SearchQueryFactory,
    RAGResultFactory,
    ConfigFactory,
    UserFactory,
)
from .assertions import (
    assert_valid_document,
    assert_valid_chunk,
    assert_valid_search_result,
    assert_valid_rag_result,
    assert_subset,
    assert_sorted_by_score,
)
from .helpers import (
    temp_env_vars,
    deterministic_uuid,
    async_collect,
    measure_time,
    poll_until,
)

__all__ = [
    "MockAIProvider", "MockEmbeddingProvider", "MockLLMProvider",
    "MockPluginContext", "MockAsyncBackend", "FakeResponse",
    "DocumentFactory", "ChunkFactory", "PluginManifestFactory",
    "SearchQueryFactory", "RAGResultFactory", "ConfigFactory", "UserFactory",
    "assert_valid_document", "assert_valid_chunk", "assert_valid_search_result",
    "assert_valid_rag_result", "assert_subset", "assert_sorted_by_score",
    "temp_env_vars", "deterministic_uuid", "async_collect",
    "measure_time", "poll_until",
]
