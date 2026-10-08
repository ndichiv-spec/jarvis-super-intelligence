"""Versioned prompts + JSON schema for the Gemini provider.

Security notes
--------------
The system prompt is the primary defence against prompt injection: it
instructs the model to (a) emit ONLY the JSON object matching the schema,
(b) refuse to execute / mutate / rewrite any training configuration, and
(c) explicitly label any value it cannot ground in the supplied metrics as
UNKNOWN.  Client-side Pydantic validation (in ``providers``) is the
second, hard defence: anything that fails to validate is rejected and the
orchestrator falls back to the deterministic LocalProvider.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .config import AdvisorConfig
from .schemas import Anomaly, AnomalySeverity, Provenance, TrainingMetricsSnapshot

PROMPT_VERSION = "1.0"

_SYSTEM_PROMPT = """\
You are Silverwing's external AI/ML research advisor - an evidence-based
consultant that never touches the training loop. Your job is to read the
supplied training metrics (with their provenance labels) and the detected
anomalies, then return a JSON recommendation. You NEVER:
  * modify the optimizer, learning rate, scheduler, batch size, or any
    training hyperparameter - you only ADVISE;
  * execute code, shell commands, install packages, or launch training runs;
  * fabricate measurements - if a metric is UNKNOWN, say so.
Return EXACTLY one JSON object matching the schema in <SCHEMA>, and nothing
else. Do not add commentary, markdown fences, or preamble. If the supplied
data is insufficient to make a reliable call, set status to "unknown" and
recommend "collect_metrics". Label model confidence honestly (0.0-1.0).
You may cite OBSERVED, DERIVED, ESTIMATED, and UNKNOWN provenance only as
provided; never invent provenance.
"""


def system_prompt() -> str:
    return _SYSTEM_PROMPT


def _metric_line(name: str, mv) -> str:
    v = mv.value if mv.value is not None else mv.text
    prov = mv.provenance.value
    return f"  - {name}: {v} [{prov}, source={mv.source}]"


def build_user_prompt(snapshots: List[TrainingMetricsSnapshot],
                      anomalies: List[Anomaly], config: AdvisorConfig,
                      observed_count: int) -> str:
    lines = [f"Prompt version: {PROMPT_VERSION}"]
    lines.append(f"Model: {snapshots[-1].model_name if snapshots else 'unknown'} "
                 f"({snapshots[-1].architecture if snapshots else 'unknown'})")
    lines.append(f"Training run id: {snapshots[-1].run_id if snapshots else 'unknown'}")
    lines.append(f"Snapshots analysed: {len(snapshots)} (OBSERVED metric-cells: {observed_count})")

    if not snapshots:
        lines.append("No training metrics snapshots are available. The Silverwing model "
                     "state is a static stub; no live training loop is emitting metrics.")
    else:
        latest = snapshots[-1]
        lines.append("Latest snapshot metrics:")
        for f in ["step", "loss", "val_loss", "perplexity", "learning_rate", "grad_norm",
                  "tokens_per_second", "tokens_processed", "training_duration_seconds"]:
            mv = getattr(latest, f, None)
            if mv is not None:
                lines.append(_metric_line(f, mv))
        if latest.eval_metrics:
            lines.append("Evaluation metrics: " + ", ".join(f"{k}={v}" for k, v in latest.eval_metrics.items()))

    lines.append("\nDetected anomalies:")
    if not anomalies:
        lines.append("  (none)")
    for a in anomalies:
        lines.append(f"  - [{a.severity.value}] {a.title}: {a.description} (hint={a.recommendation_hint})")

    lines.append("\nTASK: produce a structured recommendation. For each recommendation, "
                 "explain what was observed, why it matters, the recommended action, the "
                 "expected effect, an honest confidence (0.0-1.0), and a risk level. "
                 "Any recommendation that could change training must mark "
                 "'authorization_required': true; pure advisory actions (keep_lr, "
                 "continue_training, investigate_instability, collect_metrics) may be "
                 "authorization_required=false.")
    return "\n".join(lines)


def gemini_response_schema() -> Dict[str, Any]:
    """JSON Schema the model is constrained to emit. Validated again client-side."""
    return {
        "type": "object",
        "properties": {
            "analysis": {"type": "string"},
            "status": {"type": "string",
                       "enum": ["healthy", "warning", "critical", "unknown"]},
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "reason": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "expected_effect": {"type": "string"},
                        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                        "authorization_required": {"type": "boolean"},
                        "sub_action": {"type": ["string", "null"]},
                        "target_metric": {"type": ["string", "null"]},
                        "parameters": {"type": "object"},
                    },
                    "required": ["action", "reason", "confidence", "expected_effect", "risk"],
                },
            },
            "anomalies": {"type": "array"},
            "metrics_summary": {"type": "object"},
            "provenance": {"type": "object"},
        },
        "required": ["analysis", "status", "recommendations"],
    }
