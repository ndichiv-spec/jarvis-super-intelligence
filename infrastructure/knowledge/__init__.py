"""
Knowledge management and adaptive intelligence subsystem.

Provides:
  - Centralized KnowledgeStore with CRUD and pluggable backends
  - Document ingestion pipeline with chunking strategies
  - Embedding index manager with pluggable providers
  - Hybrid search (text + vector) with reranking
  - Conversation context management with token-aware windowing
  - Controlled learning workflow with user approval gates
  - Knowledge validation and confidence scoring
  - RAG pipeline for retrieval-augmented generation
  - Configurable retention and cleanup policies
  - Memory bridge for existing subsystem compatibility
  - Full observability for all operations

Safety:
  - No content enters the knowledge base without validation
  - Learning requires user approval (configurable)
  - All operations are audited and observable
  - Rollback capability for any learned content
  - Learning can be paused globally
"""

from .store import KnowledgeStore
from .ingest import KnowledgeIngestor, ChunkConfig
from .index import IndexManager
from .retrieval import KnowledgeRetriever, RetrievalConfig
from .context import ContextManager, ContextWindowConfig
from .learning import LearningController, LearningConfig
from .validation import KnowledgeValidator, ValidationResult
from .rag import RAGPipeline, RAGConfig
from .retention import RetentionManager, RetentionPolicy, CleanupMode
from .memory_bridge import MemoryBridge, MemoryRecord
from .observability import KnowledgeObservability, KnowledgeEvent
from .types import (
    Document, DocumentChunk, DocumentMetadata, SearchQuery, SearchResult,
    LearningRequest, RAGContext, RAGResult, ChunkingStrategy,
    KnowledgeSource, KnowledgeStatus,
)

__all__ = [
    "KnowledgeStore", "KnowledgeIngestor", "ChunkConfig",
    "IndexManager", "KnowledgeRetriever", "RetrievalConfig",
    "ContextManager", "ContextWindowConfig",
    "LearningController", "LearningConfig",
    "KnowledgeValidator", "ValidationResult",
    "RAGPipeline", "RAGConfig",
    "RetentionManager", "RetentionPolicy", "CleanupMode",
    "MemoryBridge", "MemoryRecord",
    "KnowledgeObservability", "KnowledgeEvent",
    "Document", "DocumentChunk", "DocumentMetadata",
    "SearchQuery", "SearchResult",
    "LearningRequest", "RAGContext", "RAGResult",
    "ChunkingStrategy", "KnowledgeSource", "KnowledgeStatus",
]
