"""Offline evaluation of hybrid research retrieval behavior."""
from __future__ import annotations

import json

from jarvis_backend.embeddings import cosine_similarity
from jarvis_backend.research.autonomous_research import (
    _rank_research_rows,
    _semantic_search,
)


def test_hybrid_retrieval_fuses_vector_and_keyword_rankings():
    rows = [
        (
            "semantic", "Neural graph indexing", "Learned latent representations",
            json.dumps([1.0, 0.0]),
        ),
        (
            "keyword", "Quantum entanglement", "A primer on quantum entanglement",
            json.dumps([0.0, 1.0]),
        ),
        (
            "hybrid", "Quantum entanglement models", "Vector methods for quantum systems",
            json.dumps([0.8, 0.2]),
        ),
        (
            "wrong-dimension", "Quantum entanglement history", "Historical overview",
            json.dumps([1.0]),
        ),
        ("invalid-vector", "Quantum entanglement notes", "Notes without a valid embedding", "{"),
    ]

    results = _rank_research_rows(
        rows, "quantum entanglement", [1.0, 0.0], cosine_similarity, limit=10
    )
    by_id = {result["id"]: result for result in results}

    assert set(by_id) == {"semantic", "keyword", "hybrid", "wrong-dimension", "invalid-vector"}
    assert by_id["hybrid"]["match_type"] == "hybrid"
    assert by_id["semantic"]["match_type"] == "semantic"
    assert by_id["keyword"]["match_type"] == "keyword"
    assert by_id["wrong-dimension"]["match_type"] == "keyword"
    assert by_id["invalid-vector"]["match_type"] == "keyword"
    assert results[0]["id"] == "hybrid"
    assert {"keyword", "hybrid"} <= {result["id"] for result in results[:3]}


def test_hybrid_retrieval_handles_unavailable_vectors_and_limits():
    rows = [
        ("a", "Cellular senescence", "Aging and cellular growth", None),
        ("b", "Unrelated topic", "No matching words", None),
    ]
    results = _rank_research_rows(rows, "cellular aging", None, None, limit=1)

    assert len(results) == 1
    assert results[0]["id"] == "a"
    assert results[0]["match_type"] == "keyword"


def test_semantic_search_rejects_untrusted_table_names_and_empty_queries():
    import pytest

    with pytest.raises(ValueError, match="Unsupported research search table"):
        _semantic_search("jarvis_research_items; DROP TABLE users", "quantum")
    assert _semantic_search("jarvis_research_items", "   ") == []
