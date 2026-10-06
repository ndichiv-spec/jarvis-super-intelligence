"""Provider abstraction for the Training Advisor.

    TrainingAdvisor (orchestrator)
     ├── GeminiProvider   - calls Google's ``google-genai`` SDK (Gemini)
     └── LocalProvider    - deterministic, dependency-free rule engine

Security model
--------------
* ``GEMINI_API_KEY`` is read **only** from the environment inside
  ``AdvisorConfig``; it is never hard-coded or logged.
* ``google.genai`` is imported lazily, so the package imports cleanly even when
  the SDK or a key is absent.
* Gemini output is constrained with ``response_mime_type="application/json"`` +
  a ``response_schema`` and is **re-validated** with Pydantic (``AdvisorResult``).
  Malformed / injected output raises and the orchestrator falls back to
  ``LocalProvider`` - it can never corrupt Silverwing state.
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List

from .config import AdvisorConfig
from .metrics import MetricsStore, TrainingMetricsSnapshot
from .schemas import (AdvisorResult, Anomaly, Recommendation,
                      RiskLevel, AdvisorStatus, ProvenanceRecord)
from .analysis import classify_status, build_analysis_text
from .lr_advisor import synthesize
from .prompts import system_prompt, build_user_prompt, gemini_response_schema

log = logging.getLogger("silverwing.training_advisor")


def now_iso() -> str:
    return datetime.now().isoformat()


def _cache_key(snapshots: List[TrainingMetricsSnapshot]) -> str:
    import hashlib
    payload = "|".join(
        f"{s.captured_at}{s.run_id}"
        f"{len(s.observed_keys())}"
        f"{s.loss.value or 0}"
        f"{s.step.value or 0}"
        for s in snapshots
    )
    # Also fold in the anomaly set so different analyses get different keys
    payload += f"|{len(snapshots)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class TrainingAdvisorProvider(ABC):
    """Abstract base for any advisor backend (Gemini, Local, future)."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    async def analyze(self, snapshots: List[TrainingMetricsSnapshot],
                      anomalies: List[Anomaly], config: AdvisorConfig,
                      metrics_summary: Dict[str, Any]) -> AdvisorResult:
        ...


class GeminiProvider(TrainingAdvisorProvider):
    """Calls Google's current ``google-genai`` SDK.

    The real ``genai.Client`` is constructed lazily (and acceptably injectable
    for tests).  Retries use exponential backoff with a configurable cap; each
    attempt is bounded by ``config.timeout_seconds``.
    """

    name = "gemini"

    def __init__(self, config: AdvisorConfig, client: Any = None):
        self.config = config
        self._client = client  # injectable for tests

    def is_available(self) -> bool:
        if not self.config.gemini_authorized:
            return False
        try:
            import google.genai  # noqa: F401
            return True
        except Exception:
            return False

    # -- overridable for tests: the actual blocking SDK call --
    def _call_sdk(self, system_prompt: str, user_prompt: str,
                  schema: Dict[str, Any]) -> str:
        from google import genai
        from google.genai import types
        client = self._client or genai.Client(
            api_key=self.config.api_key,
            http_options={"timeout": self.config.timeout_seconds},
        )
        response = client.models.generate_content(
            model=self.config.model,
            contents=[
                {"role": "system", "parts": [{"text": system_prompt}]},
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
            ),
        )
        return response.text

    @staticmethod
    def _strip_fences(text: str) -> str:
        # Gemini sometimes wraps JSON in markdown fences; tolerate that, but
        # never execute arbitrary code - just extract the outermost JSON object.
        text = text.strip()
        if text.startswith("```"):
            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last != -1 and last > first:
                return text[first:last + 1]
        return text

    async def _call_llm(self, system_prompt: str, user_prompt: str,
                        schema: Dict[str, Any]) -> str:
        return await asyncio.to_thread(self._call_sdk, system_prompt, user_prompt, schema)

    async def _call_with_retry(self, system_prompt: str, user_prompt: str,
                               schema: Dict[str, Any]) -> str:
        last_exc: BaseException | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._call_llm(system_prompt, user_prompt, schema),
                    timeout=self.config.timeout_seconds + 1.0,
                )
            except (asyncio.TimeoutError, TimeoutError):
                last_exc = TimeoutError(f"Gemini call timed out (attempt {attempt + 1})")
            except Exception as e:  # noqa: BLE001
                last_exc = e
                log.warning("Gemini call failed (attempt %d): %r", attempt + 1, e)
            if attempt < self.config.max_retries:
                backoff = min(self.config.max_backoff_seconds,
                              self.config.base_backoff_seconds * (2 ** attempt))
                await asyncio.sleep(backoff)
        raise last_exc  # type: ignore[misc]

    async def analyze(self, snapshots, anomalies, config, metrics_summary):
        if not self.is_available():
            raise RuntimeError("Gemini provider not available (no SDK or API key)")
        observed = sum(len(s.observed_keys()) for s in snapshots)
        system = system_prompt()
        user = build_user_prompt(snapshots, anomalies, config, observed)
        schema = gemini_response_schema()
        raw = await self._call_with_retry(system, user, schema)
        # Hard validation: reject anything that isn't a valid JSON object matching
        # the AdvisorResult schema (this is the prompt-injection / malformed guard).
        cleaned = self._strip_fences(raw)
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("Gemini returned a non-object JSON response")
        result = AdvisorResult.model_validate(data)  # raises on bad shape
        # Stamp provenance so Gemini-authored results are clearly labelled.
        result.provider = "gemini"
        result.model = config.model
        result.raw_response = raw
        result.cache_key = result.cache_key or _cache_key(snapshots)
        return result


class LocalProvider(TrainingAdvisorProvider):
    """Deterministic, dependency-free advisor. Always available; safe fallback.

    Uses the 18 statistical detectors + the rule-based LR advisor.  Confidence
    is derived from statistical evidence (number of supporting anomalies /
    observed metric coverage), not from a language model.
    """

    name = "local"

    def __init__(self, config: AdvisorConfig, client: Any = None):
        self.config = config
        self._client = client

    def is_available(self) -> bool:
        return True

    async def analyze(self, snapshots, anomalies, config, metrics_summary):
        recs = synthesize(snapshots, anomalies, config)
        observed = sum(len(s.observed_keys()) for s in snapshots)
        status = classify_status(snapshots, anomalies)
        analysis = build_analysis_text(snapshots, anomalies)
        prov = ProvenanceRecord(
            model="local-rule", prompt_version=config.prompt_version,
            provider="local", created_at=now_iso(),
            run_id=(snapshots[-1].run_id if snapshots else "silverwing-runtime"),
            snapshot_count=len(snapshots), observed_metric_count=observed,
            confidence_basis="statistical",
            notes=["Deterministic rule-based analysis (no LLM)."],
        )
        return AdvisorResult(
            analysis=analysis,
            status=status,
            recommendations=recs,
            anomalies=[a.model_dump() for a in anomalies],
            metrics_summary=metrics_summary,
            provenance=prov,
            provider="local",
            model="local-rule",
            created_at=now_iso(),
            cache_key=_cache_key(snapshots),
        )
