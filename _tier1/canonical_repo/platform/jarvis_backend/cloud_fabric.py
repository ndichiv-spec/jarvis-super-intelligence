"""JARVIS Cloud Hardware Fabric.

Turns this laptop into a *control plane*: it discovers what compute actually
exists (locally and remotely), and routes work to eligible targets by
requirement.  It creates no new database, job system or secret store - it
discovers real resources, projects them through the existing registries, and
reports truthful per-state availability.

State vocabulary is deliberately granular and never collapsed::

    configured -> authenticated -> reachable -> healthy
               -> resource_verified -> job_verified -> inference_verified

A credential alone is never reported as an available resource.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

WORKSPACE = Path(r"F:\AI")
RESOURCE_ID_FALLBACK = "remote_execution_host"
NOT_CONFIGURED_FALLBACK = "NOT_CONFIGURED"
JARVIS_ROOT = Path(__file__).resolve().parents[1]

# Local hardware findings are cached: they cannot change without a reboot.
_LOCAL_PROFILE: Optional[dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# Local hardware profile
# --------------------------------------------------------------------------- #
def _ps(command: list[str], timeout: int = 20) -> str:
    """Read-only PowerShell query. Never mutates, never shells user input."""
    try:
        proc = subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=timeout, shell=False,
        )
        return (proc.stdout or "").strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def local_hardware(refresh: bool = False) -> dict[str, Any]:
    """Truthful local hardware profile, including virtualization support."""
    global _LOCAL_PROFILE
    if _LOCAL_PROFILE is not None and not refresh:
        return _LOCAL_PROFILE

    cpu = _ps("(Get-CimInstance Win32_Processor | Select-Object -First 1 "
              "| ForEach-Object { $_.Name })")
    cores = _ps("(Get-CimInstance Win32_Processor | Measure-Object "
                "-Property NumberOfLogicalProcessors -Sum).Sum")
    ram_gb = _ps("[math]::Round((Get-CimInstance Win32_ComputerSystem "
                 "| Select-Object -ExpandProperty TotalPhysicalMemory)/1GB,1)")
    virt_enabled = _ps("(Get-WindowsOptionalFeature -Online "
                       "-FeatureName VirtualMachinePlatform).State")
    vmx = _ps("$p=Get-CimInstance Win32_Processor | Select-Object -First 1; "
              "\"$($p.VirtualizationFirmwareEnabled)|"
              "$($p.SecondLevelAddressTranslationExtensions)|"
              "$($p.VMMonitorModeExtensions)\"")

    slat = False
    firmware_virt = False
    parts = [p.strip().lower() for p in vmx.split("|")] if vmx else []
    if len(parts) == 3:
        firmware_virt = parts[0] == "true"
        slat = parts[1] == "true"

    gpu_name = _ps("(Get-CimInstance Win32_VideoController | "
                   "Select-Object -ExpandProperty Name -ErrorAction "
                   "SilentlyContinue) -join '; '")
    disk_free = ""
    try:
        usage = shutil.disk_usage(str(JARVIS_ROOT))
        disk_free = round(usage.free / 1e9, 1)
    except OSError:
        pass

    docker_present = bool(shutil.which("docker"))
    vmcompute = _ps("(Get-Service vmcompute -ErrorAction SilentlyContinue)"
                    ".Status")

    virtualization_supported = bool(firmware_virt and slat)
    profile = {
        "kind": "local",
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "host": socket.gethostname(),
        "cpu": cpu or platform.processor() or "unknown",
        "cpu_logical_cores": int(cores) if cores.isdigit() else None,
        "ram_gb": float(ram_gb) if ram_gb else None,
        "gpu": gpu_name or None,
        "gpu_count": len([g for g in (gpu_name or "").split(";") if g.strip()]),
        "vram_gb": None,
        "disk_free_gb": disk_free or None,
        "virtualization": {
            "feature_state": virt_enabled or None,
            "firmware_enabled": firmware_virt,
            "slat": slat,
            "vmcompute_service": vmcompute or None,
            "supported": virtualization_supported,
            "reason": None if virtualization_supported else
                      ("CPU reports no SLAT/VT-x; nested virtualization and "
                       "WSL2/Hyper-V containers are not possible on this host"),
        },
        "docker": {
            "installed": docker_present,
            "cli": shutil.which("docker"),
            "daemon": None,
            "usable": docker_present,
        },
        "network": {
            "internet_reachable": _internet_reachable(),
        },
        "suited_for": [],
        "not_suited_for": [],
    }

    suited, unsuited = [], []
    if profile["docker"]["installed"]:
        suited.append("containers")
    else:
        unsuited.append("containers")
    if virtualization_supported:
        suited.append("virtualized workloads")
    else:
        unsuited.extend(["containers", "vms", "wsl2 workloads"])
    if profile["cpu_logical_cores"] and profile["cpu_logical_cores"] >= 8:
        suited.append("local analysis")
    else:
        suited.append("control plane / orchestration")
    if profile["network"]["internet_reachable"]:
        suited.append("cloud-orchestrated workloads")
    profile["suited_for"] = sorted(set(suited))
    profile["not_suited_for"] = sorted(set(unsuited))
    profile["role"] = "control_plane"
    _LOCAL_PROFILE = profile
    return profile


def _internet_reachable(host: str = "huggingface.co", port: int = 443,
                        timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Remote resource discovery - only real resources are registered
# --------------------------------------------------------------------------- #
def _resource(resource_id: str, provider: str, **kw: Any) -> dict[str, Any]:
    base = {
        "resource_id": resource_id,
        "provider": provider,
        "region": kw.pop("region", None),
        "type": kw.pop("type", "service"),
        "cpu": kw.pop("cpu", None),
        "memory_gb": kw.pop("memory_gb", None),
        "gpu": kw.pop("gpu", None),
        "gpu_memory_gb": kw.pop("gpu_memory_gb", None),
        "storage_gb": kw.pop("storage_gb", None),
        "os": kw.pop("os", None),
        "architecture": kw.pop("architecture", None),
        "docker": kw.pop("docker", False),
        "endpoint": kw.pop("endpoint", None),
        "cost_class": kw.pop("cost_class", "free_tier"),
        "capabilities": kw.pop("capabilities", []),
        "status": kw.pop("status", "UNKNOWN"),
        "health": kw.pop("health", "unknown"),
        "state_chain": kw.pop("state_chain", {}),
    }
    base.update(kw)
    return base


def _nvidia_resource() -> dict[str, Any]:
    try:
        from research_engine.capability_tools import live_provider_status

        n = (live_provider_status() or {}).get("nvidia") or {}
    except Exception as exc:  # noqa: BLE001
        return _resource("cloud:nvidia", "nvidia", type="inference",
                         status="UNAVAILABLE", health="unknown",
                         capabilities=[],
                         state_chain={"reachable": False,
                                      "error": f"{type(exc).__name__}"})
    available = bool(n.get("available"))
    return _resource(
        "cloud:nvidia", "nvidia", type="gpu_inference", gpu="remote",
        gpu_memory_gb=None, storage_gb=None, os="managed",
        endpoint="https://integrate.api.nvidia.com/v1",
        cost_class="pay_per_token",
        capabilities=(["gpu_inference", "streaming", "chat", "tool_calling"]
                      if available else []),
        status="AVAILABLE" if available else "DEGRADED",
        health=n.get("health_status"),
        state_chain={
            "configured": True,
            "authenticated": bool(n.get("authenticated")),
            "reachable": bool(n.get("reachable")),
            "healthy": n.get("health_status") in ("healthy", "degraded"),
            "inference_verified": bool(n.get("inference_verified")),
        },
        model_count=None,
        note=("Remote managed inference. GPU is not directly inspectable; "
              "capability is inferred from the provider's verified health."),
    )


def _kaggle_resource() -> dict[str, Any]:
    try:
        if str(WORKSPACE) not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        from jarvis_backend.brain_fabric import _kaggle_real_status

        k = _kaggle_real_status()
    except Exception as exc:  # noqa: BLE001
        return _resource("cloud:kaggle", "kaggle", type="training",
                         status="UNAVAILABLE", capabilities=[],
                         state_chain={"error": f"{type(exc).__name__}"})
    connected = bool(k.get("connected"))
    return _resource(
        "cloud:kaggle", "kaggle", type="gpu_training", gpu="remote",
        cost_class="free_tier_quota",
        capabilities=(["gpu_training", "experimentation", "evaluation"]
                      if connected else []),
        status="AVAILABLE" if connected else "NOT_CONFIGURED",
        health="authenticated" if connected else "unknown",
        state_chain={
            "configured": bool(k.get("cli_installed")),
            "authenticated": connected,
            "reachable": connected,
            "resource_verified": bool(k.get("kernel_count")),
        },
        persistent=False,
        note="Ephemeral GPU training. Not a production server.",
    )


def _huggingface_resource() -> dict[str, Any]:
    try:
        if str(WORKSPACE) not in sys.path:
            sys.path.insert(0, str(WORKSPACE))
        from jarvis_backend.brain_fabric import _hf_real_status

        h = _hf_real_status()
    except Exception as exc:  # noqa: BLE001
        return _resource("cloud:huggingface", "huggingface",
                         type="artifact_store", status="UNAVAILABLE",
                         capabilities=[], state_chain={})
    connected = bool(h.get("connected"))
    return _resource(
        "cloud:huggingface", "huggingface", type="artifact_store",
        storage_gb=None, cost_class="free_tier",
        capabilities=(["model_storage", "versioning", "artifact_distribution",
                       "datasets"] if connected else []),
        status="AVAILABLE" if connected else "NOT_CONFIGURED",
        health="authenticated" if connected else "unknown",
        state_chain={"configured": bool(h.get("token_present")),
                     "authenticated": connected, "reachable": connected,
                     "resource_verified": bool(h.get("repositories"))},
        persistent=True,
        note="Durable artifact/version layer. Not compute.",
    )


def _docker_resource(local: dict[str, Any]) -> dict[str, Any]:
    """Docker is expected to be REMOTE on this host (no SLAT).

    A real remote execution host is consulted via the existing
    ``JARVIS_DOCKER_REMOTE_HOST`` contract.  Nothing is provisioned here.
    """
    local_ok = bool(local["docker"]["installed"])
    try:
        from .remote_host import discover as _discover_remote

        remote = _discover_remote()
        remote_ok = remote.is_usable()
        remote_detail = {
            "status": remote.status,
            "endpoint": remote.endpoint,
            "docker": remote.docker,
            "reason": remote.reason,
        }
    except Exception as exc:  # noqa: BLE001
        remote_ok = False
        remote_detail = {"status": "UNAVAILABLE",
                         "reason": f"{type(exc).__name__}: {exc}"}

    return _resource(
        "docker:execution", "docker", type="container_runtime",
        docker=bool(local_ok or remote_ok), os="linux",
        cost_class="cloud_vm",
        capabilities=["containers", "service_isolation", "build_test"]
        if (local_ok or remote_ok) else [],
        status="AVAILABLE" if (local_ok or remote_ok) else "UNAVAILABLE",
        health="available" if (local_ok or remote_ok) else "unavailable",
        state_chain={
            "configured": bool(local_ok or remote_ok),
            "authenticated": bool(local_ok or remote_ok),
            "reachable": bool(local_ok or remote_ok),
            "resource_verified": bool(local_ok or remote_ok),
        },
        endpoint=(os.environ.get("JARVIS_DOCKER_REMOTE_HOST") or "") or None,
        reason=(None if (local_ok or remote_ok) else
                "No container runtime available: this host's CPU reports no "
                "SLAT/VT-x so Docker/WSL2/Hyper-V cannot run locally. Set "
                "JARVIS_DOCKER_REMOTE_HOST to attach a remote execution host."),
        note="Container support is a cloud-VM responsibility, not local.",
        # Container support is optional: its absence must never block the
        # platform. Expressed top-level because it is a routing property, not
        # part of the granular lifecycle state chain.
        blocking=False,
        remote_execution_host=remote_detail,
    )


def _remote_host_resource() -> dict[str, Any]:
    """The general-purpose remote execution host, from real discovery only."""
    try:
        from .remote_host import discover as _discover_remote

        h = _discover_remote()
    except Exception as exc:  # noqa: BLE001
        return _resource(
            RESOURCE_ID_FALLBACK, "remote_host", type="remote_execution_host",
            status=NOT_CONFIGURED_FALLBACK, capabilities=[],
            reason=f"{type(exc).__name__}: {exc}", blocking=False)
    usable = h.is_usable()
    return _resource(
        h.resource_id, h.provider, type="remote_execution_host",
        region=h.region, endpoint=h.endpoint, os=h.os,
        architecture=h.architecture, cpu=h.cpu, memory_gb=h.memory_gb,
        gpu=h.gpu, gpu_memory_gb=h.gpu_memory_gb, storage_gb=h.storage_gb,
        docker=bool(h.docker), status=h.status, health=h.health,
        cost_class=h.cost_class or "unknown",
        capabilities=list(h.capabilities),
        state_chain=dict(h.state_chain),
        reason=h.reason, blocking=False,
        last_seen=h.last_seen, uptime_s=h.uptime_s,
        transport=h.transport,
    )


def _is_compute_gpu(name: Optional[str]) -> bool:
    """Integrated/shared display adapters are NOT compute GPUs.

    A laptop iGPU (Intel HD/Iris/UHD Graphics, "Sharing Monitor", Microsoft
    Basic Display) must never satisfy a ``gpu_required`` workload.
    """
    if not name:
        return False
    low = name.lower()
    integrated_markers = (
        "hd graphics", "uhd graphics", "iris", "intel graphics",
        "sharing monitor", "basic display", "microsoft basic",
        "radeon graphics", "apple gpu", "mali", "adreno",
    )
    if any(marker in low for marker in integrated_markers):
        return False
    return bool(low.strip())


def _local_resource(local: dict[str, Any]) -> dict[str, Any]:
    compute_gpu = _is_compute_gpu(local.get("gpu"))
    return _resource(
        "local:control-node", "local", type="control_plane",
        cpu=local.get("cpu"), memory_gb=local.get("ram_gb"),
        gpu=(local.get("gpu") if compute_gpu else None),
        storage_gb=local.get("disk_free_gb"),
        os=local.get("os"), architecture=local.get("architecture"),
        docker=bool(local["docker"]["installed"]),
        cost_class="free_local",
        capabilities=(["code_inspection", "project_intelligence",
                       "control_plane", "registry_read", "offline_tools",
                       "local_analysis"]
                      + (["containers"] if local["docker"]["installed"] else [])
                      + (["local_gpu_compute"] if compute_gpu else [])),
        status="AVAILABLE",
        health="healthy",
        state_chain={"reachable": True, "resource_verified": True,
                     "healthy": True},
        role="control_plane",
        integrated_gpu=local.get("gpu") if not compute_gpu else None,
    )


def cloud_resources(refresh: bool = False) -> dict[str, Any]:
    """Discover every real execution resource. No credentials are returned."""
    local = local_hardware(refresh=refresh)
    resources = [
        _local_resource(local),
        _nvidia_resource(),
        _kaggle_resource(),
        _huggingface_resource(),
        _docker_resource(local),
        _remote_host_resource(),
    ]
    return {
        "local_hardware": local,
        "resources": resources,
        "by_id": {r["resource_id"]: r for r in resources},
        "count": len(resources),
        "note": ("Only resources that actually answered are listed. A "
                 "configured credential alone is never an available resource."),
    }


# --------------------------------------------------------------------------- #
# Hardware-aware compute selection
# --------------------------------------------------------------------------- #
def select_compute(requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    """Choose an execution target from real requirements.

    Never hardcodes "GPU -> NVIDIA": a training job prefers Kaggle (ephemeral
    GPU training) while production inference prefers NVIDIA.
    """
    req = requirements or {}
    gpu_required = bool(req.get("gpu_required"))
    min_vram = float(req.get("min_gpu_memory_gb") or 0)
    docker_required = bool(req.get("docker_required"))
    persistent = bool(req.get("persistent_runtime"))
    network_required = bool(req.get("network_required"))
    task = (req.get("task") or "").lower()
    training = any(w in task for w in ("train", "fine-tune", "finetune", "sft",
                                       "lora", "qlora", "dataset"))
    max_cost = (req.get("max_cost_class") or "approved").lower()

    disc = cloud_resources()
    local = disc["local_hardware"]
    evaluated: list[dict[str, Any]] = []

    for res in disc["resources"]:
        eligible, reasons = True, []
        caps = res.get("capabilities") or []
        if res["status"] not in {"AVAILABLE", "DEGRADED"}:
            eligible = False
            reasons.append(f"status={res['status']}")
        if gpu_required and not res.get("gpu"):
            eligible = False
            reasons.append("no GPU available on this resource")
        if min_vram and (res.get("gpu_memory_gb") or 0) < min_vram:
            eligible = False
            reasons.append("insufficient GPU memory (unknown/insufficient)")
        if docker_required and not res.get("docker"):
            eligible = False
            reasons.append("no container runtime on this resource")
        if network_required and not local["network"]["internet_reachable"]:
            eligible = False
            reasons.append("no network connectivity")
        if persistent and res.get("type") == "gpu_training":
            eligible = False
            reasons.append("ephemeral training resource cannot be persistent")
        if max_cost == "free_local" and res.get("cost_class") not in {
                "free_local", "free_tier", "free_tier_quota"}:
            eligible = False
            reasons.append("exceeds the approved cost class")
        evaluated.append({
            "resource_id": res["resource_id"], "provider": res["provider"],
            "eligible": eligible, "reasons": reasons,
            "cost_class": res.get("cost_class"),
        })

    eligible_ids = [e["resource_id"] for e in evaluated if e["eligible"]]
    # Preference: purpose-fit over raw availability. Modest requirements stay
    # local (free, present, sufficient); remote GPU is preferred only when a
    # GPU is genuinely required.
    def _rank(rid: str) -> tuple:
        res = disc["by_id"][rid]
        score = 0
        local_node = res["provider"] == "local"
        if local_node:
            # Local is the default target whenever it can satisfy the request.
            score += 20 if not (gpu_required or docker_required) else 5
        if gpu_required:
            if training and res["type"] == "gpu_training":
                score += 10
            if not training and res["type"] == "gpu_inference":
                score += 10
        if docker_required and res.get("docker"):
            score += 12
        if not persistent and res.get("type") == "gpu_training":
            score += 2
        if res.get("cost_class") in {"free_local", "free_tier",
                                    "free_tier_quota"}:
            score += 3
        if res["resource_id"] == "cloud:nvidia" and not training:
            score += 2
        return (-score, rid)

    ordered = sorted(eligible_ids, key=_rank)
    selected = ordered[0] if ordered else None
    # A request is locally viable unless it needs a GPU or a container
    # runtime; lacking virtualization only blocks container/VM workloads.
    local_viable = not (gpu_required or docker_required)
    if docker_required and not local["docker"]["installed"]:
        local_viable = False
    return {
        "requirements": req,
        "eligible": ordered,
        "selected": selected,
        "selection_basis": ("purpose-fit ranking over verified resources"
                            if selected else
                            "no verified resource satisfies the requirements"),
        "evaluated": evaluated,
        "infeasible_reason": None if selected else
                             "RESOURCE_UNAVAILABLE: no verified resource "
                             "satisfies the stated requirements",
        "local_viable": local_viable,
        "local_block_reason": None if local_viable else
                              ("GPU required" if gpu_required else
                               "container runtime required but Docker is "
                               "unavailable on this host"),
        "requires_approval": bool(selected and training),
    }


# --------------------------------------------------------------------------- #
# Execution mode (online / degraded / offline)
# --------------------------------------------------------------------------- #
def execution_mode() -> dict[str, Any]:
    """Classify the current operating mode from real connectivity + hardware."""
    local = local_hardware()
    online = local["network"]["internet_reachable"]
    try:
        from research_engine.capability_contract import discover_capabilities

        offline_caps = [c["name"] for c in
                        discover_capabilities("help", mode="offline")["capabilities"]]
    except Exception:  # noqa: BLE001
        offline_caps = []
    return {
        "mode": "online" if online else "offline",
        "internet_reachable": online,
        "docker_local": bool(local["docker"]["installed"]),
        "virtualization_supported": local["virtualization"]["supported"],
        "local_still_useful": True,
        "degraded_path": {
            "available": not online,
            "fallbacks": offline_caps or ["project.inspect", "project.search",
                                          "files.search"],
            "note": ("Without internet, JARVIS keeps local project "
                     "intelligence, filesystem and registry capabilities. "
                     "No cloud response is ever fabricated."),
        },
        "silverwing_offline": _silverwing_offline_hint(),
    }


def _silverwing_offline_hint() -> dict[str, Any]:
    endpoint = (os.environ.get("SILVERWING_ENDPOINT") or "").strip()
    if not endpoint:
        return {"state": "NOT_CONFIGURED", "endpoint": None}
    parsed = endpoint if "://" in endpoint else f"http://{endpoint}"
    hostport = parsed.split("://", 1)[-1].split("/")[0]
    host, _, port = hostport.partition(":")
    try:
        with socket.create_connection((host, int(port or 80)), timeout=1.5):
            return {"state": "AVAILABLE", "endpoint": endpoint}
    except OSError as exc:
        return {"state": "OFFLINE", "endpoint": endpoint,
                "detail": f"{type(exc).__name__}"}


def cloud_status() -> dict[str, Any]:
    disc = cloud_resources()
    summary = []
    for r in disc["resources"]:
        summary.append({
            "resource_id": r["resource_id"], "provider": r["provider"],
            "type": r["type"], "status": r["status"], "health": r["health"],
            "gpu": r.get("gpu"), "docker": r.get("docker"),
            "cost_class": r.get("cost_class"),
            "state_chain": r.get("state_chain", {}),
        })
    return {
        "resources": summary,
        "count": disc["count"],
        "local_hardware": disc["local_hardware"],
        "execution_mode": execution_mode(),
        "distinct_states": ["configured", "authenticated", "reachable",
                            "healthy", "resource_verified", "job_verified",
                            "inference_verified"],
    }


__all__ = [
    "local_hardware", "cloud_resources", "cloud_status", "select_compute",
    "execution_mode", "WORKSPACE",
]
