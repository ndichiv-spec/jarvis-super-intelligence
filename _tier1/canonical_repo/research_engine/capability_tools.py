"""Capability Fabric v1 — thin adapters over EXISTING JARVIS subsystems.

Every capability here is a :class:`~research_engine.tool_registry.Tool`, so it
inherits the existing authorization + secret-scrubbing boundary.  No new
registry, permission system, secret manager, model router or job manager is
introduced: jobs/artifacts/models/providers are read through the registries that
already exist (``infrastructure.job_registry``, ``artifact_registry``,
``model_registry``, ``provider_registry``) and provider health through the
existing ``ProviderControlCenter``.

Honesty rule: a capability is only ever reported AVAILABLE when its backing
subsystem answers for real.  Missing credentials, missing binaries and empty
registries are reported as NOT_CONFIGURED / UNAVAILABLE / OFFLINE - never
faked.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .models import RiskLevel, ToolResult
from .project_tools import (
    PROJECT_ROOT,
    WORKSPACE_ROOT,
    _fail,
    _glob_match,
    _iter_scope_files,
    _ok,
    _proj_rel,
    _read_bounded,
    _rel,
    _sanitize,
    _is_secret_name,
    safe_path,
)
from .tool_registry import Tool, ToolContext

# Capability lifecycle states (truthful, never inferred from source presence).
AVAILABLE = "AVAILABLE"
DEGRADED = "DEGRADED"
UNAVAILABLE = "UNAVAILABLE"
OFFLINE = "OFFLINE"
NOT_CONFIGURED = "NOT_CONFIGURED"


# --------------------------------------------------------------------------- #
# Provider status (existing control center)
# --------------------------------------------------------------------------- #
def live_provider_status() -> dict[str, Any]:
    """Live provider truth from the existing ProviderControlCenter."""
    try:
        from jarvis_backend.gateway import _ensure_provider_fabric_import_path

        _ensure_provider_fabric_import_path()
        from providers.bootstrap import bootstrap_fabric
        from providers.control_center import ProviderControlCenter

        bootstrap_fabric()
        cc = ProviderControlCenter()
        out: dict[str, Any] = {}
        for pid in cc.list_providers():
            try:
                st = cc.check_provider(pid)
            except Exception as exc:  # noqa: BLE001
                out[pid] = {"state": UNAVAILABLE,
                            "error": f"{type(exc).__name__}: {exc}"}
                continue
            healthy = st.health_status in ("healthy", "degraded")
            out[pid] = {
                "configured": bool(st.configured),
                "reachable": bool(st.model_list_available),
                "authenticated": healthy,
                "available": bool(st.configured and healthy
                                  and st.model_list_available),
                "state": (AVAILABLE if (st.configured and healthy
                                        and st.model_list_available)
                          else (NOT_CONFIGURED if not st.configured else DEGRADED)),
                "health_status": st.health_status,
                "inference_verified": bool(st.inference_verified),
                "latency_ms": st.latency_ms,
                "detail": st.errors or None,
            }
        return out
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}


class ProviderStatusTool(Tool):
    """Live provider health from the existing control center."""

    name = "provider.status"
    description = (
        "Report LIVE provider state (configured / reachable / authenticated / "
        "available) for every provider in the JARVIS fabric. Uses the real "
        "provider control center; never infers availability from the presence of "
        "an adapter or an API-key variable."
    )
    schema = {"type": "object", "properties": {
        "provider": {"type": "string",
                     "description": "Optional single provider id to inspect."}},
        "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            status = live_provider_status()
            want = (args or {}).get("provider")
            if want:
                if want not in status:
                    return _fail(self.name, ctx, started,
                                 f"unknown provider: {want}")
                status = {want: status[want]}
            if "_error" in status:
                return _fail(self.name, ctx, started,
                             f"provider fabric unavailable: {status['_error']}")
            return _ok(self.name, ctx, started, {"providers": status},
                       {"count": len(status)})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# Registry-backed status tools (jobs / artifacts / models)
# --------------------------------------------------------------------------- #
def _registry_snapshot(module_name: str, class_name: str,
                       list_method: str, limit: int) -> dict[str, Any]:
    """Read an existing JARVIS registry. Reports honestly when empty/unavailable."""
    try:
        module = __import__(f"infrastructure.{module_name}",
                            fromlist=[class_name])
        registry = getattr(module, class_name).get_instance()
        lister = getattr(registry, list_method)
        try:
            items = lister(limit=limit)
        except TypeError:
            items = lister()
        rows = []
        for item in (items or [])[:limit]:
            if hasattr(item, "to_dict"):
                rows.append(item.to_dict())
            elif hasattr(item, "__dict__"):
                rows.append({k: v for k, v in vars(item).items()
                             if not k.startswith("_")})
            else:
                rows.append({"value": str(item)})
        return {"state": AVAILABLE, "count": len(rows), "items": rows}
    except Exception as exc:  # noqa: BLE001
        return {"state": UNAVAILABLE,
                "error": f"{type(exc).__name__}: {exc}", "count": 0, "items": []}


class _RegistryStatusTool(Tool):
    risk = RiskLevel.READ
    module_name = ""
    class_name = ""
    list_method = ""
    entity = "items"
    limit = 50

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        snap = _registry_snapshot(self.module_name, self.class_name,
                                  self.list_method, self.limit)
        if snap.get("state") == UNAVAILABLE:
            return _ok(self.name, ctx, started, snap, {"available": False})
        snap["registry"] = f"infrastructure.{self.module_name}.{self.class_name}"
        return _ok(self.name, ctx, started, snap, {"count": snap.get("count", 0)})


class JobStatusTool(_RegistryStatusTool):
    name = "job.status"
    description = ("Report real JARVIS jobs from the existing JobRegistry "
                   "(QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED). Returns an "
                   "empty list truthfully when no jobs exist; never fabricates.")
    schema = {"type": "object", "properties": {
        "status": {"type": "string",
                   "description": "Optional status filter, e.g. RUNNING."}},
        "required": []}
    module_name, class_name, list_method = "job_registry", "JobRegistry", "list_jobs"

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        snap = _registry_snapshot(self.module_name, self.class_name,
                                  self.list_method, self.limit)
        if snap.get("state") == UNAVAILABLE:
            return _ok(self.name, ctx, started, snap, {"available": False})
        want = ((args or {}).get("status") or "").upper()
        if want:
            snap["items"] = [
                j for j in snap["items"]
                if str(j.get("status", "")).upper() == want
            ]
            snap["count"] = len(snap["items"])
        snap["registry"] = f"infrastructure.{self.module_name}.{self.class_name}"
        if snap["count"] == 0:
            snap["note"] = "No jobs recorded. This is the real state."
        return _ok(self.name, ctx, started, snap, {"count": snap.get("count", 0)})


class ArtifactInspectTool(_RegistryStatusTool):
    name = "artifact.inspect"
    description = ("Report real model/data artifacts known to the existing "
                   "ArtifactRegistry. Empty when nothing is registered; never "
                   "fabricated.")
    schema = {"type": "object", "properties": {}, "required": []}
    module_name = "artifact_registry"
    class_name = "ArtifactRegistry"
    list_method = "list_artifacts"


class ModelStatusTool(_RegistryStatusTool):
    name = "model.status"
    description = ("Report real model records from the existing ModelRegistry, "
                   "including lifecycle state. Empty when nothing registered; "
                   "never fabricated.")
    schema = {"type": "object", "properties": {}, "required": []}
    module_name = "model_registry"
    class_name = "ModelRegistry"
    list_method = "list_models"


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
class FilesReadTool(Tool):
    """Read one workspace-confined text file (secrets excluded)."""

    name = "files.read"
    description = ("Read a single text file from the authorized JARVIS workspace. "
                   "Path traversal is rejected and secret-bearing files (.env, "
                   "*.pem, credentials, tokens) are never readable.")
    schema = {"type": "object", "properties": {
        "path": {"type": "string", "description": "Workspace-relative file path."},
        "max_bytes": {"type": "integer",
                      "description": "Cap on returned characters (default 20000)."},
    }, "required": ["path"]}
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            raw = (args or {}).get("path") or ""
            target = safe_path(raw)
            if _is_secret_name(target.name):
                return _fail(self.name, ctx, started,
                             "refused: secret-bearing files are not readable")
            if not target.is_file():
                return _fail(self.name, ctx, started,
                             f"not a file: {_rel(target)}")
            limit = min(int((args or {}).get("max_bytes") or 20_000), 100_000)
            text = _read_bounded(target) or ""
            if not text:
                return _fail(self.name, ctx, started,
                             "file empty or unreadable (binary/oversized)")
            truncated = len(text) > limit
            return _ok(self.name, ctx, started, {
                "file": _rel(target),
                "truncated": truncated,
                "content": _sanitize(text[:limit]),
            }, {"bytes": len(text)})
        except ValueError as exc:
            return _fail(self.name, ctx, started, f"path rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class FilesSearchTool(Tool):
    """Bounded workspace-confined file-name / content search."""

    name = "files.search"
    description = ("Search the authorized workspace by filename substring or "
                   "literal content, with bounded results. Traversal rejected; "
                   "secret files excluded.")
    schema = {"type": "object", "properties": {
        "query": {"type": "string", "description": "Filename substring or content."},
        "mode": {"type": "string", "enum": ["filename", "content"],
                 "description": "Default filename."},
        "path": {"type": "string", "description": "Optional scope."},
        "max_results": {"type": "integer", "description": "Default 40."},
    }, "required": ["query"]}
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            query = (args.get("query") or "").strip()
            if not query:
                return _fail(self.name, ctx, started, "query is required")
            root = safe_path(args.get("path") or str(PROJECT_ROOT))
            mode = args.get("mode") or "filename"
            max_results = min(int(args.get("max_results") or 40), 200)
            results: list[dict[str, Any]] = []
            for path in _iter_scope_files(root):
                if len(results) >= max_results:
                    break
                if mode == "filename":
                    if query.lower() in path.name.lower():
                        results.append({"file": _rel(path), "match": "filename"})
                else:
                    src = _read_bounded(path)
                    if src and query in src:
                        results.append({"file": _rel(path), "match": "content"})
            return _ok(self.name, ctx, started, {
                "query": query, "mode": mode, "scope": _rel(root),
                "count": len(results), "results": results,
                "truncated": len(results) >= max_results,
            }, {"count": len(results)})
        except ValueError as exc:
            return _fail(self.name, ctx, started, f"path rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# Docker (EXEC, honest when absent)
# --------------------------------------------------------------------------- #
class DockerStatusTool(Tool):
    """Docker availability + running containers, with honest optionality."""

    name = "docker.status"
    description = ("Report Docker availability, the required action when it is "
                   "absent, its impact on the development lifecycle, the compose "
                   "templates that exist, and running containers when reachable. "
                   "Docker is OPTIONAL: Kaggle training, Hugging Face artifacts "
                   "and NVIDIA inference do not require it. Executes no "
                   "arbitrary commands.")
    schema = {"type": "object", "properties": {}, "required": []}
    risk = RiskLevel.EXEC

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        from jarvis_backend.brain_fabric import docker_status as _ds

        base = _ds()
        exe = shutil.which("docker")
        if not exe:
            return _ok(self.name, ctx, started, base, {"available": False})
        try:
            proc = subprocess.run(  # noqa: S603
                [exe, "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"],
                capture_output=True, text=True, timeout=15, shell=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            base["state"] = OFFLINE
            base["reason"] = f"docker CLI did not respond: {type(exc).__name__}"
            return _ok(self.name, ctx, started, base, {"available": False})
        if proc.returncode != 0:
            base["state"] = OFFLINE
            base["reason"] = (proc.stderr or "docker daemon not reachable").strip()[:300]
            return _ok(self.name, ctx, started, base, {"available": False})
        containers = [
            {"name": n, "image": i, "status": s}
            for line in proc.stdout.splitlines() if line.strip()
            for n, i, s in [line.split("\t", 2)] if len((n, i, s)) == 3
        ]
        base["containers"] = containers
        base["count"] = len(containers)
        return _ok(self.name, ctx, started, base, {"count": len(containers)})


# --------------------------------------------------------------------------- #
# GitHub (NETWORK, honest when unauthenticated)
# --------------------------------------------------------------------------- #
class _GitHubBase(Tool):
    risk = RiskLevel.NETWORK
    requires_confirmation = True

    @staticmethod
    def _token() -> tuple[Optional[str], str]:
        for var in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN"):
            val = os.environ.get(var, "").strip()
            if val:
                return val, var
        return None, ""

    async def _call(self, ctx: ToolContext, started: float,
                    endpoint: str, tool_name: str,
                    params: Optional[dict[str, Any]] = None) -> ToolResult:
        token, var = self._token()
        if not token:
            return _ok(tool_name, ctx, started, {
                "state": NOT_CONFIGURED,
                "reason": ("GitHub integration is not authenticated: none of "
                           "GITHUB_TOKEN/GH_TOKEN/GITHUB_API_TOKEN is set."),
            }, {"available": False})
        try:
            import httpx
        except ImportError:
            return _ok(tool_name, ctx, started, {
                "state": UNAVAILABLE,
                "reason": "httpx not installed; GitHub API unreachable",
            }, {"available": False})
        url = f"https://api.github.com{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url, params=params or {},
                    headers={"Authorization": f"Bearer {token}",
                             "Accept": "application/vnd.github+json"},
                )
            if resp.status_code >= 400:
                return _ok(tool_name, ctx, started, {
                    "state": UNAVAILABLE,
                    "http_status": resp.status_code,
                    "reason": "GitHub API returned an error",
                }, {"available": False})
            return _ok(tool_name, ctx, started,
                       {"state": AVAILABLE, "data": resp.json(),
                        "credential_source": f"env:{var} (value never exposed)"},
                       {"http_status": resp.status_code})
        except Exception as exc:  # noqa: BLE001
            return _ok(tool_name, ctx, started, {
                "state": OFFLINE,
                "reason": f"{type(exc).__name__}: GitHub unreachable",
            }, {"available": False})


class GithubInspectTool(_GitHubBase):
    name = "github.inspect"
    description = ("Inspect a GitHub repository (metadata, branches, recent "
                   "commits) through the GitHub API. Requires an authenticated "
                   "GitHub integration; reports NOT_CONFIGURED otherwise. The "
                   "token is never returned to the model.")
    schema = {"type": "object", "properties": {
        "repo": {"type": "string", "description": "owner/name."},
        "what": {"type": "string",
                 "enum": ["repo", "branches", "commits"],
                 "description": "Default repo."},
    }, "required": ["repo"]}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        repo = ((args or {}).get("repo") or "").strip("/")
        what = (args or {}).get("what") or "repo"
        if not repo:
            return _fail(self.name, ctx, started, "repo is required")
        endpoint = {
            "repo": f"/repos/{repo}",
            "branches": f"/repos/{repo}/branches",
            "commits": f"/repos/{repo}/commits",
        }.get(what, f"/repos/{repo}")
        params = {"per_page": 10} if what in {"branches", "commits"} else None
        return await self._call(ctx, started, endpoint, self.name, params)


class GithubSearchTool(_GitHubBase):
    name = "github.search"
    description = ("Search code/issues across GitHub through the GitHub API. "
                   "Requires an authenticated GitHub integration; reports "
                   "NOT_CONFIGURED otherwise. Token never returned to the model.")
    schema = {"type": "object", "properties": {
        "query": {"type": "string"},
        "kind": {"type": "string", "enum": ["code", "issues"],
                 "description": "Default code."},
    }, "required": ["query"]}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        query = ((args or {}).get("query") or "").strip()
        if not query:
            return _fail(self.name, ctx, started, "query is required")
        kind = (args or {}).get("kind") or "code"
        endpoint = "/search/code" if kind == "code" else "/search/issues"
        return await self._call(ctx, started, endpoint, self.name,
                                {"q": query, "per_page": 10})


# --------------------------------------------------------------------------- #
# Brain / Silverwing development fabric
# --------------------------------------------------------------------------- #
class _FabricTool(Tool):
    """Read-only view over the Brain/Silverwing development fabric."""
    risk = RiskLevel.READ
    view = "brain"
    # Explicit: ``Tool.schema`` uses dataclasses.field, which yields a Field
    # object (not a dict) because Tool is not itself a dataclass. Every
    # capability must expose a real JSON schema.
    schema = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            from jarvis_backend import brain_fabric as bf

            if self.view == "brain":
                data = bf.discover_brain()
            elif self.view == "silverwing":
                data = bf.discover_silverwing()
            elif self.view == "external":
                data = bf.external_status()
            elif self.view == "pipeline":
                data = bf.pipeline_readiness()
            else:  # nvidia
                data = bf.nvidia_deployment_readiness()
            leaks = bf.assert_no_secrets(data)
            if leaks:
                data = {"error": "withheld: secret-shaped fields in metadata",
                        "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, data)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class BrainStatusTool(_FabricTool):
    name = "brain.status"
    description = ("Report real JARVIS Brain state: runtime contract, discovered "
                   "artifacts, provenance, evaluations, promotion-gate stage and "
                   "deployment/inference truth. Never claims promotion or "
                   "deployment that has not happened.")
    schema = {"type": "object", "properties": {}, "required": []}
    view = "brain"


class BrainArtifactsTool(_FabricTool):
    name = "brain.artifacts"
    description = ("List real JARVIS Brain artifacts (checkpoints, published "
                   "models) with full provenance: run id, base model + revision, "
                   "dataset revision/sha, HF repository + revision.")
    schema = {"type": "object", "properties": {}, "required": []}
    view = "brain"


class SilverwingStatusTool(_FabricTool):
    name = "silverwing.status"
    description = ("Report real Silverwing state: model directories with sizes, run "
                   "manifests, runtime endpoint reachability and local inference "
                   "status. Offline is reported honestly.")
    schema = {"type": "object", "properties": {}, "required": []}
    view = "silverwing"


class TrainingStatusTool(_FabricTool):
    name = "training.status"
    description = ("Report training-platform connectivity: Hugging Face and Kaggle "
                   "configuration/credential state and discovered kernels. Reads "
                   "only - never submits a training run.")
    schema = {"type": "object", "properties": {}, "required": []}
    view = "external"


class NvidiaDeploymentTool(_FabricTool):
    name = "nvidia.deployment"
    description = ("Report whether the verified NVIDIA provider can serve as a "
                   "deployment target for Brain/Silverwing artifacts, including "
                   "health and inference verification. Uses the existing provider "
                   "control center.")
    schema = {"type": "object", "properties": {}, "required": []}
    view = "nvidia"


class PipelineReadinessTool(_FabricTool):
    name = "fabric.pipeline"
    description = ("Report end-to-end readiness of the development pipeline "
                   "Kaggle -> Hugging Face -> NVIDIA -> JARVIS. Each link reports "
                   "its own truthful state and whether it blocks. Docker is "
                   "reported as optional and never blocking.")
    schema = {"type": "object", "properties": {}, "required": []}
    view = "pipeline"


class IntegrationsMatrixTool(_FabricTool):
    name = "fabric.integrations"
    description = ("Return the truthful integration matrix for Kaggle, Hugging "
                   "Face, NVIDIA and Docker plus Brain/Silverwing: role, "
                   "configured, authenticated, reachable, available, healthy, "
                   "last successful operation, current artifact/job, and the "
                   "derived next continuation with whether it needs approval. "
                   "Never returns credentials and never fabricates next steps.")
    schema = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        from jarvis_backend.brain_fabric import (
            assert_no_secrets,
            integration_matrix,
        )

        data = integration_matrix()
        leaks = assert_no_secrets(data)
        if leaks:
            data = {"error": "withheld: secret-shaped fields",
                    "fields": sorted(set(leaks))}
        return _ok(self.name, ctx, started, data)


def _fabric_view(view: str):
    """Resolve a fabric view name to its callable (single source of truth)."""
    import jarvis_backend.brain_fabric as bf

    return {
        "development": bf.development_status,
        "lifecycle": bf.development_status,
        "next_action": lambda: {
            "brain": bf.brain_lifecycle()["next_action"],
            "silverwing": bf.silverwing_lifecycle()["next_action"],
            "contradictions": bf.contradictions(),
        },
        "verify": bf.development_status,
        "kaggle": lambda: bf._kaggle_real_status(),
        "huggingface": lambda: bf._hf_real_status(),
        "nvidia": bf.nvidia_deployment_readiness,
        "docker": bf.docker_status,
        "brain": bf.brain_lifecycle,
        "silverwing": bf.silverwing_lifecycle,
    }[view]


class _ViewTool(Tool):
    """Generic read-only capability over the development fabric views."""
    risk = RiskLevel.READ
    view = "development"
    doc = "development fabric view"
    schema = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            data = _fabric_view(self.view)()
            from jarvis_backend.brain_fabric import assert_no_secrets

            leaks = assert_no_secrets(data)
            if leaks:
                data = {"error": "withheld: secret-shaped fields",
                        "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, data)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _mk(name: str, view: str, doc: str):
    return type(f"{name.split('.')[-1].capitalize()}ViewTool", (_ViewTool,), {
        "name": name, "view": view, "description": doc, "__doc__": doc,
    })


KaggleStatusTool = _mk("kaggle.status", "kaggle",
                       "Real Kaggle connectivity: credential-file/CLI state, "
                       "authentication, and the account's discoverable "
                       "kernels. Read-only; never submits a run.")
KaggleJobsTool = _mk("kaggle.jobs", "kaggle",
                     "Discoverable Kaggle training kernels/runs with last-run "
                     "metadata. Read-only.")
HuggingFaceStatusTool = _mk("huggingface.status", "huggingface",
                            "Real Hugging Face connectivity and authenticated "
                            "identity. Never returns the token.")
HuggingFaceArtifactsTool = _mk(
    "huggingface.artifacts", "huggingface",
    "JARVIS model repositories on the Hub with live revision, file count, "
    "locally recorded revision and any provenance mismatch.")
NvidiaModelsTool = _mk("nvidia.models", "nvidia",
                       "NVIDIA provider deployment readiness, health and "
                       "inference verification from the existing control center.")
NvidiaInferenceTool = _mk("nvidia.inference", "nvidia",
                          "NVIDIA inference verification state for the JARVIS "
                          "model lifecycle.")
BrainLifecycleTool = _mk("brain.lifecycle", "brain",
                         "Brain's full lifecycle (SOURCE..INFERENCE) with the "
                         "first incomplete stage and the safest next action.")
SilverwingLifecycleTool = _mk("silverwing.lifecycle", "silverwing",
                              "Silverwing's independent lifecycle with its own "
                              "model ids, versions and runtime state.")
SilverwingArtifactsTool = _mk("silverwing.artifacts", "silverwing",
                              "Silverwing model directories and run manifests "
                              "discovered on disk.")
DevelopmentStatusTool = _mk("development.status", "development",
                            "Combined development status for Brain, Silverwing, "
                            "Kaggle, Hugging Face, NVIDIA and Docker, including "
                            "recorded provenance contradictions.")
DevelopmentNextActionTool = _mk(
    "development.next_action", "next_action",
    "The safest next action for Brain and Silverwing, derived from actual "
    "state, plus any unresolved provenance contradictions.")
DevelopmentVerifyTool = _mk("development.verify", "verify",
                            "Re-verify the development fabric end to end and "
                            "report current truthful state.")


# --------------------------------------------------------------------------- #
# Canonical capability inventory
# --------------------------------------------------------------------------- #
def capability_inventory() -> dict[str, Any]:
    """Truthful availability for every registered capability.

    A capability is AVAILABLE only when its backing subsystem answers for real.
    """
    inventory: dict[str, Any] = {}

    # Project tools: real filesystem access, always present.
    for name in ("project.inspect", "project.search", "project.test_status",
                 "files.read", "files.search"):
        inventory[name] = {
            "state": AVAILABLE if PROJECT_ROOT.is_dir() else UNAVAILABLE,
            "risk": "read",
            "source": "research_engine.project_tools / capability_tools",
        }

    # Provider status: real probe.
    providers = live_provider_status()
    prov_ok = "_error" not in providers and bool(providers)
    inventory["provider.status"] = {
        "state": AVAILABLE if prov_ok else UNAVAILABLE,
        "risk": "read",
        "source": "providers.control_center.ProviderControlCenter",
        "detail": providers.get("_error") if not prov_ok else None,
    }

    inventory["sandbox_run"] = {
        "state": AVAILABLE if Path(sys.executable).is_file() else UNAVAILABLE,
        "risk": "exec",
        "source": "research_engine.SandboxRunTool",
        "reason": None if Path(sys.executable).is_file()
        else "current Python executable is unavailable",
    }
    inventory["static_search"] = {
        "state": AVAILABLE,
        "risk": "read",
        "source": "research_engine.StaticSearchTool",
        "reason": "deterministic in-process search capability",
    }

    # Registries: real DB reads.
    for cap, mod, cls, method in (
        ("job.status", "job_registry", "JobRegistry", "list_jobs"),
        ("artifact.inspect", "artifact_registry", "ArtifactRegistry",
         "list_artifacts"),
        ("model.status", "model_registry", "ModelRegistry", "list_models"),
    ):
        snap = _registry_snapshot(mod, cls, method, 1)
        inventory[cap] = {
            "state": snap.get("state", UNAVAILABLE),
            "risk": "read",
            "source": f"infrastructure.{mod}.{cls}",
            "count": snap.get("count", 0),
        }

    # Docker: real CLI probe.
    if not shutil.which("docker"):
        inventory["docker.status"] = {
            "state": UNAVAILABLE, "risk": "exec",
            "source": "docker CLI", "reason": "docker not installed",
        }
    else:
        inventory["docker.status"] = {
            "state": DEGRADED, "risk": "exec", "source": "docker CLI",
            "reason": "installed; daemon reachability checked per invocation",
        }

    # GitHub: credential presence only.
    token, var = _GitHubBase._token()
    inventory["github.inspect"] = {
        "state": "CONFIGURED" if token else NOT_CONFIGURED,
        "risk": "network", "source": "GitHub API",
        "reason": "credentials are present; API execution has not been verified"
        if token else None,
        "credential_source": f"env:{var}" if token else None,
    }
    inventory["github.search"] = dict(inventory["github.inspect"])

    # Brain / Silverwing development fabric: real discovery, honest state.
    for cap, view in (("brain.status", "brain"), ("brain.artifacts", "brain"),
                      ("silverwing.status", "silverwing"),
                      ("training.status", "external"),
                      ("nvidia.deployment", "nvidia")):
        inventory[cap] = {
            "state": DEGRADED, "risk": "read",
            "source": f"jarvis_backend.brain_fabric ({view})",
            "reason": "runtime dependency state is checked when invoked",
        }

    # Live web search is available only when the explicit deployment gate is
    # enabled and the existing HTTP browser engine exposes its real operations.
    from .tool_registry import _web_search_enabled
    if not _web_search_enabled():
        inventory["search_web"] = {
            "state": NOT_CONFIGURED,
            "risk": "network",
            "source": "research_engine.BrowserSearchTool",
            "reason": "live web search is disabled by deployment configuration",
        }
    else:
        try:
            from jarvis_backend.browser_engine import get_engine

            engine = get_engine("default")
            ready = callable(getattr(engine, "search", None)) and callable(
                getattr(engine, "fetch_document", None)
            )
            inventory["search_web"] = {
                "state": AVAILABLE if ready else UNAVAILABLE,
                "risk": "network",
                "source": "jarvis_backend.browser_engine.HttpBrowserEngine",
                "reason": None if ready else "browser search/extraction methods are unavailable",
            }
        except Exception as exc:  # noqa: BLE001 - report dependency failure honestly
            inventory["search_web"] = {
                "state": UNAVAILABLE,
                "risk": "network",
                "source": "jarvis_backend.browser_engine.HttpBrowserEngine",
                "reason": f"browser engine unavailable ({type(exc).__name__})",
            }

    # Registration alone is not evidence that dependencies, authorization,
    # or the execution path are currently ready.
    for name, risk in _registered_risks().items():
        if name in inventory:
            continue
        inventory[name] = {
            "state": DEGRADED,
            "risk": risk,
            "source": "research_engine ToolRegistry",
            "reason": "registered; runtime executability has not been verified",
        }

    return inventory


class CapabilityDiscoverTool(Tool):
    """Answer "what capabilities are available for this task?"."""

    name = "capability.discover"
    description = ("Discover which registered capabilities suit a task, filtered "
                   "by domain, availability, operating mode (online/degraded/"
                   "offline), risk and cost. Returns only capabilities that are "
                   "actually registered - never invents one.")
    schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "What the user wants done."},
            "mode": {"type": "string", "enum": ["online", "degraded", "offline"],
                     "description": "Operating mode (default online)."},
            "include_unavailable": {"type": "boolean"},
        },
        "required": ["task"],
    }
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            from .capability_contract import discover_capabilities

            data = discover_capabilities(
                (args or {}).get("task") or "",
                mode=(args or {}).get("mode") or "online",
                include_unavailable=bool((args or {}).get("include_unavailable")),
            )
            return _ok(self.name, ctx, started, data,
                       {"matched": data["matched"]})
        except ValueError as exc:
            return _fail(self.name, ctx, started, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class CapabilityCatalogueTool(Tool):
    """Full capability contract + domain pack catalogue."""

    name = "capability.catalogue"
    description = ("Return the canonical capability catalogue: every registered "
                   "capability's contract (domain, schemas, risk, availability, "
                   "offline support, cost model, dependencies) plus domain pack "
                   "coverage and which declared domains are still empty.")
    schema = {"type": "object", "properties": {}, "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            from .capability_contract import capability_catalogue

            return _ok(self.name, ctx, started, capability_catalogue(),
                       {"count": capability_catalogue()["capability_count"]})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class _CloudTool(Tool):
    """Read-only capability over the cloud hardware fabric."""
    risk = RiskLevel.READ
    schema = {"type": "object", "properties": {}, "required": []}
    view = "status"

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            from jarvis_backend import cloud_fabric as cf

            if self.view == "status":
                data = cf.cloud_status()
            elif self.view == "resources":
                data = cf.cloud_resources()
            elif self.view == "mode":
                data = cf.execution_mode()
            else:  # select
                data = cf.select_compute((args or {}).get("requirements")
                                         or args or {})
            return _ok(self.name, ctx, started, data)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class CloudStatusTool(_CloudTool):
    name = "cloud.status"
    description = ("Report the cloud hardware fabric: local hardware profile "
                   "(CPU/RAM/GPU/virtualization/SLAT/docker/network) and every "
                   "real remote resource with its granular state chain "
                   "(configured/authenticated/reachable/healthy/"
                   "resource_verified/inference_verified).")
    view = "status"


class CloudResourcesTool(_CloudTool):
    name = "cloud.resources"
    description = ("List real execution resources (local control node, NVIDIA, "
                   "Kaggle, Hugging Face, container runtime) with capabilities, "
                   "cost class and truthful availability. Only resources that "
                   "actually answered are listed.")
    view = "resources"


class ComputeSelectTool(_CloudTool):
    name = "compute.select"
    description = ("Select a real execution target for a workload from stated "
                   "requirements (gpu_required, min_gpu_memory_gb, "
                   "docker_required, persistent_runtime, network_required, "
                   "max_cost_class, task). Ranks verified resources by "
                   "purpose-fit; reports RESOURCE_UNAVAILABLE when nothing "
                   "satisfies the request rather than guessing.")
    view = "select"
    schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string"},
            "gpu_required": {"type": "boolean"},
            "min_gpu_memory_gb": {"type": "number"},
            "docker_required": {"type": "boolean"},
            "persistent_runtime": {"type": "boolean"},
            "network_required": {"type": "boolean"},
            "max_cost_class": {"type": "string"},
            "requirements": {"type": "object"},
        },
        "required": [],
    }


class ExecutionModeTool(_CloudTool):
    name = "cloud.execution_mode"
    description = ("Report the current operating mode (online/degraded/offline) "
                   "from real connectivity, local hardware limits and the "
                   "offline fallback capability set. No cloud response is ever "
                   "fabricated.")
    view = "mode"


# --------------------------------------------------------------------------- #
# Compute capability family (Phase 9 §3)
# --------------------------------------------------------------------------- #
# Provider-agnostic compute capabilities. The Brain sees these names; the
# control plane below resolves them to real provider-specific implementations
# (NVIDIA inference, Kaggle training, HuggingFace artifacts). Credentials are
# NEVER exposed through these tools — every result is scrubbed and every
# provider call resolves its own secrets via SecretManager.
# --------------------------------------------------------------------------- #

class ComputeDiscoverTool(Tool):
    """Discover real compute resources and their truthful availability."""
    name = "compute.discover"
    description = (
        "Report all real compute resources the fabric can see: local control "
        "node, NVIDIA inference, Kaggle training, Hugging Face, container "
        "runtime, and any configured remote host. Each resource carries its "
        "full state chain (configured/authenticated/reachable/healthy/"
        "resource_verified). Nothing is fabricated.")
    schema = {"type": "object", "properties": {}, "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import cloud_fabric as cf
            from jarvis_backend.brain_fabric import assert_no_secrets

            data = cf.cloud_resources()
            leaks = assert_no_secrets(data)
            if leaks:
                data = {"error": "withheld: secret-shaped fields in discovery",
                        "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, data)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeVerifyTool(Tool):
    """Verify that a specific compute resource is truly usable."""
    name = "compute.verify"
    description = (
        "Verify a named compute resource by re-running its real probe. The "
        "resource id (e.g. 'local:control-node', 'cloud:nvidia', "
        "'cloud:kaggle', 'cloud:huggingface', 'remote:<id>') is mapped to the "
        "real verifier for that resource. Reports RESOURCE_UNAVAILABLE when no "
        "verified resource matches rather than guessing.")
    schema = {"type": "object", "properties": {
        "resource_id": {"type": "string",
                        "description": "Resource to verify (local:control-node, "
                                       "cloud:nvidia, cloud:kaggle, "
                                       "cloud:huggingface, remote:<id>)"},
    }, "required": ["resource_id"]}
    risk = RiskLevel.READ

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import cloud_fabric as cf

            rid = (args or {}).get("resource_id", "")
            if not rid:
                return _fail(self.name, ctx, started, "resource_id is required")
            cf._PROBE_REFRESH = True  # force fresh probe for the targeted resource
            disc = cf.cloud_resources()
            resources = disc.get("resources", [])
            match = None
            for res in resources:
                if res.get("resource_id") == rid or res.get("provider") == rid:
                    match = res
                    break
            if match is None:
                return _ok(self.name, ctx, started, {
                    "resource_id": rid,
                    "verified": False,
                    "status": "NOT_FOUND",
                    "detail": (f"No resource with id '{rid}' was discovered. "
                               f"Discoverable: {sorted(r.get('resource_id') for r in resources)}"),
                })
            chain = match.get("state_chain") or {}
            verified = match.get("status") in ("AVAILABLE", "HEALTHY",
                                               "RESOURCE_VERIFIED", "JOB_VERIFIED")
            return _ok(self.name, ctx, started, {
                "resource_id": rid,
                "verified": verified,
                "status": match.get("status"),
                "state_chain": chain,
                "detail": match.get("reason") or match.get("note"),
            })
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeInferenceTool(Tool):
    """Report real inference capability without exposing credentials.

    Delegates to the existing provider control center and local hardware probe.
    The Brain sees whether inference is possible — it never sees tokens.
    """
    name = "compute.inference"
    description = (
        "Report whether real inference is available: local hardware GPU/CPU, "
        "NVIDIA inference readiness via the existing control center. Does NOT "
        "expose API keys or tokens. Actual inference execution goes through the "
        "authorized control-plane path, not through this capability.")
    schema = {"type": "object", "properties": {
        "model": {"type": "string", "description": "Optional model name/identifier."},
        "provider": {"type": "string",
                     "description": "Optional provider hint (nvidia/local)."},
    }, "required": []}
    risk = RiskLevel.NETWORK

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import cloud_fabric as cf
            from research_engine.capability_tools import live_provider_status
            from jarvis_backend.brain_fabric import assert_no_secrets

            providers = live_provider_status()
            local = cf.local_hardware()
            # Determine inference readiness truthfully
            nv = providers.get("nvidia", {})
            nv_ready = bool(nv.get("available") or nv.get("inference_verified"))
            local_gpu = bool(local.get("gpu")) and local.get("gpu_count", 0) > 0
            local_cpu = local.get("cpu_logical_cores", 0) > 0
            results = {
                "nvidia": {
                    "available": nv_ready,
                    "inference_verified": bool(nv.get("inference_verified")),
                    "health_status": nv.get("health_status"),
                    "latency_ms": nv.get("latency_ms"),
                    "detail": nv.get("detail"),
                },
                "local": {
                    "gpu_available": local_gpu,
                    "cpu_available": local_cpu,
                    "execution": ("gpu" if local_gpu else ("cpu" if local_cpu else "unavailable")),
                },
            }
            # Local inference doesn't need credentials
            local_inference = local_gpu or local_cpu
            results["any_inference_available"] = bool(nv_ready or local_inference)
            results["credentials_exposed"] = False
            leaks = assert_no_secrets(results)
            if leaks:
                results = {"error": "withheld: secret-shaped fields",
                           "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, results)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeTrainingTool(Tool):
    """Report real training readiness — never auto-submits.

    Delegates to brain_training.pipeline readiness. Training submission
    requires explicit authorization through the control plane.
    """
    name = "compute.training"
    description = (
        "Report real training readiness: Kaggle connectivity, Kaggle kernel "
        "configuration, local GPU availability, HuggingFace token validity "
        "and dataset presence. Never submits a training run — that requires "
        "explicit authorization through the control plane.")
    schema = {"type": "object", "properties": {
        "base_model": {"type": "string"},
        "dataset": {"type": "string"},
    }, "required": []}
    risk = RiskLevel.EXEC
    requires_confirmation = True

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import brain_fabric
            from jarvis_backend.brain_fabric import assert_no_secrets

            ext = brain_fabric.external_status()
            hw_lines = []
            try:
                from brain_training.hardware import gpu_probe
                hw = gpu_probe()
                hw_lines = [hw.to_status()]
            except Exception:
                hw_lines = ["unavailable"]
            kaggle = ext.get("kaggle", {})
            hf = ext.get("hugging_face", {})
            # Check dataset presence truthfully
            from brain_training.config import SFT_CORPUS
            dataset_present = SFT_CORPUS.exists()
            result = {
                "training_ready": (kaggle.get("state") == "AVAILABLE" and
                                   dataset_present),
                "kaggle": {
                    "state": kaggle.get("state"),
                    "configured": kaggle.get("configured"),
                    "kernel_count": kaggle.get("kernel_count"),
                    "detail": kaggle.get("error"),
                },
                "huggingface": {
                    "state": hf.get("state"),
                    "token_valid": hf.get("token_valid"),
                    "repositories": len(hf.get("repositories") or {}),
                },
                "local_hardware": hw_lines,
                "dataset_present": dataset_present,
                "requires_approval": True,
                "note": ("Training is NOT auto-submitted. Submit via "
                         "/api/v2/control/compute/training with authorization."),
            }
            leaks = assert_no_secrets(result)
            if leaks:
                result = {"error": "withheld: secret-shaped fields",
                          "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, result)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeEvaluationTool(Tool):
    """Report real evaluation pipeline state."""
    name = "compute.evaluation"
    description = (
        "Report the evaluation pipeline state: comparison artifacts, baseline "
        "models, and promotion-gate status. Uses real filesystem + registry "
        "checks. Never fabricates evaluation results.")
    schema = {"type": "object", "properties": {
        "model_id": {"type": "string"},
    }, "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import brain_fabric
            from jarvis_backend.brain_fabric import assert_no_secrets

            brain = brain_fabric.discover_brain()
            pipeline = brain_fabric.pipeline_readiness()
            eval_comp = None
            eval_path = None
            try:
                from brain_training.config import ARTIFACTS_DIR
                eval_path = ARTIFACTS_DIR / "evaluation" / "jarvis_brain_comparison.json"
                eval_comp = eval_path.exists()
            except Exception:
                eval_comp = False
            promotion = brain_fabric._promotion_state() if hasattr(brain_fabric, "_promotion_state") else {}
            result = {
                "evaluation_ready": bool(eval_comp),
                "comparison_present": bool(eval_comp),
                "pipeline_links": pipeline.get("links", {}),
                "core_pipeline_ready": pipeline.get("core_pipeline_ready"),
                "promotion_current_stage": promotion.get("current_stage"),
                "promotion_target_stage": promotion.get("target_stage"),
                "promotion_allowed": promotion.get("promotion_allowed"),
                "brain_lifecycle": brain.get("lifecycle"),
            }
            leaks = assert_no_secrets(result)
            if leaks:
                result = {"error": "withheld: secret-shaped fields",
                          "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, result)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeEmbeddingTool(Tool):
    """Report real embedding-generation capability."""
    name = "compute.embedding"
    description = (
        "Report whether embedding generation is available: local CPU/GPU or "
        "NVIDIA inference. Does NOT expose credentials. Actual embedding "
        "generation that requires API tokens goes through the signed control "
        "plane, not this capability.")
    schema = {"type": "object", "properties": {}, "required": []}
    risk = RiskLevel.NETWORK

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import cloud_fabric as cf
            from research_engine.capability_tools import live_provider_status
            from jarvis_backend.brain_fabric import assert_no_secrets

            local = cf.local_hardware()
            providers = live_provider_status()
            nv = providers.get("nvidia", {})
            local_cpu = local.get("cpu", {}).get("cores", 0) > 0
            result = {
                "available": bool(local_cpu or nv.get("available")),
                "local_cpu": local_cpu,
                "nvidia_available": bool(nv.get("available")),
                "credentials_exposed": False,
            }
            leaks = assert_no_secrets(result)
            if leaks:
                result = {"error": "withheld: secret-shaped fields",
                          "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, result)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeArtifactUploadTool(Tool):
    """Report real HuggingFace artifact-upload readiness — never auto-uploads."""
    name = "compute.artifact_upload"
    description = (
        "Report HuggingFace artifact-upload readiness: token presence (verified "
        "via whoami, not exposed), namespace/repo state, and secret-scan results "
        "for the local artifact directory. Never performs an upload — that "
        "requires explicit authorization through the control plane.")
    schema = {"type": "object", "properties": {
        "repo_id": {"type": "string"},
        "path": {"type": "string"},
    }, "required": []}
    risk = RiskLevel.WRITE
    requires_confirmation = True

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import brain_fabric
            from jarvis_backend.brain_fabric import assert_no_secrets

            ext = brain_fabric.external_status()
            hf = ext.get("hugging_face", {})
            result = {
                "upload_ready": bool(hf.get("token_valid")),
                "token_present": bool(hf.get("token_present")),
                "token_valid": bool(hf.get("token_valid")),
                "namespace": hf.get("namespace"),
                "repositories": sorted((hf.get("repositories") or {}).keys()),
                "requires_approval": True,
                "note": ("Upload is NOT auto-performed. Submit via "
                         "/api/v2/control/compute/artifact/upload with authorization."),
            }
            leaks = assert_no_secrets(result)
            if leaks:
                result = {"error": "withheld: secret-shaped fields",
                          "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, result)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeArtifactDownloadTool(Tool):
    """Report real HuggingFace artifact-download readiness."""
    name = "compute.artifact_download"
    description = (
        "Report HuggingFace artifact-download readiness: token validity, "
        "known repositories and the current revision of a requested repo (if "
        "specified). Does NOT expose tokens. Actual downloads go through the "
        "authorized control plane.")
    schema = {"type": "object", "properties": {
        "repo_id": {"type": "string", "description": "HF repo to inspect."},
        "revision": {"type": "string"},
    }, "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import brain_fabric
            from jarvis_backend.brain_fabric import assert_no_secrets

            ext = brain_fabric.external_status()
            hf = ext.get("hugging_face", {})
            repo_id = (args or {}).get("repo_id")
            repos = hf.get("repositories") or {}
            repo_info = None
            if repo_id and repo_id in repos:
                repo_info = repos[repo_id]
            result = {
                "download_ready": bool(hf.get("token_valid")),
                "token_present": bool(hf.get("token_present")),
                "token_valid": bool(hf.get("token_valid")),
                "repositories": sorted(repos.keys()),
                "repo_detail": repo_info,
            }
            leaks = assert_no_secrets(result)
            if leaks:
                result = {"error": "withheld: secret-shaped fields",
                          "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, result)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeJobSubmitTool(Tool):
    """Submit a compute job record to the existing JobRegistry.

    This creates a real job entry — it does NOT dispatch to any provider. The
    job is recorded for scheduling/authorization. Provider dispatch happens
    through the signed control plane, never through this capability.
    """
    name = "compute.job_submit"
    description = (
        "Create a real job record in the existing JobRegistry. The job is "
        "recorded as PENDING and must be picked up by an authorized scheduler. "
        "This capability does NOT dispatch to any provider — it only records "
        "the intent. Requires compute:submit permission.")
    schema = {"type": "object", "properties": {
        "job_type": {"type": "string",
                     "description": "inference|training|evaluation|embedding|other"},
        "model_id": {"type": "string"},
        "parameters": {"type": "object"},
        "resource_cpu": {"type": "number"},
        "resource_memory_gb": {"type": "number"},
        "resource_gpu": {"type": "integer"},
        "tags": {"type": "array", "items": {"type": "string"}},
    }, "required": ["job_type"]}
    risk = RiskLevel.EXEC
    requires_confirmation = True

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            a = args or {}
            job_type_raw = (a.get("job_type") or "").lower()
            if not job_type_raw:
                return _fail(self.name, ctx, started, "job_type is required")
            try:
                from infrastructure.job_registry import (
                    get_job_registry, JobInfo, JobType, JobStatus,
                )
            except Exception:
                return _fail(self.name, ctx, started,
                             "JobRegistry infrastructure unavailable")
            jt_map = {
                "training": JobType.TRAINING,
                "fine_tuning": JobType.FINE_TUNING,
                "inference": JobType.INFERENCE,
                "evaluation": JobType.EVALUATION,
                "deployment": JobType.DEPLOYMENT,
                "other": JobType.OTHER,
            }
            jt = jt_map.get(job_type_raw, JobType.OTHER)
            import uuid as _uuid
            jid = str(_uuid.uuid4())
            job = JobInfo(
                id=str(_uuid.uuid4()),
                job_id=jid,
                job_type=jt.value,
                status=JobStatus.PENDING.value,
                user_id=ctx.user_id,
                model_id=a.get("model_id") or "",
                resource_cpu=float(a.get("resource_cpu") or 1.0),
                resource_memory_gb=float(a.get("resource_memory_gb") or 1.0),
                resource_gpu=int(a.get("resource_gpu") or 0),
                parameters=dict(a.get("parameters") or {}),
                tags=list(a.get("tags") or []),
                created_by=ctx.user_id,
            )
            registry = get_job_registry()
            saved = registry.create_job(job)
            return _ok(self.name, ctx, started, {
                "job_id": saved.job_id,
                "status": saved.status,
                "job_type": saved.job_type,
                "note": ("Job recorded as PENDING. Provider dispatch requires "
                         "separate authorization through the control plane."),
            }, {"job_id": jid})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeJobStatusTool(Tool):
    """Report real job status from the existing JobRegistry."""
    name = "compute.job_status"
    description = (
        "Report the real status of a job from the existing JobRegistry. "
        "Returns NOT_FOUND when the job_id is unknown. Empty list truthfully "
        "when no jobs exist.")
    schema = {"type": "object", "properties": {
        "job_id": {"type": "string", "description": "Job identifier."},
    }, "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from infrastructure.job_registry import get_job_registry
            registry = get_job_registry()
            a = args or {}
            jid = a.get("job_id")
            if jid:
                job = registry.get(jid)
                if job is None:
                    return _ok(self.name, ctx, started, {
                        "job_id": jid,
                        "status": "NOT_FOUND",
                        "found": False,
                    })
                return _ok(self.name, ctx, started, {
                    "job_id": job.job_id,
                    "status": job.status,
                    "job_type": job.job_type,
                    "found": True,
                    "provider_job_id": job.result.get("provider_job_id") if job.result else None,
                })
            # No job_id: list recent
            jobs = registry.list_jobs(limit=20)
            rows = []
            for j in jobs:
                rows.append({
                    "job_id": j.job_id,
                    "status": j.status,
                    "job_type": j.job_type,
                })
            return _ok(self.name, ctx, started, {
                "jobs": rows,
                "count": len(rows),
            })
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeJobCancelTool(Tool):
    """Cancel a job in the existing JobRegistry."""
    name = "compute.job_cancel"
    description = (
        "Cancel a pending/running job recorded in the existing JobRegistry by "
        "transitioning it to CANCELLED. Requires compute:cancel permission. "
        "Returns NOT_FOUND for unknown job_id.")
    schema = {"type": "object", "properties": {
        "job_id": {"type": "string", "description": "Job to cancel."},
        "reason": {"type": "string"},
    }, "required": ["job_id"]}
    risk = RiskLevel.EXEC
    requires_confirmation = True

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from infrastructure.job_registry import get_job_registry
            registry = get_job_registry()
            a = args or {}
            jid = a.get("job_id")
            if not jid:
                return _fail(self.name, ctx, started, "job_id is required")
            # Verify the job exists first
            job = registry.get(jid)
            if job is None:
                return _ok(self.name, ctx, started, {
                    "job_id": jid,
                    "cancelled": False,
                    "status": "NOT_FOUND",
                })
            ok = registry.cancel_job(jid, reason=a.get("reason") or "")
            return _ok(self.name, ctx, started, {
                "job_id": jid,
                "cancelled": bool(ok),
                "status": "CANCELLED" if ok else job.status,
            })
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class ComputeResourceHealthTool(Tool):
    """Report real health of compute resources."""
    name = "compute.resource_health"
    description = (
        "Report real health state for all compute resources, or a single "
        "resource by id. Aggregates local hardware, provider control-center "
        "health checks and remote-host probes. Health is derived from actual "
        "verification, never from credential presence alone.")
    schema = {"type": "object", "properties": {
        "resource_id": {"type": "string"},
    }, "required": []}
    risk = RiskLevel.READ

    async def invoke(self, args, ctx):
        started = time.monotonic()
        try:
            from jarvis_backend import cloud_fabric as cf
            from research_engine.capability_tools import live_provider_status
            from jarvis_backend.brain_fabric import assert_no_secrets

            resources = cf.cloud_resources()
            providers = live_provider_status()
            by_provider = {p: v for p, v in providers.items() if p != "_error"}
            # Build health summary per resource
            health = {}
            for res in resources.get("resources", []):
                rid = res.get("resource_id")
                prov = res.get("provider", "")
                prov_health = by_provider.get(prov, {})
                health[rid] = {
                    "state": res.get("status"),
                    "configured": bool(prov_health.get("configured")),
                    "authenticated": bool(prov_health.get("authenticated")),
                    "reachable": bool(prov_health.get("reachable")),
                    "available": bool(res.get("status") == "AVAILABLE"),
                    "health_status": prov_health.get("health_status") or res.get("health"),
                    "latency_ms": prov_health.get("latency_ms"),
                    "detail": (prov_health.get("detail") or res.get("note")
                               or res.get("reason")),
                }
            # Add local resource health
            local = resources.get("local_hardware", {})
            health["local:control-node"] = {
                "state": "AVAILABLE" if local.get("usable") else "DEGRADED",
                "configured": True,
                "authenticated": True,
                "reachable": True,
                "available": bool(local.get("usable")),
                "health_status": "local",
                "detail": local.get("reason"),
            }
            a = args or {}
            rid = a.get("resource_id")
            if rid:
                result = {"resource_id": rid, "health": health.get(rid, {
                    "state": "NOT_FOUND",
                    "available": False,
                    "detail": "Resource not discovered",
                })}
            else:
                result = {"resources": health,
                          "summary": {
                              "total": len(health),
                              "available": sum(1 for v in health.values()
                                               if v.get("available")),
                              "unavailable": sum(1 for v in health.values()
                                                 if not v.get("available")),
                          }}
            leaks = assert_no_secrets(result)
            if leaks:
                result = {"error": "withheld: secret-shaped fields",
                          "fields": sorted(set(leaks))}
            return _ok(self.name, ctx, started, result)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started,
                         f"{type(exc).__name__}: {exc}")


class _RemoteTool(Tool):
    """Read-only capability over the remote execution host abstraction."""
    risk = RiskLevel.READ
    schema = {"type": "object", "properties": {}, "required": []}
    view = "status"

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            from jarvis_backend import remote_host as rh

            if self.view == "status":
                data = rh.remote_status()
            elif self.view == "health":
                host = rh.discover()
                data = {"resource": host.to_dict(), "available": host.is_usable(),
                        "blocking": False, "health": host.health}
            elif self.view == "resources":
                host = rh.discover()
                data = {
                    "cpu": host.cpu, "cpu_cores": host.cpu_cores,
                    "memory_gb": host.memory_gb, "gpu": host.gpu,
                    "gpu_count": host.gpu_count,
                    "gpu_memory_gb": host.gpu_memory_gb,
                    "storage_gb": host.storage_gb, "docker": host.docker,
                    "docker_version": host.docker_version,
                    "uptime_s": host.uptime_s, "available": host.is_usable(),
                    "note": "Unavailable fields remain null; nothing is inferred.",
                }
            elif self.view == "verify":
                data = rh.verify_job()
            else:  # requirements
                host = rh.discover()
                ok, why = rh.meets_requirements(host, args or {})
                data = {"eligible": ok, "reasons": why,
                        "host_status": host.status,
                        "available": host.is_usable(), "blocking": False}
            return _ok(self.name, ctx, started, data)
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class RemoteComputeStatusTool(_RemoteTool):
    name = "remote.compute.status"
    description = ("Report the remote execution host: endpoint, transport, "
                   "lifecycle state chain (configured/authenticated/reachable/"
                   "healthy/resource_verified/job_verified), capabilities, cost "
                   "class and whether it is usable. Reports NOT_CONFIGURED with "
                   "blocking=false when no host is attached, and never "
                   "fabricates a host.")
    view = "status"


class RemoteComputeHealthTool(_RemoteTool):
    name = "remote.compute.health"
    description = "Health of the remote execution host. Read-only, no secrets."
    view = "health"


class RemoteComputeResourcesTool(_RemoteTool):
    name = "remote.compute.resources"
    description = ("CPU/RAM/GPU/VRAM/storage/Docker/uptime of the remote host. "
                   "Unavailable fields stay null rather than being inferred.")
    view = "resources"


class RemoteComputeVerifyTool(_RemoteTool):
    name = "remote.compute.verify"
    description = ("Run the safe read-only test job on the remote host and "
                   "report the ACTUAL exit code and output. Mock results are "
                   "never reported as remote execution verified.")
    view = "verify"


class DockerRemoteStatusTool(_RemoteTool):
    name = "docker.remote.status"
    description = ("Status of remote Docker: whether a remote execution host "
                   "with a reachable Docker daemon is attached. Local Docker "
                   "absence is reported as non-blocking.")
    view = "status"


class DockerRemoteImagesTool(_RemoteTool):
    name = "docker.remote.images"
    description = ("Images available on the remote Docker host. Reports "
                   "truthfully when no verified host exists.")
    view = "resources"


class DockerRemoteContainersTool(_RemoteTool):
    name = "docker.remote.containers"
    description = ("Containers on the remote Docker host. Reports truthfully "
                   "when no verified host exists.")
    view = "resources"


class DockerRemoteLogsTool(_RemoteTool):
    name = "docker.remote.logs"
    description = ("Logs for a job on the remote host. Requires a verified "
                   "host; reports NOT_CONFIGURED otherwise.")
    view = "status"


class DockerRemoteHealthTool(_RemoteTool):
    name = "docker.remote.health"
    description = "Docker daemon health on the remote execution host."
    view = "health"


def _document_tools():
    """Documents domain adapters, registered lazily (optional deps)."""
    from .document_tools import DOCUMENT_TOOLS

    return [cls() for cls in DOCUMENT_TOOLS]


def _data_tools():
    """Data analytics domain adapters, registered lazily."""
    from .data_tools import DATA_TOOLS

    return [cls() for cls in DATA_TOOLS]


def _geography_tools():
    """Geography domain adapters, registered lazily (stdlib only)."""
    from .geography_tools import GEOGRAPHY_TOOLS

    return [cls() for cls in GEOGRAPHY_TOOLS]


def _registered_risks() -> dict[str, str]:
    """name -> risk for every capability in the existing ToolRegistry."""
    try:
        return {d["name"]: d["risk"] for d in build_capability_registry().describe()}
    except Exception:  # noqa: BLE001
        return {}


def build_capability_registry(policy=None):
    """A ToolRegistry populated with the real capability set.

    Uses the EXISTING ToolRegistry/Policy - this only wires adapters in.
    """
    from .tool_registry import DefaultPermissionPolicy, ToolRegistry

    registry = ToolRegistry(policy=policy or DefaultPermissionPolicy())
    # Project intelligence (already implemented, reused as-is).
    from .project_tools import (
        ProjectInspectTool,
        ProjectSearchTool,
        ProjectTestStatusTool,
    )
    registry.register(ProjectInspectTool())
    registry.register(ProjectSearchTool())
    registry.register(ProjectTestStatusTool())
    # Existing tools in the existing fabric.
    from .tool_registry import (
        BrowserSearchTool,
        KnowledgeRetrieveTool,
        MemoryRecallTool,
        MemoryTool,
        ModelConsultTool,
        SandboxRunTool,
        StaticSearchTool,
    )
    for tool in (
        SandboxRunTool(), BrowserSearchTool(), KnowledgeRetrieveTool(),
        MemoryTool(), MemoryRecallTool(), ModelConsultTool(), StaticSearchTool(),
    ):
        registry.register(tool)
    # New capability adapters.
    for tool in (
        ProviderStatusTool(), ModelStatusTool(), JobStatusTool(),
        ArtifactInspectTool(), FilesReadTool(), FilesSearchTool(),
        DockerStatusTool(), GithubInspectTool(), GithubSearchTool(),
        BrainStatusTool(), BrainArtifactsTool(), SilverwingStatusTool(),
        TrainingStatusTool(), NvidiaDeploymentTool(), PipelineReadinessTool(), IntegrationsMatrixTool(),
        CapabilityDiscoverTool(), CapabilityCatalogueTool(),
        RemoteComputeStatusTool(), RemoteComputeHealthTool(), RemoteComputeResourcesTool(),
        RemoteComputeVerifyTool(), DockerRemoteStatusTool(), DockerRemoteImagesTool(),
        DockerRemoteContainersTool(), DockerRemoteLogsTool(), DockerRemoteHealthTool(),
        CloudStatusTool(), CloudResourcesTool(), ComputeSelectTool(), ExecutionModeTool(),
        ComputeDiscoverTool(), ComputeVerifyTool(), ComputeInferenceTool(),
        ComputeTrainingTool(), ComputeEvaluationTool(), ComputeEmbeddingTool(),
        ComputeArtifactUploadTool(), ComputeArtifactDownloadTool(),
        ComputeJobSubmitTool(), ComputeJobStatusTool(), ComputeJobCancelTool(),
        ComputeResourceHealthTool(),
        *_document_tools(),
        *_data_tools(),
        TrainingStatusTool(), NvidiaDeploymentTool(), PipelineReadinessTool(), IntegrationsMatrixTool(),
        CapabilityDiscoverTool(), CapabilityCatalogueTool(),
        RemoteComputeStatusTool(), RemoteComputeHealthTool(), RemoteComputeResourcesTool(),
        RemoteComputeVerifyTool(), DockerRemoteStatusTool(), DockerRemoteImagesTool(),
        DockerRemoteContainersTool(), DockerRemoteLogsTool(), DockerRemoteHealthTool(),
        CloudStatusTool(), CloudResourcesTool(), ComputeSelectTool(), ExecutionModeTool(),
        *_document_tools(),
        *_data_tools(),        KaggleStatusTool(), KaggleJobsTool(), HuggingFaceStatusTool(),        HuggingFaceArtifactsTool(), NvidiaModelsTool(), NvidiaInferenceTool(),        BrainLifecycleTool(), SilverwingLifecycleTool(), SilverwingArtifactsTool(),        DevelopmentStatusTool(), DevelopmentNextActionTool(), DevelopmentVerifyTool(),
        *_geography_tools(),
    ):
        registry.register(tool)
    # Contract permissions must be enforced by the same registry that invokes
    # the tools, not merely advertised to the resolver.
    from .capability_contract import _META

    for name, metadata in _META.items():
        required_permissions = tuple(metadata.get("required_permissions", ()))
        if required_permissions and name in registry.available():
            registry.require_permissions(name, required_permissions)
    return registry


__all__ = [
    "ProviderStatusTool", "ModelStatusTool", "JobStatusTool",
    "ArtifactInspectTool", "FilesReadTool", "FilesSearchTool",
    "DockerStatusTool", "GithubInspectTool", "GithubSearchTool",
    "BrainStatusTool", "BrainArtifactsTool", "SilverwingStatusTool",
    "TrainingStatusTool", "NvidiaDeploymentTool", "PipelineReadinessTool", "IntegrationsMatrixTool",
    "CapabilityDiscoverTool", "CapabilityCatalogueTool",
    "RemoteComputeStatusTool", "RemoteComputeHealthTool",
    "RemoteComputeResourcesTool", "RemoteComputeVerifyTool",
    "DockerRemoteStatusTool", "DockerRemoteImagesTool",
    "DockerRemoteContainersTool", "DockerRemoteLogsTool",
    "DockerRemoteHealthTool", "DOCUMENT_TOOLS", "DATA_TOOLS", "GEOGRAPHY_TOOLS",
    "CloudStatusTool", "CloudResourcesTool", "ComputeSelectTool",
    "ExecutionModeTool",
    "ComputeDiscoverTool", "ComputeVerifyTool",
    "ComputeInferenceTool", "ComputeTrainingTool", "ComputeEvaluationTool",
    "ComputeEmbeddingTool", "ComputeArtifactUploadTool",
    "ComputeArtifactDownloadTool", "ComputeJobSubmitTool",
    "ComputeJobStatusTool", "ComputeJobCancelTool",
    "ComputeResourceHealthTool",
    "KaggleStatusTool", "KaggleJobsTool", "HuggingFaceStatusTool",
    "HuggingFaceArtifactsTool", "NvidiaModelsTool", "NvidiaInferenceTool",
    "BrainLifecycleTool", "SilverwingLifecycleTool", "SilverwingArtifactsTool",
    "DevelopmentStatusTool", "DevelopmentNextActionTool", "DevelopmentVerifyTool",
    "capability_inventory", "build_capability_registry", "live_provider_status",
    "AVAILABLE", "DEGRADED", "UNAVAILABLE", "OFFLINE", "NOT_CONFIGURED",
]
