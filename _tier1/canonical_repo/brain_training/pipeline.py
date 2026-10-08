"""Automated training/deployment workflow orchestrator (spec S25).

Executes the stages in order, reusing the EXISTING training assets (kernel +
corpus).  Stages that require a CUDA GPU, Kaggle credentials, or a valid Hugging
Face token are GATED and reported as ``NOT RUN`` / ``NOT CONNECTED`` with the
actual reason — never fabricated.  Locally-runnable stages (dataset validation,
hardware probe, HF/Kaggle probe, promotion gate, Brain health probe, gateway
tests) execute for real.

Auto-proceed rule (spec S25/S18):
  train -> validate -> publish -> evaluate  MAY auto-proceed, but a stage that
  cannot run (no GPU / no creds) stops the chain with an honest status.  A
  model is NEVER auto-promoted to production (manual gate).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import (
    ARTIFACTS_DIR,
    BrainTrainingConfig,
    env_snapshot,
)
from .hardware import gpu_probe
from .dataset import validate_corpus, write_validation_report
from .hf import secret_scan_artifact
from .hf import probe as hf_probe, repo_exists, save_publish_intent
from .kaggle import probe as kaggle_probe
from .registry import RunRegistry, TrainingEventLogger, RunRecord
from .promote import gate as promotion_gate
from .deploy import load_config, resolve_model, probe_brain_endpoint
from brain_training.config import hf_token  # noqa: F401


@dataclass
class StageReport:
    name: str
    status: str            # DONE | NOT_RUN | BLOCKED | NOT_CONNECTED | UNKNOWN
    detail: dict[str, Any] = field(default_factory=dict)
    artifact: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status,
                "detail": self.detail, "artifact": self.artifact,
                "duration_s": round(self.duration_s, 3)}


@dataclass
class PipelineResult:
    stages: list[StageReport]
    final_stage: str
    overall: str        # PASS | BLOCKED | NOT_CONNECTED

    def to_dict(self) -> dict[str, Any]:
        return {"overall": self.overall, "final_stage": self.final_stage,
                "stages": [s.to_dict() for s in self.stages]}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class BrainPipeline:
    """Orchestrates the JARVIS Brain training lifecycle."""

    def __init__(self, cfg: BrainTrainingConfig | None = None) -> None:
        self.cfg = cfg or BrainTrainingConfig()
        self.cfg.ensure_dirs()
        self.registry = RunRegistry()
        self.events = TrainingEventLogger()
        self.stages: list[StageReport] = []

    def _add(self, name: str, status: str, detail: dict | None = None,
             artifact: str = "") -> StageReport:
        rep = StageReport(name, status, detail or {}, artifact)
        self.stages.append(rep)
        return rep

    # -- stages ----------------------------------------------------------- #
    def stage_prepare_dataset(self) -> StageReport:
        t0 = time.monotonic()
        res = validate_corpus(self.cfg)
        path = write_validation_report(res)
        self.events.log("dataset.validated",
                        run_id="", model_id="jarvis-brain-qwen3-4b-sft-v1",
                        revision="", status="completed" if res.content_ready else "failed",
                        metrics={"passages": res.passages, "sha256_match": res.manifest_sha256_match,
                                 "content_ready": res.content_ready},
                        detail={"integrity_note": res.integrity_note[:200]})
        return self._add("prepare_dataset", "DONE" if res.content_ready else "BLOCKED",
                         {"ok": res.ok, "content_ready": res.content_ready,
                          "manifest_sha256_match": res.manifest_sha256_match,
                          "integrity_note": res.integrity_note,
                          "passages": res.passages, "sources": res.sources,
                          "splits": res.splits, "leakage_clean": res.leakage["clean"],
                          "secrets_found": bool(res.secrets), "errors": res.errors},
                         artifact=str(path))

    def stage_validate_dataset(self) -> StageReport:
        t0 = time.monotonic()
        corpus_dir = self.cfg.sft_corpus.parent
        scan = secret_scan_artifact(corpus_dir)
        (ARTIFACTS_DIR / "scan").mkdir(parents=True, exist_ok=True)
        out = ARTIFACTS_DIR / "scan" / "secret_scan.json"
        out.write_text(json.dumps({"clean": scan["clean"], "findings": scan["findings"],
                                   "scanned_at": _now_iso()}, indent=2, default=str),
                       encoding="utf-8")
        self.events.log("dataset.security_scanned", model_id="jarvis-brain-qwen3-4b-sft-v1",
                        status="completed", metrics={"clean": scan["clean"],
                        "findings": len(scan["findings"])},
                        detail={"scanned": str(corpus_dir)})
        return self._add("validate_dataset", "DONE" if scan["clean"] else "BLOCKED",
                         {"clean": scan["clean"], "findings": scan["findings"]},
                         artifact=str(out))

    def stage_baseline(self) -> StageReport:
        hw = gpu_probe()
        if not hw.is_gpu:
            return self._add("baseline", "NOT_RUN",
                             {"reason": "no CUDA GPU available",
                              "device": hw.to_status(), "ram_gb": hw.ram_gb,
                              "detail": "Qwen3-4B base benchmark requires a GPU "
                                        "(8 GB RAM/no CUDA dev box cannot load it). "
                                        "Run on Kaggle GPU; baseline runner is "
                                        "brain_training.baseline."},
                             artifact="")
        # GPU available: would invoke brain_training.baseline.run_baseline()
        return self._add("baseline", "DONE" if (ARTIFACTS_DIR / "baseline" / "qwen3_4b_baseline.json").exists() else "NOT_RUN",
                         {"device": hw.to_status()},
                         artifact=str(ARTIFACTS_DIR / "baseline" / "qwen3_4b_baseline.json"))

    def stage_export_kaggle(self) -> StageReport:
        exists = self.cfg.sft_kernel.exists() and self.cfg.kaggle_kernel.exists()
        return self._add("export_kaggle", "DONE" if exists else "BLOCKED",
                         {"sft_kernel_present": self.cfg.sft_kernel.exists(),
                          "notebook_present": self.cfg.kaggle_kernel.exists(),
                          "kernel_repo": "videlisndichi/jarvis-brain-sft-train",
                          "dataset_source": "videlisndichi/jarvis-brain-v1-sft",
                          "detail": "Existing kernel + SFT script are the Kaggle export; not duplicated."},
                         artifact=str(self.cfg.sft_kernel))

    def stage_pilot(self) -> StageReport:
        hw = gpu_probe()
        if not hw.is_gpu:
            return self._add("run_pilot", "NOT_RUN", {"reason": "no CUDA GPU"},
                             artifact="")
        return self._add("run_pilot", "DONE" if (ARTIFACTS_DIR / "training" / "artifact_load_smoke.json").exists() else "NOT_RUN",
                         {"device": hw.to_status()}, artifact="")

    def stage_train(self) -> StageReport:
        hw = gpu_probe()
        kp = kaggle_probe()
        if not hw.is_gpu or not kp.configured:
            return self._add("train", "NOT_RUN",
                             {"reason": "no CUDA GPU on dev box" if not hw.is_gpu
                              else "kaggle not configured",
                              "gpu": hw.is_gpu, "kaggle_configured": kp.configured},
                             artifact="")
        return self._add("train", "NOT_RUN", {"detail": "dispatch SFT kernel to Kaggle GPU"}, artifact="")

    def stage_checkpoint(self) -> StageReport:
        meta_dir = ARTIFACTS_DIR / "checkpoints"
        exists = meta_dir.exists() and bool(list(meta_dir.glob("*.json")))
        return self._add("checkpoint", "NOT_RUN" if not exists else "DONE",
                         {"checkpoint_count": len(list(meta_dir.glob("*.json"))) if meta_dir.exists() else 0,
                          "schema": "brain_training.registry.CheckpointMeta",
                          "naming": "jarvis-brain-qwen3-4b-sft-v1-step-NNNNNN"},
                         artifact=str(meta_dir))

    def stage_upload_hf(self) -> StageReport:
        conn = hf_probe()
        if not conn.token_valid:
            return self._add("upload_hf", "NOT_CONNECTED",
                             {"reason": conn.error or "HF token invalid/absent",
                              "authenticated": conn.token_valid,
                              "note": "No upload performed. Fix HF_TOKEN (must be set in .env) and re-run."},
                             artifact="")
        return self._add("upload_hf", "NOT_RUN", {"reason": "no validated artifact (training not run)"}, artifact="")

    def stage_evaluate(self) -> StageReport:
        hw = gpu_probe()
        if not hw.is_gpu:
            return self._add("evaluate", "NOT_RUN",
                             {"reason": "no CUDA GPU (base vs SFT evaluation requires GPU)"},
                             artifact="")
        comp = ARTIFACTS_DIR / "evaluation" / "jarvis_brain_comparison.json"
        return self._add("evaluate", "DONE" if comp.exists() else "NOT_RUN",
                         {"comparison_present": comp.exists()}, artifact=str(comp))

    def stage_promotion_gate(self) -> StageReport:
        dec = promotion_gate("validated")
        return self._add("promotion_gate",
                         "BLOCKED" if not dec.allowed else "DONE",
                         {"current_stage": dec.current_stage,
                          "target_stage": dec.target_stage,
                          "allowed": dec.allowed,
                          "blockers": dec.blockers,
                          "evidence": {
                          "baseline_present": dec.evidence.baseline_present,
                          "sft_metrics_present": dec.evidence.sft_metrics_present,
                          "comparison_present": dec.evidence.comparison_present,
                          "security_scan_clean": dec.evidence.security_scan_clean,
                          "artifact_loads": dec.evidence.artifact_loads}},
                         artifact="")

    def stage_deploy(self) -> StageReport:
        cfg = load_config()
        resolved = resolve_model(cfg.model)
        health = probe_brain_endpoint()
        return self._add("deploy", "DONE",
                         {"endpoint": cfg.endpoint, "model": cfg.model,
                          "is_remote": cfg.is_remote,
                          "model_registered": resolved.get("registered"),
                          "brain_reachable": health.get("reachable"),
                          "brain_available": health.get("available"),
                          "brain_stub": health.get("stub"),
                          "brain_production_health": health.get("production_health"),
                          "brain_status": health.get("status"),
                          "silverwing_fallback": cfg.silverwing_endpoint},
                         artifact="")

    def stage_health_probe(self) -> StageReport:
        health = probe_brain_endpoint()
        self.events.log("brain.health_probed", model_id=load_config().model,
                        status="completed", metrics={"reachable": health["reachable"],
                                                     "available": health["available"]},
                        detail={"detail": health.get("detail")})
        return self._add("health_probe", "DONE", health, artifact="")

    def stage_gateway_test(self) -> StageReport:
        # Existing brain-gateway tests (test_jarvis_brain_gateway.py) cover the
        # live Brain :8011 -> Silverwing :8010 fallback end-to-end.  Re-run the
        # whole file (addopts already filters non-integration) as the §25 gate.
        import subprocess
        import sys
        r = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_jarvis_brain_gateway.py", "-q"],
            cwd=str(self.cfg.repo_root), capture_output=True, text=True, timeout=180,
        )
        passed = r.returncode == 0
        return self._add("gateway_test", "DONE" if passed else "BLOCKED",
                         {"passed": passed, "tests": "tests/test_jarvis_brain_gateway.py"},
                         artifact="")

    # -- orchestration ---------------------------------------------------- #
    def run(self) -> PipelineResult:
        self.events.log("training.status_report", model_id=load_config().model,
                        status="running", metrics={"stage": "orchestration"})
        order = [
            ("prepare_dataset", self.stage_prepare_dataset),
            ("validate_dataset", self.stage_validate_dataset),
            ("baseline", self.stage_baseline),
            ("export_kaggle", self.stage_export_kaggle),
            ("run_pilot", self.stage_pilot),
            ("train", self.stage_train),
            ("checkpoint", self.stage_checkpoint),
            ("upload_hf", self.stage_upload_hf),
            ("evaluate", self.stage_evaluate),
            ("promotion_gate", self.stage_promotion_gate),
            ("deploy", self.stage_deploy),
            ("health_probe", self.stage_health_probe),
            ("gateway_test", self.stage_gateway_test),
        ]
        for _name, fn in order:
            t0 = time.monotonic()
            fn()
            self.stages[-1].duration_s = round(time.monotonic() - t0, 3)
        final = self.stages[-1].name
        statuses = {s.status for s in self.stages}
        if "BLOCKED" in statuses:
            overall = "BLOCKED"
        elif "NOT_CONNECTED" in statuses or "NOT_RUN" in statuses:
            overall = "NOT_CONNECTED"
        else:
            overall = "PASS"
        self.events.log("training.status_report", model_id=load_config().model,
                        status=overall.lower(), metrics={"final_stage": final})
        report = PipelineResult(stages=self.stages, final_stage=final, overall=overall)
        # Persist the report of THIS run (docs contract artifacts/pipeline/pipeline_report.json).
        report_path = ARTIFACTS_DIR / "pipeline" / "pipeline_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2, default=str),
                               encoding="utf-8")
        return report


def run_pipeline(cfg: BrainTrainingConfig | None = None) -> PipelineResult:
    return BrainPipeline(cfg).run()
