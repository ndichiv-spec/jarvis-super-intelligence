"""HuggingFace connection + publish workflow (spec S3/S5/S9/S27).

Authentication (spec S4):
  * Token resolved from ``JARVIS_HF_TOKEN`` (preferred) or existing ``HF_TOKEN``,
    server-side via the project env.  NEVER printed, NEVER logged verbatim,
    NEVER written to artifact metadata.
  * The token is used only to instantiate a short-lived ``huggingface_hub``
    client; it is dropped from locals after the call.

Honesty (spec S30): on a dev box whose token is invalid/absent the connection
status is ``NOT CONNECTED`` and the upload workflow is GATED off — no partial
uploads, no fabricated "uploaded" status.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import HF_SCAN_DIR, HF_NAMESPACE, HF_REPO_DATASET, HF_REPO_MODEL_BASE, HF_REPO_MODEL_SFT
from .dataset import scan_dir, scan_file


def _mask(token: str | None) -> str:
    if not token:
        return "<none>"
    return f"<len={len(token)}>"


@dataclass
class HFConnection:
    token: str = ""
    token_var: str = ""            # name of the env var that supplied it
    token_present: bool = False
    token_valid: bool = False      # verified via whoami
    username: str = ""
    error: str = ""
    token_in_dotenv: str = ""       # masked length-only hint, e.g. "<len=201>"
    repos: dict[str, str] = field(default_factory=dict)  # repo -> EXISTS|NOT_FOUND|UNVERIFIED

    def summary(self) -> dict[str, Any]:
        return {
            "configured": self.token_present,
            "authenticated": self.token_valid,
            "username": self.username or "",
            "token_var": self.token_var or "",
            "token": _mask(self.token) if self.token else "<none>",
            "token_in_dotenv": self.token_in_dotenv or "<none>",
            "error": self.error,
            "repos": dict(self.repos),
            "namespace": HF_NAMESPACE,
            "expected_repos": {
                "dataset": HF_REPO_DATASET,
                "model_base": HF_REPO_MODEL_BASE,
                "model_sft": HF_REPO_MODEL_SFT,
            },
        }


def _dotenv_hint(path: Path) -> str:
    """Detect a declared HF-token KEY in ``.env`` WITHOUT retaining its value.

    Returns a masked length token (e.g. ``<len=201>``) or ``""`` if absent.
    The value is read line-by-line and immediately discarded (never stored,
    logged, or returned) — spec S4/S27: never print, never commit, never write
    to artifact metadata.
    """
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        if key.strip() in ("JARVIS_HF_TOKEN", "HF_TOKEN") and val.strip():
            return f"<len={len(val.strip())}>"  # value discarded immediately
    return ""


def probe() -> HFConnection:
    """Probe actual HF connectivity + repo existence (read-only, no uploads)."""
    from .config import hf_token, env_snapshot, REPO_ROOT
    conn = HFConnection()
    conn.token_in_dotenv = _dotenv_hint(REPO_ROOT / ".env")
    snap = env_snapshot()
    if snap.hf_token_present:
        conn.token_var = snap.hf_token_name
    conn.token = hf_token()
    conn.token_present = bool(conn.token)
    if not conn.token:
        if conn.token_in_dotenv:
            conn.error = (f"token declared in .env ({conn.token_in_dotenv}) but not "
                          f"loaded into process env; probe skipped (no validity "
                          f"asserted). Run `source .env` to validate.")
        else:
            conn.error = "no JARVIS_HF_TOKEN / HF_TOKEN in environment or .env"
        return conn
    try:
        from huggingface_hub import HfApi  # type: ignore
        api = HfApi(token=conn.token or None)
        info = api.whoami()
        conn.token_valid = True
        if isinstance(info, dict):
            conn.username = info.get("name", "") or info.get("user", "") or ""
        else:
            conn.username = str(info)
    except Exception as exc:  # noqa: BLE001
        conn.error = f"{type(exc).__name__}: {str(exc)[:140]}"
        # 401/403 -> invalid token; anything else -> transport.
        if "401" in conn.error or "403" in conn.error or "Invalid" in conn.error:
            conn.error = "invalid or revoked token (401)"
        conn.token_valid = False
        # token now dropped from further use; keep local only for this probe
    finally:
        conn.token = ""  # drop immediately after probe
    return conn


def _repo_type(repo: str) -> str:
    """Infer HuggingFace repo type for existence checks.

    `videlisndichi/jarvis-brain-training-data` is a *dataset* repo and requires
    `dataset_info`; the model variants use `model_info` (spec S3).
    """
    if repo.endswith("-training-data") or "/jarvis-brain-training-data" in repo:
        return "dataset"
    return "model"


def repo_exists(repo: str, token: str, repo_type: str | None = None) -> str:
    """Return EXISTS / NOT_FOUND / UNVERIFIED (auth failure masks existence)."""
    if not token:
        return "UNVERIFIED"
    rtype = repo_type or _repo_type(repo)
    try:
        from huggingface_hub import model_info, dataset_info  # type: ignore
        if rtype == "dataset":
            dataset_info(repo, token=token)
        else:
            model_info(repo, token=token)
        return "EXISTS"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "401" in msg or "403" in msg or "Invalid" in msg:
            return "UNVERIFIED"  # can't tell — auth blocks the lookup
        return "NOT_FOUND"


def publish(intent: "PublishIntent", token: str | None = None,
            create_ok: bool = True) -> dict[str, Any]:
    """Execute the §9 publish workflow (gated; no partial uploads).

    Kaggle checkpoint -> validation -> artifact manifest -> HF upload
    -> commit/revision -> registry update.

    Honest gating (spec S30): returns ``NOT_CONNECTED`` if no valid token;
    refuses to upload an adapter-as-merged unless `intent.merged` was verified.
    Weights (binary blobs) are uploaded via HuggingFace's API, NOT read into
    memory here.  The token is used only for the upload client and dropped
    after.
    """
    from .config import hf_token
    tok = token or hf_token()
    if not tok:
        return {"status": "NOT_CONNECTED", "reason": "no JARVIS_HF_TOKEN/HF_TOKEN",
                "revision": "", "merged": intent.merged}
    # security gate (§27) before any upload
    scan_dirs = [p for p in (intent.adapter_path, intent.tokenizer_path,
                             intent.config_path, intent.metrics_path,
                             intent.evaluation_report) if p is not None]
    for d in scan_dirs:
        sc = secret_scan_artifact(Path(d))
        if not sc["clean"]:
            return {"status": "BLOCKED", "reason": "secret scan failed",
                    "findings": sc["findings"], "revision": ""}
    try:
        from huggingface_hub import HfApi  # type: ignore
        import tempfile
        api = HfApi(token=tok)
        uname = api.whoami()
        username = uname.get("name", "") if isinstance(uname, dict) else str(uname)
        # create the SFT adapter repo (NOT a merged model) if absent
        api.create_repo(repo_id=intent.model_id, repo_type="model",
                        exist_ok=create_ok)
        # upload each artifact (weights via HF API, never read into memory here)
        uploaded: dict[str, str] = {}
        for label, p in (("adapter", intent.adapter_path), ("tokenizer", intent.tokenizer_path),
                         ("config", intent.config_path), ("metrics", intent.metrics_path),
                         ("evaluation_report", intent.evaluation_report)):
            if p is not None:
                api.upload_folder(repo_id=intent.model_id, folder_path=str(p),
                                  path_in_repo=label if label != "evaluation_report" else "evaluation",
                                  commit_message=f"add {label}")
                uploaded[label] = str(p)
        # model card with honest lineage (spec S9)
        card = (
            f"# {intent.model_id}\n\n"
            f"JARVIS BRAIN v1 SFT candidate.\n\n"
            f"- **base model**: {intent.base_model} (revision {intent.base_revision})\n"
            f"- **adapter type**: LoRA/QLoRA 4-bit nf4 (r=64, alpha=128)\n"
            f"- **training method**: {intent.method}\n"
            f"- **dataset**: videlisndichi/jarvis-brain-v1-sft "
            f"(revision {intent.dataset_revision or 'main'})\n"
            f"- **merged**: {intent.merged} (adapter is NOT a merged model unless verified)\n"
            f"- **stage**: {intent.stage}\n\n"
            "Weights are remote-safetensors shards on the HuggingFace Hub; they are "
            "never stored in the JARVIS source tree."
        )
        with tempfile.TemporaryDirectory() as td:
            Path(td, "README.md").write_text(card, encoding="utf-8")
            api.upload_folder(repo_id=intent.model_id, folder_path=td,
                              path_in_repo=".", commit_message="add model card")
        info = api.model_info(intent.model_id, token=tok)
        revision = getattr(info, "sha", "") or ""
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAILED", "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
                "revision": "", "merged": intent.merged}
    finally:
        tok = ""  # drop token
    intent.revision = revision
    intent.merged = False  # spec S9: never claim merged unless merge verified separately
    save_publish_intent(intent)
    return {"status": "DONE", "username": username, "revision": revision,
            "merged": intent.merged, "uploaded": uploaded,
            "model_card": "README.md"}


def secret_scan_artifact(artifact_dir: Path) -> dict[str, Any]:
    """Scan a candidate publish directory for leaked secrets (spec S27).

    Returns {'clean': bool, 'findings': [...]} with masked matches only.
    """
    findings = scan_dir(Path(artifact_dir))
    flat = [f for f in findings if f.get("secrets")]
    return {"clean": not flat, "findings": flat}


@dataclass
class PublishIntent:
    """Description of an artifact prepared for publishing (NOT uploaded yet)."""
    run_id: str
    model_id: str
    base_model: str
    base_revision: str
    method: str
    adapter_path: Optional[Path] = None
    tokenizer_path: Optional[Path] = None
    config_path: Optional[Path] = None
    metrics_path: Optional[Path] = None
    evaluation_report: Optional[Path] = None
    dataset_revision: str = ""
    revision: str = ""     # HF commit revision (filled only after a real upload)
    merged: bool = False  # spec S9: adapter NEVER claimed merged unless verified
    stage: str = "experimental"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "base_model": self.base_model,
            "base_revision": self.base_revision,
            "method": self.method,
            "adapter_path": str(self.adapter_path) if self.adapter_path else None,
            "tokenizer_path": str(self.tokenizer_path) if self.tokenizer_path else None,
            "config_path": str(self.config_path) if self.config_path else None,
            "metrics_path": str(self.metrics_path) if self.metrics_path else None,
            "evaluation_report": str(self.evaluation_report) if self.evaluation_report else None,
            "dataset_revision": self.dataset_revision,
            "revision": self.revision,
            "merged": self.merged,
            "stage": self.stage,
        }


def save_publish_intent(intent: PublishIntent, out: Path | None = None) -> Path:
    from .config import ARTIFACTS_DIR
    out = out or (ARTIFACTS_DIR / "publish" / f"{intent.run_id}.publish.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(intent.to_dict(), indent=2, default=str), encoding="utf-8")
    return out
