"""Canonical Runtime Status Surface for JARVIS.

Reports the verified live state of platform subsystems without fabricating
availability or equating 'configured' with 'working'.

Subsystems:
- AUTH
- CHAT
- DATABASE
- OPENAI
- GOOGLE
- NVIDIA
- BRAIN
- SILVERWING
- KAGGLE
- HUGGING_FACE

States:
- AVAILABLE - Successfully verified via live probe
- UNAVAILABLE - Runtime error detecting state
- UNCONFIGURED - Missing credentials/configuration
- CONFIGURED - Has credentials but not yet verified
- AUTHENTICATION_FAILED - Credentials present but invalid/expired
- UNREACHABLE - Network error reaching the service
- DEGRADED - Unexpected response from service
- NOT_DEPLOYED - Service not deployed/configured
"""

from __future__ import annotations

import enum
import os
import subprocess
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
import httpx

from .core import get_current_user, get_store, now_iso
from .db import get_engine, database_url
from .runtime import ACTIVE_STATES as ACTIVE_EXECUTION_STATES, runtime as jarvis_runtime

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime-status"])


class RuntimeState(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNCONFIGURED = "UNCONFIGURED"
    CONFIGURED = "CONFIGURED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    UNREACHABLE = "UNREACHABLE"
    DEGRADED = "DEGRADED"
    NOT_DEPLOYED = "NOT_DEPLOYED"


async def check_database_status() -> Dict[str, Any]:
    """Verify database connectivity via a live query."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        return {
            "status": RuntimeState.AVAILABLE.value,
            "url": database_url().split("@")[-1],  # mask credentials if any
            "detail": "Database connection verified",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Database check failed: {exc.__class__.__name__}",
        }


async def check_auth_status() -> Dict[str, Any]:
    """Verify auth subsystem store and key availability."""
    try:
        store = get_store("users")
        users = store.load()
        user_count = len(users) if isinstance(users, dict) else 0
        return {
            "status": RuntimeState.AVAILABLE.value,
            "user_count": user_count,
            "detail": "Auth store accessible and active",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Auth store error: {exc.__class__.__name__}",
        }


async def check_chat_status() -> Dict[str, Any]:
    """Verify chat session storage and persistence."""
    try:
        store = get_store("chat_sessions")
        sessions = store.load()
        count = len(sessions) if isinstance(sessions, dict) else 0
        return {
            "status": RuntimeState.AVAILABLE.value,
            "session_count": count,
            "detail": "Chat session storage active",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Chat storage error: {exc.__class__.__name__}",
        }


async def check_openai_status(probe: bool = False) -> Dict[str, Any]:
    """Verify OpenAI provider."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key or not key.strip():
        return {
            "status": RuntimeState.UNCONFIGURED.value,
            "detail": "OPENAI_API_KEY is not set",
        }
    if not probe:
        return {
            "status": RuntimeState.DEGRADED.value,  # Configured but unverified without probe
            "configured": True,
            "authenticated": None,
            "reachable": None,
            "healthy": None,
            "executable": False,
            "detail": "Configured (pass probe=true for live validation)",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.status_code == 200:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "configured": True,
                    "authenticated": True,
                    "reachable": True,
                    "healthy": True,
                    "executable": False,
                    "detail": "Model listing succeeded; inference has not been verified.",
                }
            elif resp.status_code in (401, 403):
                return {
                    "status": RuntimeState.AUTHENTICATION_FAILED.value,
                    "detail": f"Authentication rejected ({resp.status_code})",
                }
            else:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "detail": f"Unexpected status {resp.status_code}",
                }
    except (httpx.ConnectError, httpx.TimeoutException):
        return {
            "status": RuntimeState.UNREACHABLE.value,
            "detail": "Network timeout or connect error to api.openai.com",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Probe error: {exc.__class__.__name__}",
        }


