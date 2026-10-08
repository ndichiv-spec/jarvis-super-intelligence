"""Evidence / provenance integration: mirrors Advisor results into Silverwing's
existing Evidence + Knowledge Graph + Observatory (events + WebSocket) systems.

To avoid an import cycle (``main`` imports ``training_advisor.advisor`` which
imports this module; this module imports ``backing.main``), the Silverwing model
classes (``Evidence``, ``KnowledgeEntity``, ``generate_id``) are imported
*lazily inside methods* at call time, after ``main`` is fully loaded.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import AdvisorConfig
from .schemas import AdvisorResult, TrainingMetricsSnapshot

log = logging.getLogger("silverwing.training_advisor.provenance")


def _now() -> str:
    return datetime.utcnow().isoformat()


def _safe_ws(ws) -> Optional[Any]:
    return ws


class ProvenanceRecorder:
    """Records advisor outputs into the canonical Silverwing evidence store."""

    def __init__(self, config: AdvisorConfig, db: Any, ws: Any = None):
        self.config = config
        self.db = db
        self.ws = ws
        # In-process approval ledger (advisory-only policy book). Replays to
        # Evidence via TRAINING_APPROVED events on each approve().
        self._approvals: List[Dict[str, Any]] = []

    # -------------------------------------------------------------- metrics
    async def record_metrics(self, snap: TrainingMetricsSnapshot, run_id: str) -> Dict[str, Any]:
        """Persist an ingested metric snapshot and fan it out on the Observatory."""
        # Mirror to the persisted metrics buffer.
        try:
            self.db.training_metrics.append(snap)
        except AttributeError:
            pass  # db may not be wired (unit tests)
        obs_keys = snap.observed_keys()
        try:
            ev = self.db.emit_event(
                "TRAINING_METRICS_INGESTED", "Training Advisor",
                {"run_id": run_id, "observed_keys": obs_keys,
                 "captured_at": snap.captured_at})
            event_id = ev.id
        except Exception:  # db may be a stub
            event_id = None

        payload = {
            "type": "TRAINING_METRICS_INGESTED",
            "source": "training_advisor",
            "run_id": run_id,
            "snapshot": snap.model_dump(mode="json"),
            "event_id": event_id,
        }
        ws = _safe_ws(self.ws)
        if ws is not None:
            try:
                await ws.broadcast(payload)
            except Exception as e:  # WS failures must never break ingestion
                log.warning("Observable broadcast failed: %r", e)
        return {"event_id": event_id, "run_id": run_id, "observed_keys": obs_keys}

    # --------------------------------------------------------------- result
    async def record_result(self, result: AdvisorResult) -> Dict[str, Any]:
        """Persist an AdvisorResult and record Evidence + a Knowledge entity."""
        try:
            self.db.training_history.append(result)
        except AttributeError:
            pass

        try:
            ev = self.db.emit_event(
                "TRAINING_ADVISOR_RESULT", "Training Advisor",
                {"status": result.status.value, "provider": result.provider,
                 "model": result.model, "cache_key": result.cache_key,
                 "recommendation_count": len(result.recommendations),
                 "created_at": result.created_at})
            event_id = ev.id
        except Exception:
            event_id = None

        evidence_ids: List[str] = []
        from main import Evidence, generate_id  # lazy: avoids import cycle
        for rec in result.recommendations:
            rec_id = rec.id if hasattr(rec, "id") else rec.get("id")
            action = rec.action if hasattr(rec, "action") else rec.get("action")
            reason = (rec.reason if hasattr(rec, "reason")
                      else rec.get("reason", ""))
            conf = rec.confidence if hasattr(rec, "confidence") else rec.get("confidence", 0.0)
            ev_obj = Evidence(
                id=generate_id(),
                source_id=result.provenance.run_id,
                source_title=f"Training Advisor ({result.provider})",
                source_type="training_advisor",
                evidence_text=str(reason),
                claim_text=f"recommend:{action}",
                confidence=float(conf) if conf is not None else 0.0,
                retrieved_at=result.created_at,
            )
            try:
                self.db.evidence[ev_obj.id] = ev_obj
                evidence_ids.append(ev_obj.id)
            except Exception:
                pass

        entity_id: Optional[str] = None
        try:
            from main import KnowledgeEntity, generate_id  # lazy
            stamp = result.created_at[:19].replace(":", "-")
            entity = KnowledgeEntity(
                id=generate_id(),
                name=f"training-advice-{result.provenance.run_id}-{stamp}",
                type="experiment",
                description=result.analysis,
                evidence_count=len(evidence_ids),
                properties={
                    "provider": result.provider,
                    "model": result.model,
                    "status": result.status.value,
                    "cache_key": result.cache_key,
                },
            )
            self.db.knowledge[entity.id] = entity
            entity_id = entity.id
        except Exception as e:
            log.warning("Could not persist Knowledge entity: %r", e)

        summary = {
            "type": "TRAINING_ADVISOR_RESULT",
            "source": "training_advisor",
            "status": result.status.value,
            "provider": result.provider,
            "cache_key": result.cache_key,
            "recommendation_count": len(result.recommendations),
            "evidence_ids": evidence_ids,
            "entity_id": entity_id,
            "event_id": event_id,
            "created_at": result.created_at,
        }
        ws = _safe_ws(self.ws)
        if ws is not None:
            try:
                await ws.broadcast(summary)
            except Exception as e:
                log.warning("Observable broadcast failed: %r", e)
        return {"event_id": event_id, "entity_id": entity_id,
                "evidence_ids": evidence_ids, "status": result.status.value,
                "provider": result.provider}

    # ----------------------------------------------------------- accessors
    async def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        out = []
        hist = getattr(self.db, "training_history", None) or []
        for r in hist[-limit:]:
            try:
                out.append(r.model_dump(mode="json"))
            except Exception:
                out.append(r if isinstance(r, dict) else {})
        return out

    async def evidence(self, limit: int = 100) -> List[Dict[str, Any]]:
        out = []
        ev = getattr(self.db, "evidence", None) or {}
        for e in list(ev.values())[-limit:]:
            try:
                out.append(e.model_dump(mode="json"))
            except Exception:
                out.append(e if isinstance(e, dict) else {})
        return out

    async def experiments(self, limit: int = 50) -> List[Dict[str, Any]]:
        out = []
        kg = getattr(self.db, "knowledge", None) or {}
        for k in list(kg.values()):
            try:
                if getattr(k, "type", None) == "experiment":
                    out.append(k.model_dump(mode="json"))
            except Exception:
                pass
        return out[-limit:]

    # ------------------------------------------------------------ approval
    async def approve(self, recommendation_id: str, approver: str = "operator",
                      metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Mark a recommendation as human-approved and log the decision.

        Approval does NOT execute any training mutation - it merely records
        authorization so an external operator/tool can act on it.
        """
        from main import generate_id  # lazy
        hist = getattr(self.db, "training_history", []) or []
        for result in hist:
            for rec in getattr(result, "recommendations", []) or []:
                rid = rec.id if hasattr(rec, "id") else rec.get("id")
                if rid == recommendation_id:
                    rec.approved = True
                    ap = {
                        "id": generate_id(),
                        "recommendation_id": recommendation_id,
                        "approver": approver,
                        "at": _now(),
                        "status": getattr(result, "status", None),
                        "metadata": metadata or {},
                    }
                    self._approvals.append(ap)
                    try:
                        self.db.emit_event(
                            "TRAINING_APPROVED", "Training Advisor",
                            {**ap})
                    except Exception:
                        pass
                    ws = _safe_ws(self.ws)
                    if ws is not None:
                        try:
                            await ws.broadcast({
                                "type": "TRAINING_APPROVED", "source": "training_advisor",
                                "recommendation_id": recommendation_id, "approver": approver,
                                "at": ap["at"]})
                        except Exception as e:
                            log.warning("Observable broadcast failed: %r", e)
                    return {"approved": True, "approver": approver,
                            "at": ap["at"], "recommendation_id": recommendation_id}
        return {"approved": False, "error": "recommendation not found",
                "recommendation_id": recommendation_id}

    def approvals(self) -> List[Dict[str, Any]]:
        return list(self._approvals)
