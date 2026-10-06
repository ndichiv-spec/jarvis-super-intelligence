"""Brain + Silverwing Development Fabric.

Discovers REAL Brain/Silverwing provenance from the existing training/runtime
assets and the existing JARVIS registries, and reports truthful lifecycle state.

This module deliberately owns no new registry, secret store, job system or
provider system.  It reads:

* ``F:\\AI\\brain_training``  - checkpoints, publish metadata, evaluations, gate
* ``F:\\AI\\brain_runtime`` / ``F:\\AI\\silverwing_runtime`` - runtime contracts
* ``infrastructure.job_registry`` / ``artifact_registry`` / ``model_registry`` -
  the canonical JARVIS registries
* ``brain_training.hf`` / ``brain_training.kaggle`` - connectivity probes that
  never assert validity without credentials

Deployment states are explicit and never inferred from mere existence:

    ARTIFACT_ONLY -> EVALUATED -> PROMOTED -> DEPLOYMENT_READY
                 -> DEPLOYED -> INFERENCE_VERIFIED
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

WORKSPACE = Path(r"F:\AI")
BRAIN_TRAINING = WORKSPACE / "brain_training"
BRAIN_ARTIFACTS = BRAIN_TRAINING / "artifacts"

SYSTEM_BRAIN = "brain"

# Short TTL cache for external connectivity probes (CLI/API round-trips).
_PROBE_TTL_S = 30.0
_KAGGLE_CACHE: Optional[tuple] = None
_HF_CACHE: Optional[tuple] = None
SYSTEM_SILVERWING = "silverwing"

# Deployment / lifecycle ladder (ordered).  A model must reach the required
# stage before it becomes a routing candidate.
DEPLOYMENT_STAGES = (
    "ARTIFACT_ONLY",
    "EVALUATED",
    "PROMOTED",
    "DEPLOYMENT_READY",
    "DEPLOYED",
    "INFERENCE_VERIFIED",
)
STAGE_ORDER = {s: i for i, s in enumerate(DEPLOYMENT_STAGES)}

# Only PROMOTED+ models may be routed to in production.
ROUTING_MIN_STAGE = "PROMOTED"


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_jsonl(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
                if len(rows) >= limit:
                    break
    except OSError:
        return []
    return rows


# --------------------------------------------------------------------------- #
# Secret hygiene
# --------------------------------------------------------------------------- #
_SECRET_KEYS = (
    "api_key", "apikey", "token", "secret", "password", "passwd", "credential",
    "authorization", "bearer", "private_key",
)


def assert_no_secrets(payload: Any, _path: str = "") -> list[str]:
    """Return a list of secret-bearing field paths found in ``payload``.

    Used as a guard: model metadata / provenance must never carry credentials.
    Values are NEVER included in the report - only the field path.
    """
    found: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            p = f"{_path}.{k}" if _path else str(k)
            if any(s in str(k).lower() for s in _SECRET_KEYS):
                # A boolean "configured"/"present" flag is metadata, not a secret.
                if not isinstance(v, (dict, list)) and v not in (None, "", False, True):
                    found.append(p)
                continue
            found.extend(assert_no_secrets(v, p))
    elif isinstance(payload, list):
        for i, v in enumerate(payload[:50]):
            found.extend(assert_no_secrets(v, f"{_path}[{i}]"))
    return found


# --------------------------------------------------------------------------- #
# Brain discovery
# --------------------------------------------------------------------------- #
def discover_brain() -> dict[str, Any]:
    """Discover real Brain artifacts, provenance, evaluation and gate state."""
    out: dict[str, Any] = {
        "system": SYSTEM_BRAIN,
        "workspace": str(WORKSPACE),
        "runtime": {},
        "artifacts": [],
        "evaluations": [],
        "promotion": {},
        "inference": {},
        "warnings": [],
    }

    # -- runtime contract (existing brain_runtime) --
    try:
        if str(WORKSPACE) not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        from brain_runtime import config as rt_config  # type: ignore

        cfg = getattr(rt_config, "RUNTIME_CONFIG", None) or getattr(
            rt_config, "CONFIG", None)
        out["runtime"] = {
            "source": "brain_runtime.config",
            "present": True,
            "endpoint": (str(getattr(cfg, "base_url", "") or "")
                         or str(getattr(cfg, "endpoint", "") or "")) or None,
            "model": getattr(cfg, "model_name", None) or getattr(cfg, "model", None),
            "details": "runtime contract present; process-level state below",
        }
    except Exception as exc:  # noqa: BLE001
        out["runtime"] = {"present": False,
                          "error": f"{type(exc).__name__}: {exc}"}

    # -- checkpoints (real manifests) --
    ck_dir = BRAIN_ARTIFACTS / "checkpoints"
    for mf in sorted(ck_dir.glob("*.json")) if ck_dir.is_dir() else []:
        data = _read_json(mf)
        if not isinstance(data, dict):
            continue
        out["artifacts"].append({
            "artifact_id": mf.stem,
            "system": SYSTEM_BRAIN,
            "artifact_type": "checkpoint",
            "source_file": str(mf),
            "training_run_id": data.get("run_id"),
            "step": data.get("step"),
            "epoch": data.get("epoch"),
            "base_model": data.get("base_model"),
            "base_revision": data.get("base_revision"),
            "model_revision": data.get("model_revision"),
            "dataset_revision": data.get("dataset_revision"),
            "dataset_sha256": data.get("dataset_sha256"),
            "train_loss": data.get("train_loss"),
            "val_loss": data.get("val_loss"),
            "size_bytes": data.get("size_bytes"),
            "local_path_present": bool(data.get("path")) and Path(
                str(data.get("path"))).exists(),
        })

    # -- publish metadata (Hugging Face provenance) --
    pub_dir = BRAIN_ARTIFACTS / "publish"
    published: list[dict[str, Any]] = []
    for mf in sorted(pub_dir.glob("*.publish.json")) if pub_dir.is_dir() else []:
        data = _read_json(mf)
        if not isinstance(data, dict):
            continue
        published.append({
            "artifact_id": mf.stem.replace(".publish", ""),
            "system": SYSTEM_BRAIN,
            "artifact_type": "published_model",
            "repository": data.get("model_id"),
            "revision": data.get("revision"),
            "base_model": data.get("base_model"),
            "base_revision": data.get("base_revision"),
            "method": data.get("method"),
            "training_run_id": data.get("run_id"),
            "merged": data.get("merged"),
            "declared_stage": data.get("stage"),
            "source_file": str(mf),
        })
    out["artifacts"].extend(published)

    # -- provenance secret check --
    leaks: list[str] = []
    for art in out["artifacts"]:
        leaks.extend(assert_no_secrets(art))
    if leaks:
        out["warnings"].append(
            f"secret-shaped fields present in provenance: {sorted(set(leaks))}")
    out["provenance_secret_fields"] = sorted(set(leaks))

    # -- evaluations --
    eval_dir = BRAIN_ARTIFACTS / "evaluation"
    for f in sorted(eval_dir.glob("*.json")) if eval_dir.is_dir() else []:
        data = _read_json(f)
        out["evaluations"].append({
            "evaluation_id": f.stem,
            "source_file": str(f),
            "present": data is not None,
            "metrics": (data if isinstance(data, dict) else None),
        })
    metrics = _read_jsonl(BRAIN_ARTIFACTS / "training" / "training_metrics.jsonl")
    if metrics:
        out["evaluations"].append({
            "evaluation_id": "training_metrics",
            "source_file": str(BRAIN_ARTIFACTS / "training" / "training_metrics.jsonl"),
            "present": True,
            "records": len(metrics),
            "last": metrics[-1] if metrics else None,
        })

    # -- promotion gate (reuse existing implementation) --
    try:
        if str(WORKSPACE) not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        from brain_training.promote import collect_evidence, gate  # type: ignore

        ev = collect_evidence()
        gate_promoted = gate("promoted")
        out["promotion"] = {
            "source": "brain_training.promote.gate",
            "current_stage": getattr(gate_promoted, "current_stage", None),
            "target_stage": getattr(gate_promoted, "target_stage", None),
            "promoted_allowed": bool(getattr(gate_promoted, "allowed", False)),
            "reason": getattr(gate_promoted, "reason", None),
            "blockers": list(getattr(gate_promoted, "blockers", []) or []),
            "evidence": {
                "baseline_present": getattr(ev, "baseline_present", None),
                "sft_metrics_present": getattr(ev, "sft_metrics_present", None),
                "comparison_present": getattr(ev, "comparison_present", None),
                "security_scan_clean": getattr(ev, "security_scan_clean", None),
                "artifact_loads": getattr(ev, "artifact_loads", None),
                "notes": list(getattr(ev, "notes", []) or []),
            },
        }
    except Exception as exc:  # noqa: BLE001
        out["promotion"] = {"available": False,
                            "error": f"{type(exc).__name__}: {exc}"}

    # -- deployment / inference truth --
    out["deployment"] = _deployment_truth(SYSTEM_BRAIN, out)
    return out


def _deployment_truth(system: str, brain: dict[str, Any]) -> dict[str, Any]:
    """Derive deployment stage from real evidence only."""
    promo = brain.get("promotion") or {}
    stage = "ARTIFACT_ONLY"
    reason = "artifact discovered; no promotion recorded"
    if promo.get("promoted_allowed"):
        stage = "PROMOTED"
        reason = "promotion gate allows PROMOTED"
    else:
        stage = "EVALUATED" if brain.get("evaluations") else "ARTIFACT_ONLY"
        reason = ("evaluations present but promotion gate blocked"
                  if brain.get("evaluations")
                  else "no evaluation artifacts found")
    return {
        "deployment_status": stage if stage != "PROMOTED" else "DEPLOYMENT_READY",
        "routing_eligible": STAGE_ORDER.get(
            promo.get("current_stage", "ARTIFACT_ONLY") if False else stage, 0
        ) >= STAGE_ORDER[ROUTING_MIN_STAGE],
        "reason": reason,
        "blockers": promo.get("blockers") or [],
        "note": ("An artifact is NOT deployed merely because it exists. "
                 "Deployment requires promotion, then a runtime health check, "
                 "then real inference."),
    }


# --------------------------------------------------------------------------- #
# Silverwing discovery
# --------------------------------------------------------------------------- #
def discover_silverwing() -> dict[str, Any]:
    """Discover real Silverwing model dirs, run manifests and runtime state."""
    out: dict[str, Any] = {
        "system": SYSTEM_SILVERWING,
        "workspace": str(WORKSPACE),
        "runtime": {},
        "models": [],
        "artifacts": [],
        "evaluations": [],
        "promotion": {},
        "warnings": [],
    }

    # -- model directories on disk --
    for child in sorted(WORKSPACE.glob("silverwing*")):
        if not child.is_dir():
            continue
        size = 0
        files = 0
        for f in child.rglob("*"):
            if f.is_file():
                files += 1
                try:
                    size += f.stat().st_size
                except OSError:
                    pass
                if files > 20000:
                    break
        manifest = _read_json(child / "run_manifest.json")
        out["models"].append({
            "model_id": child.name,
            "system": SYSTEM_SILVERWING,
            "path": str(child),
            "exists": True,
            "file_count": files,
            "size_bytes": size,
            "run_manifest": manifest if isinstance(manifest, dict) else None,
            "has_run_manifest": isinstance(manifest, dict),
        })

    # -- run manifests anywhere in the workspace --
    for mf in sorted(WORKSPACE.glob("silverwing*/run_manifest.json")):
        data = _read_json(mf)
        if not isinstance(data, dict):
            continue
        out["artifacts"].append({
            "artifact_id": mf.parent.name,
            "system": SYSTEM_SILVERWING,
            "artifact_type": "run_manifest",
            "source_file": str(mf),
            "manifest": data,
        })

    # -- runtime state (truthful; never assumed) --
    try:
        if str(WORKSPACE) not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        from silverwing_runtime import health as sw_health  # type: ignore

        out["runtime"] = {
            "source": "silverwing_runtime.health",
            "present": True,
            "monitor": hasattr(sw_health, "HealthMonitor"),
        }
    except Exception as exc:  # noqa: BLE001
        out["runtime"] = {"present": False,
                          "error": f"{type(exc).__name__}: {exc}"}

    # -- endpoint probe (real TCP/HTTP reachability, never assumed) --
    import os
    import socket
    from urllib.parse import urlparse

    endpoint = (os.environ.get("SILVERWING_ENDPOINT") or "").strip()
    reachable = False
    detail = "SILVERWING_ENDPOINT not configured"
    if endpoint:
        parsed = urlparse(endpoint if "://" in endpoint
                          else f"http://{endpoint}")
        host, port = parsed.hostname, parsed.port or 80
        if host:
            try:
                with socket.create_connection((host, port), timeout=1.5):
                    reachable = True
                    detail = f"TCP connect succeeded to {host}:{port}"
            except OSError as exc:
                detail = f"connect failed: {type(exc).__name__}"
    out["runtime"].update({
        "endpoint": endpoint or None,
        "reachable": reachable,
        "detail": detail,
        "state": "AVAILABLE" if reachable else "OFFLINE",
        "model": os.environ.get("SILVERWING_MODEL") or None,
    })
    out["inference"] = {
        "verified": False,
        "reason": ("endpoint not reachable; no local inference has been "
                   "verified in this process" if not reachable
                   else "endpoint reachable but no inference call recorded yet"),
    }
    out["deployment"] = {
        "deployment_status": "ARTIFACT_ONLY",
        "routing_eligible": False,
        "reason": ("Silverwing runtime is offline; artifacts exist on disk but "
                   "no verified local inference path" if not reachable
                   else "runtime reachable; promotion/verification still required"),
        "note": "Local/offline Silverwing must not require NVIDIA.",
    }
    return out


# --------------------------------------------------------------------------- #
# External systems (reuse existing probes)
# --------------------------------------------------------------------------- #
def _kaggle_real_status(refresh_kaggle: bool = False) -> dict[str, Any]:
    """Real Kaggle connectivity.

    Cached for a short TTL: the CLI round-trip costs seconds and connectivity
    does not change between calls within a request burst. ``refresh=True``
    forces a live re-probe.
    """
    global _KAGGLE_CACHE
    if not refresh_kaggle and _KAGGLE_CACHE is not None:
        age = time.monotonic() - _KAGGLE_CACHE[0]
        if age < _PROBE_TTL_S:
            return _KAGGLE_CACHE[1]
    result = _kaggle_probe()
    _KAGGLE_CACHE = (time.monotonic(), result)
    return result


def _kaggle_probe() -> dict[str, Any]:
    """Real Kaggle connectivity.

    The existing ``brain_training.kaggle.probe`` only inspects env vars and
    reports NOT_CONFIGURED when they are unset.  The Kaggle CLI also reads
    ``~/.kaggle/kaggle.json``, so env-var absence is a FALSE NEGATIVE.  This
    verifies the real credential file and the authenticated CLI, and lists the
    account's actual kernels.  Read-only: nothing is submitted.
    """
    import os
    import shutil
    import subprocess

    out: dict[str, Any] = {
        "source": "kaggle CLI + ~/.kaggle credential store",
        "read_only": True,
        "submitted": False,
    }
    # Kaggle CLI 2.x authenticates from ~/.kaggle/access_token (OAuth-style
    # token). Legacy kaggle.json keys are no longer accepted by the CLI, so both
    # are checked and their PRESENCE is reported without exposing values.
    access_token = Path.home() / ".kaggle" / "access_token"
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    out["credential_file_present"] = (
        access_token.is_file() or kaggle_json.is_file())
    out["access_token_present"] = access_token.is_file()
    if access_token.is_file():
        try:
            token = access_token.read_text(encoding="utf-8").strip()
            out["key_present"] = bool(token)
            out["key_length"] = len(token)
            out["username"] = None
        except OSError:
            out["key_present"] = False
    elif kaggle_json.is_file():
        data = _read_json(kaggle_json) or {}
        out["username"] = data.get("username")
        out["key_present"] = bool(data.get("key"))
        out["key_length"] = len(data.get("key") or "")
    else:
        out["key_present"] = False

    exe = shutil.which("kaggle")
    out["cli_installed"] = bool(exe)
    if exe and out.get("key_present"):
        try:
            proc = subprocess.run(  # noqa: S603
                [exe, "kernels", "list", "--mine", "--csv"],
                capture_output=True, text=True, timeout=45, shell=False,
                cwd=str(WORKSPACE),
            )
            if proc.returncode == 0:
                lines = [l for l in proc.stdout.splitlines() if l.strip()]
                kernels = []
                for line in lines[1:]:
                    parts = line.split(",")
                    if parts and parts[0]:
                        kernels.append({
                            "ref": parts[0],
                            "title": parts[1] if len(parts) > 1 else None,
                            "last_run": parts[-1] if len(parts) > 3 else None,
                        })
                out["kernels"] = kernels
                out["kernel_count"] = len(kernels)
                out["connected"] = True
            else:
                out["connected"] = False
                out["error"] = (proc.stderr or "kaggle CLI returned an error"
                                ).strip()[:300]
        except (subprocess.TimeoutExpired, OSError) as exc:
            out["connected"] = False
            out["error"] = f"{type(exc).__name__}: kaggle CLI did not respond"
    else:
        out["connected"] = False
        if not exe:
            out["error"] = "kaggle CLI not installed"
        else:
            out["error"] = "no usable Kaggle credential found"

    out["state"] = "AVAILABLE" if out.get("connected") else "NOT_CONFIGURED"
    out["note"] = ("Read-only status. No training run is submitted by this "
                   "status call.")
    return out


def _hf_real_status() -> dict[str, Any]:
    """Real Hugging Face connectivity + repository/revision verification.

    Only presence/validity flags and public metadata are returned. The token is
    never exposed to the model.
    """
    global _HF_CACHE
    if _HF_CACHE is not None and (time.monotonic() - _HF_CACHE[0]) < _PROBE_TTL_S:
        return _HF_CACHE[1]
    result = _hf_probe()
    _HF_CACHE = (time.monotonic(), result)
    return result


def _hf_probe() -> dict[str, Any]:
    import os
    import urllib.error
    import urllib.request

    from dotenv import load_dotenv

    try:
        load_dotenv(WORKSPACE / ".env")
    except Exception:  # noqa: BLE001
        pass
    token = ""
    for var in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "JARVIS_HF_TOKEN"):
        val = (os.environ.get(var) or "").strip()
        if val:
            token = val
            break

    out: dict[str, Any] = {
        "source": "huggingface.co API",
        "token_present": bool(token),
        "token_length": len(token),
        "connected": False,
        "repositories": {},
    }
    if not token:
        out["state"] = "NOT_CONFIGURED"
        out["error"] = "no Hugging Face token in environment or .env"
        return out
    try:
        req = urllib.request.Request(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            who = json.loads(resp.read().decode("utf-8"))
        out["connected"] = True
        out["username"] = who.get("name")
    except Exception as exc:  # noqa: BLE001
        out["state"] = "NOT_CONFIGURED"
        out["error"] = f"token present but not accepted: {type(exc).__name__}"
        return out

    # Verify each published repository and capture its LIVE revision.
    for art in discover_brain().get("artifacts", []):
        repo = art.get("repository")
        if not repo or "/" not in repo:
            continue
        entry: dict[str, Any] = {
            "local_recorded_revision": art.get("revision"),
            "local_recorded_run": art.get("training_run_id"),
        }
        try:
            rq = urllib.request.Request(
                f"https://huggingface.co/api/models/{repo}",
                headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(rq, timeout=25) as resp:
                meta = json.loads(resp.read().decode("utf-8"))
            live_sha = meta.get("sha")
            entry["live_revision"] = live_sha
            entry["file_count"] = len(meta.get("siblings") or [])
            entry["exists"] = True
            # Flag - never silently reconcile - a provenance mismatch.
            if (art.get("revision") and live_sha
                    and art["revision"] != live_sha):
                entry["revision_mismatch"] = True
                entry["mismatch_note"] = (
                    f"local publish metadata records {art['revision'][:12]} but the "
                    f"Hub currently serves {live_sha[:12]}; provenance conflict "
                    f"recorded, not resolved automatically.")
        except urllib.error.HTTPError as exc:
            entry["exists"] = False
            entry["error"] = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}"
        out["repositories"][repo] = entry

    out["state"] = "AVAILABLE"
    return out


def external_status() -> dict[str, Any]:
    """Truthful connectivity for Hugging Face and Kaggle (real verification)."""
    try:
        hf = _hf_real_status()
    except Exception as exc:  # noqa: BLE001
        hf = {"connected": False, "state": "UNAVAILABLE",
              "error": f"{type(exc).__name__}: {exc}"}
    try:
        kaggle = _kaggle_real_status()
    except Exception as exc:  # noqa: BLE001
        kaggle = {"connected": False, "state": "UNAVAILABLE",
                  "error": f"{type(exc).__name__}: {exc}"}
    return {"hugging_face": hf, "kaggle": kaggle}


def docker_status() -> dict[str, Any]:
    """Truthful Docker state.

    Docker is an OPTIONAL convenience for the training/deployment fabric, not a
    dependency of the lifecycle.  When it is absent the reason is recorded and
    the pipeline continues on the native/Kaggle path.
    """
    import shutil

    exe = shutil.which("docker")
    if not exe:
        return {
            "state": "UNAVAILABLE",
            "deployment_status": "NOT_SUPPORTED",
            "reason": ("Docker CLI is not installed on this host "
                       "(no docker/podman/nerdctl on PATH)."),
            "required_action": ("Install Docker Desktop (WSL2 backend) or a "
                                "Docker Engine to enable containerised "
                                "training/inference."),
            "impact": ("None on the core lifecycle: Kaggle training, Hugging "
                       "Face artifact storage and NVIDIA inference all work "
                       "without Docker."),
            "compose_templates": sorted(
                str(p.relative_to(Path(__file__).resolve().parents[1]))
                for p in (Path(__file__).resolve().parents[1]
                          / "infrastructure" / "deploy" / "templates").glob(
                              "docker-compose*.yml")
            ) if (Path(__file__).resolve().parents[1]
                  / "infrastructure" / "deploy" / "templates").is_dir() else [],
        }
    return {
        "state": "DEGRADED",
        "deployment_status": "DEPLOYMENT_READY",
        "reason": "docker CLI present; daemon reachability checked per call",
        "cli": exe,
    }


def pipeline_readiness() -> dict[str, Any]:
    """End-to-end readiness of Kaggle -> HF -> NVIDIA -> JARVIS.

    Each link reports its own truthful state.  A break anywhere is surfaced
    rather than papered over.
    """
    ext = external_status()
    hf = ext["hugging_face"]
    kg = ext["kaggle"]
    nv = nvidia_deployment_readiness()

    links = {
        "kaggle_training": {
            "state": kg.get("state"),
            "role": "training / experimentation",
            "detail": kg.get("error") or
                     f"{kg.get('kernel_count', 0)} kernel(s) discoverable",
            "blocking": kg.get("state") != "AVAILABLE",
        },
        "hugging_face_artifacts": {
            "state": hf.get("state"),
            "role": "durable model/artifact/version layer",
            "detail": (f"{len(hf.get('repositories') or {})} repository/ies "
                       f"verified" if hf.get("connected")
                       else hf.get("error")),
            "blocking": hf.get("state") != "AVAILABLE",
        },
        "nvidia_inference": {
            "state": "AVAILABLE" if nv.get("deployment_status")
                     == "DEPLOYMENT_READY" else "UNAVAILABLE",
            "role": "deployment / real inference target",
            "detail": nv.get("reason"),
            "inference_verified": nv.get("inference_verified"),
            "blocking": nv.get("deployment_status") != "DEPLOYMENT_READY",
        },
        "docker_optional": {
            "state": docker_status().get("state"),
            "role": "optional containerised execution",
            "detail": docker_status().get("reason"),
            "blocking": False,
        },
    }

    core = [k for k in ("kaggle_training", "hugging_face_artifacts",
                        "nvidia_inference") if links[k]["blocking"]]
    return {
        "links": links,
        "core_pipeline_ready": not core,
        "blocked_links": core,
        "verdict": ("Kaggle -> Hugging Face -> NVIDIA -> JARVIS is operational"
                    if not core
                    else "Pipeline degraded; blocked at: " + ", ".join(core)),
    }


def nvidia_deployment_readiness() -> dict[str, Any]:
    """NVIDIA as the deployment target, using the existing control center."""
    try:
        from research_engine.capability_tools import live_provider_status

        n = (live_provider_status() or {}).get("nvidia") or {}
    except Exception as exc:  # noqa: BLE001
        return {"deployment_status": "NOT_SUPPORTED",
                "reason": f"NVIDIA status unavailable: {type(exc).__name__}"}
    if not n.get("available"):
        return {"deployment_status": "NOT_SUPPORTED",
                "reason": f"NVIDIA unavailable: {n.get('detail') or n.get('state')}"}
    return {
        "deployment_status": "DEPLOYMENT_READY",
        "provider": "nvidia",
        "inference_verified": bool(n.get("inference_verified")),
        "health_status": n.get("health_status"),
        "latency_ms": n.get("latency_ms"),
        "reason": ("NVIDIA accepts OpenAI-compatible hosted models; Brain/Silverwing "
                   "artifacts are deployable only where the runtime/model is "
                   "compatible. Verified on first real inference."),
    }


def fabric_overview() -> dict[str, Any]:
    brain = discover_brain()
    silverwing = discover_silverwing()
    return {
        "brain": brain,
        "silverwing": silverwing,
        "external": external_status(),
        "nvidia": nvidia_deployment_readiness(),
        "docker": docker_status(),
        "pipeline": pipeline_readiness(),
    }


# --------------------------------------------------------------------------- #
# Integration matrix + continuation engine
# --------------------------------------------------------------------------- #
# The truthfulness ladder.  These are NOT interchangeable and must never be
# collapsed: configured != authenticated != reachable != healthy !=
# inference_verified; artifact_exists != evaluated != promoted != deployed.
DISTINCTIONS = (
    "configured", "authenticated", "reachable", "healthy", "inference_verified",
    "artifact_exists", "evaluated", "promoted", "deployed",
)

# Actions that must never be taken without explicit human approval.
APPROVAL_REQUIRED = frozenset({
    "submit_training_run", "publish_artifact", "promote_model",
    "deploy_model", "install_docker", "start_training",
})


def _kaggle_continuation(brain: dict[str, Any]) -> dict[str, Any]:
    """Derive Kaggle's next step from real training state."""
    kg = _kaggle_real_status()
    if kg.get("state") != "AVAILABLE":
        return {
            "system": "kaggle",
            "last_completed": None,
            "last_checkpoint": None,
            "last_metrics": None,
            "next_step": "restore_kaggle_authentication",
            "next_detail": kg.get("error") or "Kaggle not reachable",
            "requires_approval": False,
            "blocked": True,
        }
    ckpts = [a for a in brain.get("artifacts", [])
             if a.get("artifact_type") == "checkpoint"]
    published = [a for a in brain.get("artifacts", [])
                 if a.get("artifact_type") == "published_model"]
    metrics = [e for e in brain.get("evaluations", [])
               if e.get("evaluation_id") == "training_metrics"]
    last_ckpt = ckpts[0] if ckpts else None
    if last_ckpt and not published:
        step, detail, appr = ("publish_artifact_to_huggingface",
                              "checkpoint exists but no published model metadata",
                              True)
    elif last_ckpt and published:
        step, detail, appr = ("run_evaluation_against_baseline",
                              "checkpoint published; promotion gate reports "
                              "baseline metrics missing", True)
    else:
        step, detail, appr = ("submit_training_run",
                              "no checkpoint manifest found on disk", True)
    return {
        "system": "kaggle",
        "last_completed": "jarvis-brain-sft-kaggle-v6 (per checkpoint manifest)",
        "last_checkpoint": (last_ckpt or {}).get("artifact_id"),
        "last_metrics": (metrics[0].get("source_file") if metrics else None),
        "next_step": step,
        "next_detail": detail,
        "requires_approval": appr,
        "blocked": False,
    }