async def check_google_status(probe: bool = False) -> Dict[str, Any]:
    """Verify Google Gemini provider."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key or not key.strip():
        return {
            "status": RuntimeState.UNCONFIGURED.value,
            "detail": "GOOGLE_API_KEY is not set",
        }
    if not probe:
        return {
            "status": RuntimeState.DEGRADED.value,
            "configured": True,
            "authenticated": None,
            "reachable": None,
            "healthy": None,
            "executable": False,
            "detail": "Configured (pass probe=true for live validation)",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": key},
            )
            if resp.status_code == 200:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "configured": True,
                    "authenticated": True,
                    "reachable": True,
                    "healthy": True,
                    "executable": False,
                    "detail": "Model listing succeeded; inference has not been verified.",
                }
            elif resp.status_code in (400, 401, 403):
                return {
                    "status": RuntimeState.AUTHENTICATION_FAILED.value,
                    "detail": f"Authentication rejected ({resp.status_code})",
                }
            else:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "detail": f"Unexpected status {resp.status_code}",
                }
    except (httpx.ConnectError, httpx.TimeoutException):
        return {
            "status": RuntimeState.UNREACHABLE.value,
            "detail": "Network timeout or connect error to Google API",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Probe error: {exc.__class__.__name__}",
        }


async def check_nvidia_status(probe: bool = False) -> Dict[str, Any]:
    """Verify NVIDIA NIM provider."""
    key = (
        os.environ.get("NVIDIA_API_KEY")
        or os.environ.get("NVIDIA_API_TOKEN")
        or os.environ.get("NIM_API_KEY")
    )
    if not key or not key.strip():
        return {
            "status": RuntimeState.UNCONFIGURED.value,
            "detail": "NVIDIA_API_KEY is not set",
        }
    if not probe:
        return {
            "status": RuntimeState.DEGRADED.value,
            "configured": True,
            "authenticated": None,
            "reachable": None,
            "healthy": None,
            "executable": False,
            "detail": "Configured (pass probe=true for live validation)",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://integrate.api.nvidia.com/v1/models",
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
            if resp.status_code == 200:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "configured": True,
                    "authenticated": True,
                    "reachable": True,
                    "healthy": True,
                    "executable": False,
                    "detail": "Model listing succeeded; inference has not been verified.",
                }
            elif resp.status_code in (401, 403):
                return {
                    "status": RuntimeState.AUTHENTICATION_FAILED.value,
                    "detail": f"Authentication rejected ({resp.status_code})",
                }
            else:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "detail": f"Unexpected status {resp.status_code}",
                }
    except (httpx.ConnectError, httpx.TimeoutException):
        return {
            "status": RuntimeState.UNREACHABLE.value,
            "detail": "Network timeout or connect error to integrate.api.nvidia.com",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Probe error: {exc.__class__.__name__}",
        }


async def check_brain_status() -> Dict[str, Any]:
    """Verify JARVIS BRAIN endpoint."""
    endpoint = os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()
    if not endpoint:
        return {
            "status": RuntimeState.NOT_DEPLOYED.value,
            "detail": "JARVIS_BRAIN_ENDPOINT is not set",
        }
    try:
        from .gateway import ProviderGateway
        probe = await ProviderGateway().probe_brain()
        if probe.get("healthy"):
            return {
                "status": RuntimeState.AVAILABLE.value,
                "configured": True,
                "authenticated": True,
                "reachable": True,
                "healthy": True,
                "executable": True,
                "model": probe.get("model"),
                "detail": "Brain endpoint probe succeeded",
            }
        elif probe.get("configured"):
            return {
                "status": RuntimeState.UNREACHABLE.value,
                "detail": probe.get("reason") or "Brain endpoint unreachable",
            }
        else:
            return {
                "status": RuntimeState.NOT_DEPLOYED.value,
                "detail": "Brain not configured",
            }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Brain check error: {exc.__class__.__name__}",
        }


async def check_silverwing_status() -> Dict[str, Any]:
    """Verify Silverwing local/remote model server."""
    endpoint = os.environ.get("SILVERWING_ENDPOINT", "").strip()
    if not endpoint:
        return {
            "status": RuntimeState.NOT_DEPLOYED.value,
            "detail": "SILVERWING_ENDPOINT is not set",
        }
    try:
        from .routers.health import _probe_silverwing
        res = await _probe_silverwing()
        if res.get("reachable"):
            return {
                "status": RuntimeState.DEGRADED.value,
                "configured": True,
                "reachable": True,
                "healthy": None,
                "executable": False,
                "detail": "Runtime is reachable; inference readiness has not been verified.",
            }
        return {
            "status": RuntimeState.UNREACHABLE.value,
            "configured": True,
            "reachable": False,
            "healthy": False,
            "executable": False,
            "detail": f"Silverwing endpoint unreachable at {endpoint}",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Silverwing check error: {exc.__class__.__name__}",
        }


async def check_kaggle_status(probe: bool = False) -> Dict[str, Any]:
    """Verify Kaggle integration."""
    user = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    if not user or not key:
        return {
            "status": RuntimeState.UNCONFIGURED.value,
            "detail": "KAGGLE_USERNAME or KAGGLE_KEY is not set",
        }
    if not probe:
        # Configured but unverified - must probe to confirm availability
        return {
            "status": RuntimeState.CONFIGURED.value if (user and key) else RuntimeState.UNCONFIGURED.value,
            "username": user,
            "detail": f"Configured for user {user} (pass probe=true for live authentication)",
        }
    try:
        # Lightweight check: version + credential check via kaggle CLI or API
        proc = subprocess.run(
            ["kaggle", "kernels", "list", "--mine", "--page-size", "1"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode == 0:
            return {
                "status": RuntimeState.CONFIGURED.value,
                "configured": True,
                "authenticated": True,
                "reachable": True,
                "cli_installed": True,
                "executable": False,
                "username": user,
                "detail": "Kaggle CLI authentication and kernel discovery verified; job execution has not been verified.",
            }
        elif "401" in proc.stderr or "Unauthorized" in proc.stderr:
            return {
                "status": RuntimeState.AUTHENTICATION_FAILED.value,
                "detail": "Kaggle authentication failed (invalid credentials)",
            }
        else:
            return {
                "status": RuntimeState.UNREACHABLE.value,
                "detail": f"Kaggle CLI exited with code {proc.returncode}",
            }
    except FileNotFoundError:
        return {
            "status": RuntimeState.CONFIGURED.value,
            "configured": True,
            "authenticated": False,
            "reachable": False,
            "cli_installed": False,
            "executable": False,
            "username": user,
            "detail": "Credentials are configured, but the Kaggle CLI is not installed.",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"Kaggle check error: {exc.__class__.__name__}",
        }


async def check_huggingface_status(probe: bool = False) -> Dict[str, Any]:
    """Verify Hugging Face integration."""
    token = os.environ.get("HF_TOKEN")
    if not token or not token.strip():
        return {
            "status": RuntimeState.UNCONFIGURED.value,
            "detail": "HF_TOKEN is not set",
        }
    if not probe:
        # Configured but unverified - must probe to confirm availability
        return {
            "status": RuntimeState.CONFIGURED.value,
            "configured": True,
            "authenticated": None,
            "reachable": None,
            "executable": False,
            "detail": "HF_TOKEN configured (pass probe=true for live authentication)",
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://huggingface.co/api/whoami",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                username = data.get("name") or data.get("username") or "authenticated"
                return {
                    "status": RuntimeState.CONFIGURED.value,
                    "configured": True,
                    "authenticated": True,
                    "reachable": True,
                    "executable": False,
                    "user": username,
                    "detail": (
                        f"Authenticated with Hugging Face as {username}; "
                        "model execution has not been verified."
                    ),
                }
            elif resp.status_code in (401, 403):
                return {
                    "status": RuntimeState.AUTHENTICATION_FAILED.value,
                    "detail": "Invalid or expired HF_TOKEN",
                }
            else:
                return {
                    "status": RuntimeState.DEGRADED.value,
                    "detail": f"Unexpected response status {resp.status_code}",
                }
    except (httpx.ConnectError, httpx.TimeoutException):
        return {
            "status": RuntimeState.UNREACHABLE.value,
            "detail": "Network timeout or connect error to huggingface.co",
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "detail": f"HF check error: {exc.__class__.__name__}",
        }


async def build_canonical_runtime_status(probe: bool = False) -> Dict[str, Any]:
    """Build the single canonical runtime-status surface."""
    import asyncio

    from .mcp_runtime import mcp_status

    (
        auth_res,
        chat_res,
        db_res,
        openai_res,
        google_res,
        nvidia_res,
        brain_res,
        silverwing_res,
        kaggle_res,
        hf_res,
        mcp_res,
    ) = await asyncio.gather(
        check_auth_status(),
        check_chat_status(),
        check_database_status(),
        check_openai_status(probe=probe),
        check_google_status(probe=probe),
        check_nvidia_status(probe=probe),
        check_brain_status(),
        check_silverwing_status(),
        check_kaggle_status(probe=probe),
        check_huggingface_status(probe=probe),
        mcp_status(),
    )

    components = {
        "AUTH": auth_res,
        "CHAT": chat_res,
        "DATABASE": db_res,
        "OPENAI": openai_res,
        "GOOGLE": google_res,
        "NVIDIA": nvidia_res,
        "BRAIN": brain_res,
        "SILVERWING": silverwing_res,
        "KAGGLE": kaggle_res,
        "HUGGING_FACE": hf_res,
        "MCP": mcp_res,
    }

    # Derive overall platform health
    # At least AUTH, CHAT, and DATABASE must be AVAILABLE
    core_ok = (
        auth_res["status"] == RuntimeState.AVAILABLE.value
        and chat_res["status"] == RuntimeState.AVAILABLE.value
        and db_res["status"] == RuntimeState.AVAILABLE.value
        and mcp_res["status"] == "AVAILABLE"
    )
    # At least one AI provider must be AVAILABLE
    any_provider_available = any(
        res["status"] == RuntimeState.AVAILABLE.value
        for name, res in components.items()
        if name in ("OPENAI", "GOOGLE", "NVIDIA", "BRAIN", "SILVERWING")
    )

    if core_ok and any_provider_available:
        overall_status = "OPERATIONAL"
    elif core_ok:
        overall_status = "DEGRADED"  # Core works, but no AI providers active
    else:
        overall_status = "UNAVAILABLE"

    return {
        "status": overall_status,
        "alive": True,
        "service_readiness": "READY" if core_ok else "DEGRADED",
        "generated_at": now_iso(),
        "probe": probe,
        "components": components,
    }


@router.get("/status")
async def runtime_status_endpoint(probe: bool = Query(False, description="Run live network probes")):
    """Canonical runtime status surface distinguishing all required platform components."""
    return await build_canonical_runtime_status(probe=probe)


@router.get("")
async def runtime_snapshot(user: Dict[str, Any] = Depends(get_current_user)):
    """Owner-scoped runtime view; distinct from subsystem health checks."""
    import asyncio

    from .connectors.dispatch import list_connectors
    from .routers.ai import _provider_catalog

    user_id = str(user.get("id") or user.get("email") or "")
    commands = [
        command for command in get_store("commands").load().values()
        if command.get("user_id") == user_id
    ]
    commands.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    executions = jarvis_runtime.list_executions(user_id=user_id, limit=500)
    active_executions = [
        item for item in executions
        if item.get("status") in ACTIVE_EXECUTION_STATES
        or item.get("status") in {"QUEUED", "PAUSED"}
    ]
    owned_command_ids = {command.get("command_id") for command in commands}
    recent_events = []
    for command_id in list(owned_command_ids)[:100]:
        recent_events.extend(
            jarvis_runtime.replay_events(command_id, after_sequence=0, limit=50)
        )
    recent_events.sort(key=lambda event: (event["timestamp"], event["sequence"]))
    catalog = await _provider_catalog()
    from .mcp_runtime import mcp_status

    mcp = await mcp_status()
    from research_engine.capability_tools import build_capability_registry

    from research_engine.capability_contract import build_contracts

    capabilities = list(
        build_contracts(build_capability_registry()).values()
    )
    provider_evidence = []
    for provider in catalog.get("providers", []):
        model_available = bool(
            provider.get("model_list_available")
            or provider.get("models")
            or provider.get("model")
        )
        executable = provider.get("inference_verified") is True
        provider_evidence.append({
            **provider,
            "configured": bool(provider.get("configured")),
            "authenticated": bool(provider.get("authorized")),
            "reachable": bool(
                provider.get("reachable")
                or provider.get("model_list_available")
                or provider.get("health_status") in {"healthy", "degraded"}
            ),
            "health": provider.get("health_status", "unknown"),
            "model_available": model_available,
            "executable": executable,
            "last_error": provider.get("errors"),
        })
    agents = [
        {**agent, "status": "REGISTERED"}
        for agent in get_store("agents").load().values()
    ]
    from .routers.commands import _WORKER_ID, _command_jobs

    active_owned_jobs = sum(
        not job.done()
        for command_id, job in _command_jobs.items()
        if command_id in owned_command_ids
    )
    worker_execution_counts: dict[str, int] = {}
    for execution in executions:
        worker_id = execution.get("worker_id")
        if worker_id:
            worker_execution_counts[worker_id] = (
                worker_execution_counts.get(worker_id, 0) + 1
            )
    inference_ready = any(
        provider.get("inference_verified") is True
        and provider.get("available") is True
        for provider in catalog.get("providers", [])
    )
    auth_status, chat_status, database_status = await asyncio.gather(
        check_auth_status(),
        check_chat_status(),
        check_database_status(),
    )
    service_ready = bool(
        auth_status.get("status") == RuntimeState.AVAILABLE.value
        and chat_status.get("status") == RuntimeState.AVAILABLE.value
        and database_status.get("status") == RuntimeState.AVAILABLE.value
        and mcp.get("status") == "AVAILABLE"
    )
    return {
        "runtime": {
            "status": "ALIVE",
            "service_readiness": "READY" if service_ready else "DEGRADED",
            "service_components": {
                "auth": auth_status.get("status"),
                "chat": chat_status.get("status"),
                "database": database_status.get("status"),
                "mcp": mcp.get("status"),
            },
            "execution_readiness": "READY" if inference_ready else "DEGRADED",
            "provider_execution_available": inference_ready,
            "database": database_status.get("status"),
            "worker_id": _WORKER_ID,
            "generated_at": now_iso(),
        },
        "active_commands": [
            command for command in commands
            if command.get("status") not in {
                "COMPLETED", "PARTIAL", "FAILED", "CANCELLED",
                "RECOVERY_REQUIRED",
            }
        ][:100],
        "active_executions": active_executions,
        "workers": {
            "active_command_jobs": active_owned_jobs,
            "items": [
                {"worker_id": worker_id, "execution_count": count}
                for worker_id, count in worker_execution_counts.items()
            ],
            "current_worker_id": _WORKER_ID,
        },
        "providers": provider_evidence,
        "models": [
            {"provider": provider.get("provider"), "model": model,
             "executable": provider.get("inference_verified") is True}
            for provider in provider_evidence
            for model in provider.get("models", [])
        ],
        "capabilities": capabilities,
        "agents": agents,
        "connectors": list_connectors(),
        "mcp": mcp,
        "queue": {
            "queued": sum(1 for item in executions if item["status"] == "QUEUED"),
            "active": len(active_executions),
        },
        "recent_events": recent_events[-100:],
    }
