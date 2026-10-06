"""
Controlled learning workflow.

Prevents uncontrolled self-modification by requiring:
  - User approval for new knowledge
  - Confidence scoring before acceptance
  - Validation pipelines
  - Auditable learning requests
  - Rollback capability
"""

from __future__ import annotations
import time
import uuid
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from .types import (
    LearningRequest, KnowledgeSource, KnowledgeStatus,
    Document, DocumentMetadata,
)
from .store import KnowledgeStore

logger = logging.getLogger(__name__)


@dataclass
class LearningConfig:
    require_approval: bool = True
    min_confidence: float = 0.6
    max_pending_requests: int = 50
    auto_approve_sources: List[str] = field(default_factory=lambda: ["document"])
    enable_learning: bool = True
    audit_all: bool = True


class LearningController:
    """
    Controlled learning workflow engine.

    Flow:
      Content → LearningRequest (pending) → Review → Approved/Rejected → Store

    Safety:
      - No content enters knowledge base without passing validation
      - Learning can be paused globally
      - All operations are audited
      - User can rollback learned content
    """

    def __init__(self, store: KnowledgeStore, config: Optional[LearningConfig] = None):
        self.store = store
        self.config = config or LearningConfig()
        self._pending: Dict[str, LearningRequest] = {}
        self._validators: List[Callable[[LearningRequest], float]] = []
        self._audit_log: List[Dict[str, Any]] = []

    def add_validator(self, fn: Callable[[LearningRequest], float]):
        """Add a validator that returns a confidence score (0.0 - 1.0)."""
        self._validators.append(fn)

    def propose(self, content: str, source: KnowledgeSource,
                metadata: Optional[DocumentMetadata] = None,
                user_id: str = "") -> LearningRequest:
        """Propose new content for learning."""
        if not self.config.enable_learning:
            raise RuntimeError("Learning is disabled")

        if len(self._pending) >= self.config.max_pending_requests:
            raise RuntimeError(f"Max pending requests ({self.config.max_pending_requests}) reached")

        request_id = uuid.uuid4().hex[:16]
        requires_approval = self._requires_approval(source)

        request = LearningRequest(
            id=request_id,
            source=source,
            content=content,
            metadata=metadata or DocumentMetadata(source=source),
            user_id=user_id,
            requires_approval=requires_approval,
        )

        # Run validators
        confidence = self._validate(request)
        request.confidence = confidence

        self._pending[request_id] = request
        self._audit("propose", request_id, {
            "source": source.value,
            "content_length": len(content),
            "confidence": confidence,
            "requires_approval": requires_approval,
        })

        logger.info(f"Learning proposed: {request_id} (confidence={confidence:.2f}, source={source.value})")

        # Auto-approve if applicable
        if not requires_approval and confidence >= self.config.min_confidence:
            self.approve(request_id, user_id="system")

        return request

    def approve(self, request_id: str, user_id: str = "",
                notes: Optional[List[str]] = None) -> Optional[Document]:
        """Approve a learning request and store it."""
        request = self._pending.get(request_id)
        if not request:
            logger.warning(f"Learning request not found: {request_id}")
            return None

        request.approved = True
        request.reviewed_at = time.time()
        if notes:
            request.validation_notes.extend(notes)

        doc = self.store.create_document(
            content=request.content,
            metadata=request.metadata,
            user_id=request.user_id or user_id,
            status=KnowledgeStatus.ACTIVE,
        )
        doc.confidence = request.confidence

        del self._pending[request_id]
        self._audit("approve", request_id, {"user_id": user_id})
        logger.info(f"Learning approved: {request_id} -> document {doc.id}")
        return doc

    def reject(self, request_id: str, reason: str = "",
               user_id: str = "") -> bool:
        """Reject a learning request."""
        request = self._pending.get(request_id)
        if not request:
            return False

        request.approved = False
        request.reviewed_at = time.time()
        if reason:
            request.validation_notes.append(reason)

        del self._pending[request_id]
        self._audit("reject", request_id, {"reason": reason, "user_id": user_id})
        logger.info(f"Learning rejected: {request_id} ({reason})")
        return True

    def rollback(self, doc_id: str, user_id: str = "") -> bool:
        """Remove a document that was previously learned."""
        doc = self.store.get_document(doc_id)
        if not doc:
            return False

        doc.status = KnowledgeStatus.REJECTED
        self._audit("rollback", doc_id, {"user_id": user_id})
        logger.info(f"Learning rolled back: {doc_id}")
        return True

    def get_pending(self, limit: int = 50) -> List[LearningRequest]:
        requests = list(self._pending.values())
        requests.sort(key=lambda r: r.created_at, reverse=True)
        return requests[:limit]

    def get_pending_count(self) -> int:
        return len(self._pending)

    def is_learning_enabled(self) -> bool:
        return self.config.enable_learning

    def set_learning_enabled(self, enabled: bool):
        self.config.enable_learning = enabled
        self._audit("toggle", "", {"enabled": enabled})

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._audit_log[-limit:]

    def _validate(self, request: LearningRequest) -> float:
        if not self._validators:
            return 0.8  # default confidence if no validators
        scores = []
        for fn in self._validators:
            try:
                score = fn(request)
                scores.append(max(0.0, min(1.0, score)))
            except Exception as e:
                logger.warning(f"Validator failed: {e}")
        return sum(scores) / len(scores) if scores else 0.5

    def _requires_approval(self, source: KnowledgeSource) -> bool:
        if not self.config.require_approval:
            return False
        return source.value not in self.config.auto_approve_sources

    def _audit(self, action: str, request_id: str, details: Dict[str, Any]):
        if self.config.audit_all:
            self._audit_log.append({
                "action": action,
                "request_id": request_id,
                "details": details,
                "timestamp": time.time(),
            })
