"""Promotion gate for JARVIS Brain v1 (spec S18).

Promotion is EVIDENCE-driven and NEVER automatic.  A model advances through
``experimental -> candidate -> validated -> promoted`` only when the required
artifacts exist AND the honest checks pass:

  * baseline metrics present (qwen3_4b_baseline.json/md)
  * SFT metrics present (training_metrics.jsonl / training_summary.json)
  * base-vs-SFT comparison present (jarvis_brain_comparison.json)
  * security scan clean (no secrets in publish artifact)
  * artifact loads correctly (adapter reload + generation smoke)

On a dev box where no training has run, every input is absent, so the gate is
``BLOCKED`` — reported honestly, not fabricated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ARTIFACTS_DIR, SFT_KERNEL, BASE_MODEL_ID, BASE_REVISION

STAGES = ("experimental", "candidate", "validated", "promoted")


@dataclass
class PromotionEvidence:
    baseline_present: bool = False
    baseline_path: str = ""
    sft_metrics_present: bool = False
    sft_metrics_path: str = ""
    comparison_present: bool = False
    comparison_path: str = ""
    security_scan_clean: bool = False
    artifact_loads: bool = False
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PromotionDecision:
    current_stage: str
    target_stage: str
    allowed: bool
    reason: str
    evidence: PromotionEvidence
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_stage": self.current_stage,
            "target_stage": self.target_stage,
            "allowed": self.allowed,
            "reason": self.reason,
            "blockers": self.blockers,
            "evidence": {
                "baseline_present": self.evidence.baseline_present,
                "sft_metrics_present": self.evidence.sft_metrics_present,
                "comparison_present": self.evidence.comparison_present,
                "security_scan_clean": self.evidence.security_scan_clean,
                "artifact_loads": self.evidence.artifact_loads,
                "baseline_path": self.evidence.baseline_path,
                "sft_metrics_path": self.evidence.sft_metrics_path,
                "comparison_path": self.evidence.comparison_path,
                "errors": self.evidence.errors,
                "notes": self.evidence.notes,
            },
        }


def collect_evidence(base_dir: Path | None = None) -> PromotionEvidence:
    """Inspect ACTUAL artifacts (never invent)."""
    base = base_dir or ARTIFACTS_DIR
    ev = PromotionEvidence()

    # Baseline (spec S16) — produced by brain_training.baseline / the kernel.
    baseline_json = base / "baseline" / "qwen3_4b_baseline.json"
    baseline_md = base / "baseline" / "qwen3_4b_baseline.md"
    if baseline_json.exists():
        ev.baseline_present, ev.baseline_path = True, str(baseline_json)
    elif baseline_md.exists():
        ev.baseline_present, ev.baseline_path = True, str(baseline_md)

    # SFT metrics (produced by SFT kernel / brain_training.pilot.train)
    sft_metrics = base / "training" / "training_metrics.jsonl"
    sft_summary = base / "training" / "training_summary.json"
    if sft_metrics.exists():
        ev.sft_metrics_present = True
        ev.sft_metrics_path = str(sft_metrics)
    elif sft_summary.exists():
        ev.sft_metrics_present = True
        ev.sft_metrics_path = str(sft_summary)

    # Comparison (base vs SFT, spec S17)
    comp = base / "evaluation" / "jarvis_brain_comparison.json"
    if comp.exists():
        ev.comparison_present, ev.comparison_path = True, str(comp)

    # Security scan (spec S27)
    scan = base / "scan" / "secret_scan.json"
    if scan.exists():
        try:
            data = json.loads(scan.read_text(encoding="utf-8"))
            ev.security_scan_clean = bool(data.get("clean", False))
        except Exception as exc:  # noqa: BLE001
            ev.errors.append(f"secret scan unreadable: {exc}")

    # Artifact load smoke (spec S12: adapter save/reload + generation)
    load_marker = base / "training" / "artifact_load_smoke.json"
    if load_marker.exists():
        try:
            ev.artifact_loads = bool(json.loads(load_marker.read_text())
                                     .get("generation_works", False))
        except Exception:
            ev.artifact_loads = False

    if not ev.baseline_present:
        ev.notes.append("baseline not run (requires CUDA GPU + Qwen3-4B download; dev box is CPU-only 8 GB).")
    if not ev.sft_metrics_present:
        ev.notes.append("no SFT run recorded (requires Kaggle GPU; not configured on dev box).")
    return ev


def gate(target_stage: str = "validated", base_dir: Path | None = None) -> PromotionDecision:
    """Evaluate whether `target_stage` is reachable from current evidence."""
    ev = collect_evidence(base_dir)
    blockers: list[str] = []

    if target_stage == "candidate":
        if not ev.sft_metrics_present:
            blockers.append("SFT metrics missing (training not completed)")
    elif target_stage == "validated":
        if not ev.sft_metrics_present:
            blockers.append("SFT metrics missing")
        if not ev.baseline_present:
            blockers.append("baseline metrics missing")
        if not ev.comparison_present:
            blockers.append("base-vs-SFT comparison missing")
        if not ev.security_scan_clean:
            blockers.append("security scan not clean or absent")
        if not ev.artifact_loads:
            blockers.append("adapter reload / generation smoke not verified")
    elif target_stage == "promoted":
        # validated is prerequisite
        sub = gate("validated", base_dir=base_dir)
        if not sub.allowed:
            blockers.append("validated stage not reached: " + "; ".join(sub.blockers))
        blockers.append("promotion to production requires manual approval "
                        "(spec S18: never auto-promote on training completion)")

    allowed = (not blockers) and (target_stage != "promoted")
    if target_stage == "promoted" and not blockers:
        # even if evidence is full, production promotion is a manual gate
        allowed = False
        blockers.append("manual promotion gate (spec S18)")

    # current stage inference
    if not ev.sft_metrics_present:
        current = "experimental"
    elif ev.comparison_present and ev.baseline_present and ev.security_scan_clean and ev.artifact_loads:
        current = "validated"
    elif ev.sft_metrics_present:
        current = "candidate"
    else:
        current = "experimental"

    return PromotionDecision(
        current_stage=current,
        target_stage=target_stage,
        allowed=allowed,
        reason=("all evidence present" if allowed else
                "insufficient evidence / manual gate" if target_stage == "promoted" else
                "; ".join(blockers) if blockers else "blocked"),
        evidence=ev,
        blockers=blockers,
    )
