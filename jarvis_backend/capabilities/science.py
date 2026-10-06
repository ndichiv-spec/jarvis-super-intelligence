"""
JARVIS SCIENCE ENGINE CAPABILITY
================================

Symbolic and numerical mathematical reasoning using SymPy, NumPy, and SciPy.

Actions:
- 'solve': Solve an algebraic equation
- 'derivative': Compute symbolic derivative
- 'integral': Compute symbolic integral
- 'integrate': Numerical integration
- 'limit': Compute limit
- 'series': Taylor series expansion
- 'determinant': Matrix determinant
- 'inverse': Matrix inverse
- 'eigenvalues': Matrix eigenvalues
- 'roots': Find numerical roots
- 'optimize': Numerical optimization
- 'mean'/'std'/'median': Statistical operations
- 'monte_carlo': Monte Carlo simulation
- 'hypothesis': Formulate a scientific hypothesis
- 'test_hypothesis': Simulate and test a hypothesis
- 'proof': Construct a step-by-step proof
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


class ScienceCapability(Capability):
    """
    Scientific reasoning capability for JARVIS.

    Wraps ScienceEngine to provide symbolic math (SymPy), numerical
    computation (NumPy/SciPy), hypothesis testing, and proof construction.
    """

    name = "science.engine"
    version = "1.0.0"
    category = "science"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._engine = None
        self._sympy_available = False
        self._numpy_available = False
        self._scipy_available = False

    def _get_engine(self):
        """Lazy-load the science engine."""
        if self._engine is None:
            try:
                from jarvis_backend.research.science_engine import ScienceEngine
                self._engine = ScienceEngine()
                self._sympy_available = True
                self._numpy_available = True
                self._scipy_available = True
            except ImportError:
                pass
        return self._engine

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check — verify scientific libraries."""
        sympy_ok = False
        numpy_ok = False
        scipy_ok = False

        try:
            import sympy  # noqa: F401
            sympy_ok = True
        except ImportError:
            pass

        try:
            import numpy  # noqa: F401
            numpy_ok = True
        except ImportError:
            pass

        try:
            import scipy  # noqa: F401
            scipy_ok = True
        except ImportError:
            pass

        self._sympy_available = sympy_ok
        self._numpy_available = numpy_ok
        self._scipy_available = scipy_ok

        ready = sympy_ok or numpy_ok
        return {
            'status': CapabilityStatus.READY if ready else CapabilityStatus.NOT_CONFIGURED,
            'healthy': ready,
            'sympy_available': sympy_ok,
            'numpy_available': numpy_ok,
            'scipy_available': scipy_ok,
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a scientific reasoning operation."""
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        start_time = time.time()
        correlation_id = context.correlation_id

        engine = self._get_engine()
        if engine is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Science engine not available",
                error_type="NOT_AVAILABLE",
                correlation_id=correlation_id,
            )

        try:
            result = await engine.solve(request)
            result_obj = ExecutionResult(
                capability=self.name,
                success=True,
                data=result,
                correlation_id=correlation_id,
                metrics={'domain': result.get('domain', ''), 'verified': result.get('verified', False)},
            )
        except Exception as e:
            result_obj = ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id,
            )

        result_obj.latency_ms = (time.time() - start_time) * 1000.0

        self._event_bus.emit(
            event_type=f'science.solve.completed',
            source='orchestrator',
            capability=self.name,
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed' if result_obj.success else 'failed',
            payload={'operation': request.get('operation', 'solve'), 'success': result_obj.success},
        )

        AuditLog.log(
            event_type=f'science.solve',
            source=self.name,
            capability=self.name,
            user_id=context.user_id,
            session_id=context.session_id,
            action=request.get('operation', 'solve'),
            result='success' if result_obj.success else 'error',
        )

        return result_obj

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self._engine = None
        self.set_status(CapabilityStatus.OFFLINE)
        return True
