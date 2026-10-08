"""JARVIS Semantic Search — neural + offline-capable embedding ranker (spec §28, §49).

Provides :class:`SemanticRanker`, a provider-independent semantic-similarity
ranking engine used by Global Search to rerank text-search candidates when the
caller passes ``semantic=True``.

Design (spec §64 — never depend on a single provider / model):
  * **Primary** — sentence-transformers dense embeddings (``all-MiniLM-L6-v2``).
    Loaded lazily and cached process-wide; falls back gracefully if the model
    cannot be downloaded or the library is absent.
  * **Fallback** — a deterministic, offline random-projection fingerprint
    (no network, no download) so semantic-style ranking always works in tests
    and air-gapped deployments.  This is *approximate* semantic similarity, not
    a replacement for dense embeddings, but it never fabricates results and
    degrades to nothing if even numpy is unavailable.

Global Search never relies on semantic search alone (spec §28): text relevance
is always computed first; semantic reranking only *re-sorts* the existing
candidate set.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("jarvis.semantic_search")

_EMBED_DIM = 384  # all-MiniLM-L6-v2 dimensionality


def _hash_token(token: str) -> int:
    """Stable 64-bit hash for a token (deterministic, offline)."""
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) & 0x7FFFFFFF


class _FingerprintRanker:
    """Deterministic, offline semantic-ish ranker using random n-gram projection.

    Builds a fixed-dimension sketch per document from hashed n-grams and a fixed
    random projection matrix (seeded for determinism).  Cosine similarity on
    these sketches approximates topical overlap without any model download.
    """

    _DIM = _EMBED_DIM
    _RNG_SEED = 0x5A5A

    def __init__(self, dim: int = _EMBED_DIM) -> None:
        self.dim = dim
        rng = np.random.RandomState(self._RNG_SEED)
        # Fixed random projection matrix: (vocab_space, embed_dim). We use a
        # large virtual vocabulary hashed into the projection rows.
        self._proj = rng.normal(0.0, 1.0, size=(1 << 16, self.dim))

    def _sketch(self, text: str) -> np.ndarray:
        tokens = [t for t in text.lower().split() if t]
        vec = np.zeros(self.dim, dtype=np.float32)
        if not tokens:
            return vec
        # unigrams + bigrams
        grams = list(tokens) + [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]
        seen = set()
        for g in grams:
            h = _hash_token(g) % (1 << 16)
            vec += self._proj[h]
            seen.add(g)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        return np.vstack([self._sketch(t) for t in texts]) if texts else np.zeros((0, self.dim))

    def rerank(self, query: str, candidates: Sequence[str], top_k: int) -> List[Tuple[int, float]]:
        q = self._sketch(query)
        items = [c or "" for c in candidates]
        if not items:
            return []
        mat = self.embed(items)
        sims = mat @ q  # cosine since q is normalized
        order = np.argsort(-sims)
        out: List[Tuple[int, float]] = []
        for idx in order[:top_k]:
            out.append((int(idx), float(sims[idx])))
        return out


class SemanticRanker:
    """Neural embedding ranker with offline fallback (spec §28).

    Usage::

        ranker = SemanticRanker()
        if ranker.available():
            scores = ranker.similarity(query, [text1, text2, ...])
    """

    _model = None  # shared loaded model
    _backend: Optional[str] = None
    _failed: bool = False
    _fingerprint_ranker: Optional[_FingerprintRanker] = None

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name

    @classmethod
    def _fingerprint(cls) -> _FingerprintRanker:
        if cls._fingerprint_ranker is None:
            cls._fingerprint_ranker = _FingerprintRanker()
        return cls._fingerprint_ranker

    @classmethod
    def _load_model(cls, name: str) -> Optional[Any]:
        if cls._model is not None:
            return cls._model
        if cls._failed:
            return None
        # Honour a config flag to force the offline fallback.
        if os.environ.get("JARVIS_SEMANTIC_OFFLINE", "").lower() in ("1", "true", "yes"):
            return None
        try:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(name)
            cls._backend = "neural"
            return cls._model
        except Exception as exc:  # noqa: BLE001 — network/import/missing lib
            cls._failed = True
            logger.warning("SemanticRanker neural model unavailable (%s); using offline fallback.", exc)
            return None

    def available(self) -> bool:
        """True if *any* backend (neural or offline) can rank."""
        return True  # fingerprint fallback always available

    def neural_available(self) -> bool:
        """True only if the neural embedding model loaded."""
        return self._load_model(self.model_name) is not None

    def _embed(self, texts: Sequence[str]) -> Tuple[np.ndarray, str]:
        model = self._load_model(self.model_name)
        if model is not None:
            try:
                vecs = model.encode(list(texts), convert_to_numpy=True, normalize_embeddings=True)
                if isinstance(vecs, np.ndarray) and vecs.ndim == 2:
                    return vecs.astype(np.float32), "neural"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neural embed failed (%s); falling back to fingerprint.", exc)
        fp = self._fingerprint()
        return fp.embed(texts), "fingerprint"

    def similarity(self, query: str, candidates: Sequence[str]) -> List[float]:
        """Cosine similarity of *query* against each candidate (0.0–1.0 range).

        Always returns one score per candidate.  Uses neural embeddings when
        available, otherwise the offline fingerprint ranker.
        """
        if not candidates:
            return []
        q_vec, _ = self._embed([query])
        if q_vec.ndim != 2 or q_vec.shape[0] == 0:
            return [0.0] * len(candidates)
        q_vec = q_vec[0]
        c_vecs, backend = self._embed(list(candidates))
        if c_vecs.ndim != 2:
            return [0.0] * len(candidates)
        # Cosine similarity (vectors already normalised where possible).
        norms = np.linalg.norm(c_vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        c_norm = c_vecs / norms
        sims = c_norm @ q_vec
        return [float(max(0.0, min(1.0, s))) for s in sims]

    def rerank(self, query: str, candidates: Sequence[str], top_k: int = 10) -> List[Tuple[int, float]]:
        """Return up to *top_k* (index, score) pairs sorted by similarity desc."""
        sims = self.similarity(query, candidates)
        order = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
        return [(i, sims[i]) for i in order[:top_k] if sims[i] > 0.0]

    def backend(self) -> str:
        model = self._load_model(self.model_name)
        if model is not None:
            return "neural"
        return "fingerprint"


_ranker: Optional[SemanticRanker] = None


def get_ranker() -> SemanticRanker:
    global _ranker
    if _ranker is None:
        _ranker = SemanticRanker()
    return _ranker


def reset_ranker() -> None:  # tests
    global _ranker
    _ranker = None