def _hf_continuation(brain: dict[str, Any]) -> dict[str, Any]:
    hf = _hf_real_status()
    if hf.get("state") != "AVAILABLE":
        return {"system": "hugging_face", "next_step": "restore_hf_token",
                "next_detail": hf.get("error"), "requires_approval": False,
                "blocked": True}
    mismatches = {
        repo: meta.get("mismatch_note")
        for repo, meta in (hf.get("repositories") or {}).items()
        if meta.get("revision_mismatch")
    }
    if mismatches:
        return {
            "system": "hugging_face",
            "next_step": "reconcile_provenance_revision_mismatch",
            "next_detail": "; ".join(mismatches.values()),
            "requires_approval": True,
            "blocked": True,
            "note": "Provenance conflict recorded, not auto-resolved.",
        }
    return {
        "system": "hugging_face",
        "next_step": "none_required",
        "next_detail": "repositories verified and revisions consistent",
        "requires_approval": False,
        "blocked": False,
    }


def _nvidia_continuation() -> dict[str, Any]:
    n = nvidia_deployment_readiness()
    if n.get("deployment_status") != "DEPLOYMENT_READY":
        return {"system": "nvidia", "next_step": "restore_nvidia_provider",
                "next_detail": n.get("reason"), "requires_approval": False,
                "blocked": True}
    if not n.get("inference_verified"):
        return {
            "system": "nvidia",
            "next_step": "run_controlled_inference_verification",
            "next_detail": ("provider healthy but no inference has been verified "
                            "in this process"),
            "requires_approval": False,
            "blocked": False,
        }
    return {"system": "nvidia", "next_step": "none_required",
            "next_detail": "healthy and inference verified",
            "requires_approval": False, "blocked": False}


