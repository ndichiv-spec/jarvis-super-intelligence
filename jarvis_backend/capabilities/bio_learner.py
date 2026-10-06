"""
JARVIS BIO-LEARNER CAPABILITY
=============================

Bio-growth learning framework: curriculum learning, SM-2 spaced
repetition, hippocampal replay memory consolidation, and cross-domain
synthesis.

Actions:
- 'initialize': Initialize learning domains and curriculum
- 'study_concept': Study a concept within a domain
- 'consolidate': Run hippocampal replay and cross-domain synthesis
- 'get_learning_path': Get the curriculum for a domain
- 'get_status': Get overall learning status
- 'review_due': Get due reviews (SM-2 spaced repetition)
- 'perform_review': Review a concept (updates SM-2 schedule)
"""

from __future__ import annotations

import os
import sys
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import (
    Capability, CapabilityStatus, ExecutionContext, ExecutionResult
)
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import AuditLog


class BioLearnerCapability(Capability):
    """
    Bio-growth learning framework capability for JARVIS.

    Wraps BioLearner to provide curriculum learning with
    SM-2 spaced repetition, memory consolidation, and
    cross-domain synthesis.
    """

    name = "bio.learner"
    version = "1.0.0"
    category = "learning"
    _max_cached_profiles = 64

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._learners: OrderedDict[str, Any] = OrderedDict()

    def _get_learner(self, user_id: str):
        """Load an isolated learner and durable progress for one authenticated user."""
        learner = self._learners.get(user_id)
        if learner is not None:
            self._learners.move_to_end(user_id)
            return learner

        from jarvis_backend.core import get_store
        from jarvis_backend.research.bio_learner import BioLearner

        learner = BioLearner()
        learner.initialize()
        saved = get_store("bio_learning").load().get(user_id)
        if saved:
            learner.load_snapshot(saved)
        self._learners[user_id] = learner
        if len(self._learners) > self._max_cached_profiles:
            self._learners.popitem(last=False)
        return learner

    @staticmethod
    def _save_learner(user_id: str, learner) -> None:
        from jarvis_backend.core import get_store

        store = get_store("bio_learning")
        store.load()[user_id] = learner.to_snapshot()
        store.save()

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check — verify bio-learner infrastructure."""
        from jarvis_backend.research.bio_learner import BioLearner

        learner = BioLearner()
        learner.initialize()
        from jarvis_backend.core import get_store

        profiles = get_store("bio_learning").load()

        return {
            'status': CapabilityStatus.READY,
            'healthy': True,
            'learner_available': True,
            'domains': len(learner._domains),
            'curriculum_concepts': len(learner._concepts),
            'persisted_profiles': len(profiles),
            'growth_stage': learner._growth_stage.value,
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a bio-learning operation."""
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'status')
        start_time = time.time()
        correlation_id = context.correlation_id

        user_id = str(context.user_id or "anonymous")
        learner = self._get_learner(user_id)

        try:
            if action == 'initialize':
                status = learner.get_status()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=status,
                    correlation_id=correlation_id,
                    metrics={'domains': status.get('domains', 0)},
                )

            elif action == 'study_concept':
                domain = request.get('domain', '')
                concept = request.get('concept', '')
                result_data = await learner.study_concept(domain, concept)
                result = ExecutionResult(
                    capability=self.name,
                    success=result_data.get('success', False),
                    data=result_data,
                    error=result_data.get('error'),
                    correlation_id=correlation_id,
                    metrics={
                        'mastery': result_data.get('mastery_level', 0),
                        'assessment_required': result_data.get('assessment_required', False),
                    },
                )

            elif action == 'consolidate':
                result_data = await learner.consolidate()
                result = ExecutionResult(
                    capability=self.name,
                    success=result_data.get('success', False),
                    data=result_data,
                    correlation_id=correlation_id,
                    metrics={'syntheses': result_data.get('syntheses_generated', 0)},
                )

            elif action == 'get_learning_path':
                domain = request.get('domain', '')
                path = learner.get_learning_path(domain)
                result = ExecutionResult(
                    capability=self.name,
                    success='error' not in path,
                    data=path,
                    error=path.get('error'),
                    correlation_id=correlation_id,
                )

            elif action == 'review_due':
                due = learner.get_due_reviews()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={'due_reviews': due, 'count': len(due)},
                    correlation_id=correlation_id,
                )

            elif action == 'perform_review':
                item_key = request.get('item_key', '')
                quality = request.get('quality', 3)  # 0-5 scale (SM-2)
                result_data = await learner.perform_review(item_key, quality)
                result = ExecutionResult(
                    capability=self.name,
                    success=result_data.get('success', False),
                    data=result_data,
                    correlation_id=correlation_id,
                )

            elif action == 'get_status':
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=learner.get_status(),
                    correlation_id=correlation_id,
                )

            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown action: {action}",
                    error_type="INVALID_ACTION",
                    correlation_id=correlation_id,
                )

        except Exception as e:
            result = ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id,
            )

        result.latency_ms = (time.time() - start_time) * 1000.0

        if action in {'study_concept', 'consolidate', 'perform_review'} and result.success:
            self._save_learner(user_id, learner)

        self._event_bus.emit(
            event_type=f'bio.{action}.completed',
            source='orchestrator',
            capability=self.name,
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed' if result.success else 'failed',
            payload={'action': action, 'success': result.success},
        )

        AuditLog.log(
            event_type=f'bio.{action}',
            source=self.name,
            capability=self.name,
            user_id=context.user_id,
            session_id=context.session_id,
            action=action,
            result='success' if result.success else 'error',
        )

        return result

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self._learners.clear()
        self.set_status(CapabilityStatus.OFFLINE)
        return True
