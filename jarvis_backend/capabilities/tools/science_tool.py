"""
Science Tool - wraps the ScienceEngine for tool/connector execution.

This tool provides symbolic math (SymPy), numerical computation
(NumPy/SciPy), hypothesis testing, and proof construction as a
JARVIS tool that can be invoked through the MCP bridge.
"""
from __future__ import annotations

import sys
import os
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class ToolBase:
    """Base class for all tools."""
    name: str = "base"
    version: str = "1.0.0"
    category: str = "tool"

    async def health(self) -> Dict[str, Any]:
        return {'status': 'unknown', 'healthy': False}

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        raise NotImplementedError


class ScienceTool(ToolBase):
    """Scientific reasoning tool - uses SymPy, NumPy, SciPy."""

    name = "science"
    version = "0.1.0"
    category = "science"
    description = "Scientific reasoning: symbolic math, numerical computation, hypothesis testing"

    def __init__(self):
        self._engine = None

    async def health(self) -> Dict[str, Any]:
        deps = {}
        for mod_name, label in [("sympy", "sympy"), ("numpy", "numpy"), ("scipy", "scipy")]:
            try:
                __import__(mod_name)
                deps[label] = True
            except ImportError:
                deps[label] = False

        healthy = deps.get("sympy", False) or deps.get("numpy", False)
        return {
            'status': 'ok' if healthy else 'unavailable',
            'healthy': healthy,
            'dependencies': deps,
        }

    def _get_engine(self):
        if self._engine is None:
            try:
                from jarvis_backend.research.science_engine import ScienceEngine
                self._engine = ScienceEngine()
            except ImportError:
                self._engine = None
        return self._engine

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        if action != "solve":
            return {
                "success": False,
                "error": f"Unknown science action: {action}",
                "error_type": "INVALID_ACTION",
            }
        engine = self._get_engine()
        if not engine:
            return {'success': False, 'error': 'Science engine not available', 'error_type': 'ENGINE_UNAVAILABLE'}

        try:
            import asyncio
            result = await engine.solve(params)
            if isinstance(result, dict) and 'error' in result:
                return {'success': False, 'error': result.get('error', 'Unknown error'),
                        'error_type': result.get('error_type', 'ERROR')}
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e), 'error_type': type(e).__name__}

    async def shutdown(self):
        pass


__all__ = ['ScienceTool', 'ToolBase']
