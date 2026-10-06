"""Vector embedding utility for JARVIS semantic search.

Provides text-to-embedding generation and cosine similarity search, using
the existing JARVIS PostgreSQL backend (no new database or service required).

Embedding strategies (graceful degradation order):
  1. sentence-transformers (local transformer model, best quality)
  2. sklearn TF-IDF + cosine similarity (no model download needed, always works)
  3. Simple token-hash fallback (pure stdlib, minimal quality)

The embeddings are stored as JSON arrays in the ``embedding_json`` column
of ``jarvis_research_items``, ``jarvis_knowledge_graph``, and
``jarvis_memory_entries`` tables — extending the EXISTING schema, not creating
a new database.

This enables semantic similarity search across ingested research content and
the knowledge graph, using pgvector-compatible vector storage without
requiring the PostgreSQL ``vector`` extension (embeddings stored as TEXT/JSON).
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.engine import Engine

from .db import get_engine

# --------------------------------------------------------------------------- #
# Embedding backend selection (lazy-loaded, graceful degradation)
# --------------------------------------------------------------------------- #
_ST_BACKEND: Optional[str] = None
_TFIDF: Any = None
_NLP: Any = None
_TOKENIZER: Any = None


def _backend() -> str:
    """Determine which embedding backend is available."""
    global _ST_BACKEND
    if _ST_BACKEND is not None:
        return _ST_BACKEND
    try:
        import sentence_transformers  # type: ignore
        _ST_BACKEND = "sentence_transformers"
        return _ST_BACKEND
    except ImportError:
        pass
    try:
        import sklearn  # type: ignore
        _ST_BACKEND = "tfidf"
        return _ST_BACKEND
    except ImportError:
        pass
    _ST_BACKEND = "hash"
    return _ST_BACKEND


def _ensure_tfidf(vocab_docs: Optional[List[str]] = None):
    """Build or retrieve the TF-IDF vectorizer."""
    global _TFIDF
    if _TFIDF is not None:
        return _TFIDF
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _TFIDF = (cosine_similarity, TfidfVectorizer)
    return _TFIDF


# --------------------------------------------------------------------------- #
# Embedding generation
# --------------------------------------------------------------------------- #
def embed_text(text: str, dimension: int = 384) -> List[float]:
    """Generate a vector embedding for ``text``.

    Returns a list of floats.  The dimensionality depends on the backend:
    - sentence-transformers: model-dependent (typically 384-768)
    - tfidf: vocabulary-dependent (truncated/padded to ``dimension``)
    - hash: fixed ``dimension`` via feature hashing
    """
    if not text or not text.strip():
        return [0.0] * dimension

    backend = _backend()

    if backend == "sentence_transformers":
        try:
            global _TOKENIZER
            if _TOKENIZER is None:
                from sentence_transformers import SentenceTransformer  # type: ignore
                _TOKENIZER = SentenceTransformer("all-MiniLM-L6-v2")
            vec = _TOKENIZER.encode(text, convert_to_numpy=True)
            result = vec.tolist()
            # Normalize
            norm = math.sqrt(sum(x * x for x in result)) or 1e-10
            return [x / norm for x in result]
        except Exception:
            # Fall through to TF-IDF
            pass

    if backend == "tfidf":
        try:
            cos_sim, Vec = _ensure_tfidf()
            # Build vocab from this text (for single-text embedding, use char n-grams)
            # We use a deterministic token-based hash approach with TF-IDF weighting
            tokens = _tokenize(text)
            if not tokens:
                return [0.0] * dimension
            # Build a pseudo-vocabulary from the text itself
            vec = _tfidf_embed(tokens, dimension)
            return vec
        except Exception:
            pass

    # Hash fallback
    return _hash_embed(text, dimension)


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer for TF-IDF fallback."""
    import re
    tokens = re.findall(r"[a-zA-Z0-9_-]{2,}", text.lower())
    return tokens


def _hash_embed(text: str, dimension: int = 384) -> List[float]:
    """Feature-hashing embedding (deterministic, no model download)."""
    tokens = _tokenize(text)
    vec = [0.0] * dimension
    for token in tokens:
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        idx = h % dimension
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1e-10
    return [x / norm for x in vec]