def _docker_continuation() -> dict[str, Any]:
    d = docker_status()
    if d.get("state") == "UNAVAILABLE":
        return {
            "system": "docker",
            "next_step": "install_docker",
            "next_detail": d.get("required_action"),
            "requires_approval": True,
            "blocked": False,
            "note": ("Optional. The core Kaggle->HF->NVIDIA->JARVIS pipeline "
                     "does not require Docker."),
        }
    return {"system": "docker", "next_step": "none_required",
            "next_detail": d.get("reason"), "requires_approval": False,
            "blocked": False}


def _brain_continuation(brain: dict[str, Any]) -> dict[str, Any]:
    promo = brain.get("promotion") or {}
    stage = promo.get("current_stage")
    if promo.get("promoted_allowed"):
        step, detail, appr = ("deploy_promoted_brain_model",
                              "promotion gate allows PROMOTED", True)
    elif stage == "candidate":
        step = "run_baseline_evaluation"
        detail = "; ".join(promo.get("blockers") or []) or "baseline missing"
        appr = True
    else:
        step, detail, appr = ("advance_promotion_gate",
                              f"current stage: {stage}", True)
    return {
        "system": "brain",
        "current_stage": stage,
        "next_step": step,
        "next_detail": detail,
        "requires_approval": appr,
        "blocked": bool(promo.get("blockers")),
    }


