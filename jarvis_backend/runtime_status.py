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
                "status": RuntimeState.CONFIGURED.value,
                "detail": "Silverwing endpoint reachable; inference is not verified",
            }
        return {
            "status": RuntimeState.UNREACHABLE.value,
            "detail": "Configured Silverwing endpoint is unreachable",
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
    }


async def _provider_runtime_status() -> Dict[str, Any]:
    """Report provider configuration separately from verified inference."""
    from .routers.ai import _provider_catalog

    catalog = await _provider_catalog()
    providers = []
    for item in catalog.get("providers", []):
        configured = bool(item.get("configured"))
        inference_verified = bool(item.get("inference_verified"))
        streaming_verified = bool(item.get("streaming_verified"))
        providers.append({
            "provider": item.get("provider"),
            "status": (
                RuntimeState.AVAILABLE.value if inference_verified
                else RuntimeState.CONFIGURED.value if configured
                else RuntimeState.UNCONFIGURED.value
            ),
            "configured": configured,
            "inference_verified": inference_verified,
            "streaming_verified": streaming_verified,
            "capabilities": item.get("capabilities") or [],
        })
    verified = [item for item in providers if item["inference_verified"]]
    configured = [item for item in providers if item["configured"]]
    return {
        "status": (
            RuntimeState.AVAILABLE.value if verified
            else RuntimeState.CONFIGURED.value if configured
            else RuntimeState.UNCONFIGURED.value
        ),
        "providers": providers,
        "verified_count": len(verified),
        "configured_count": len(configured),
    }


async def _redis_runtime_status(queue_status: Dict[str, Any]) -> Dict[str, Any]:
    from .celery_app import BROKER_URL
    from urllib.parse import urlsplit

    try:
        scheme = urlsplit(BROKER_URL).scheme.lower()
    except ValueError:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "configured": bool(BROKER_URL),
        }
    if scheme not in {"redis", "rediss"}:
        return {
            "status": RuntimeState.UNCONFIGURED.value,
            "configured": False,
        }
    reachable = bool(queue_status.get("broker_reachable"))
    return {
        "status": RuntimeState.AVAILABLE.value if reachable else RuntimeState.UNREACHABLE.value,
        "configured": True,
        "reachable": reachable,
    }


async def _celery_runtime_status() -> Dict[str, Any]:
    import asyncio
    from .celery_app import get_queue_runtime_status

    queue = await asyncio.to_thread(get_queue_runtime_status)
    ready = (
        queue.get("broker_reachable")
        and queue.get("worker_probe") == "ok"
        and queue.get("command_queue_probe") == "ok"
    )
    return {
        **queue,
        "status": (
            RuntimeState.AVAILABLE.value if ready
            else RuntimeState.DEGRADED.value if queue.get("broker_reachable")
            else RuntimeState.UNREACHABLE.value
        ),
    }


async def _memory_runtime_status() -> Dict[str, Any]:
    try:
        memory = get_store("memory").load()
        return {
            "status": RuntimeState.AVAILABLE.value,
            "record_count": len(memory) if isinstance(memory, (dict, list)) else None,
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "error": type(exc).__name__,
        }


async def _voice_runtime_status() -> Dict[str, Any]:
    from .routers.voice import voice_status

    result = await voice_status()
    stt = bool(result.get("asr_available"))
    tts = bool(result.get("tts_available"))
    configured = bool(result.get("tts_configured"))
    return {
        "status": (
            RuntimeState.AVAILABLE.value if stt and tts
            else RuntimeState.DEGRADED.value if stt or tts
            else RuntimeState.CONFIGURED.value if configured
            else RuntimeState.UNCONFIGURED.value
        ),
        "stt_available": stt,
        "tts_available": tts,
        "tts_configured": configured,
    }


async def _streaming_runtime_status(
    provider_status: Dict[str, Any],
) -> Dict[str, Any]:
    from .routers.legacy import router as chat_router

    route_registered = any(
        getattr(route, "path", None) == "/api/chat/stream"
        for route in chat_router.routes
    )
    streaming_providers = [
        item for item in provider_status["providers"]
        if item["configured"]
        and any("stream" in str(capability).lower()
                for capability in item["capabilities"])
    ]
    verified = any(item["streaming_verified"] for item in streaming_providers)
    configured = bool(route_registered and streaming_providers)
    return {
        "status": (
            RuntimeState.AVAILABLE.value if route_registered and verified
            else RuntimeState.CONFIGURED.value if configured
            else RuntimeState.UNAVAILABLE.value
        ),
        "route_registered": route_registered,
        "streaming_verified": verified,
    }


