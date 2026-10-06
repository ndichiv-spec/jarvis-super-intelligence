"""Factory functions for creating test data with sensible defaults."""

from __future__ import annotations
import uuid
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from infrastructure.knowledge.types import (
    Document, DocumentChunk, DocumentMetadata, SearchQuery, SearchResult,
    LearningRequest, RAGContext, RAGResult, ChunkingStrategy, KnowledgeSource,
    KnowledgeStatus,
)


def _hex_id(length: int = 16) -> str:
    return uuid.uuid4().hex[:length]


class DocumentFactory:
    """Create Document instances with sensible defaults for testing."""

    @staticmethod
    def create(content: Optional[str] = None,
               id: Optional[str] = None,
               metadata: Optional[DocumentMetadata] = None,
               status: KnowledgeStatus = KnowledgeStatus.PENDING,
               user_id: str = "test-user",
               session_id: str = "test-session",
               chunks: Optional[List[DocumentChunk]] = None,
               **overrides) -> Document:
        return Document(
            id=id or _hex_id(),
            content=content or "Test content for knowledge document.",
            metadata=metadata or DocumentMetadata(title="Test Document"),
            status=status,
            user_id=user_id,
            session_id=session_id,
            chunks=chunks or [],
            **overrides,
        )

    @staticmethod
    def create_batch(count: int = 3, **shared_kwargs) -> List[Document]:
        return [
            DocumentFactory.create(
                content=f"Document {i}: Test content.",
                **shared_kwargs,
            )
            for i in range(count)
        ]


class ChunkFactory:
    """Create DocumentChunk instances for testing."""

    @staticmethod
    def create(content: Optional[str] = None,
               id: Optional[str] = None,
               document_id: Optional[str] = None,
               index: int = 0,
               tokens: Optional[int] = None,
               embedding: Optional[List[float]] = None,
               metadata: Optional[DocumentMetadata] = None,
               **overrides) -> DocumentChunk:
        return DocumentChunk(
            id=id or _hex_id(),
            document_id=document_id or _hex_id(),
            content=content or f"Chunk content at index {index}.",
            index=index,
            tokens=tokens,
            embedding=embedding,
            metadata=metadata,
            **overrides,
        )


class PluginManifestFactory:
    """Create plugin manifests for testing plugin subsystem."""

    @staticmethod
    def create(plugin_id: str = "test-plugin",
               name: str = "Test Plugin",
               version: str = "1.0.0",
               **overrides):
        from infrastructure.plugins.types import (
            PluginManifest, PluginPermission, PluginHook,
        )
        return PluginManifest(
            id=plugin_id,
            name=name,
            version=version,
            description=overrides.pop("description", "A test plugin"),
            author=overrides.pop("author", "Test Author"),
            permissions=overrides.pop("permissions", [
                PluginPermission.KNOWLEDGE_READ,
                PluginPermission.MEMORY_READ,
            ]),
            hooks=overrides.pop("hooks", [
                PluginHook.CHAT_BEFORE_RESPOND,
                PluginHook.KNOWLEDGE_BEFORE_RETRIEVE,
            ]),
            **overrides,
        )


class SearchQueryFactory:
    """Create SearchQuery instances for testing retrieval."""

    @staticmethod
    def create(text: str = "test query",
               top_k: int = 5,
               min_score: float = 0.0,
               namespace: str = "default",
               filters: Optional[Dict[str, Any]] = None,
               embedding: Optional[List[float]] = None,
               **overrides) -> SearchQuery:
        return SearchQuery(
            text=text,
            top_k=top_k,
            min_score=min_score,
            namespace=namespace,
            filters=filters or {},
            embedding=embedding,
            **overrides,
        )


class RAGResultFactory:
    """Create RAGResult instances for testing."""

    @staticmethod
    def create(answer: str = "This is a generated answer.",
               chunks: Optional[List[DocumentChunk]] = None,
               query: str = "test query",
               confidence: float = 0.85,
               latency_ms: float = 100.0,
               **overrides) -> RAGResult:
        chunks = chunks or [ChunkFactory.create()]
        ctx = RAGContext(
            query=query,
            chunks=chunks,
            conversation_history=[],
            system_prompt="You are a helpful assistant.",
            max_tokens=1000,
        )
        return RAGResult(
            answer=answer,
            context=ctx,
            confidence=confidence,
            latency_ms=latency_ms,
            **overrides,
        )


class ConfigFactory:
    """Create configuration dictionaries for testing."""

    @staticmethod
    def create(**overrides) -> Dict[str, Any]:
        base = {
            "app_name": "Jarvis Test",
            "debug": True,
            "log_level": "DEBUG",
            "database_url": "sqlite:///test_jarvis.db",
            "redis_url": "redis://localhost:6379/0",
            "secret_key": "test-secret-key-not-for-production",
            "allowed_hosts": ["*"],
            "rate_limit": {"requests_per_minute": 1000},
            "ai": {"provider": "mock", "model": "test-model"},
        }
        base.update(overrides)
        return base

    @staticmethod
    def create_minimal() -> Dict[str, Any]:
        return {
            "app_name": "Jarvis Minimal Test",
            "secret_key": "minimal-test-key",
        }


class UserFactory:
    """Create user-related test data."""

    @staticmethod
    def create(user_id: str = "test-user",
               role: str = "admin",
               permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "id": user_id,
            "username": f"user-{user_id}",
            "role": role,
            "permissions": permissions or ["read", "write", "admin"],
            "enabled": True,
        }

    @staticmethod
    def create_token_payload(user_id: str = "test-user",
                             role: str = "admin") -> Dict[str, Any]:
        return {
            "sub": user_id,
            "role": role,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
