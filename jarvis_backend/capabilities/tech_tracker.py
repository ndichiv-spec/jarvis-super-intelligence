"""
JARVIS TECH EVOLUTION TRACKER CAPABILITY
=========================================

Discovers and maps technological species: tech radar, research frontier
mapping, lifecycle modeling, and cross-domain synthesis detection.

Actions:
- 'initialize': Initialize seed technology catalog
- 'discover': Discover new technologies from research ingestion
- 'model_lifecycle': Model a technology's adoption lifecycle (S-curve)
- 'get_tech_radar': Generate a ThoughtWorks-style tech radar
- 'get_frontiers': Get mapped research frontiers
- 'get_status': Get tracker status
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import (
    Capability, CapabilityStatus, ExecutionContext, ExecutionResult
)
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import AuditLog


class TechEvolutionTrackerCapability(Capability):
    """
    Technology Evolution Tracker capability for JARVIS.

    Wraps TechEvolutionTracker to discover and map technological
    species with tech radar, frontier mapping, and lifecycle modeling.
    """

    name = "tech.evolution"
    version = "1.0.0"
    category = "research"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._tracker = None
        self._initialized = False
        self._cortex = None

    def _get_tracker(self):
        """Lazy-load the tech evolution tracker."""
        if self._tracker is None:
            try:
                from jarvis_backend.research.tech_evolution import TechEvolutionTracker
                self._tracker = TechEvolutionTracker()
            except ImportError:
                pass
        return self._tracker

    def _get_cortex(self):
        """Get or create a research cortex for integration."""
        if self._cortex is None:
            try:
                from jarvis_backend.research.autonomous_research import AutonomousResearchCortex
                self._cortex = AutonomousResearchCortex()
                self._cortex.initialize()
            except ImportError:
                pass
        return self._cortex

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check — verify tech evolution infrastructure."""
        tracker_available = False
        technologies_count = 0
        frontiers_count = 0

        tracker = self._get_tracker()
        if tracker is not None:
            tracker_available = True
            if not self._initialized:
                cortex = self._get_cortex()
                tracker.initialize(cortex=cortex)
                self._initialized = True
            technologies_count = len(tracker._technologies)
            frontiers_count = len(tracker._frontiers)

        return {
            'status': CapabilityStatus.READY if tracker_available else CapabilityStatus.NOT_CONFIGURED,
            'healthy': tracker_available,
            'tracker_available': tracker_available,
            'technologies_count': technologies_count,
            'frontiers_count': frontiers_count,
            'growth_stage': tracker._growth_stage if tracker else 'unknown',
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a tech evolution tracking operation."""
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'status')
        start_time = time.time()
        correlation_id = context.correlation_id

        tracker = self._get_tracker()
        if tracker is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Tech evolution tracker not available",
                error_type="NOT_AVAILABLE",
                correlation_id=correlation_id,
            )

        try:
            if not self._initialized:
                cortex = self._get_cortex()
                tracker.initialize(cortex=cortex)
                self._initialized = True

            if action == 'initialize':
                result_data = tracker.get_status()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=result_data,
                    correlation_id=correlation_id,
                    metrics={'technologies': result_data.get('total_technologies', 0)},
                )

            elif action == 'discover':
                limit = request.get('limit', 50)
                result_data = await tracker.discover_new_technologies(limit)
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=result_data,
                    correlation_id=correlation_id,
                    metrics={'new_technologies': result_data.get('new_technologies', 0)},
                )

            elif action == 'model_lifecycle':
                tech_id = request.get('tech_id', '')
                result_data = tracker.model_lifecycle(tech_id)
                result = ExecutionResult(
                    capability=self.name,
                    success=result_data.get('success', 'error' not in result_data),
                    data=result_data,
                    error=result_data.get('error'),
                    correlation_id=correlation_id,
                )

            elif action == 'get_tech_radar':
                radar = tracker.get_tech_radar()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=radar,
                    correlation_id=correlation_id,
                )

            elif action == 'get_frontiers':
                frontiers = tracker.get_frontiers()
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=frontiers,
                    correlation_id=correlation_id,
                )

            elif action == 'get_status':
                result = ExecutionResult(
                    capability=self.name,
                    success=True,
                    data=tracker.get_status(),
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

        self._event_bus.emit(
            event_type=f'tech.{action}.completed',
            source='orchestrator',
            capability=self.name,
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed' if result.success else 'failed',
            payload={'action': action, 'success': result.success},
        )

        AuditLog.log(
            event_type=f'tech.{action}',
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
        self._tracker = None
        self.set_status(CapabilityStatus.OFFLINE)
        return True