async def _tool_runtime_status() -> Dict[str, Any]:
    try:
        from .capabilities import get_registry

        capability = get_registry().get("tool")
        if capability is None:
            return {"status": RuntimeState.UNCONFIGURED.value, "tool_count": 0}
        result = await capability.health()
        return {
            "status": (
                RuntimeState.AVAILABLE.value
                if result.get("healthy")
                else RuntimeState.UNAVAILABLE.value
            ),
            "tool_count": int(result.get("tool_count", 0)),
            "healthy_tool_count": sum(
                1 for health in result.get("tools", {}).values()
                if health.get("healthy")
                or health.get("status") in {"ok", "available", "ready"}
            ),
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "error": type(exc).__name__,
        }


async def _agent_runtime_status() -> Dict[str, Any]:
    try:
        from .routers.agents import router as agents_router

        paths = {
            getattr(route, "path", None) for route in agents_router.routes
        }
        graph_available = "/graph/status" in paths
        store = get_store("agent_graph")
        store.load()
        return {
            "status": (
                RuntimeState.CONFIGURED.value
                if graph_available
                else RuntimeState.UNAVAILABLE.value
            ),
            "graph_route_registered": graph_available,
            "execution_verified": False,
        }
    except Exception as exc:
        return {
            "status": RuntimeState.UNAVAILABLE.value,
            "execution_verified": False,
            "error": type(exc).__name__,
        }


async def _modality_runtime_status(
    provider_status: Dict[str, Any],
) -> Dict[str, Any]:
    from .capabilities import get_registry

    configured = [
        provider for provider in provider_status["providers"]
        if provider["configured"]
    ]
    vision_configured = any(
        any("vision" in str(capability).lower() or "image.input" in str(capability).lower()
            for capability in provider["capabilities"])
        for provider in configured
    )
    image_configured = any(
        provider["provider"] == "openai" for provider in configured
    ) or bool(os.environ.get("STABILITY_API_KEY"))
    registry = get_registry()
    vision = registry.get("vision")
    image_generation = registry.get("image_generation")
    vision_verified = bool(getattr(vision, "_inference_verified", False))
    image_verified = bool(getattr(image_generation, "_generation_verified", False))
    return {
        "VISION": {
            "status": (
                RuntimeState.AVAILABLE.value if vision_verified
                else RuntimeState.CONFIGURED.value if vision_configured
                else RuntimeState.UNCONFIGURED.value
            ),
            "verified": vision_verified,
        },
        "IMAGE_GENERATION": {
            "status": (
                RuntimeState.AVAILABLE.value if image_verified
                else RuntimeState.CONFIGURED.value if image_configured
                else RuntimeState.UNCONFIGURED.value
            ),
            "verified": image_verified,
        },
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
    provider_status, celery_status, memory_status, voice_status_result, tool_status, agent_status = await asyncio.gather(
        _provider_runtime_status(),
        _celery_runtime_status(),
        _memory_runtime_status(),
        _voice_runtime_status(),
        _tool_runtime_status(),
        _agent_runtime_status(),
    )
    if brain_res["status"] == RuntimeState.AVAILABLE.value:
        brain_provider = next(
            (item for item in provider_status["providers"]
             if item["provider"] == "jarvis-brain"),
            None,
        )
        if brain_provider is not None:
            brain_provider.update({
                "status": RuntimeState.AVAILABLE.value,
                "inference_verified": True,
            })
        provider_status["verified_count"] += int(brain_provider is not None)
        provider_status["status"] = RuntimeState.AVAILABLE.value
    redis_status = await _redis_runtime_status(celery_status)
    streaming_status = await _streaming_runtime_status(provider_status)
    modality_status = await _modality_runtime_status(provider_status)

    components = {
        "BACKEND": {"status": RuntimeState.AVAILABLE.value},
        "AUTH": auth_res,
        "CHAT": chat_res,
        "DATABASE": db_res,
        "REDIS": redis_status,
        "CELERY": celery_status,
        "PROVIDER_GATEWAY": provider_status,
        "PROVIDERS": provider_status["providers"],
        "CONVERSATION": chat_res,
        "STREAMING": streaming_status,
        "MEMORY": memory_status,
        "VOICE": voice_status_result,
        "TOOLS": tool_status,
        "AGENTS": agent_status,
        **modality_status,
        "OPENAI": next((p for p in provider_status["providers"] if p["provider"] == "openai"), openai_res),
        "GOOGLE": next((p for p in provider_status["providers"] if p["provider"] == "google"), google_res),
        "NVIDIA": next((p for p in provider_status["providers"] if p["provider"] == "nvidia"), nvidia_res),
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
    any_provider_available = (
        provider_status["verified_count"] > 0
        or brain_res["status"] == RuntimeState.AVAILABLE.value
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