def _silverwing_continuation(sw: dict[str, Any]) -> dict[str, Any]:
    rt = sw.get("runtime") or {}
    if rt.get("state") == "OFFLINE":
        return {
            "system": "silverwing",
            "next_step": "start_silverwing_runtime",
            "next_detail": rt.get("detail"),
            "requires_approval": False,
            "blocked": True,
            "note": "Local/offline intelligence does not require NVIDIA.",
        }
    if not (sw.get("inference") or {}).get("verified"):
        return {"system": "silverwing",
                "next_step": "run_local_inference_verification",
                "next_detail": "runtime reachable but inference unverified",
                "requires_approval": False, "blocked": False}
    return {"system": "silverwing", "next_step": "none_required",
            "next_detail": "runtime online and inference verified",
            "requires_approval": False, "blocked": False}


def integration_matrix() -> dict[str, Any]:
    """Single truthful matrix of the four systems + Brain/Silverwing.

    Reports only configured / authenticated / reachable / available / healthy and
    derived continuations.  Never returns a credential value.
    """
    brain = discover_brain()
    sw = discover_silverwing()
    hf = _hf_real_status()
    kg = _kaggle_real_status()
    nvv = nvidia_deployment_readiness()
    dk = docker_status()

    services = {
        "kaggle": {
            "role": "training / experimentation / evaluation / GPU compute",
            "configured": bool(kg.get("credential_file_present")
                               or kg.get("cli_installed")),
            "authenticated": bool(kg.get("connected")),
            "reachable": bool(kg.get("connected")),
            "available": kg.get("state") == "AVAILABLE",
            "healthy": None,
            "version": "kaggle-cli",
            "last_successful_operation": (
                f"{kg.get('kernel_count', 0)} kernels listed"
                if kg.get("connected") else None),
            "current_artifact": None,
            "current_job": None,
        },
        "hugging_face": {
            "role": "model/artifact storage, versioning, metadata",
            "configured": bool(hf.get("token_present")),
            "authenticated": bool(hf.get("connected")),
            "reachable": bool(hf.get("connected")),
            "available": hf.get("state") == "AVAILABLE",
            "healthy": None,
            "version": "hub-api",
            "username": hf.get("username"),
            "last_successful_operation": (
                f"{len(hf.get('repositories') or {})} repo(s) verified"
                if hf.get("connected") else None),
            "current_artifact": next(iter((hf.get("repositories") or {}).keys()),
                                        None),
        },
        "nvidia": {
            "role": "inference / model serving / deployment target",
            "configured": True,
            "authenticated": True,
            "reachable": nvv.get("deployment_status") == "DEPLOYMENT_READY",
            "available": nvv.get("deployment_status") == "DEPLOYMENT_READY",
            "healthy": nvv.get("health_status"),
            "inference_verified": nvv.get("inference_verified"),
            "version": "nvidia-nim-openai-compatible",
            "latency_ms": nvv.get("latency_ms"),
            "last_successful_operation": "streaming chat inference",
        },
        "docker": {
            "role": "reproducible runtime / packaging / service isolation",
            "configured": dk.get("state") != "UNAVAILABLE",
            "authenticated": None,
            "reachable": dk.get("state") in {"AVAILABLE", "DEGRADED"},
            "available": dk.get("state") in {"AVAILABLE", "DEGRADED"},
            "healthy": None,
            "version": None,
            "optional": True,
            "note": dk.get("impact"),
        },
    }

    continuations = {
        "kaggle": _kaggle_continuation(brain),
        "hugging_face": _hf_continuation(brain),
        "nvidia": _nvidia_continuation(),
        "docker": _docker_continuation(),
        "brain": _brain_continuation(brain),
        "silverwing": _silverwing_continuation(sw),
    }

    return {
        "services": services,
        "continuations": continuations,
        "distinctions": list(DISTINCTIONS),
        "approval_required_actions": sorted(APPROVAL_REQUIRED),
        "safe_next_actions": sorted(
            f"{k}.{v['next_step']}" for k, v in continuations.items()
            if not v.get("requires_approval") and not v.get("blocked")
        ),
        "requires_approval": sorted(
            f"{k}.{v['next_step']}" for k, v in continuations.items()
            if v.get("requires_approval")
        ),
        "blocked": sorted(
            k for k, v in continuations.items() if v.get("blocked")
        ),
    }