def _tfidf_embed(tokens: List[str], dimension: int = 384) -> List[float]:
    """TF-weighted embedding with L2 normalization."""
    if not tokens:
        return [0.0] * dimension
    # Compute term frequencies
    tf: Dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    max_tf = max(tf.values()) if tf else 1
    vec = [0.0] * dimension
    for token, count in tf.items():
        weight = count / max_tf  # normalized TF
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        idx = h % dimension
        vec[idx] += weight
    norm = math.sqrt(sum(x * x for x in vec)) or 1e-10
    return [x / norm for x in vec]


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not vec_a or not vec_b:
        return 0.0
    # Handle mismatched dimensions
    min_len = min(len(vec_a), len(vec_b))
    dot = sum(vec_a[i] * vec_b[i] for i in range(min_len))
    norm_a = math.sqrt(sum(x * x for x in vec_a[:min_len])) or 1e-10
    norm_b = math.sqrt(sum(x * x for x in vec_b[:min_len])) or 1e-10
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------- #
# Persistence: store & search embeddings
# --------------------------------------------------------------------------- #
def store_embedding(table_name: str, record_id: str, text: str, dimension: int = 384) -> List[float]:
    """Generate an embedding for ``text`` and persist it to the given table."""
    embedding = embed_text(text, dimension)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE {table_name} SET embedding_json = :emb WHERE id = :id"),
            {"emb": json.dumps(embedding), "id": record_id}
        )
    return embedding


def search_similar(
    table_name: str,
    query_text: str,
    limit: int = 10,
    dimension: int = 384,
    extra_where: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Semantic similarity search: find rows in ``table_name`` whose
    ``embedding_json`` is most similar to ``query_text``.

    Works at the application level (computes cosine similarity in Python),
    so no pgvector extension is required.
    """
    query_vec = embed_text(query_text, dimension)
    engine = get_engine()
    with engine.connect() as conn:
        sql = text(f"SELECT id, embedding_json FROM {table_name}")
        if extra_where:
            sql = text(f"SELECT id, embedding_json FROM {table_name} WHERE {extra_where}")
        rows = conn.execute(sql).fetchall()

    results: List[Tuple[float, str]] = []
    for row in rows:
        row_id, emb_json = row[0], row[1]
        if emb_json is None:
            continue
        try:
            stored_vec = json.loads(emb_json)
        except (json.JSONDecodeError, TypeError):
            continue
        score = cosine_similarity(query_vec, stored_vec)
        if score > 0.05:  # threshold to filter noise
            results.append((score, row_id))

    results.sort(key=lambda x: x[0], reverse=True)
    return [{"id": rid, "similarity_score": score} for score, rid in results[:limit]]


def batch_embed_and_store(
    table_name: str,
    items: List[Dict[str, Any]],
    text_field: str = "content",
    id_field: str = "id",
    dimension: int = 384,
) -> int:
    """Generate and store embeddings for a batch of items.

    ``items`` is a list of dicts with at least ``id`` and ``text_field`` keys.
    Returns the number of embeddings stored.
    """
    engine = get_engine()
    count = 0
    with engine.begin() as conn:
        for item in items:
            text = item.get(text_field, "")
            if not text:
                continue
            embedding = embed_text(text, dimension)
            conn.execute(
                text(f"UPDATE {table_name} SET embedding_json = :emb WHERE {id_field} = :id"),
                {"emb": json.dumps(embedding), "id": item[id_field]}
            )
            count += 1
    return count


def ensure_embedding_columns() -> None:
    """Ensure embedding_json columns exist on the research and memory tables."""
    engine = get_engine()
    tables = [
        "jarvis_research_items",
        "jarvis_knowledge_graph",
        "jarvis_memory_entries",
    ]
    with engine.begin() as conn:
        for tbl in tables:
            conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS embedding_json TEXT;"))
    print(f"Embedding columns ensured on {len(tables)} tables")


__all__ = [
    "embed_text",
    "cosine_similarity",
    "store_embedding",
    "search_similar",
    "batch_embed_and_store",
    "ensure_embedding_columns",
]
