"""Brain runtime deployment configuration + live health probe (spec S19-S22).

Deployment targets (configurable, never faked):

  * dev   -> http://127.0.0.1:8011/v1  (local stub / local transformers backend)
  * remote-> https://<inference-host>/v1 (HF Inference Endpoints / Kaggle GPU)

Model switching (spec S22): ``JARVIS_BRAIN_MODEL`` selects
``jarvis-brain-qwen3-4b-v1`` (base) or ``jarvis-brain-qwen3-4b-sft-v1`` (SFT)
without frontend changes — the Brain runtime's ``BrainCatalog`` resolves either.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import (
    BASE_MODEL_ID,
    BRAIN_ENDPOINT,
    BRAIN_HOST,
    BRAIN_PORT,
    SILVERWING_ENDPOINT,
    env_snapshot,
)


@dataclass
class DeployConfig:
    endpoint: str
    model: str
    host: str
    port: int
    silverwing_endpoint: str
    profiles: dict[str, str]

    @property
    def is_remote(self) -> bool:
        h = (self.endpoint or "").lower()
        return h.startswith("https://") or ("127.0.0.1" not in (self.endpoint or "")
                                            and "localhost" not in (self.endpoint or ""))

    def summary(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "model": self.model,
            "host": self.host,
            "port": self.port,
            "binding": "127.0.0.1 (loopback only)" if not self.is_remote else "remote",
            "silverwing_fallback": self.silverwing_endpoint,
            "profiles": self.profiles,
            "api_key_present": bool(os.environ.get("JARVIS_BRAIN_API_KEY")),
            "hf_token_present": bool(os.environ.get("JARVIS_HF_TOKEN") or os.environ.get("HF_TOKEN")),
        }


def load_config() -> DeployConfig:
    endpoint = (os.environ.get("JARVIS_BRAIN_ENDPOINT") or BRAIN_ENDPOINT).strip()
    model = (os.environ.get("JARVIS_BRAIN_MODEL") or "").strip()
    if not model:
        # fall back to the lineage default (SFT candidate per target config)
        model = "jarvis-brain-qwen3-4b-sft-v1"
    profiles = {
        "dev": "http://127.0.0.1:8011/v1",
        "remote": os.environ.get("JARVIS_BRAIN_REMOTE_ENDPOINT", "https://<actual-brain-inference-service>/v1"),
        "local_stub": "http://127.0.0.1:8011/v1",
    }
    return DeployConfig(
        endpoint=endpoint,
        model=model,
        host=BRAIN_HOST,
        port=BRAIN_PORT,
        silverwing_endpoint=SILVERWING_ENDPOINT,
        profiles=profiles,
    )


def resolve_model(model_id: str | None = None) -> dict[str, Any]:
    """Confirm the configured model is registered in the Brain catalog (no weights)."""
    from brain_runtime.model_registry import BrainCatalog
    cat = BrainCatalog()
    mid = model_id or load_config().model
    try:
        entry = cat.lookup(mid)
    except Exception as exc:  # noqa: BLE001
        return {"model": mid, "registered": False, "error": str(exc)}
    if entry is None:
        return {"model": mid, "registered": False,
                "error": "not found in Brain catalog (check JARVIS_BRAIN_MODEL)"}
    return {
        "model": entry.full_id,
        "registered": True,
        "repository": entry.repository,
        "revision": entry.revision,
        "parameters": entry.parameter_count,
        "training_method": entry.training_method,
        "status": entry.status,
        "merged": bool(getattr(entry, "merged", False)),
    }


def probe_brain_endpoint(endpoint: str | None = None) -> dict[str, Any]:
    """Live, unauthenticated GET /health probe of the Brain runtime.

    Honest: if the Brain is not running, returns reachable=False with the actual
    error.  Never fabricates availability.
    """
    cfg = load_config()
    base = (endpoint or cfg.endpoint).rstrip("/")
    health_url = base.rstrip("/v1") + "/health" if base.endswith("/v1") else base + "/health"
    # normalize: base may be http://host:port or http://host:port/v1
    if "/v1" in base:
        root = base[: base.rfind("/v1")]
    else:
        root = base
    health_url = root + "/health"
    result: dict[str, Any] = {
        "endpoint": cfg.endpoint,
        "health_url": health_url,
        "reachable": False, "available": False, "stub": None,
        "production_health": False, "status": "unknown",
        "model": None, "backend": None, "detail": None,
    }
    try:
        req = Request(health_url, headers={"User-Agent": "brain_training-deploy/1.0"})
        with urlopen(req, timeout=5) as r:
            raw = r.read().decode("utf-8", "replace")
            status_code = r.status
    except HTTPError as e:
        # 503 is an ANSWER (stub brain) -> reachable
        if e.code == 503:
            try:
                raw = e.read().decode("utf-8", "replace")
                status_code = 503
            except Exception:
                raw = ""; status_code = 503
            result["reachable"] = True
        else:
            result["detail"] = f"HTTP {e.code}"
            return result
    except (URLError, OSError, ConnectionError) as exc:
        result["detail"] = f"unreachable: {type(exc).__name__}"
        return result
    try:
        data = json.loads(raw)
    except Exception:
        data = {"raw": raw[:200]}
    result["reachable"] = True
    result["status"] = data.get("status", result["status"])
    result["available"] = bool(data.get("available", False))
    result["stub"] = data.get("stub")
    result["production_health"] = bool(data.get("production_health", False))
    result["model"] = data.get("model")
    result["backend"] = data.get("backend")
    result["http_status"] = status_code
    result["detail"] = data.get("detail")
    return result