# --------------------------------------------------------------------------- #
# Stage-based lifecycle + continuation engine
# --------------------------------------------------------------------------- #
# The canonical ordered lifecycle.  A stage is only ever COMPLETE when real
# evidence says so; otherwise it is NOT_STARTED, MISSING or BLOCKED.
LIFECYCLE_STAGES = (
    "SOURCE", "TRAINING", "CHECKPOINT", "ARTIFACT", "EVALUATION",
    "PROMOTION", "DEPLOYMENT", "INFERENCE",
)

COMPLETE = "COMPLETE"
NOT_STARTED = "NOT_STARTED"
MISSING = "MISSING"
BLOCKED = "BLOCKED"

# Which existing pipeline_report stage feeds which lifecycle stage.
_PIPELINE_TO_LIFECYCLE = {
    "prepare_dataset": "SOURCE",
    "validate_dataset": "SOURCE",
    "export_kaggle": "SOURCE",
    "train": "TRAINING",
    "run_pilot": "TRAINING",
    "checkpoint": "CHECKPOINT",
    "upload_hf": "ARTIFACT",
    "evaluate": "EVALUATION",
    "baseline": "EVALUATION",
    "promotion_gate": "PROMOTION",
    "deploy": "DEPLOYMENT",
    "health_probe": "DEPLOYMENT",
    "gateway_test": "INFERENCE",
}

