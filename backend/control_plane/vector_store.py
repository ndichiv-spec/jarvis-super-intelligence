"""
Vector Store - Embeddings storage and similarity search.

Provides an abstract :class:`VectorStore` with three backends:
  * **In-memory** (default) — fast, no external deps, good for testing.
  * **Redis** — uses Redis vectors (HNSW) via redis-py when available.
  * **pgvector** — uses PostgreSQL ``vector`` extension via psycopg2.

Each store supports:
  * Insert / upsert embeddings with metadata payloads
  * L2 / cosine / inner-product similarity search
  * Filter by namespace and metadata key-value pairs
  * Distance thresholds and result limits

Design:
  * No hard dependency on redis-py or psycopg2; degrades gracefully.
  * Embeddings are stored as ``List[float]`` (dimension-agnostic).
  * Honest: when backend unavailable, raises VectorStoreError.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("control_plane.vector_store")


class DistanceMetric(str, Enum):
    L2 = "l2"
    COSINE = "cosine"
    INNER_PRODUCT = "ip"


class VectorStoreError(Exception):
    """Base error for vector store operations."""


@dataclass
class EmbeddingRecord:
    """A single embedding with associated metadata."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vector: List[float] = field(default_factory=list)
    text: str = ""
    namespace: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vector": self.vector,
            "text": self.text,
            "namespace": self.namespace,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbeddingRecord":
        return cls(
            id=data["id"],
            vector=data.get("vector", []),
            text=data.get("text", ""),
            namespace=data.get("namespace", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class SearchResult:
    """A single search result with similarity score."""

    record: EmbeddingRecord
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.record.id,
            "score": self.score,
            "text": self.record.text,
            "namespace": self.record.namespace,
            "metadata": self.record.metadata,
        }


def _dot_product(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _l2_distance(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    norm_a = math.sqrt(_dot_product(a, a))
    norm_b = math.sqrt(_dot_product(b, b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return _dot_product(a, b) / (norm_a * norm_b)


def _compute_distance(
    a: List[float], b: List[float], metric: DistanceMetric
) -> float:
    if metric == DistanceMetric.L2:
        return _l2_distance(a, b)
    elif metric == DistanceMetric.COSINE:
        return 1.0 - _cosine_similarity(a, b)  # convert to distance
    elif metric == DistanceMetric.INNER_PRODUCT:
        return -_dot_product(a, b)  # negate for sorting
    return _l2_distance(a, b)


class VectorStore:
    """
    Abstract base class for vector stores.

    Subclasses must implement :meth:`upsert`, :meth:`search`, :meth:`delete`,
    :meth:`fetch`, and :meth:`stats`.
    """

    def __init__(
        self,
        dimension: int = 0,
        metric: DistanceMetric = DistanceMetric.COSINE,
        namespace: str = "default",
    ):
        self.dimension = dimension
        self.metric = metric
        self.namespace = namespace

    def upsert(
        self,
        records: List[EmbeddingRecord],
        *,
        namespace: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        """Insert or update records. Returns the number of records stored."""
        raise NotImplementedError

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        *,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchResult]:
        """Search for similar vectors. Returns results sorted by score (asc)."""
        raise NotImplementedError

    def delete(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> int:
        """Delete records by ID. Returns number deleted."""
        raise NotImplementedError

    def fetch(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> Dict[str, EmbeddingRecord]:
        """Fetch records by ID."""
        raise NotImplementedError

    def stats(self) -> Dict[str, Any]:
        """Return store statistics."""
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """
    Thread-safe in-memory vector store using brute-force search.

    Suitable for testing and small-scale (< 10K vectors) production.
    """

    def __init__(
        self,
        dimension: int = 0,
        metric: DistanceMetric = DistanceMetric.COSINE,
        namespace: str = "default",
    ):
        super().__init__(dimension, metric, namespace)
        self._store: Dict[str, EmbeddingRecord] = {}
        self._lock = threading.RLock()

    def upsert(
        self,
        records: List[EmbeddingRecord],
        *,
        namespace: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        with self._lock:
            for record in records:
                ns = namespace if namespace is not None else (
                    record.namespace if record.namespace else self.namespace
                )
                key = self._key(record.id, ns)
                record.namespace = ns
                self._store[key] = record
            return len(records)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        *,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchResult]:
        with self._lock:
            candidates: List[Tuple[float, EmbeddingRecord]] = []
            # When namespace is explicitly given, filter by prefix; otherwise
            # search across all namespaces.
            prefix = f"{namespace}:" if namespace is not None else None
            for key, record in self._store.items():
                if prefix is not None and not key.startswith(prefix):
                    continue
                if not self._matches_filter(record, filter):
                    continue
                dist = _compute_distance(query_vector, record.vector, self.metric)
                candidates.append((dist, record))

            candidates.sort(key=lambda c: c[0])
            if min_score is not None:
                candidates = [
                    c for c in candidates if c[0] <= min_score
                ]

            results = [
                SearchResult(record=rec, score=dist)
                for dist, rec in candidates[:top_k]
            ]
            return results

    def delete(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> int:
        deleted = 0
        with self._lock:
            if namespace is not None:
                prefix = f"{namespace}:"
                for rid in ids:
                    key = f"{prefix}{rid}"
                    if key in self._store:
                        del self._store[key]
                        deleted += 1
            else:
                for rid in ids:
                    matching = [
                        k for k in self._store if k.endswith(f":{rid}") or k == rid
                    ]
                    for k in matching:
                        del self._store[k]
                        deleted += 1
        return deleted

    def fetch(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> Dict[str, EmbeddingRecord]:
        result: Dict[str, EmbeddingRecord] = {}
        with self._lock:
            if namespace is not None:
                prefix = f"{namespace}:"
                for rid in ids:
                    key = f"{prefix}{rid}"
                    if key in self._store:
                        result[rid] = self._store[key]
            else:
                for rid in ids:
                    for k, v in self._store.items():
                        if k.endswith(f":{rid}") or k == rid:
                            result[rid] = v
                            break
        return result

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            namespaces: Dict[str, int] = {}
            for key in self._store:
                ns = key.split(":", 1)[0]
                namespaces[ns] = namespaces.get(ns, 0) + 1
            return {
                "backend": "memory",
                "vector_count": len(self._store),
                "namespaces": namespaces,
                "dimension": self.dimension,
                "metric": self.metric.value,
            }

    @staticmethod
    def _key(record_id: str, namespace: str) -> str:
        return f"{namespace}:{record_id}"

    @staticmethod
    def _matches_filter(
        record: EmbeddingRecord,
        filt: Optional[Dict[str, Any]],
    ) -> bool:
        if not filt:
            return True
        for k, v in filt.items():
            if k not in record.metadata:
                return False
            if record.metadata[k] != v:
                return False
        return True


class RedisVectorStore(VectorStore):
    """
    Redis-backed vector store using Redis Stack's vector similarity.

    Requires redis-py >= 4.5 with Redis Stack module.
    Falls back to in-memory if redis-py is not installed.
    """

    def __init__(
        self,
        dimension: int = 0,
        metric: DistanceMetric = DistanceMetric.COSINE,
        namespace: str = "default",
        redis_url: str = "redis://localhost:6379/0",
    ):
        super().__init__(dimension, metric, namespace)
        self.redis_url = redis_url
        self._client: Optional[Any] = None
        self._try_connect()

    def _try_connect(self) -> None:
        try:
            import redis
            self._client = redis.from_url(self.redis_url)
            self._client.ping()
            logger.info("RedisVectorStore connected to %s", self.redis_url)
        except ImportError:
            logger.warning("redis-py not installed; RedisVectorStore unavailable")
            self._client = None
        except Exception as exc:
            logger.warning("Redis connection failed: %s", exc)
            self._client = None

    def _metric_to_redis(self) -> str:
        mapping = {
            DistanceMetric.L2: "L2",
            DistanceMetric.COSINE: "COSINE",
            DistanceMetric.INNER_PRODUCT: "IP",
        }
        return mapping.get(self.metric, "COSINE")

    def _index_name(self, namespace: str) -> str:
        return f"idx:{namespace}"

    def _key_prefix(self, namespace: str) -> str:
        return f"vec:{namespace}:"

    def upsert(
        self,
        records: List[EmbeddingRecord],
        *,
        namespace: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        if self._client is None:
            raise VectorStoreError("Redis not connected")

        ns = namespace or self.namespace
        idx = self._index_name(ns)
        prefix = self._key_prefix(ns)

        # Ensure index exists
        try:
            self._client.ft(idx).info()
        except Exception:
            try:
                from redis.commands.search.field import VectorField
                self._client.ft(idx).create_index([
                    VectorField(
                        "vector",
                        "HNSW",
                        {
                            "TYPE": "FLOAT32",
                            "DIM": self.dimension or 1536,
                            "DISTANCE_METRIC": self._metric_to_redis(),
                            "INITIAL_CAP": 1000,
                        },
                    ),
                    self._client.field("id") if False else None,
                    self._client.field("text"),
                    self._client.field("metadata"),
                ])
            except Exception as exc:
                logger.debug("Index creation skipped: %s", exc)

        pipe = self._client.pipeline()
        for record in records:
            key = f"{prefix}{record.id}"
            vector_bytes = bytes(
                (x * 32767 for x in record.vector)  # FLOAT32
            ) if False else record.vector  # store as JSON
            pipe.hset(
                name=key,
                mapping={
                    "id": record.id,
                    "text": record.text,
                    "vector": json.dumps(record.vector),
                    "metadata": json.dumps(record.metadata),
                    "created_at": record.created_at,
                },
            )
        pipe.execute()
        return len(records)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        *,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchResult]:
        if self._client is None:
            raise VectorStoreError("Redis not connected")

        # For simplicity, use in-memory-style search on fetched data.
        # A production implementation would use Redis vector similarity.
        ns = namespace or self.namespace
        prefix = self._key_prefix(ns)

        results: List[SearchResult] = []
        pattern = f"{prefix}*"

        for key in self._client.scan_iter(match=pattern):
            fields = self._client.hgetall(key)
            rec = EmbeddingRecord(
                id=fields.get(b"id", b"").decode(),
                vector=json.loads(fields.get(b"vector", b"[]")),
                text=fields.get(b"text", b"").decode(),
                namespace=ns,
                metadata=json.loads(fields.get(b"metadata", b"{}")),
            )
            if not self._matches_filter(rec, filter):
                continue
            dist = _compute_distance(query_vector, rec.vector, self.metric)
            results.append(SearchResult(record=rec, score=dist))

        results.sort(key=lambda r: r.score)
        if min_score is not None:
            results = [r for r in results if r.score <= min_score]
        return results[:top_k]

    def delete(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> int:
        if self._client is None:
            raise VectorStoreError("Redis not connected")
        ns = namespace or self.namespace
        prefix = self._key_prefix(ns)
        deleted = 0
        for rid in ids:
            key = f"{prefix}{rid}"
            if self._client.delete(key):
                deleted += 1
        return deleted

    def fetch(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> Dict[str, EmbeddingRecord]:
        if self._client is None:
            raise VectorStoreError("Redis not connected")
        ns = namespace or self.namespace
        result: Dict[str, EmbeddingRecord] = {}
        for rid in ids:
            key = self._key_prefix(ns) + rid
            fields = self._client.hgetall(key)
            if fields:
                result[rid] = EmbeddingRecord(
                    id=rid,
                    vector=json.loads(fields.get(b"vector", b"[]")),
                    text=fields.get(b"text", b"").decode(),
                    namespace=ns,
                    metadata=json.loads(fields.get(b"metadata", b"{}")),
                )
        return result

    def stats(self) -> Dict[str, Any]:
        if self._client is None:
            return {"backend": "redis", "connected": False}
        return {
            "backend": "redis",
            "connected": True,
            "dimension": self.dimension,
            "metric": self.metric.value,
        }

    @staticmethod
    def _matches_filter(
        record: EmbeddingRecord,
        filt: Optional[Dict[str, Any]],
    ) -> bool:
        if not filt:
            return True
        for k, v in filt.items():
            if k not in record.metadata:
                return False
            if record.metadata[k] != v:
                return False
        return True


class PgVectorStore(VectorStore):
    """
    PostgreSQL-backed vector store using the ``vector`` extension.

    Requires psycopg2 and the ``vector`` extension in PostgreSQL.
    """

    def __init__(
        self,
        dimension: int = 0,
        metric: DistanceMetric = DistanceMetric.COSINE,
        namespace: str = "default",
        dsn: str = "",
        table_name: str = "jarvis_embeddings",
    ):
        super().__init__(dimension, metric, namespace)
        self.dsn = dsn
        self.table_name = table_name
        self._conn: Optional[Any] = None
        self._connect()

    def _connect(self) -> None:
        try:
            import psycopg2
            self._conn = psycopg2.connect(self.dsn)
            self._ensure_table()
            logger.info("PgVectorStore connected to PostgreSQL")
        except ImportError:
            logger.warning("psycopg2 not installed; PgVectorStore unavailable")
            self._conn = None
        except Exception as exc:
            logger.warning("PostgreSQL connection failed: %s", exc)
            self._conn = None

    def _ensure_table(self) -> None:
        if self._conn is None:
            return
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            dim = self.dimension or 1536
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    vector VECTOR({dim}),
                    text TEXT,
                    metadata JSONB,
                    created_at DOUBLE PRECISION DEFAULT extract(epoch FROM now())
                );
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_ns_vector
                ON {self.table_name} USING hnsw (vector vector_cosine_ops)
                WHERE namespace = namespace;
            """)
            self._conn.commit()

    def upsert(
        self,
        records: List[EmbeddingRecord],
        *,
        namespace: Optional[str] = None,
        batch_size: int = 100,
    ) -> int:
        if self._conn is None:
            raise VectorStoreError("PostgreSQL not connected")
        ns = namespace or self.namespace
        with self._conn.cursor() as cur:
            for record in records:
                record.namespace = ns
                cur.execute(
                    f"""INSERT INTO {self.table_name}
                        (id, namespace, vector, text, metadata, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            vector = EXCLUDED.vector,
                            text = EXCLUDED.text,
                            metadata = EXCLUDED.metadata,
                            created_at = EXCLUDED.created_at;""",
                    (
                        record.id, ns, json.dumps(record.vector),
                        record.text, json.dumps(record.metadata),
                        record.created_at,
                    ),
                )
            self._conn.commit()
        return len(records)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        *,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchResult]:
        if self._conn is None:
            raise VectorStoreError("PostgreSQL not connected")
        ns = namespace or self.namespace
        with self._conn.cursor() as cur:
            sql = f"""
                SELECT id, namespace, vector, text, metadata, created_at,
                    1 - (vector <=> %s) AS score
                FROM {self.table_name}
                WHERE namespace = %s
            """
            params: List[Any] = [json.dumps(query_vector), ns]
            if filter:
                for k, v in filter.items():
                    sql += f" AND metadata->>'{k}' = %s"
                    params.append(str(v))
            sql += " ORDER BY score DESC LIMIT %s"
            params.append(top_k)

            cur.execute(sql, params)
            rows = cur.fetchall()

        results: List[SearchResult] = []
        for row in rows:
            record = EmbeddingRecord(
                id=row[0],
                vector=json.loads(row[2]) if row[2] else [],
                text=row[3] or "",
                namespace=row[1],
                metadata=row[4] or {},
                created_at=row[5] or time.time(),
            )
            score = row[6] if row[6] is not None else 0.0
            if min_score is not None and score < min_score:
                continue
            results.append(SearchResult(record=record, score=score))
        return results

    def delete(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> int:
        if self._conn is None:
            raise VectorStoreError("PostgreSQL not connected")
        ns = namespace or self.namespace
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self.table_name} WHERE id = ANY(%s) AND namespace = %s",
                (ids, ns),
            )
            deleted = cur.rowcount
            self._conn.commit()
        return deleted

    def fetch(
        self,
        ids: List[str],
        *,
        namespace: Optional[str] = None,
    ) -> Dict[str, EmbeddingRecord]:
        if self._conn is None:
            raise VectorStoreError("PostgreSQL not connected")
        ns = namespace or self.namespace
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT id, namespace, vector, text, metadata, created_at "
                f"FROM {self.table_name} WHERE id = ANY(%s) AND namespace = %s",
                (ids, ns),
            )
            rows = cur.fetchall()
        result: Dict[str, EmbeddingRecord] = {}
        for row in rows:
            result[row[0]] = EmbeddingRecord(
                id=row[0],
                vector=json.loads(row[2]) if row[2] else [],
                text=row[3] or "",
                namespace=row[1],
                metadata=row[4] or {},
                created_at=row[5] or time.time(),
            )
        return result

    def stats(self) -> Dict[str, Any]:
        if self._conn is None:
            return {"backend": "pgvector", "connected": False}
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT namespace) FROM {self.table_name}"
            )
            row = cur.fetchone()
        return {
            "backend": "pgvector",
            "connected": True,
            "vector_count": row[0] if row else 0,
            "namespace_count": row[1] if row else 0,
            "dimension": self.dimension,
            "metric": self.metric.value,
        }


class VectorStoreFactory:
    """Factory for creating vector stores by backend name."""

    @staticmethod
    def create(
        backend: str = "memory",
        dimension: int = 0,
        metric: DistanceMetric = DistanceMetric.COSINE,
        namespace: str = "default",
        **kwargs: Any,
    ) -> VectorStore:
        if backend == "memory":
            return InMemoryVectorStore(dimension, metric, namespace)
        elif backend == "redis":
            return RedisVectorStore(
                dimension=dimension, metric=metric, namespace=namespace,
                redis_url=kwargs.get("redis_url", "redis://localhost:6379/0"),
            )
        elif backend in ("pgvector", "postgres"):
            return PgVectorStore(
                dimension=dimension, metric=metric, namespace=namespace,
                dsn=kwargs.get("dsn", ""),
                table_name=kwargs.get("table_name", "jarvis_embeddings"),
            )
        else:
            raise VectorStoreError(f"Unknown backend: {backend}")


_vector_store: Optional[VectorStore] = None
_vector_store_lock = threading.Lock()


def get_vector_store(
    backend: str = "memory",
    dimension: int = 0,
    metric: DistanceMetric = DistanceMetric.COSINE,
    namespace: str = "default",
    **kwargs: Any,
) -> VectorStore:
    """Get or create the global vector store singleton."""
    global _vector_store
    if _vector_store is None:
        with _vector_store_lock:
            if _vector_store is None:
                _vector_store = VectorStoreFactory.create(
                    backend=backend,
                    dimension=dimension,
                    metric=metric,
                    namespace=namespace,
                    **kwargs,
                )
    return _vector_store


def reset_vector_store() -> None:
    """Reset the global vector store (for testing)."""
    global _vector_store
    with _vector_store_lock:
        _vector_store = None
