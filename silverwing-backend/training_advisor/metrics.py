"""Metrics ingestion + historical store for the Training Advisor.

Two sources of metrics:

* ``ingest``  - real metrics POSTed by a live training loop (OBSERVED).
* ``runtime_snapshot`` - what the *currently running* Silverwing backend can
  observe right now (runtime telemetry, OBSERVED) plus the static
  ``ModelState`` stub fields, which are labelled **UNKNOWN** because they are
  hard-coded defaults rather than live measurements.

No metric is ever fabricated.  When a value is absent it is recorded as
``Provenance.UNKNOWN`` with a note pointing operators to
``/api/training/metrics`` so a real loop can supply it.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import AdvisorConfig
from .schemas import MetricValue, Provenance, TrainingMetricsSnapshot

# Metric attributes on TrainingMetricsSnapshot that carry a single MetricValue.
SNAPSHOT_METRIC_FIELDS = [
    "step", "total_steps", "epoch", "loss", "val_loss", "perplexity",
    "learning_rate", "weight_decay",
    "grad_norm", "grad_mean", "grad_std", "max_grad_abs", "clipping_applied",
    "optimizer", "optimizer_state", "scheduler", "scheduler_state",
    "batch_size", "sequence_length",
    "tokens_processed", "tokens_per_second", "train_throughput",
    "checkpoint_path", "checkpoint_step", "parameter_count",
    "cpu_util", "ram_util", "gpu_util", "vram_used_mb", "vram_total_mb",
    "training_duration_seconds",
]

# Fields whose value is categorical text rather than a number.
_TEXT_FIELDS = {"optimizer", "optimizer_state", "scheduler", "scheduler_state",
                "checkpoint_path"}

_STUB_NOTE = ("Static ModelState stub (Laboratory/model endpoint); no live "
              "training instrumentation. POST real metrics to /api/training/metrics.")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _to_metric(value: Any, source: str, note: Optional[str] = None) -> Optional[MetricValue]:
    """Best-effort coercion of a raw value into an OBSERVED MetricValue."""
    if isinstance(value, bool):
        return MetricValue.observed(float(value), source, note)
    if isinstance(value, (int, float)):
        return MetricValue.observed(float(value), source, note)
    if value is None:
        return None
    return MetricValue.observed(str(value), source, note)  # text path via .observed(str)


class MetricsStore:
    """In-memory historical buffer of ``TrainingMetricsSnapshot`` objects.

    Snapshots ingested here are also mirrored to ``db.training_history`` (via the
    advisor orchestrator) so that analysis survives restarts; the in-memory
    buffer is the fast path for trend detection within a running process.
    """

    def __init__(self, config: AdvisorConfig):
        self.config = config
        self.snapshots: List[TrainingMetricsSnapshot] = []
        self._lock = threading.Lock()
        self._db: Any | None = None

    def set_runtime(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------ ingest
    def ingest(self, raw: Dict[str, Any], run_id: Optional[str] = None) -> TrainingMetricsSnapshot:
        raw = raw or {}
        run_id = run_id or raw.get("run_id") or raw.get("run") or "silverwing-training"
        snap = TrainingMetricsSnapshot(
            captured_at=raw.get("captured_at") or _now_iso(),
            run_id=str(run_id),
            model=str(raw.get("model", "silverwing-decoder-v2")),
            model_name=str(raw.get("model_name", "Silverwing-Decoder-V2")),
            architecture=str(raw.get("architecture", "transformer-decoder")),
            status=str(raw.get("status", "training")),
        )

        for fname in SNAPSHOT_METRIC_FIELDS:
            if fname in raw and raw[fname] is not None:
                mv = _to_metric(raw[fname], "training_loop")
                if mv is not None:
                    setattr(snap, fname, mv)

        if raw.get("dataset_stats"):
            snap.dataset_stats = {str(k): float(v) for k, v in raw["dataset_stats"].items()
                                  if isinstance(v, (int, float))}
        if raw.get("eval_metrics"):
            snap.eval_metrics = {str(k): (float(v) if isinstance(v, (int, float)) else v)
                                 for k, v in raw["eval_metrics"].items()}

        snap.error_logs = [str(x) for x in (raw.get("error_logs") or [])]
        snap.warning_logs = [str(x) for x in (raw.get("warning_logs") or [])]

        # DERIVED: perplexity <-> loss
        if snap.loss.value is None and snap.perplexity.value is not None:
            snap.loss = MetricValue.derived(math.log(max(snap.perplexity.value, 1e-9)), "derived:ln(perplexity)",
                                            "loss ≈ ln(perplexity)")
        if snap.perplexity.value is None and snap.loss.value is not None and snap.loss.value > 0:
            snap.perplexity = MetricValue.derived(math.exp(snap.loss.value), "derived:exp(loss)")

        # DERIVED: throughput from tokens_processed + duration
        if (snap.tokens_processed.value is not None and snap.training_duration_seconds.value
                and snap.training_duration_seconds.value > 0):
            dur = snap.training_duration_seconds.value
            tps = snap.tokens_processed.value / dur
            src = "derived:tokens_processed/training_duration"
            snap.tokens_per_second = MetricValue.derived(tps, src)
            snap.train_throughput = MetricValue.derived(tps, src)

        # Label absent metric fields as UNKNOWN with an operator-facing note.
        for fname in SNAPSHOT_METRIC_FIELDS:
            mv = getattr(snap, fname)
            if (mv.provenance == Provenance.UNKNOWN and mv.value is None
                    and mv.text is None and not mv.note):
                setattr(snap, fname, MetricValue.unknown(
                    "training_loop", "metric not reported by training loop"))
        self._append(snap)
        return snap

    def _append(self, snap: TrainingMetricsSnapshot) -> None:
        with self._lock:
            self.snapshots.append(snap)
            if len(self.snapshots) > max(self.config.max_history, 1):
                self.snapshots = self.snapshots[-max(self.config.max_history, 1):]

    # ------------------------------------------------------------- runtime obs
    def runtime_snapshot(self) -> TrainingMetricsSnapshot:
        snap = TrainingMetricsSnapshot(
            captured_at=_now_iso(), run_id="silverwing-runtime",
            model="silverwing-decoder-v2", model_name="Silverwing-Decoder-V2",
            architecture="transformer-decoder", status="training")
        if self._db is not None:
            try:
                uptime = (datetime.utcnow() - self._db.start_time).total_seconds()
                snap.training_duration_seconds = MetricValue.observed(
                    max(uptime, 0.0), "runtime", "wall-clock uptime since db.start_time")
            except Exception:
                pass
            try:
                snap.error_logs = [f"{e.type}:{e.payload}" for e in self._db.events
                                   if isinstance(getattr(e, "type", None), str)
                                   and "error" in e.type.lower()]
                snap.warning_logs = [f"{e.type}:{e.payload}" for e in self._db.events
                                     if isinstance(getattr(e, "type", None), str)
                                     and "warn" in e.type.lower()]
            except Exception:
                pass
        # All training-specific metrics remain UNKNOWN (no live loop instrumented).
        for fname in SNAPSHOT_METRIC_FIELDS:
            if fname == "training_duration_seconds":
                continue
            setattr(snap, fname, MetricValue.unknown("laboratory/model_stub", _STUB_NOTE))
        return snap

    # ------------------------------------------------------------- accessors
    def history(self, limit: Optional[int] = None) -> List[TrainingMetricsSnapshot]:
        with self._lock:
            h = list(self.snapshots)
        if limit:
            h = h[-limit:]
        return h

    def all(self) -> List[TrainingMetricsSnapshot]:
        return self.history()

    def series(self, field: str) -> List[float]:
        out = []
        for s in self.snapshots:
            mv = getattr(s, field, None)
            if isinstance(mv, MetricValue) and mv.value is not None:
                out.append(mv.value)
        return out

    def latest(self) -> Optional[TrainingMetricsSnapshot]:
        with self._lock:
            return self.snapshots[-1] if self.snapshots else None

    def summary(self, snapshots: List[TrainingMetricsSnapshot]) -> Dict[str, Any]:
        latest = snapshots[-1] if snapshots else None
        obs = 0
        for s in snapshots:
            obs += len(s.observed_keys())
        return {
            "n_snapshots": len(snapshots),
            "captured_at": latest.captured_at if latest else None,
            "run_id": latest.run_id if latest else None,
            "observed_metric_count": obs,
            "latest": latest.as_dict() if latest else {},
        }