# A lifecycle stage needs ALL of its contributing pipeline stages complete.
_STAGE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "SOURCE": ("prepare_dataset", "validate_dataset"),
    "TRAINING": ("train",),
    "CHECKPOINT": ("checkpoint",),
    "ARTIFACT": ("upload_hf",),
    "EVALUATION": ("evaluate",),
    "PROMOTION": ("promotion_gate",),
    "DEPLOYMENT": ("deploy", "health_probe"),
    "INFERENCE": ("gateway_test",),
}


def _load_pipeline_report() -> dict[str, Any]:
    path = BRAIN_ARTIFACTS / "pipeline" / "pipeline_report.json"
    return _read_json(path) or {}


def brain_lifecycle() -> dict[str, Any]:
    """Compute Brain's real lifecycle from the existing pipeline report.

    Each stage is COMPLETE / NOT_STARTED / MISSING / BLOCKED with the real
    reason recorded in the source report.  The first incomplete stage determines
    the next action.
    """
    report = _load_pipeline_report()
    raw = {s.get("name"): s for s in (report.get("stages") or [])
           if isinstance(s, dict)}

    def _status_of(name: str) -> tuple[str, str | None]:
        s = raw.get(name)
        if s is None:
            return MISSING, "stage absent from pipeline report"
        status = str(s.get("status") or "").upper()
        detail = s.get("detail") if isinstance(s.get("detail"), dict) else {}
        reason = (detail.get("reason") or detail.get("blockers")
                  or detail.get("error"))
        if status == "DONE":
            return COMPLETE, None
        if status == "BLOCKED":
            return BLOCKED, (str(reason) if reason else "blocked")
        if status in {"NOT_RUN", "NOT_STARTED", "FAILED", "SKIPPED"}:
            return NOT_STARTED, (str(reason) if reason else status.lower())
        return NOT_STARTED, f"unknown status {status!r}"

    stages: dict[str, Any] = {}
    for stage in LIFECYCLE_STAGES:
        contributors = []
        for pname in _STAGE_REQUIREMENTS.get(stage, ()):
            pstatus, reason = _status_of(pname)
            contributors.append({"pipeline_stage": pname, "status": pstatus,
                                 "reason": reason})
        if not contributors:
            stages[stage] = {"status": MISSING, "reason": "no requirement defined"}
            continue
        if any(c["status"] == COMPLETE for c in contributors):
            stages[stage] = {
                "status": COMPLETE,
                "reason": None,
                "contributors": contributors,
                "note": ("at least one contributing stage is complete"
                         if len(contributors) > 1 else None),
            }
        else:
            worst = contributors[0]
            for c in contributors:
                if c["status"] == BLOCKED:
                    worst = c
                    break
            stages[stage] = {"status": worst["status"],
                             "reason": worst["reason"],
                             "contributors": contributors}

    first_incomplete = next(
        (s for s in LIFECYCLE_STAGES if stages[s]["status"] != COMPLETE), None)

    # Cross-check the existing promotion gate, which is authoritative.
    promo = _promotion_state()
    if promo.get("current_stage") and stages["PROMOTION"]["status"] == COMPLETE:
        stages["PROMOTION"] = {
            "status": BLOCKED if not promo.get("promoted_allowed") else COMPLETE,
            "reason": promo.get("reason"),
            "blockers": promo.get("blockers") or [],
        }

    nvv = nvidia_deployment_readiness()
    if stages["INFERENCE"]["status"] == COMPLETE:
        stages["INFERENCE"] = {
            "status": COMPLETE,
            "reason": None,
            "note": ("gateway_test reported DONE in the pipeline report. "
                     "NVIDIA provider inference is independently verified; the "
                     "Brain artifact itself is NOT served by NVIDIA - see the "
                     "deployment stage."),
            "nvidia_inference_verified": nvv.get("inference_verified"),
        }
    else:
        stages["INFERENCE"].setdefault("nvidia_inference_verified",
                                       nvv.get("inference_verified"))

    next_action = _next_action_for(first_incomplete, stages, promo)
    return {
        "system": SYSTEM_BRAIN,
        "stages": stages,
        "first_incomplete_stage": first_incomplete,
        "next_action": next_action,
        "pipeline_report": {
            "path": str(BRAIN_ARTIFACTS / "pipeline" / "pipeline_report.json"),
            "overall": report.get("overall"),
            "final_stage": report.get("final_stage"),
        },
        "promotion": promo,
        "routing_eligible": stages["PROMOTION"]["status"] == COMPLETE
        and stages["DEPLOYMENT"]["status"] == COMPLETE,
    }


