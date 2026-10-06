"""
Knowledge management types: documents, chunks, sources, embeddings.
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class KnowledgeSource(Enum):
    """Origin of knowledge entries."""
    DOCUMENT = "document"
    CONVERSATION = "conversation"
    USER_INPUT = "user_input"
    AGENT_OUTPUT = "agent_output"
    EXTERNAL_API = "external_api"
    WEB_SCRAPE = "web_scrape"
    CODEBASE = "codebase"
    PLUGIN = "plugin"
    MANUAL = "manual"


class KnowledgeStatus(Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    ACTIVE = "active"
    ARCHIVED = "archived"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ChunkingStrategy(Enum):
    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"


@dataclass
class DocumentMetadata:
    title: str = ""
    author: str = ""
    source: KnowledgeSource = KnowledgeSource.DOCUMENT
    source_url: str = ""
    content_type: str = "text/plain"
    language: str = "en"
    tags: List[str] = field(default_factory=list)
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "source": self.source.value,
            "source_url": self.source_url,
            "content_type": self.content_type,
            "language": self.language,
            "tags": self.tags,
            "custom": self.custom,
        }


@dataclass
class DocumentChunk:
    """A single chunk of a larger document."""
    id: str
    document_id: str
    content: str
    index: int
    embedding: Optional[List[float]] = None
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    tokens: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "content": self.content[:500],
            "index": self.index,
            "has_embedding": self.embedding is not None,
            "metadata": self.metadata.to_dict(),
            "tokens": self.tokens,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
        }


@dataclass
class Document:
    """A knowledge document."""
    id: str
    content: str
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    chunks: List[DocumentChunk] = field(default_factory=list)
    status: KnowledgeStatus = KnowledgeStatus.PENDING
    embedding: Optional[List[float]] = None
    confidence: float = 0.0
    user_id: str = ""
    session_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content_preview": self.content[:300],
            "content_length": len(self.content),
            "chunk_count": len(self.chunks),
            "metadata": self.metadata.to_dict(),
            "status": self.status.value,
            "confidence": round(self.confidence, 4),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "updated_at": datetime.fromtimestamp(self.updated_at, tz=timezone.utc).isoformat(),
            "expires_at": datetime.fromtimestamp(self.expires_at, tz=timezone.utc).isoformat()
                if self.expires_at else None,
        }


@dataclass
class SearchQuery:
    text: str
    embedding: Optional[List[float]] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    top_k: int = 10
    min_score: float = 0.0
    namespace: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text[:200],
            "has_embedding": self.embedding is not None,
            "filters": self.filters,
            "top_k": self.top_k,
            "min_score": self.min_score,
            "namespace": self.namespace,
        }


@dataclass
class SearchResult:
    chunk: DocumentChunk
    score: float
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk": self.chunk.to_dict(),
            "score": round(self.score, 4),
            "rank": self.rank,
        }


@dataclass
class LearningRequest:
    """A controlled learning request requiring user approval."""
    id: str
    source: KnowledgeSource
    content: str
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    user_id: str = ""
    requires_approval: bool = True
    approved: Optional[bool] = None
    confidence: float = 0.0
    validation_notes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    reviewed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.value,
            "content_preview": self.content[:200],
            "requires_approval": self.requires_approval,
            "approved": self.approved,
            "confidence": round(self.confidence, 4),
            "validation_notes": self.validation_notes,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "reviewed_at": datetime.fromtimestamp(self.reviewed_at, tz=timezone.utc).isoformat()
                if self.reviewed_at else None,
        }


# RAG types

@dataclass
class RAGContext:
    """Context assembled for RAG."""
    query: str
    chunks: List[DocumentChunk] = field(default_factory=list)
    documents: List[Document] = field(default_factory=list)
    conversation_history: List[str] = field(default_factory=list)
    system_prompt: str = ""
    max_tokens: int = 4096

    def assembled_prompt(self) -> str:
        parts = [self.system_prompt] if self.system_prompt else []
        if self.chunks:
            context = "\n\n".join(
                f"[Source {i+1}]: {c.content}"
                for i, c in enumerate(self.chunks[:10])
            )
            parts.append(f"Context:\n{context}")
        parts.append(f"Query: {self.query}")
        return "\n\n".join(parts)

    def token_estimate(self) -> int:
        """Rough token estimate (4 chars per token)."""
        return len(self.assembled_prompt()) // 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query[:200],
            "chunks": len(self.chunks),
            "documents": len(self.documents),
            "history_turns": len(self.conversation_history),
            "estimated_tokens": self.token_estimate(),
        }


@dataclass
class RAGResult:
    answer: str
    context: RAGContext
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer_preview": self.answer[:300],
            "provider": self.provider,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 2),
            "confidence": round(self.confidence, 4),
            "context": self.context.to_dict(),
        }
