"""
Knowledge retrieval with hybrid search, reranking, and filtering.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from .types import SearchQuery, SearchResult, DocumentChunk, Document
from .store import KnowledgeStore

logger = logging.getLogger(__name__)

RerankerFunction = Callable[[List[SearchResult], str], List[SearchResult]]


@dataclass
class RetrievalConfig:
    top_k: int = 10
    min_score: float = 0.3
    text_weight: float = 0.3
    embedding_weight: float = 0.7
    enable_rerank: bool = False
    enable_hybrid: bool = True


class KnowledgeRetriever:
    """
    Retrieves knowledge using hybrid search with optional reranking.

    Supports:
      - Text search (keyword/TF)
      - Vector search (cosine similarity)
      - Hybrid search (combined scores)
      - Reranking (cross-encoder style)
      - Metadata filtering
      - Result deduplication
    """

    def __init__(self, store: KnowledgeStore, config: Optional[RetrievalConfig] = None):
        self.store = store
        self.config = config or RetrievalConfig()
        self._rerankers: List[RerankerFunction] = []

    def add_reranker(self, fn: RerankerFunction):
        self._rerankers.append(fn)

    def retrieve(self, query: SearchQuery) -> List[SearchResult]:
        """Main retrieval entry point."""
        cfg = self.config
        query.top_k = query.top_k or cfg.top_k
        query.min_score = query.min_score or cfg.min_score

        if cfg.enable_hybrid and query.embedding:
            results = self.store.hybrid_search(
                query,
                text_weight=cfg.text_weight,
                embedding_weight=cfg.embedding_weight,
            )
        elif query.embedding:
            results = self.store.search_by_embedding(query)
        else:
            results = self.store.search(query)

        # Apply rerankers
        for reranker in self._rerankers:
            try:
                results = reranker(results, query.text)
            except Exception as e:
                logger.warning(f"Reranker failed: {e}")

        # Apply filters
        if query.filters:
            results = self._apply_filters(results, query.filters)

        return results[:query.top_k]

    def retrieve_by_ids(self, chunk_ids: List[str]) -> List[DocumentChunk]:
        chunks = []
        for cid in chunk_ids:
            chunk = self.store.get_chunk(cid)
            if chunk:
                chunks.append(chunk)
        return chunks

    def retrieve_document_chunks(self, doc_id: str) -> List[DocumentChunk]:
        return self.store.get_document_chunks(doc_id)

    def retrieve_context(self, query: SearchQuery, max_tokens: int = 3000) -> str:
        """Retrieve and assemble context string for RAG."""
        results = self.retrieve(query)
        chunks = [r.chunk for r in results]

        context_parts = []
        token_budget = max_tokens

        for chunk in chunks:
            tokens = chunk.tokens or len(chunk.content) // 4
            if tokens > token_budget:
                break
            context_parts.append(chunk.content)
            token_budget -= tokens

        return "\n\n".join(context_parts)

    def deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        seen: set = set()
        unique: List[SearchResult] = []
        for r in results:
            key = r.chunk.content[:100]
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    def _apply_filters(self, results: List[SearchResult],
                       filters: Dict[str, Any]) -> List[SearchResult]:
        filtered = []
        for r in results:
            match = True
            chunk_meta = r.chunk.metadata
            for key, value in filters.items():
                attr = getattr(chunk_meta, key, None)
                if attr is not None:
                    if isinstance(value, (list, tuple)):
                        if attr not in value:
                            match = False
                    elif attr != value:
                        match = False
                if not match:
                    break
            if match:
                filtered.append(r)
        return filtered