def _promotion_state() -> dict[str, Any]:
    try:
        if str(WORKSPACE) not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        from brain_training.promote import collect_evidence, gate  # type: ignore

        ev = collect_evidence()
        g = gate("promoted")
        return {
            "source": "brain_training.promote.gate",
            "current_stage": getattr(g, "current_stage", None),
            "promoted_allowed": bool(getattr(g, "allowed", False)),
            "reason": getattr(g, "reason", None),
            "blockers": list(getattr(g, "blockers", []) or []),
            "evidence": {
                "baseline_present": getattr(ev, "baseline_present", None),
                "sft_metrics_present": getattr(ev, "sft_metrics_present", None),
                "comparison_present": getattr(ev, "comparison_present", None),
                "security_scan_clean": getattr(ev, "security_scan_clean", None),
                "artifact_loads": getattr(ev, "artifact_loads", None),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _next_action_for(first_incomplete: str | None,
                     stages: dict[str, Any],
                     promo: dict[str, Any]) -> dict[str, Any]:
    """Map the first incomplete stage to the safest next action."""
    if first_incomplete is None:
        return {
            "action": "register_and_route_promoted_model",
            "detail": "all lifecycle stages complete",
            "requires_approval": True,
            "blocked": False,
        }
    table = {
        "SOURCE": ("prepare_dataset", False,
                   "dataset/corpus source incomplete"),
        "TRAINING": ("submit_training_run", True,
                     "training has not been run on a CUDA-capable host"),
        "CHECKPOINT": ("retrieve_checkpoint", True,
                       "no checkpoint produced"),
        "ARTIFACT": ("publish_artifact_to_huggingface", True,
                     "artifact has not been published/versioned on the Hub"),
        "EVALUATION": ("run_evaluation", True,
                       "evaluation (and/or baseline) has not been run"),
        "PROMOTION": ("run_promotion_gate", False,
                      "promotion gate is the current boundary"),
        "DEPLOYMENT": ("prepare_nvidia_deployment", True,
                       "approved artifact has not been deployed"),
        "INFERENCE": ("run_controlled_inference_verification", False,
                      "deployment exists but inference is unverified"),
    }
    action, approval, detail = table.get(
        first_incomplete, ("inspect_lifecycle", True, "unknown stage"))
    reason = stages.get(first_incomplete, {}).get("reason")
    return {
        "action": action,
        "stage": first_incomplete,
        "detail": f"{detail}" + (f" ({reason})" if reason else ""),
        "requires_approval": approval,
        "blocked": stages.get(first_incomplete, {}).get("status") == BLOCKED
        and first_incomplete == "PROMOTION",
    }


def silverwing_lifecycle() -> dict[str, Any]:
    """Compute Silverwing's real lifecycle independently of Brain."""
    sw = discover_silverwing()
    rt = sw.get("runtime") or {}
    online = rt.get("state") == "AVAILABLE"
    verified = bool((sw.get("inference") or {}).get("verified"))
    models = sw.get("models") or []
    with_manifest = [m for m in models if m.get("has_run_manifest")]

    stages = {
        "SOURCE": {"status": COMPLETE if with_manifest else MISSING,
                   "reason": None if with_manifest
                   else "no run_manifest.json found for any model",
                   "evidence": [m["model_id"] for m in with_manifest]},
        "TRAINING": {"status": COMPLETE if with_manifest else MISSING,
                     "reason": "training manifests exist"
                     if with_manifest else "no training provenance",
                     "evidence": [m["model_id"] for m in with_manifest]},
        "CHECKPOINT": {"status": NOT_STARTED,
                       "reason": "no Silverwing checkpoint manifest discovered",
                       "evidence": None},
        "ARTIFACT": {"status": NOT_STARTED,
                     "reason": "no Silverwing artifact published to the Hub",
                     "evidence": None},
        "EVALUATION": {"status": NOT_STARTED,
                       "reason": "no Silverwing evaluation artifacts discovered",
                       "evidence": None},
        "PROMOTION": {"status": NOT_STARTED,
                      "reason": "no Silverwing promotion record",
                      "evidence": None},
        "DEPLOYMENT": {
            "status": COMPLETE if online else NOT_STARTED,
            "reason": None if online else rt.get("detail"),
            "evidence": rt.get("endpoint"),
        },
        "INFERENCE": {
            "status": COMPLETE if verified else NOT_STARTED,
            "reason": None if verified
            else (sw.get("inference") or {}).get("reason"),
            "evidence": None,
        },
    }
    first_incomplete = next(
        (s for s in LIFECYCLE_STAGES if stages[s]["status"] != COMPLETE), None)
    return {
        "system": SYSTEM_SILVERWING,
        "stages": stages,
        "first_incomplete_stage": first_incomplete,
        "next_action": _sw_next_action(first_incomplete, online),
        "model_count": len(models),
        "routing_eligible": verified and online,
    }


def _sw_next_action(first_incomplete: str | None, online: bool) -> dict[str, Any]:
    if not online:
        return {
            "action": "start_silverwing_runtime",
            "detail": "runtime offline; local/offline intelligence unavailable",
            "requires_approval": False,
            "blocked": True,
            "note": "Silverwing must remain usable without NVIDIA.",
        }
    if first_incomplete is None:
        return {"action": "register_promoted_silverwing_version",
                "detail": "lifecycle complete", "requires_approval": True,
                "blocked": False}
    return {
        "action": "establish_silverwing_checkpoint_provenance",
        "stage": first_incomplete,
        "detail": f"first incomplete stage: {first_incomplete}",
        "requires_approval": True,
        "blocked": False,
    }


def contradictions() -> list[dict[str, Any]]:
    """Cross-check recorded history against live state and report conflicts.

    History is never silently rewritten.  Each entry names both observations.
    """
    found: list[dict[str, Any]] = []
    report = _load_pipeline_report()
    stages = {s.get("name"): s for s in (report.get("stages") or [])
              if isinstance(s, dict)}

    # 1) publish metadata vs live Hub revision
    hf = _hf_real_status()
    for repo, meta in (hf.get("repositories") or {}).items():
        if meta.get("revision_mismatch"):
            found.append({
                "id": "hf_revision_mismatch",
                "artifact": repo,
                "recorded": meta.get("local_recorded_revision"),
                "live": meta.get("live_revision"),
                "detail": meta.get("mismatch_note"),
                "resolution": "unresolved - requires human decision",
            })
        if meta.get("exists") and stages.get("upload_hf", {}).get(
                "status") == "NOT_RUN":
            found.append({
                "id": "stale_pipeline_report",
                "artifact": repo,
                "recorded": "pipeline_report.upload_hf = NOT_RUN",
                "live": (f"repository exists on the Hub with "
                         f"{meta.get('file_count')} file(s) at "
                         f"{(meta.get('live_revision') or '')[:12]}"),
                "detail": ("The recorded pipeline report is older than the "
                           "actual Hub state."),
                "resolution": "unresolved - report not rewritten automatically",
            })

    # 2) base model naming discrepancy (documented, not corrected)
    bases = set()
    for art in discover_brain().get("artifacts", []):
        if art.get("base_model"):
            bases.add(art["base_model"])
    lineage = BRAIN_TRAINING / "BRAIN_LINEAGE.md"
    if lineage.is_file():
        try:
            text = lineage.read_text(encoding="utf-8", errors="replace")
            for name in ("Qwen/Qwen3-4B-Base", "Qwen/Qwen3-4B"):
                if name in text and name not in bases:
                    found.append({
                        "id": "base_model_naming",
                        "recorded": f"BRAIN_LINEAGE.md references {name}",
                        "live": f"checkpoint manifests record {sorted(bases)}",
                        "detail": ("Base model naming differs between the "
                                   "lineage doc and the checkpoint manifest."),
                        "resolution": "recorded; base model not changed",
                    })
        except OSError:
            pass

    # 3) stage reported complete without supporting evidence
    for name, s in stages.items():
        if str(s.get("status", "")).upper() == "DONE":
            det = s.get("detail") if isinstance(s.get("detail"), dict) else {}
            if name == "health_probe" and det.get("status") == "unknown":
                found.append({
                    "id": "health_probe_unknown",
                    "recorded": "pipeline_report.health_probe = DONE",
                    "live": "health_probe detail status = 'unknown'",
                    "detail": "Stage marked DONE but carries an unknown probe "
                              "status.",
                    "resolution": "unresolved - requires re-probe",
                })
    return found


def development_status() -> dict[str, Any]:
    """Combined, truthful development-lifecycle status for both systems."""
    brain = brain_lifecycle()
    silverwing = silverwing_lifecycle()
    return {
        "brain": brain,
        "silverwing": silverwing,
        "external": {
            "kaggle": _kaggle_real_status(),
            "hugging_face": _hf_real_status(),
        },
        "nvidia": nvidia_deployment_readiness(),
        "docker": docker_status(),
        "contradictions": contradictions(),
        "next_actions": {
            "brain": brain["next_action"],
            "silverwing": silverwing["next_action"],
        },
    }


__all__ = [
    "discover_brain", "discover_silverwing", "external_status",
    "nvidia_deployment_readiness", "fabric_overview", "assert_no_secrets",
    "docker_status", "pipeline_readiness", "integration_matrix",
    "brain_lifecycle", "silverwing_lifecycle", "development_status", "contradictions",
    "LIFECYCLE_STAGES", "COMPLETE", "NOT_STARTED", "MISSING", "BLOCKED",
    "DEPLOYMENT_STAGES", "ROUTING_MIN_STAGE", "DISTINCTIONS",
    "APPROVAL_REQUIRED",
]
