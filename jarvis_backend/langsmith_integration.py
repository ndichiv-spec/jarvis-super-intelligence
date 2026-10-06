"""LangSmith integration for JARVIS observability.

Extends the existing OpenTelemetry instrumentation with prompt tracing,
token usage, and cost attribution for LLM provider calls.  Falls back to
in-memory recording when LANGSMITH_API_KEY is not configured (graceful
degradation).

This module is safe to import even if ``langsmith`` is not installed —
all public functions guard with a try/except.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.langsmith_integration")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
# Approximate per-1K-token pricing (USD) for major providers as of 2025.
# Source: provider docs (OpenAI, Anthropic, Google, etc.).
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # model_name_or_prefix -> {"prompt": $/1k, "completion": $/1k}
    "gpt-4o":           {"prompt": 0.0050, "completion": 0.0150},
    "gpt-4o-mini":      {"prompt": 0.000150, "completion": 0.000600},
    "gpt-4-turbo":      {"prompt": 0.0100, "completion": 0.0300},
    "gpt-4":            {"prompt": 0.0300, "completion": 0.0600},
    "gpt-3.5-turbo":    {"prompt": 0.0005, "completion": 0.0015},
    "claude-3-5-sonnet": {"prompt": 0.0030, "completion": 0.0150},
    "claude-3-5-haiku":  {"prompt": 0.000250, "completion": 0.0010},
    "claude-3-opus":     {"prompt": 0.0150, "completion": 0.0750},
    "gemini-1.5-flash":  {"prompt": 0.000075, "completion": 0.000300},
    "gemini-1.5-pro":    {"prompt": 0.001250, "completion": 0.005000},
    "llama3-70b":        {"prompt": 0.000650, "completion": 0.000900},
    "nvidia-nemotron":   {"prompt": 0.0010, "completion": 0.0010},
    "nvidia/nemotron":   {"prompt": 0.0010, "completion": 0.0010},
    "qwen":              {"prompt": 0.000080, "completion": 0.000080},
}


# --------------------------------------------------------------------------- #
# Cost calculation
# --------------------------------------------------------------------------- #
def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate USD cost for a given model and token usage.

    Uses prefix matching against MODEL_PRICING so 'gpt-4o-mini-2024-...' matches 'gpt-4o'.
    Returns 0.0 if the model is not in the pricing table (unknown cost).
    """
    prompt_k = prompt_tokens / 1000.0
    completion_k = completion_tokens / 1000.0

    # Try exact match first
    price = MODEL_PRICING.get(model_name)
    if price is None:
        # Try prefix match
        for prefix, price_entry in MODEL_PRICING.items():
            if model_name.startswith(prefix):
                price = price_entry
                break

    if price is None:
        logger.debug("No pricing data for model '%s'; cost = $0.00", model_name)
        return 0.0

    cost = (prompt_k * price["prompt"]) + (completion_k * price["completion"])
    return round(cost, 6)


