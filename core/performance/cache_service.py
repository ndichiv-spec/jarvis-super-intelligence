from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any


class CacheLevel(str, Enum):
    MEMORY = "memory"
    REDIS = "redis"
    DISTRIBUTED = "distributed"


class CacheService:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._metrics = {"hits": 0, "misses": 0, "sets": 0}

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            json.dumps(value, default=str)
        except (TypeError, ValueError):
            raise TypeError("Cache value must be JSON serializable")
        self._store[key] = {
            "value": value,
            "timestamp": time.time(),
            "ttl": ttl,
        }
        self._metrics["sets"] += 1

    async def get(self, key: str) -> Any:
        entry = self._store.get(key)
        if not entry:
            self._metrics["misses"] += 1
            return None
        expires_at = entry["timestamp"] + (entry["ttl"] or 0)
        if entry["ttl"] is not None and time.time() > expires_at:
            self._store.pop(key, None)
            self._metrics["misses"] += 1
            return None
        self._metrics["hits"] += 1
        return entry["value"]

    def get_metrics(self) -> dict[str, Any]:
        total = self._metrics["hits"] + self._metrics["misses"]
        hit_rate = (self._metrics["hits"] / total) if total else 0.0
        metrics = dict(self._metrics)
        metrics["hit_rate"] = round(hit_rate, 4)
        return metrics

    async def get_cache_stats(self) -> dict[str, Any]:
        return {"memory_cache": {"entries": len(self._store)}, "metrics": self.get_metrics()}


cache_service = CacheService()

__all__ = ["CacheLevel", "CacheService", "cache_service"]
