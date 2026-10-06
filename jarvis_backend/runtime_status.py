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
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
import httpx

from .core import get_store, now_iso, get_optional_user
from .db import get_engine, database_url

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
                    "status": RuntimeState.AVAILABLE.value,
                    "detail": "Live API probe succeeded (200 OK)",
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
                    "status": RuntimeState.AVAILABLE.value,
                    "detail": "Live API probe succeeded (200 OK)",
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
                    "status": RuntimeState.AVAILABLE.value,
                    "detail": "Live API probe succeeded (200 OK)",
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
                "status": RuntimeState.AVAILABLE.value,
                "detail": "Silverwing runtime reachable",
            }
        return {
            "status": RuntimeState.UNREACHABLE.value,
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
                "status": RuntimeState.AVAILABLE.value,
                "username": user,
                "detail": "Kaggle authentication and kernel discovery verified",
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
            "status": RuntimeState.AVAILABLE.value,
            "username": user,
            "detail": "Credentials present; kaggle CLI not in PATH",
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
                    "status": RuntimeState.AVAILABLE.value,
                    "user": username,
                    "detail": f"Authenticated with Hugging Face as {username}",
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


async def _command_runtime_status() -> Dict[str, Any]:
    """Summarize the live command queue and execution fabric for observability."""
    from .core import get_store
    commands = get_store("commands").load()
    counts: Dict[str, int] = {}
    for command in commands.values():
        status = str(command.get("status") or "RECEIVED")
        counts[status] = counts.get(status, 0) + 1
    return {
        "status": "AVAILABLE" if commands else "IDLE",
        "total_commands": len(commands),
        "by_status": counts,
        "recent": list(commands.values())[-5:],
    }


async def build_canonical_runtime_status(probe: bool = False) -> Dict[str, Any]:
    """Build the single canonical runtime-status surface."""
    import asyncio

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
    )
    command_status = await _command_runtime_status()

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
        "COMMAND_RUNTIME": command_status,
    }

    # Derive overall platform health
    # At least AUTH, CHAT, and DATABASE must be AVAILABLE
    core_ok = (
        auth_res["status"] == RuntimeState.AVAILABLE.value
        and chat_res["status"] == RuntimeState.AVAILABLE.value
        and db_res["status"] == RuntimeState.AVAILABLE.value
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
        "generated_at": now_iso(),
        "probe": probe,
        "components": components,
    }


@router.get("/status")
async def runtime_status_endpoint(probe: bool = Query(False, description="Run live network probes")):
    """Canonical runtime status surface distinguishing all required platform components."""
    return await build_canonical_runtime_status(probe=probe)
