"""
Configurable retention and cleanup policies for knowledge management.

Provides:
  - Time-based expiry
  - Usage-based eviction
  - Status-based cleanup
  - Configurable policies per namespace
"""

from __future__ import annotations
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from .types import Document, KnowledgeStatus
from .store import KnowledgeStore

logger = logging.getLogger(__name__)


class CleanupMode(Enum):
    TIME_BASED = "time_based"
    COUNT_BASED = "count_based"
    STATUS_BASED = "status_based"
    HYBRID = "hybrid"


@dataclass
class RetentionPolicy:
    namespace: str = "default"
    mode: CleanupMode = CleanupMode.HYBRID
    max_documents: int = 10_000
    max_age_days: int = 90
    archive_after_days: int = 30
    cleanup_interval_hours: float = 24.0
    preserve_system: bool = True
    auto_cleanup: bool = True
    on_cleanup: Optional[Callable[[List[Document]], None]] = None


class RetentionManager:
    """
    Manages document retention and cleanup.

    Policies can be configured per namespace.
    Cleanup runs automatically based on interval.
    """

    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._policies: Dict[str, RetentionPolicy] = {}
        self._last_cleanup: float = 0

    def set_policy(self, namespace: str, policy: RetentionPolicy):
        self._policies[namespace] = policy

    def get_policy(self, namespace: str) -> RetentionPolicy:
        return self._policies.get(namespace, RetentionPolicy(namespace=namespace))

    def cleanup(self, namespace: str = "") -> Dict[str, Any]:
        """Run cleanup for a namespace (or all if empty)."""
        namespaces = [namespace] if namespace else list(self._policies.keys()) or ["default"]
        total_removed = 0
        total_archived = 0

        for ns in namespaces:
            policy = self.get_policy(ns)
            removed, archived = self._cleanup_namespace(ns, policy)
            total_removed += removed
            total_archived += archived

        self._last_cleanup = time.time()
        logger.info(f"Cleanup completed: {total_removed} removed, {total_archived} archived")
        return {"removed": total_removed, "archived": total_archived, "namespaces": namespaces}

    def _cleanup_namespace(self, namespace: str, policy: RetentionPolicy) -> tuple:
        removed = 0
        archived = 0
        now = time.time()

        docs = self.store.list_documents(limit=policy.max_documents + 1000)

        for doc in docs:
            # Time-based expiry
            if doc.expires_at and now > doc.expires_at:
                doc.status = KnowledgeStatus.EXPIRED
                self.store.delete_document(doc.id)
                removed += 1
                continue

            # Max age
            if policy.mode in (CleanupMode.TIME_BASED, CleanupMode.HYBRID):
                age_seconds = now - doc.created_at
                age_days = age_seconds / 86400
                if age_days > policy.max_age_days:
                    doc.status = KnowledgeStatus.EXPIRED
                    self.store.delete_document(doc.id)
                    removed += 1
                    continue
                if age_days > policy.archive_after_days and doc.status == KnowledgeStatus.ACTIVE:
                    doc.status = KnowledgeStatus.ARCHIVED
                    archived += 1

        # Count-based eviction (remove oldest)
        if policy.mode in (CleanupMode.COUNT_BASED, CleanupMode.HYBRID):
            active = [d for d in docs if d.status == KnowledgeStatus.ACTIVE and not d.is_expired]
            if len(active) > policy.max_documents:
                to_remove = sorted(active, key=lambda d: d.created_at)[:len(active) - policy.max_documents]
                for doc in to_remove:
                    self.store.delete_document(doc.id)
                    removed += 1

        # Status-based cleanup (remove rejected/expired)
        if policy.mode in (CleanupMode.STATUS_BASED, CleanupMode.HYBRID):
            stale = [d for d in docs if d.status in (KnowledgeStatus.REJECTED, KnowledgeStatus.EXPIRED)]
            for doc in stale:
                self.store.delete_document(doc.id)
                removed += 1

        if policy.on_cleanup:
            try:
                policy.on_cleanup(docs)
            except Exception:
                pass

        return removed, archived

    def estimate_storage(self, namespace: str = "") -> Dict[str, Any]:
        docs = self.store.list_documents(limit=10_000)
        total_chars = sum(len(d.content) for d in docs)
        return {
            "document_count": len(docs),
            "total_chars": total_chars,
            "estimated_bytes": total_chars * 2,  # rough UTF-8 estimate
            "estimated_mb": round(total_chars * 2 / 1024 / 1024, 2),
        }

    def needs_cleanup(self) -> bool:
        if not self._policies:
            return False
        policy = next(iter(self._policies.values()))
        if not policy.auto_cleanup:
            return False
        interval = policy.cleanup_interval_hours * 3600
        return (time.time() - self._last_cleanup) > interval
