"""Tests for memory and persistence validation."""

from __future__ import annotations
import time
import pytest
from typing import Dict, Any, Optional


class TestMemoryStore:
    def test_set_and_get(self):
        store = InMemoryStore()
        store.set("key1", "value1")
        assert store.get("key1") == "value1"

    def test_get_missing(self):
        store = InMemoryStore()
        assert store.get("nonexistent") is None

    def test_get_missing_with_default(self):
        store = InMemoryStore()
        assert store.get("missing", "default") == "default"

    def test_overwrite(self):
        store = InMemoryStore()
        store.set("key", "old")
        store.set("key", "new")
        assert store.get("key") == "new"

    def test_delete_exists(self):
        store = InMemoryStore()
        store.set("key", "val")
        assert store.delete("key") is True
        assert store.get("key") is None

    def test_delete_missing(self):
        store = InMemoryStore()
        assert store.delete("nonexistent") is False

    def test_list_keys(self):
        store = InMemoryStore()
        store.set("a", 1)
        store.set("b", 2)
        store.set("c", 3)
        keys = store.list_keys()
        assert len(keys) == 3
        assert "a" in keys

    def test_list_keys_with_prefix(self):
        store = InMemoryStore()
        store.set("user:1", "alice")
        store.set("user:2", "bob")
        store.set("config:app", "value")
        user_keys = store.list_keys(prefix="user:")
        assert len(user_keys) == 2
        assert all(k.startswith("user:") for k in user_keys)

    def test_clear(self):
        store = InMemoryStore()
        store.set("a", 1)
        store.set("b", 2)
        store.clear()
        assert store.list_keys() == []

    def test_exists(self):
        store = InMemoryStore()
        assert store.exists("missing") is False
        store.set("present", "val")
        assert store.exists("present") is True

    def test_get_all(self):
        store = InMemoryStore()
        store.set("a", 1)
        store.set("b", 2)
        all_items = store.get_all()
        assert all_items["a"] == 1
        assert all_items["b"] == 2

    def test_get_all_returns_copy(self):
        store = InMemoryStore()
        store.set("key", "val")
        all_items = store.get_all()
        all_items["key"] = "modified"
        assert store.get("key") == "val"

    def test_ttl_expiration(self):
        store = InMemoryStore()
        store.set("ephemeral", "data", ttl=0.05)
        assert store.get("ephemeral") == "data"
        time.sleep(0.06)
        assert store.get("ephemeral") is None

    def test_ttl_not_expired(self):
        store = InMemoryStore()
        store.set("persistent", "data", ttl=60)
        assert store.get("persistent") == "data"

    def test_increment(self):
        store = InMemoryStore()
        store.set("counter", 0)
        store.increment("counter")
        assert store.get("counter") == 1
        store.increment("counter", 5)
        assert store.get("counter") == 6

    def test_increment_missing(self):
        store = InMemoryStore()
        store.increment("new_counter")
        assert store.get("new_counter") == 1


class TestMemoryPersistence:
    def test_snapshot_and_restore(self):
        store = InMemoryStore()
        store.set("a", 1)
        store.set("b", 2)
        snapshot = store.snapshot()
        store.clear()
        assert store.list_keys() == []
        store.restore(snapshot)
        assert store.get("a") == 1
        assert store.get("b") == 2

    def test_persistence_to_dict(self):
        store = InMemoryStore()
        store.set("user:1", {"name": "Alice", "role": "admin"})
        store.set("user:2", {"name": "Bob", "role": "user"})
        data = store.to_dict()
        assert len(data) == 2
        assert data["user:1"]["name"] == "Alice"


class InMemoryStore:
    """Simple in-memory store for testing memory patterns."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}

    def get(self, key: str, default: Any = None) -> Any:
        self._evict_expired()
        return self._data.get(key, default)

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        self._data[key] = value
        if ttl is not None:
            self._expiry[key] = time.time() + ttl
        elif key in self._expiry:
            del self._expiry[key]

    def delete(self, key: str) -> bool:
        self._evict_expired()
        self._expiry.pop(key, None)
        return self._data.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        self._evict_expired()
        return key in self._data

    def list_keys(self, prefix: str = "") -> list:
        self._evict_expired()
        return [k for k in self._data if k.startswith(prefix)]

    def clear(self):
        self._data.clear()
        self._expiry.clear()

    def increment(self, key: str, amount: int = 1) -> int:
        current = self._data.get(key, 0)
        self._data[key] = current + amount
        return self._data[key]

    def get_all(self) -> Dict[str, Any]:
        self._evict_expired()
        return dict(self._data)

    def snapshot(self) -> Dict[str, Any]:
        return {"data": dict(self._data), "expiry": dict(self._expiry)}

    def restore(self, snapshot: Dict[str, Any]):
        self._data = dict(snapshot["data"])
        self._expiry = dict(snapshot.get("expiry", {}))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, t in self._expiry.items() if t <= now]
        for k in expired:
            self._data.pop(k, None)
            self._expiry.pop(k, None)
