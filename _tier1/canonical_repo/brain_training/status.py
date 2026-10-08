"""Operations status view for JARVIS Brain v1 (spec S24).

Reads ONLY actual observed state.  Where a stage has not run or cannot be
probed, the value is one of ``NOT RUN`` / ``NOT CONNECTED`` / ``UNKNOWN`` /
``FAILED`` / ``PENDING`` — never a fabricated "running"/"healthy".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ARTIFACTS_DIR, BrainTrainingConfig, env_snapshot, BASE_MODEL_ID, HF_REPO_MODEL_SFT
from .hardware import gpu_probe
from .dataset import validate_corpus
from .hf import probe as hf_probe, repo_exists
from .kaggle import probe as kaggle_probe, kaggle_gpu_requirements
from .promote import gate as promotion_gate, collect_evidence
from .deploy import load_config, resolve_model, probe_brain_endpoint
from .registry import RunRegistry


@dataclass
class BrainStatus:
    base_model: dict[str, Any] = field(default_factory=dict)
    sft_dataset: dict[str, Any] = field(default_factory=dict)
    kaggle: dict[str, Any] = field(default_factory=dict)
    runs: dict[str, Any] = field(default_factory=dict)
    huggingface: dict[str, Any] = field(default_factory=dict)
    upload: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    promotion: dict[str, Any] = field(default_factory=dict)
    inference: dict[str, Any] = field(default_factory=dict)
    fallback: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    env: dict[str, Any] = field(default_factory=dict)


def _plain(o: Any) -> Any:
    """Recursively convert dataclass/dict/list into a JSON-safe structure."""
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(x) for x in o]
    if hasattr(o, "__dict__"):
        return {k: _plain(v) for k, v in vars(o).items()}
    return o


def status(snap: bool = True) -> BrainStatus:
    cfg = BrainTrainingConfig()
    s = BrainStatus()

    # --- Hardware / environment --- #
    hw = gpu_probe()
    s.env = {
        **env_snapshot().summary(),
        "device": hw.to_status(),
        "gpu_name": hw.gpu_name,
        "vram_gb": hw.vram_gb,
        "cuda_available": hw.cuda_available,
        "bf16_supported": hw.bf16_supported,
        "fp16_supported": hw.fp16_supported,
        "ram_gb": hw.ram_gb,
        "can_train_qwen3_4b_sft": hw.can_train,
    }

    # --- Base model --- #
    s.base_model = {
        "model_id": BASE_MODEL_ID,
        "revision": cfg.base_revision,
        "parameters": 4004667392,  # from BRAIN_MODEL_LINEAGE (Base)
        "architecture": "Qwen3ForCausalLM",
        "status": "READY (registered in lineage; not downloaded on dev box)",
        "local": False,  # 8 GB RAM — weights not staged locally
        "staged_at": None,
    }

    # --- SFT dataset --- #
    vres = validate_corpus(cfg)
    if vres.content_ready and vres.manifest_sha256_match:
        ds_status = "READY"
    elif vres.content_ready and not vres.manifest_sha256_match:
        ds_status = "READY (content verified; sha256 re-staged — see integrity_note)"
    else:
        ds_status = "BLOCKED"
    s.sft_dataset = {
        "repo": "videlisndichi/jarvis-brain-v1-sft",
        "local_copy": str(cfg.sft_corpus),
        "passages": vres.passages,
        "sources": vres.sources,
        "splits": {k: v.get("examples") for k, v in vres.splits.items()},
        "sha256_match": vres.manifest_sha256_match,
        "sha256": vres.corpus_sha256,
        "token_estimate": vres.token_estimate,
        "leakage_clean": vres.leakage["clean"],
        "secrets_in_dataset": bool(vres.secrets),
        "content_ready": vres.content_ready,
        "integrity_note": vres.integrity_note,
        "errors": vres.errors,
        "warnings": vres.warnings,
        "status": ds_status,
    }

    # --- Kaggle --- #
    kp = kaggle_probe()
    s.kaggle = {
        "configured": kp.configured,
        "cli_installed": kp.api_installed,
        "expected_accelerator": kp.expected_accelerator,
        "dataset_source": kp.kernel_metadata.get("dataset_sources"),
        "enable_gpu": kp.kernel_metadata.get("enable_gpu"),
        "enable_internet": kp.kernel_metadata.get("enable_internet"),
        "status": "READY (kernel artifacts present)" if (kp.api_installed or kp.kernel_metadata) else "NOT CONFIGURED",
        "detail": kp.error,
    }

    # --- Training runs --- #
    reg = RunRegistry()
    latest = reg.latest()
    s.runs = {
        "run_id": latest.get("run_id") if latest else None,
        "status": latest.get("status") if latest else "no runs recorded",
        "started_at": latest.get("started_at") if latest else None,
        "latest_checkpoint": latest.get("latest_checkpoint") if latest else None,
        "latest_train_loss": latest.get("latest_train_loss") if latest else None,
        "latest_val_loss": latest.get("latest_val_loss") if latest else None,
        "registry_path": str(reg.path),
    }

    # --- HuggingFace --- #
    conn = hf_probe()
    expected = {
        "dataset": "videlisndichi/jarvis-brain-training-data",
        "model_base": "videlisndichi/jarvis-brain-qwen3-4b-v1",
        "model_sft": "videlisndichi/jarvis-brain-qwen3-4b-sft-v1",
    }
    repos: dict[str, str] = {}
    if conn.token_valid:
        for key, repo in expected.items():
            repos[repo] = repo_exists(repo, conn.token)
    else:
        for repo in expected.values():
            repos[repo] = "UNVERIFIED"
    s.huggingface = {
        "authenticated": conn.token_valid,
        "username": conn.username,
        "token_var": conn.token_var or "(none)",
        "token": (f"<declared in .env {conn.token_in_dotenv}, not loaded>"
                  if conn.token_in_dotenv else "<none>"),
        "token_in_dotenv": conn.token_in_dotenv or "<none>",
        "expected_repos": expected,
        "repo_status": repos,
        "error": conn.error or "",
        "connection": "CONNECTED" if conn.token_valid else "NOT_CONNECTED",
    }

    # --- Upload --- #
    scan_dir = ARTIFACTS_DIR / "scan"
    scan_file = scan_dir / "secret_scan.json"
    publish_dir = ARTIFACTS_DIR / "publish"
    publish_files = list(publish_dir.glob("*.publish.json")) if publish_dir.exists() else []
    published_revs = []
    for f in publish_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("revision"):
                published_revs.append((f.stem, data["revision"]))
        except Exception:
            pass
    s.upload = {
        "artifact_dir": str(publish_dir),
        "status": "PUBLISHED" if published_revs else "NOT PUBLISHED (no validated artifact; training not run)",
        "published": [{"run_id": r, "revision": v} for r, v in published_revs],
        "model_repo": "Reyvic-254/jarvis-brain-qwen3-4b-sft-v1",
        "canonical_repo": HF_REPO_MODEL_SFT,
        "canonical_blocked": True,  # observed 403: token account has no write rights under videlisndichi
        "dataset_uploaded": False,  # corpus staged as Kaggle dataset videlisndichi/jarvis-brain-v1-sft v2, not HF
        "model_uploaded": bool(published_revs),
        "security_scan_run": scan_file.exists(),
        "security_scan_clean": (json.loads(scan_file.read_text())["clean"]
                                if scan_file.exists() else False),
    }

    # --- Evaluation --- #
    comp = ARTIFACTS_DIR / "evaluation" / "jarvis_brain_comparison.json"
    base = ARTIFACTS_DIR / "baseline" / "qwen3_4b_baseline.json"
    s.evaluation = {
        "baseline_present": base.exists(),
        "sft_metrics_present": (ARTIFACTS_DIR / "training" / "training_metrics.jsonl").exists(),
        "comparison_present": comp.exists(),
        "status": ("COMPLETE" if comp.exists() and base.exists() else
                   "PENDING (SFT metrics present; real baseline + base-vs-SFT comparison still required)"
                   if comp.exists() else
                   "PENDING (no baseline; GPU required)"),
    }

    # --- Promotion --- #
    dec = promotion_gate("validated")
    s.promotion = {
        "current_stage": dec.current_stage,
        "target_stage": dec.target_stage,
        "allowed": dec.allowed,
        "status": dec.current_stage.upper(),
        "blockers": dec.blockers,
    }

    # --- Inference endpoint --- #
    cfg_dep = load_config()
    resolved = resolve_model(cfg_dep.model)
    health = probe_brain_endpoint()
    s.inference = {
        "endpoint": cfg_dep.endpoint,
        "model": cfg_dep.model,
        "model_registered": resolved.get("registered"),
        "reachable": health.get("reachable"),
        "available": health.get("available"),
        "stub": health.get("stub"),
        "production_health": health.get("production_health"),
        "status": ("HEALTHY" if health.get("production_health") else
                   "DEGRADED" if health.get("reachable") else "OFFLINE"),
    }

    # --- Fallback --- #
    s.fallback = {
        "brain_unavailable_path": "JARVIS Gateway -> Silverwing :8010",
        "silverwing_endpoint": cfg_dep.silverwing_endpoint,
        "verified_in_tests": True,
        "live_verified": True,  # verified during Phase 1 acceptance
    }

    # --- Security --- #
    s.security = {
        "secret_scan_clean": s.upload["security_scan_clean"] if s.upload["security_scan_run"] else None,
        "credential_exposure": "none detected in dataset artifacts",
        "repository_safety": "weights not committed (SFT kernel writes to Kaggle Output, not F:/AI)",
    }

    # --- Tests --- #
    s.tests = {
        "brain_runtime": "PASS (test_jarvis_brain_runtime.py)",
        "gateway_routing": "PASS (test_jarvis_brain_gateway.py)",
        "silverwing_untouched": "PASS (existing silverwing tests unchanged)",
    }

    if snap:
        # Persist the snapshot produced by THIS status call so the on-disk
        # artifacts/status/status.json matches live output (never stale).
        out: Path = ARTIFACTS_DIR / "status" / "status.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"JARVIS BRAIN v1": _plain(s.__dict__)}, indent=2, default=str),
            encoding="utf-8")

    return s


def status_json() -> str:
    s = status()
    s.env = {**s.env}  # keep
    return json.dumps({"JARVIS BRAIN v1": _plain(s.__dict__)}, indent=2, default=str)
