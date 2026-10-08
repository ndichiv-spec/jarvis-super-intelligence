"""The Training Advisor orchestrator.

Coordinates:
  * ``MetricsStore``            - historical, provenance-labelled metric buffer
  * ``run_all_detectors``        - the 18 statistical anomaly detectors
  * ``GeminiProvider`` (primary) / ``LocalProvider`` (fallback)
  * ``ProvenanceRecorder``       - Evidence / Knowledge Graph / Observatory fan-out

Advisory-only contract: provider selection, cache/dedup, interval gating, and
retry-with-fallback all live here.  No recommendation is ever applied to the
training loop automatically.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from .config import AdvisorConfig
from .schemas import (AdvisorResult, AdvisorStatus, Anomaly,
                      TrainingMetricsSnapshot)
from .metrics import MetricsStore
from .analysis import run_all_detectors
from .providers import GeminiProvider, LocalProvider
from .provenance import ProvenanceRecorder

log = logging.getLogger("silverwing.training_advisor")


def _hash_snapshots(snapshots: List[TrainingMetricsSnapshot]) -> str:
    h = hashlib.sha256()
    for s in snapshots:
        try:
            h.update(s.model_dump_json().encode("utf-8"))
        except Exception:
            h.update(str(getattr(s, "captured_at", "")).encode("utf-8"))
    h.update(b"|")
    h.update(str(len(snapshots)).encode("utf-8"))
    return h.hexdigest()[:16]


class TrainingAdvisor:
    def __init__(self, config: Optional[AdvisorConfig] = None, db: Any = None, ws: Any = None):
        self.config = config or AdvisorConfig()
        self.store = MetricsStore(self.config)
        if db is not None:
            self.store.set_runtime(db)
        self.db = db
        self.ws = ws
        self.primary = GeminiProvider(self.config)
        self.fallback = LocalProvider(self.config)
        self.recorder = ProvenanceRecorder(self.config, db, ws) if db is not None else None
        # cache: metric-window-hash -> AdvisorResult
        self._cache: Dict[str, AdvisorResult] = {}
        self._cache_ts: Dict[str, float] = {}
        self._last_result: Optional[AdvisorResult] = None
        self._last_run: float = 0.0
        self._autorun_task: Optional[asyncio.Task] = None

    # -------------------------------------------------------------- ingest
    async def ingest(self, raw: Dict[str, Any], run_id: Optional[str] = None) -> TrainingMetricsSnapshot:
        """Ingest a real training metric snapshot (OBSERVED provenance)."""
        snap = self.store.ingest(raw, run_id)
        if self.recorder is not None:
            await self.recorder.record_metrics(snap, snap.run_id)
        return snap

    # -------------------------------------------------------------- analyze
    async def analyze(self, force: bool = False) -> AdvisorResult:
        """Run the full analysis -> provider -> record pipeline.

        ``force=True`` bypasses cache + interval gating (used by explicit
        /analyze calls and tests).  ``force=False`` (autorun and the status
        endpoint) respects ``advisory_interval`` and ``cache_ttl``.
        """
        snapshots = self.store.history()
        key = _hash_snapshots(snapshots)
        now = time.time()

        if not force:
            cached = self._cache.get(key)
            if cached is not None and (now - self._cache_ts.get(key, 0.0)) < self.config.cache_ttl_seconds:
                return cached
            if (now - self._last_run) < self.config.advisory_interval_seconds and self._last_result is not None:
                return self._last_result

        anomalies = run_all_detectors(snapshots, self.config)
        metrics_summary = self.store.summary(snapshots)

        result: Optional[AdvisorResult] = None
        used_provider = "local"
        if self.config.gemini_authorized and self.primary.is_available():
            try:
                result = await self.primary.analyze(snapshots, anomalies, self.config, metrics_summary)
                used_provider = "gemini"
            except Exception as e:
                log.warning("Gemini analyze failed (%r); falling back to LocalProvider.", e)
                result = None
        if result is None:
            result = await self.fallback.analyze(snapshots, anomalies, self.config, metrics_summary)
            used_provider = result.provider

        result.cache_key = result.cache_key or key
        self._cache[key] = result
        self._cache_ts[key] = time.time()
        self._last_run = time.time()
        self._last_result = result

        if self.recorder is not None:
            try:
                await self.recorder.record_result(result)
            except Exception as e:
                log.warning("Provenance recording failed (non-fatal): %r", e)
        log.info("analyze done provider=%s status=%s recs=%d",
                 used_provider, result.status.value, len(result.recommendations))
        return result

    async def analyze_once(self) -> AdvisorResult:
        """Uncached, always-recompute analysis (used by the explicit endpoint)."""
        return await self.analyze(force=True)

    # ----------------------------------------------------------- queries
    def latest(self) -> Optional[AdvisorResult]:
        if self._last_result is not None:
            return self._last_result
        # Fall back to the newest persisted result.
        hist = getattr(self.db, "training_history", None) if self.db else None
        if hist:
            return hist[-1]
        return None

    async def status(self) -> Dict[str, Any]:
        latest = self.latest()
        snap_hist = self.store.history()
        rec = self.recorder if self.recorder else None
        return {
            "status": latest.status.value if latest else AdvisorStatus.UNKNOWN.value,
            "provider": latest.provider if latest else "none",
            "model": latest.model if latest else "none",
            "last_created_at": latest.created_at if latest else None,
            "recommendation_count": len(latest.recommendations) if latest else 0,
            "pending_approvals": sum(1 for r in (latest.recommendations if latest else [])
                                     if r.authorization_required and not r.approved),
            "gemini_authorized": self.config.gemini_authorized,
            "gemini_available": self.primary.is_available(),
            "autorun": bool(self.config.autorun),
            "snapshot_count": len(snap_hist),
            "cache_size": len(self._cache),
        }

    async def recommendations(self) -> List[Dict[str, Any]]:
        latest = self.latest()
        if not latest:
            return []
        return [r.model_dump(mode="json") for r in latest.recommendations]

    async def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.recorder is not None:
            return await self.recorder.history(limit)
        return [r.model_dump(mode="json") for r in (self._cache.values() or [])][-limit:]

    async def evidence(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.recorder is not None:
            return await self.recorder.evidence(limit)
        return []

    async def experiments(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.recorder is not None:
            return await self.recorder.experiments(limit)
        return []

    async def approve(self, recommendation_id: str, approver: str = "operator",
                      metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.recorder is not None:
            return await self.recorder.approve(recommendation_id, approver, metadata)
        # In-memory-only fallback for tests without a recorder.
        latest = self._last_result
        if latest:
            for rec in latest.recommendations:
                if rec.id == recommendation_id:
                    rec.approved = True
                    return {"approved": True, "approver": approver,
                            "recommendation_id": recommendation_id,
                            "at": __import__("datetime").datetime.utcnow().isoformat()}
        return {"approved": False, "error": "recommendation not found",
                "recommendation_id": recommendation_id}

    # ----------------------------------------------------------- tool iface
    async def tool_handler(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Unified Tool interface for /api/tools/invoke (tool='training_advisor')."""
        action = (input_data or {}).get("action", "analyze")
        try:
            if action in ("analyze", "recommend", "status"):
                result = await self.analyze(force=(action != "status"))
                return {"status": "ok", "provider": result.provider,
                        "summary": result.metrics_summary,
                        "result": result.model_dump(mode="json")}
            if action == "metrics":
                snaps = self.store.history()
                return {"status": "ok", "snapshots": [s.model_dump(mode="json") for s in snaps],
                        "summary": self.store.summary(snaps)}
            if action == "recommendations":
                return {"status": "ok", "recommendations": await self.recommendations()}
            if action == "history":
                return {"status": "ok", "history": await self.history(50)}
            if action == "evidence":
                return {"status": "ok", "evidence": await self.evidence()}
            if action == "experiments":
                return {"status": "ok", "experiments": await self.experiments()}
            if action == "approve":
                return {"status": "ok",
                        "result": await self.approve(
                            str(input_data.get("recommendation_id", "")),
                            str(input_data.get("approver", "operator")),
                            input_data.get("metadata"))}
            return {"status": "error", "error": f"unknown action: {action}"}
        except Exception as e:
            log.exception("training_advisor tool_handler failed")
            return {"status": "error", "error": str(e)}

    # ----------------------------------------------------------- autorun
    async def start_autorun(self) -> None:
        if not self.config.autorun:
            return
        self._autorun_task = asyncio.create_task(self._autorun_loop())

    async def _autorun_loop(self) -> None:
        try:
            while True:
                try:
                    await self.analyze()
                except Exception:
                    log.exception("autorun analyze failed")
                await asyncio.sleep(self.config.advisory_interval_seconds)
        except asyncio.CancelledError:
            raise

    def stop_autorun(self) -> None:
        if self._autorun_task is not None:
            self._autorun_task.cancel()
            self._autorun_task = None
