"""Custom test assertions for knowledge and infrastructure types."""

from typing import Dict, List, Any, Optional
from infrastructure.knowledge.types import (
    Document, DocumentChunk, SearchResult, RAGResult,
)


def assert_valid_document(doc: Document, check_chunks: bool = True):
    """Validate a Document instance has all required fields."""
    assert doc.id, "Document must have an id"
    assert doc.content, "Document must have content"
    assert doc.metadata is not None, "Document must have metadata"
    assert doc.status is not None, "Document must have a status"
    if check_chunks:
        for chunk in doc.chunks:
            assert_valid_chunk(chunk)
            assert chunk.document_id == doc.id, "Chunk must reference its document"


def assert_valid_chunk(chunk: DocumentChunk):
    """Validate a DocumentChunk instance."""
    assert chunk.id, "Chunk must have an id"
    assert chunk.document_id, "Chunk must have a document_id"
    assert chunk.content, "Chunk must have content"
    assert chunk.index >= 0, "Chunk index must be non-negative"
    if chunk.embedding is not None:
        assert len(chunk.embedding) > 0, "Embedding must not be empty"


def assert_valid_search_result(result: SearchResult):
    """Validate a SearchResult instance."""
    assert result.chunk is not None, "SearchResult must have a chunk"
    assert result.score >= 0.0, "SearchResult score must be non-negative"
    assert result.score <= 1.0, "SearchResult score must not exceed 1.0"
    assert_valid_chunk(result.chunk)


def assert_valid_rag_result(result: RAGResult):
    """Validate a RAGResult instance."""
    assert result.answer, "RAGResult must have an answer"
    assert result.context is not None, "RAGResult must have context"
    assert result.latency_ms >= 0, "Latency must be non-negative"
    assert 0 <= result.confidence <= 1.0, "Confidence must be in [0, 1]"


def assert_subset(subset: Dict[str, Any], superset: Dict[str, Any]):
    """Assert that all key-value pairs in subset exist in superset."""
    for key, value in subset.items():
        assert key in superset, f"Key '{key}' not found in superset"
        assert superset[key] == value, (
            f"Key '{key}': expected {value!r}, got {superset[key]!r}"
        )


def assert_sorted_by_score(results: List[SearchResult], descending: bool = True):
    """Assert that search results are sorted by score."""
    for i in range(len(results) - 1):
        if descending:
            assert results[i].score >= results[i + 1].score, (
                f"Results not sorted descending at index {i}: "
                f"{results[i].score} < {results[i + 1].score}"
            )
        else:
            assert results[i].score <= results[i + 1].score, (
                f"Results not sorted ascending at index {i}: "
                f"{results[i].score} > {results[i + 1].score}"
            )
