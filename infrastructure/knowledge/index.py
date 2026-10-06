"""
Index manager for embeddings and vector search.

Provides:
  - Embedding generation (with pluggable provider)
  - Vector index maintenance
  - Batch indexing operations
"""

from __future__ import annotations
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field

from .types import Document, DocumentChunk, SearchQuery, SearchResult

logger = logging.getLogger(__name__)

EmbeddingFunction = Callable[[List[str]], List[List[float]]]


@dataclass
class IndexStats:
    total_chunks: int = 0
    indexed_chunks: int = 0
    last_indexed: Optional[float] = None
    dimensions: int = 0


class IndexManager:
    """
    Manages embedding generation and vector indexing.

    Uses a pluggable embedding function so any provider can be used:
      - Local: sentence-transformers
      - API: OpenAI, Gemini embeddings
      - Mock: for testing
    """

    def __init__(self, embed_fn: Optional[EmbeddingFunction] = None,
                 dimensions: int = 768):
        self._embed_fn = embed_fn or self._mock_embed
        self.dimensions = dimensions
        self.stats = IndexStats(dimensions=dimensions)

    def set_embedding_function(self, fn: EmbeddingFunction):
        self._embed_fn = fn

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self._embed_fn(texts)

    def embed_single(self, text: str) -> List[float]:
        return self._embed_fn([text])[0]

    def index_document(self, doc: Document) -> Document:
        """Generate embeddings for all chunks in a document."""
        if not doc.chunks:
            logger.warning(f"No chunks to index for document {doc.id}")
            return doc

        texts = [c.content for c in doc.chunks]
        try:
            embeddings = self.embed(texts)
            for i, chunk in enumerate(doc.chunks):
                if i < len(embeddings):
                    chunk.embedding = embeddings[i]
                    self.stats.indexed_chunks += 1

            # Document-level embedding (mean of all chunk embeddings)
            if embeddings:
                mean_emb = [sum(dim) / len(embeddings) for dim in zip(*embeddings)]
                doc.embedding = mean_emb

            self.stats.total_chunks = len(doc.chunks)
            self.stats.last_indexed = time.time()
            logger.info(f"Indexed document {doc.id}: {len(doc.chunks)} chunks")
        except Exception as e:
            logger.error(f"Failed to index document {doc.id}: {e}")

        return doc

    def index_batch(self, documents: List[Document]) -> List[Document]:
        return [self.index_document(doc) for doc in documents]

    @staticmethod
    def _mock_embed(texts: List[str]) -> List[List[float]]:
        """Deterministic mock embedding for testing."""
        import hashlib
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode())
            vec = [int(h.hexdigest()[i:i+2], 16) / 255.0 for i in range(0, 32, 2)]
            vec = vec * 24  # extend to 384 dims
            results.append(vec[:384])
        return results

    def snapshot(self) -> Dict[str, Any]:
        return {
            "dimensions": self.dimensions,
            "total_chunks": self.stats.total_chunks,
            "indexed_chunks": self.stats.indexed_chunks,
            "last_indexed": self.stats.last_indexed,
        }