# --------------------------------------------------------------------------- #
# LangSmith trace recording
# --------------------------------------------------------------------------- #
class LangSmithTracer:
    """Thin wrapper around langsmith that records traces with fallback.

    When LANGSMITH_API_KEY is set, uses the real langsmith client.
    When not set, records traces in an in-memory buffer for local inspection.
    """

    def __init__(self):
        self._client: Any = None
        self._in_memory: list = []
        self._max_in_memory = 500
        self._api_key = os.environ.get("LANGSMITH_API_KEY")
        self._project = os.environ.get("LANGSMITH_PROJECT", "jarvis")
        self._setup()

    def _setup(self):
        """Initialise the langsmith client (or fall back to in-memory)."""
        if not self._api_key:
            logger.info("LANGSMITH_API_KEY not set; using in-memory trace buffer")
            return

        try:
            from langsmith import Client
            self._client = Client(
                api_key=self._api_key,
                api_url=os.environ.get("LANGSMITH_API_URL", "https://api.smith.langchain.com"),
            )
            # Create project if it doesn't exist
            try:
                self._client.create_project(project_name=self._project, upsert=True)
            except Exception:
                pass  # Project may already exist
            logger.info("LangSmith client initialised (project=%s)", self._project)
        except ImportError:
            logger.warning("langsmith package not installed; using in-memory trace buffer")
        except Exception as e:
            logger.warning("Failed to init LangSmith client: %s; using in-memory", e)

    @property
    def available(self) -> bool:
        """True if real LangSmith tracing is available."""
        return self._client is not None

    @property
    def available_or_buffered(self) -> bool:
        """True if either real LangSmith or in-memory buffer is active."""
        return True  # Always available — falls back to in-memory

    def record_trace(
        self,
        run_name: str,
        run_type: str = "chain",
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Optional[str]:
        """Record a trace/run in LangSmith (or in-memory fallback).

        Returns the run_id if a trace was recorded, None if tracing failed.
        """
        now = datetime.now(timezone.utc).isoformat()
        trace = {
            "run_name": run_name,
            "run_type": run_type,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "metadata": metadata or {},
            "start_time": start_time,
            "end_time": end_time,
            "timestamp": now,
        }

        if self._client:
            try:
                run = self._client.create_run(
                    project_name=self._project,
                    name=run_name,
                    run_type=run_type,
                    inputs=inputs,
                    outputs=outputs,
                    metadata=metadata,
                    start_time=datetime.fromtimestamp(start_time, tz=timezone.utc) if start_time else None,
                    end_time=datetime.fromtimestamp(end_time, tz=timezone.utc) if end_time else None,
                )
                return run.id if hasattr(run, "id") else str(run)
            except Exception as e:
                logger.warning("LangSmith trace recording failed: %s; falling back", e)
                self._client = None  # Disable further attempts

        # In-memory fallback
        self._in_memory.append(trace)
        if len(self._in_memory) > self._max_in_memory:
            self._in_memory = self._in_memory[-self._max_in_memory:]
        return f"mem-{len(self._in_memory)}"

    def record_llm_call(
        self,
        model: str,
        prompt: str,
        response: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        correlation_id: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Record an LLM provider call with cost attribution."""
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        metadata = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "correlation_id": correlation_id,
            **extra,
        }
        self.record_trace(
            run_name=f"llm.{model}",
            run_type="llm",
            inputs={"prompt": prompt[:2000]},  # Truncate for safety
            outputs={"response": response[:2000]},
            metadata=metadata,
        )
        return metadata

    def record_capability_execution(
        self,
        capability: str,
        action: str,
        request: Dict[str, Any],
        result: Dict[str, Any],
        latency_ms: float,
        correlation_id: str,
        user_id: str = "",
    ) -> Dict[str, Any]:
        """Record a full capability execution trace (mirrors OTel span)."""
        metadata = {
            "capability": capability,
            "action": action,
            "correlation_id": correlation_id,
            "user_id": user_id,
            "latency_ms": round(latency_ms, 2),
        }
        self.record_trace(
            run_name=f"capability.{capability}.{action}",
            run_type="chain",
            inputs={"request": request},
            outputs={"result": result},
            metadata=metadata,
        )
        return metadata

    def get_in_memory_traces(self) -> list:
        """Return all in-memory traces (for local inspection / testing)."""
        return list(self._in_memory)

    def clear_in_memory(self) -> int:
        """Clear the in-memory trace buffer. Returns count of cleared traces."""
        count = len(self._in_memory)
        self._in_memory.clear()
        return count


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #
_tracer: Optional[LangSmithTracer] = None


def get_langsmith_tracer() -> LangSmithTracer:
    """Return the singleton LangSmithTracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTracer()
    return _tracer


def langsmith_available() -> bool:
    """Check if langsmith package is importable."""
    try:
        import langsmith  # noqa: F401
        return True
    except ImportError:
        return False
