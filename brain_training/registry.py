"""Training run registry + event log + checkpoint manifest (spec S12/S14/S15).

Append-only, JSONL-backed.  Every record carries real observed metrics — never
fabricated — and never includes secrets (the event logger redacts known secret
var names from free-text detail).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import RUNS_DIR, EVENTS_DIR, CKPT_DIR  # noqa: F401  (paths)

# Re-export friendly aliases
from .config import (  # noqa: F401
    REPO_ROOT,
    SFT_KERNEL,
    SFT_CORPUS,
    BASE_MODEL_ID,
    BASE_REVISION,
    BrainTrainingConfig,
)

_REDACT_KEYS = re.compile(r"(?i)\b(JARVIS_HF_TOKEN|HF_TOKEN|JARVIS_BRAIN_API_KEY|KAGGLE_KEY|JARVIS_SECRET_KEY|N8N_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY|REPLICATE_API_KEY|POOLSIDE_API_KEY)\b")


def _redact_detail(detail: Any) -> Any:
    if isinstance(detail, str):
        return _REDACT_KEYS.sub("<redacted>", detail)
    if isinstance(detail, dict):
        return {k: ("<redacted>" if _REDACT_KEYS.fullmatch(k) else _redact_detail(v))
                for k, v in detail.items()}
    if isinstance(detail, list):
        return [_redact_detail(x) for x in detail]
    return detail


@dataclass
class TrainingEvent:
    """A single append-only lifecycle event (spec S14)."""
    event: str
    run_id: str
    model_id: str
    revision: str
    status: str
    dataset_revision: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    metrics: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"event": self.event, "run_id": self.run_id, "model_id": self.model_id,
             "revision": self.revision, "status": self.status,
             "dataset_revision": self.dataset_revision, "timestamp": self.timestamp,
             "metrics": self.metrics, "detail": _redact_detail(self.detail)}
        return d


class TrainingEventLogger:
    """Append-only event stream -> training_events.jsonl."""

    def __init__(self, path: Path | None = None) -> None:
        from .config import EVENTS_DIR
        self.path = path or (EVENTS_DIR / "training_events.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: TrainingEvent | str, **kwargs: Any) -> TrainingEvent:
        if isinstance(event, str):
            ev = TrainingEvent(
                event=event,
                run_id=kwargs.get("run_id", ""),
                model_id=kwargs.get("model_id", ""),
                revision=kwargs.get("revision", ""),
                status=kwargs.get("status", ""),
                dataset_revision=kwargs.get("dataset_revision", ""),
                metrics=kwargs.get("metrics", {}),
                detail=kwargs.get("detail", {}),
            )
        else:
            ev = event
        ev.detail = _redact_detail(ev.detail)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev.to_dict(), default=str) + "\n")
        return ev

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out


@dataclass
class RunRecord:
    run_id: str
    model_id: str
    base_model: str
    base_revision: str
    method: str            # LoRA | QLoRA
    status: str            # planned | running | paused | completed | failed | cancelled
    started_at: str
    ended_at: str = ""
    dataset_revision: str = ""
    dataset_sha256: str = ""
    latest_checkpoint: str = ""
    latest_train_loss: float | None = None
    latest_val_loss: float | None = None
    latest_lr: float | None = None
    latest_step: int = 0
    latest_tokens: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @staticmethod
    def new(model_id: str, method: str, base_model: str = BASE_MODEL_ID,
            base_revision: str = BASE_REVISION, dataset_revision: str = "",
            dataset_sha256: str = "") -> "RunRecord":
        return RunRecord(
            run_id=f"jarvis-brain-sft-{uuid.uuid4().hex[:8]}",
            model_id=model_id, base_model=base_model, base_revision=base_revision,
            method=method, status="planned",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            dataset_revision=dataset_revision, dataset_sha256=dataset_sha256,
        )


class RunRegistry:
    """Persistent registry of training runs -> runs/training_runs.jsonl."""

    def __init__(self, path: Path | None = None) -> None:
        from .config import RUNS_DIR
        self.path = path or (RUNS_DIR / "training_runs.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def upsert(self, rec: RunRecord) -> RunRecord:
        recs = self._all()
        out = []
        found = False
        for r in recs:
            if r["run_id"] == rec.run_id:
                out.append(rec.to_dict()); found = True
            else:
                out.append(r)
        if not found:
            out.append(rec.to_dict())
        self._write(out)
        return rec

    def _all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")

    def latest(self, model_id: str | None = None) -> dict | None:
        recs = self._all()
        if model_id:
            recs = [r for r in recs if r.get("model_id") == model_id]
        return recs[-1] if recs else None

    def latest_checkpoint(self, model_id: str | None = None) -> str | None:
        rec = self.latest(model_id)
        return rec.get("latest_checkpoint") if rec else None


@dataclass
class CheckpointMeta:
    """Manifest for a single training checkpoint (spec S12).

    Each checkpoint preserves: adapter + optimizer + scheduler + scaler + step +
    epoch + random state + training config + dataset revision + tokenizer hash.
    """
    run_id: str
    step: int
    epoch: int
    path: str
    dataset_revision: str
    dataset_sha256: str
    tokenizer_sha256: str
    model_revision: str
    base_revision: str
    base_model: str
    optimizer_state: bool = False
    scheduler_state: bool = False
    scaler_state: bool = False
    random_state: bool = False
    train_loss: float | None = None
    val_loss: float | None = None
    tokens: int = 0
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def write_checkpoint_manifest(meta: CheckpointMeta, out: Path | None = None) -> Path:
    p = out or (CKPT_DIR / f"{meta.run_id}-step-{meta.step:06d}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta.to_dict(), indent=2, default=str), encoding="utf-8")
    return p
