"""
Bridge between the knowledge system and existing memory subsystem.

Provides two-way sync and query translation.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .types import Document, DocumentMetadata, KnowledgeSource, KnowledgeStatus
from .store import KnowledgeStore

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    id: str
    content: str
    namespace: str
    key: str
    metadata: Dict[str, Any]


class MemoryBridge:
    """
    Bidirectional bridge between KnowledgeStore and external memory systems.

    Adapts knowledge documents to/from memory record format used by
    the orchestrator, agents, and other subsystems.
    """

    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._memory_stores: Dict[str, Any] = {}

    def register_memory_store(self, name: str, store_backend: Any):
        """Register an external memory store."""
        self._memory_stores[name] = store_backend

    def document_to_memory(self, doc: Document) -> MemoryRecord:
        """Convert a knowledge document to a memory record."""
        return MemoryRecord(
            id=doc.id,
            content=doc.content,
            namespace=doc.metadata.source.value,
            key=f"knowledge:{doc.id}",
            metadata={
                "source": doc.metadata.source.value,
                "status": doc.status.value,
                "confidence": doc.confidence,
                "tags": doc.metadata.tags,
                "title": doc.metadata.title,
                "user_id": doc.user_id,
                "session_id": doc.session_id,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
            },
        )

    def memory_to_document(self, record: MemoryRecord) -> Document:
        """Convert a memory record to a knowledge document."""
        meta = DocumentMetadata(
            title=record.metadata.get("title", ""),
            source=KnowledgeSource(record.metadata.get("source", "document")),
            tags=record.metadata.get("tags", []),
        )
        return Document(
            id=record.id,
            content=record.content,
            metadata=meta,
            status=KnowledgeStatus(record.metadata.get("status", "active")),
            confidence=record.metadata.get("confidence", 0.0),
            user_id=record.metadata.get("user_id", ""),
            session_id=record.metadata.get("session_id", ""),
        )

    def sync_to_memory(self, doc: Document, store_name: str = "default") -> bool:
        """Sync a document to an external memory store."""
        store = self._memory_stores.get(store_name)
        if not store:
            logger.warning(f"Memory store '{store_name}' not registered")
            return False
        record = self.document_to_memory(doc)
        try:
            store.save(record.key, record.content, record.metadata)
            logger.debug(f"Synced document {doc.id} to memory store '{store_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to sync document {doc.id} to memory: {e}")
            return False

    def sync_from_memory(self, record: MemoryRecord, store_name: str = "default") -> Optional[Document]:
        """Import a memory record as a knowledge document."""
        doc = self.memory_to_document(record)
        existing = self.store.get_document(doc.id)
        if existing:
            self.store.update_document(doc.id, content=doc.content, updated_at=doc.updated_at)
            return existing
        return self.store.create_document(
            content=doc.content,
            metadata=doc.metadata,
            user_id=doc.user_id,
            session_id=doc.session_id,
        )

    def batch_sync_to_memory(self, docs: List[Document], store_name: str = "default") -> int:
        count = 0
        for doc in docs:
            if self.sync_to_memory(doc, store_name):
                count += 1
        return count

    def batch_sync_from_memory(self, records: List[MemoryRecord], store_name: str = "default") -> int:
        count = 0
        for record in records:
            if self.sync_from_memory(record, store_name):
                count += 1
        return count
