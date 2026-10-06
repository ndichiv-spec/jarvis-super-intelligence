"""
Centralized knowledge store.

Provides CRUD operations for documents, chunks, and metadata.
In-memory implementation with pluggable backend interface for DB/vector store.
"""

from __future__ import annotations
import time
import uuid
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

from .types import (
    Document, DocumentChunk, DocumentMetadata, KnowledgeStatus,
    SearchQuery, SearchResult, KnowledgeSource,
)

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """
    Centralized knowledge storage.

    Design:
      - In-memory default (suitable for development/testing)
      - Backend-agnostic: swap with Postgres, Redis, or vector DB
      - All operations are observable (callbacks for monitoring)
    """

    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self._documents: Dict[str, Document] = {}
        self._chunks: Dict[str, DocumentChunk] = {}
        self._observers: List[Callable[[str, str, Any], None]] = []

    def add_observer(self, fn: Callable[[str, str, Any], None]):
        """Observe operations: fn(operation, doc_id, data)."""
        self._observers.append(fn)

    def _notify(self, operation: str, doc_id: str, data: Any = None):
        for fn in self._observers:
            try:
                fn(operation, doc_id, data)
            except Exception:
                pass

    # ── Document CRUD ──────────────────────────────────────

    def create_document(self, content: str, metadata: Optional[DocumentMetadata] = None,
                        user_id: str = "", session_id: str = "",
                        status: KnowledgeStatus = KnowledgeStatus.PENDING,
                        ttl: Optional[float] = None) -> Document:
        doc_id = uuid.uuid4().hex[:16]
        now = time.time()
        doc = Document(
            id=doc_id,
            content=content,
            metadata=metadata or DocumentMetadata(),
            status=status,
            user_id=user_id,
            session_id=session_id,
            created_at=now,
            updated_at=now,
            expires_at=(now + ttl) if ttl else None,
        )
        self._documents[doc_id] = doc
        self._notify("create", doc_id, doc.to_dict())
        logger.info(f"Document created: {doc_id} ({len(content)} chars)")
        return doc

    def get_document(self, doc_id: str) -> Optional[Document]:
        doc = self._documents.get(doc_id)
        if doc and doc.is_expired:
            self.delete_document(doc_id)
            return None
        return doc

    def update_document(self, doc_id: str, **kwargs) -> Optional[Document]:
        doc = self._documents.get(doc_id)
        if not doc:
            return None
        for key, value in kwargs.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
        doc.updated_at = time.time()
        self._notify("update", doc_id, kwargs)
        return doc

    def delete_document(self, doc_id: str) -> bool:
        doc = self._documents.pop(doc_id, None)
        if doc:
            for chunk in doc.chunks:
                self._chunks.pop(chunk.id, None)
            self._notify("delete", doc_id)
            logger.info(f"Document deleted: {doc_id}")
            return True
        return False

    def list_documents(self, status: Optional[KnowledgeStatus] = None,
                       source: Optional[KnowledgeSource] = None,
                       user_id: str = "",
                       limit: int = 100) -> List[Document]:
        docs = list(self._documents.values())
        if status:
            docs = [d for d in docs if d.status == status]
        if source:
            docs = [d for d in docs if d.metadata.source == source]
        if user_id:
            docs = [d for d in docs if d.user_id == user_id]
        docs = [d for d in docs if not d.is_expired]
        docs.sort(key=lambda d: d.updated_at, reverse=True)
        return docs[:limit]

    def count(self, status: Optional[KnowledgeStatus] = None) -> int:
        if status:
            return sum(1 for d in self._documents.values()
                       if d.status == status and not d.is_expired)
        return sum(1 for d in self._documents.values() if not d.is_expired)

    # ── Chunk CRUD ─────────────────────────────────────────

    def add_chunk(self, chunk: DocumentChunk):
        self._chunks[chunk.id] = chunk
        doc = self._documents.get(chunk.document_id)
        if doc:
            doc.chunks.append(chunk)
            doc.updated_at = time.time()

    def get_chunk(self, chunk_id: str) -> Optional[DocumentChunk]:
        return self._chunks.get(chunk_id)

    def get_document_chunks(self, doc_id: str) -> List[DocumentChunk]:
        doc = self._documents.get(doc_id)
        if doc:
            return sorted(doc.chunks, key=lambda c: c.index)
        return []

    def delete_chunk(self, chunk_id: str) -> bool:
        chunk = self._chunks.pop(chunk_id, None)
        if chunk:
            doc = self._documents.get(chunk.document_id)
            if doc:
                doc.chunks = [c for c in doc.chunks if c.id != chunk_id]
            return True
        return False

    # ── Search (in-memory fallback) ─────────────────────────

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Basic text search. Override with vector search when embeddings available."""
        query_text = query.text.lower()
        results: List[SearchResult] = []

        for chunk in self._chunks.values():
            if query.namespace != "default":
                doc = self._documents.get(chunk.document_id)
                if not doc or doc.metadata.source.value != query.namespace:
                    continue

            score = self._text_relevance(chunk.content, query_text)
            if score >= query.min_score:
                results.append(SearchResult(chunk=chunk, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(results[:query.top_k]):
            r.rank = i + 1

        self._notify("search", "", {"query": query_text, "results": len(results)})
        return results[:query.top_k]

    def search_by_embedding(self, query: SearchQuery) -> List[SearchResult]:
        """Cosine similarity search on embeddings. Requires embeddings on chunks."""
        if not query.embedding:
            return self.search(query)

        results: List[SearchResult] = []
        for chunk in self._chunks.values():
            if not chunk.embedding:
                continue
            score = self._cosine_similarity(query.embedding, chunk.embedding)
            if score >= query.min_score:
                results.append(SearchResult(chunk=chunk, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(results[:query.top_k]):
            r.rank = i + 1
        return results[:query.top_k]

    def hybrid_search(self, query: SearchQuery, text_weight: float = 0.3,
                      embedding_weight: float = 0.7) -> List[SearchResult]:
        """Combine text and embedding scores."""
        if not query.embedding:
            return self.search(query)

        text_results = {r.chunk.id: r.score for r in self.search(query)}
        embedding_results = {r.chunk.id: r.score for r in self.search_by_embedding(query)}

        all_ids = set(text_results) | set(embedding_results)
        combined: List[SearchResult] = []
        for cid in all_ids:
            t_score = text_results.get(cid, 0.0)
            e_score = embedding_results.get(cid, 0.0)
            combined.append(SearchResult(
                chunk=self._chunks[cid],
                score=text_weight * t_score + embedding_weight * e_score,
            ))

        combined.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(combined[:query.top_k]):
            r.rank = i + 1
        return combined[:query.top_k]

    @staticmethod
    def _text_relevance(content: str, query: str) -> float:
        """Simple TF-ish relevance score."""
        content_lower = content.lower()
        words = query.split()
        if not words:
            return 0.0
        matches = sum(1 for w in words if w in content_lower)
        return matches / len(words)

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── Snapshot ────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "documents": len(self._documents),
            "chunks": len(self._chunks),
            "by_status": {
                s.value: self.count(s) for s in KnowledgeStatus
            },
            "active": self.count(KnowledgeStatus.ACTIVE),
            "pending": self.count(KnowledgeStatus.PENDING),
            "expired": self.count(KnowledgeStatus.EXPIRED),
        }

    def clear(self):
        self._documents.clear()
        self._chunks.clear()
        self._notify("clear", "")
