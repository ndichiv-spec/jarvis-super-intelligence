"""Application/service boundary to the Silverwing model gateway.

``ChatService`` delegates every real provider call to :class:`ProviderGateway`
so the chat layer never talks to provider SDKs directly and never fabricates a
reply.

Two routing paths exist (both reuse the existing platform infrastructure):

* **Silverwing runtime** (``SILVERWING_ENDPOINT`` set) â€” delegates to the
  platform :class:`~backend.model_gateway.routing.ModelGateway`, which calls the
  Silverwing runtime over HTTP at ``/v1/chat/completions``.  This is the
  preferred path: the runtime serves the real 120 M parameter TorchBackend
  weights (rev ``r1``, device ``cpu``, backend ``torch``).
* **Cloud / local-rule fallback** (``SILVERWING_ENDPOINT`` unset) â€” falls back
  to the existing Silverwing ``ModelRouter.route_and_chat`` entry point in
  ``silverwing-backend/model_provider.py``.  An honesty guard requires at least
  one cloud provider API key; if none is configured the gateway raises
  ``PROVIDER_UNAVAILABLE`` rather than returning a deterministic echo.
* **JARVIS Brain remote** (``JARVIS_BRAIN_ENDPOINT`` set) â€” the preferred
  general-purpose path when a remote OpenAI-compatible endpoint (the Kaggle GPU
  host serving Qwen3-4B / SFT adapter) is configured.  Calls ``/v1/chat/completions``
  over HTTP; no weights live on the JARVIS PC.  If the Brain is confirmed
  unreachable, the gateway falls back to the offline Silverwing runtime and
  records ``fallback`` in the reply so provenance is never misrepresented.

Honesty contract
----------------
* If no real provider is configured AND the Silverwing runtime endpoint is not
  set, the gateway raises :class:`~jarvis_backend.errors.ChatError`
  (PROVIDER_UNAVAILABLE).  It NEVER returns Silverwing's ``local-rule``
  deterministic echo as a "real" answer.
* If Silverwing itself falls back to ``local`` (e.g. a requested provider lacks
  credentials), that response is rejected the same way.
* Timeouts and transport errors are mapped to TIMEOUT / NETWORK_ERROR so the
  chat service can retry them with bounded backoff.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict, Iterator, Optional

from infrastructure.vault.manager import get_secrets_manager
from jarvis_runtime import SILVERWING_BACKEND_ROOT, WORKSPACE_ROOT, ensure_import_paths

from .errors import ChatError, ErrorCategory, from_provider_exception

logger = logging.getLogger("jarvis_backend.gateway")
_STREAMING_PROVIDER_VERIFIED: set[str] = set()


def verified_streaming_providers() -> set[str]:
    """Return providers that have completed a real stream in this process."""
    return set(_STREAMING_PROVIDER_VERIFIED)

_SILVERWING_BACKEND = SILVERWING_BACKEND_ROOT
_PROVIDER_FABRIC_ROOT = WORKSPACE_ROOT
_PHASE6_PROVIDER_IDS = frozenset({"openai", "nvidia", "google", "aws", "hf"})

_sw_module: Any | None = None


def _ensure_provider_fabric_import_path() -> str:
    ensure_import_paths()
    return str(_PROVIDER_FABRIC_ROOT)


def _load_silverwing() -> Any:
    """Lazily import Silverwing's ``model_provider`` module (idempotent)."""
    global _sw_module
    if _sw_module is None:
        ensure_import_paths()
        try:
            import model_provider as sw  # type: ignore[import-not-found]
        except Exception as exc:
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "The model gateway is not available.",
                detail=f"silverwing import failed: {type(exc).__name__}",
                retryable=False,
            )
        _sw_module = sw
    return _sw_module


def _has_cloud_key(sw: Any) -> bool:
    try:
        return bool(sw.ModelConfig().any_cloud_key())
    except Exception:
        return False


def _default_model() -> str:
    return os.environ.get("JARVIS_MODEL") or "local-rule"


def _parse_model_reference(model: str | None) -> tuple[Optional[str], Optional[str]]:
    raw = (model or "").strip()
    if not raw or raw.lower() in {"auto", "ollama", "local-rule"}:
        return None, None
    _ensure_provider_fabric_import_path()
    try:
        from providers.models import ModelRef
    except ImportError:
        return None, raw

    if ":" not in raw:
        return None, raw
    try:
        ref = ModelRef.parse(raw)
    except ValueError:
        return None, raw
    provider = ref.provider.strip().lower()
    if provider in _PHASE6_PROVIDER_IDS or provider == "silverwing":
        return provider, ref.model.strip()
    return None, raw


def _model_for_adapter(provider: str, model: str | None) -> str | None:
    if not model:
        return model
    prefix = f"{provider}:"
    if model.startswith(prefix):
        return model[len(prefix):]
    return model


def _resolve_router(sw: Any) -> Any:
    """Get or build a Silverwing ModelRouter, tolerating constructor variance."""
    for attr in ("model_router", "router", "MODEL_ROUTER", "_router"):
        r = getattr(sw, attr, None)
        if r is not None and hasattr(r, "route_and_chat"):
            return r
    ctor = getattr(sw, "ModelRouter", None)
    if ctor is None:
        raise ChatError(
            ErrorCategory.PROVIDER_UNAVAILABLE,
            "The model gateway does not expose a router.",
            retryable=False,
        )
    # Try the simplest constructor first, then with a registry if required.
    registry = getattr(sw, "ModelRegistry", None)
    manager = getattr(sw, "ModelManager", None)
    for kwargs in ({}, {"registry": registry}, {"registry": registry, "manager": manager}):
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        try:
            return ctor(**kwargs)
        except TypeError:
            continue
    raise ChatError(
        ErrorCategory.PROVIDER_UNAVAILABLE,
        "The model gateway router could not be initialised.",
        retryable=False,
    )


def _silverwing_endpoint() -> str:
    """Return the configured Silverwing runtime endpoint (empty if unset)."""
    return os.environ.get("SILVERWING_ENDPOINT", "").strip()


def _jarvis_brain_endpoint() -> str:
    """Return the configured remote JARVIS Brain endpoint (empty if unset).

    This is an OpenAI-compatible endpoint served by the Kaggle GPU host.
    ``JARVIS_BRAIN_ENDPOINT`` may be ``https://host/v1`` or a bare host URL;
    we normalise it to accept either form without double-slashing.
    """
    return os.environ.get("JARVIS_BRAIN_ENDPOINT", "").strip()


def _jarvis_brain_api_key() -> str:
    """JARVIS Brain API key loaded through the project secret vault.

    Resolved via ``SecretsManager`` (env variables / ``.env`` / an encrypted
    vault file in production) -- never read as a raw env var and never
    persisted to the application KV store. Never logged.
    """
    try:
        return (get_secrets_manager().get_or_none("brain_api_key") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _jarvis_brain_api_key_configured() -> bool:
    """True iff a JARVIS Brain API key is present (safe to expose as a boolean)."""
    return bool(_jarvis_brain_api_key())


# --------------------------------------------------------------------------- #
# Remote JARVIS Brain backend selection (spec sections 1 / 7 / 33).
#
# The remote Brain boundary is an OpenAI-compatible /v1/chat/completions
# endpoint. Two credentials are NEVER merged (spec section 33):
#   * JARVIS_BRAIN_API_KEY / vault 'brain_api_key'  -> authenticates the
#     local JARVIS API -> Brain boundary (a local :8011-style gate).
#   * NVIDIA_API_KEY / vault 'nvidia_api_key'       -> Brain -> NVIDIA NIM
#     upstream. Selected automatically when JARVIS_BRAIN_ENDPOINT points at
#     integrate.api.nvidia.com; otherwise the legacy brain key is used
#     upstream (e.g. a Kaggle-hosted Qwen Brain).
# --------------------------------------------------------------------------- #
_NVIDIA_NIM_HOSTS = ("integrate.api.nvidia.com", "nvcf.nvidia.com", "nim.nvidia.com")


def _brain_provider(endpoint: str) -> str:
    """Provider name for the remote Brain backend, derived from the endpoint."""
    ep = (endpoint or "").lower()
    for host in _NVIDIA_NIM_HOSTS:
        if host in ep:
            return "nvidia"
    return "jarvis-brain"


def _brain_upstream_key(endpoint: str) -> str:
    """Credential for Brain -> upstream (spec section 33).

    NVIDIA NIM uses NVIDIA_API_KEY (vault 'nvidia_api_key' aliases
    JARVIS_NVIDIA_API_KEY, else the raw NVIDIA_API_KEY env var). Non-NVIDIA
    Brains use the local boundary key from the vault. The two are never merged.
    Never logged.
    """
    if _brain_provider(endpoint) == "nvidia":
        try:
            val = get_secrets_manager().get_or_none("nvidia_api_key")
        except Exception:  # noqa: BLE001 -- vault always best-effort
            val = None
        return (val or os.environ.get("NVIDIA_API_KEY") or "").strip()
    return _jarvis_brain_api_key()


def _brain_model() -> str:
    """Remote Brain model (JARVIS_BRAIN_MODEL / JARVIS_NVIDIA_MODEL, then a
    documented NVIDIA default). Honest: the live probe/validator confirms it."""
    return (
        os.environ.get("JARVIS_BRAIN_MODEL")
        or os.environ.get("JARVIS_NVIDIA_MODEL")
        or "nvidia/nemotron-3-ultra-550b-a55b"
    )


def _brain_backend() -> str:
    """'remote' when a remote Brain endpoint is configured, else 'local'."""
    return "remote" if _jarvis_brain_endpoint() else "local"


def _endpoint(url: str, path: str = "/chat/completions") -> str:
    """Join a base URL and a path without duplicating slashes."""
    return url.rstrip("/") + "/" + path.lstrip("/")


_STREAM_SENTINEL = object()


async def _aiter_blocking(make_iterator: Callable[[], Iterator[Any]]) -> AsyncIterator[Any]:
    """Bridge a *blocking* (synchronous) iterator into an async iterator.

    Provider adapters expose ``stream()`` as a synchronous generator that performs
    blocking network I/O (``google.client.GoogleProvider.stream`` calls the sync
    ``google_genai`` ``generate_content_stream``). Iterating that generator
    directly from inside an ``async def`` blocked the whole asyncio event loop, so
    a single streaming request stalled the server and every other endpoint became
    unresponsive.

    The blocking iteration is pushed onto a worker thread and each produced item
    is handed back to the event-loop thread, so deltas still reach the client in
    real time while the server stays responsive.
    """
    loop = asyncio.get_running_loop()
    inbox: asyncio.Queue = asyncio.Queue()
    stopped = threading.Event()

    def _pump() -> None:
        try:
            for item in make_iterator():
                if stopped.is_set() or loop.is_closed():
                    break
                loop.call_soon_threadsafe(inbox.put_nowait, item)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the loop thread
            if not stopped.is_set() and not loop.is_closed():
                loop.call_soon_threadsafe(inbox.put_nowait, exc)
        finally:
            if not stopped.is_set() and not loop.is_closed():
                loop.call_soon_threadsafe(inbox.put_nowait, _STREAM_SENTINEL)

    worker = threading.Thread(
        target=_pump, name="jarvis-provider-stream", daemon=True
    )
    worker.start()
    try:
        while True:
            item = await inbox.get()
            if item is _STREAM_SENTINEL:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stopped.set()


async def _run_blocking(fn: Callable[[], Any]) -> Any:
    """Execute a blocking call off the event-loop thread."""
    return await asyncio.to_thread(fn)


class ProviderGateway:
    """The application boundary to the existing Silverwing model gateway.

    ChatService owns one instance; tests may inject a fake gateway (or a fake
    ``router``) to drive the chat/service-layer logic without a real provider.
    """

    def __init__(self, router: Any | None = None, *, max_retries: int = 0,
                 timeout: float | None = None,
                 brain_client: Any | None = None) -> None:
        self._router = router  # injected test double (must have route_and_chat)
        self._brain_client = brain_client  # injected BrainClient (or built lazily)
        self.max_retries = max(0, int(max_retries))
        # When the Silverwing runtime is configured, honour SILVERWING_TIMEOUT
        # (CPU inference can take 5-15 s per request).  Override with the
        # explicit ``timeout`` argument or JARVIS_GATEWAY_TIMEOUT for cloud
        # providers.
        if timeout is not None:
            self.timeout = float(timeout)
        else:
            env_timeout = os.environ.get("JARVIS_GATEWAY_TIMEOUT")
            if env_timeout:
                self.timeout = float(env_timeout)
            elif os.environ.get("SILVERWING_ENDPOINT"):
                self.timeout = float(os.environ.get("SILVERWING_TIMEOUT", "300"))
            else:
                self.timeout = 30.0

    def _get_router(self) -> Any:
        if self._router is not None:
            return self._router
        sw = _load_silverwing()
        if self._router is None:
            self._router = _resolve_router(sw)
        return self._router

    async def chat(self, messages: list[dict[str, Any]], model: str | None = None,
                   system: str | None = None,
                   timeout: float | None = None,
                   *, _bypass_gateway: bool = False) -> dict[str, Any]:
        """Call the gateway once and return a normalized result dict.

        Returns ``{"content", "model", "provider", "revision", "backend",
        "device", "latency_ms", "usage"}``.
        Never returns a local-rule/fallback answer; raises ChatError instead.
        """
        deadline = float(timeout if timeout is not None else self.timeout)
        explicit_provider, explicit_model = _parse_model_reference(model)
        explicit_cloud = explicit_provider in _PHASE6_PROVIDER_IDS
        explicit_silverwing = explicit_provider == "silverwing"
        local_model = explicit_model if explicit_silverwing else None

        fabric_attempted = False
        fabric_last_error: BaseException | None = None
        brain_fallback_reason: str | None = None
        if explicit_cloud and not explicit_silverwing:
            try:
                fabric_result = await self._chat_via_phase6_fabric(
                    messages, model, system, deadline,
                )
                fabric_attempted = True
                if fabric_result is not None:
                    return fabric_result
                # Fabric returned None for an explicit cloud provider — the
                # provider was tried but could not serve the request (bad model,
                # auth error, etc.).  Do NOT silently fall through to the
                # Silverwing runtime or auto-routing with a different provider.
                raise ChatError(
                    ErrorCategory.PROVIDER_UNAVAILABLE,
                    f"The requested provider '{explicit_provider}' could not "
                    f"generate a real response (model: "
                    f"{explicit_model or 'default'}).",
                    retryable=True,
                    detail=f"provider={explicit_provider}, "
                           f"model={explicit_model or 'default'}",
                )
            except ChatError:
                # Re-raise our own PROVIDER_UNAVAILABLE (from the None case
                # above) -- do not swallow it into fabric_last_error.
                raise
            except Exception as exc:
                # Fabric failed with an exception (network error, provider
                # error, etc.).  Save the error so we can re-raise it if no
                # fallback path succeeds, and so we don't silently replace
                # the user's chosen provider with another one.
                fabric_attempted = True
                fabric_last_error = exc

        # ---- JARVIS Brain remote path (primary, when configured) ------------
        # JARVIS BRAIN (Qwen3-4B) is the preferred general-purpose model when a
        # remote OpenAI-compatible endpoint (Kaggle GPU host) is configured.
        # Health is checked by an actual successful inference, never assumed.
        brain_ep = (
            _jarvis_brain_endpoint()
            if not _bypass_gateway and not explicit_cloud and not explicit_silverwing
            else ""
        )
        if brain_ep:
            try:
                result = await self._chat_via_remote_brain(
                    brain_ep, messages, model, system, deadline,
                )
                if not (result.get("content") or "").strip():
                    raise ChatError(
                        ErrorCategory.PROVIDER_UNAVAILABLE,
                        "The JARVIS Brain returned an empty reply.",
                        detail=f"provider={result.get('provider')}",
                        retryable=False,
                    )
                return result
            except ChatError as exc:
                if exc.category != ErrorCategory.PROVIDER_UNAVAILABLE:
                    raise
                brain_fallback_reason = exc.safe_message

        if not fabric_attempted and not explicit_silverwing:
            try:
                fabric_result = await self._chat_via_phase6_fabric(
                    messages, model, system, deadline,
                )
                if fabric_result is not None:
                    return fabric_result
            except Exception:
                # Fabric failed (no working provider) - let honesty guard handle it
                pass

        # ---- Silverwing runtime path (fallback) -----------------------------
        # When the JARVIS Brain is not configured (or was confirmed down), the
        # local Silverwing runtime is the offline path.  When SILVERWING_ENDPOINT
        # is set, delegate to the platform ModelGateway which calls the real
        # TorchBackend over HTTP.  This bypasses the cloud-key honesty guard
        # because Silverwing is the platform's own model.
        #
        # TRUTHFULNESS: when the user *explicitly* requested a cloud provider
        # (e.g. ``nvidia:bad-model``) and that provider failed, do NOT
        # silently substitute the Silverwing runtime or another cloud provider.
        # Re-raise the original error so the caller sees which provider the
        # user asked for and why it failed.
        if explicit_cloud and fabric_attempted:
            if fabric_last_error is not None:
                raise fabric_last_error
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                f"The requested provider '{explicit_provider}' could not "
                f"generate a real response.",
                retryable=True,
            )

        endpoint = _silverwing_endpoint() if not _bypass_gateway else ""
        if endpoint:
            try:
                result = await self._chat_via_model_gateway(
                    messages, local_model, system, deadline,
                )
                if brain_fallback_reason:
                    result["fallback"] = {
                        "from": os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1"),
                        "to": result.get("model", ""),
                        "reason": brain_fallback_reason,
                    }
                return result
            except ChatError as exc:
                # Only bridge a confirmed-unreachable runtime; timeouts/
                # transient errors are retried by the chat service, and a
                # local-rule / echo response from a live runtime must NOT be
                # silently replaced by a cloud call.
                if exc.category != ErrorCategory.PROVIDER_UNAVAILABLE:
                    raise
                # Self-resilient bridge: the local Silverwing runtime is
                # unreachable, but a real cloud provider key is configured
                # -- i.e. an extension (OpenAI, Claude, Gemini, ...) has been
                # *connected* to the platform. Serve from that provider so
                # /api/chat keeps returning real replies when :8010 is down
                # ("Jarvis connected as an AI platform"). With no cloud key
                # configured we re-raise so the honesty guard fires.
                try:
                    _sw = _load_silverwing()
                except ChatError:
                    _sw = None
                if _sw is not None and _has_cloud_key(_sw):
                    pass  # fall through to the cloud / local-rule path below
                else:
                    raise


        # ---- Cloud / local-rule path (fallback) ----------------------------
        sw = _load_silverwing()

        # Honesty guard #1: with no real provider configured, refuse rather
        # than returning Silverwing's deterministic local echo.
        if not _has_cloud_key(sw):
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "No AI provider is configured (no cloud provider API key is set). "
                "Responses are never faked; configure a provider key "
                "(e.g. OPENAI_API_KEY) to receive real responses.",
                retryable=False,
            )

        router = self._get_router()
        request = sw.ModelRequest(
            messages=list(messages),
            model=local_model or _default_model(),
            system=system,
        )

        try:
            resp, _decision = await asyncio.wait_for(
                router.route_and_chat(request, task="jarvis.chat"), timeout=deadline
            )
        except TimeoutError:
            raise ChatError(
                ErrorCategory.TIMEOUT,
                "The AI provider did not respond within the time limit. "
                "Please try again.",
                retryable=True,
            )
        except ChatError:
            raise
        except Exception as exc:
            raise from_provider_exception(exc)

        # Honesty guard #2: a local-rule / empty response must never be
        # presented as a real model answer.
        provider = getattr(resp, "provider", "") or ""
        if provider in ("local", "local-rule") or not (resp.content or "").strip():
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "The AI provider could not generate a real response. "
                "Your request was not answered by a model.",
                retryable=False,
            )

        latency_ms = getattr(resp, "latency_ms", None)
        usage = getattr(resp, "usage", {}) or {}
        return {
            "content": resp.content or "",
            "model": f"{resp.provider}:{resp.model}",
            "provider": resp.provider,
            "latency_ms": int(latency_ms) if latency_ms is not None else None,
            "usage": usage,
        }

    def _resolve_fabric_candidates(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
    ) -> tuple[list[tuple[str, Any, Optional[str]]], Optional[str], Any]:
        """Resolve fabric candidates as ``(provider_id, adapter, model)`` triples.

        Shared by the buffered (:meth:`_chat_via_phase6_fabric`) and streaming
        (:meth:`stream_chat_via_fabric`) paths so both route identically.

        Returns ``(candidates, forced_provider, registry)``; ``candidates`` is
        empty when the fabric is unavailable or nothing is routable.
        """
        _ensure_provider_fabric_import_path()

        from providers.base import Message  # type: ignore[import-not-found]
        from providers.bootstrap import bootstrap_fabric  # type: ignore[import-not-found]
        from providers.routing import (  # type: ignore[import-not-found]
            ProviderRouter,
            TaskClassifier,
        )

        forced_provider, resolved_model = _parse_model_reference(model)
        if forced_provider == "silverwing":
            return [], None, None

        registry = bootstrap_fabric()
        router = ProviderRouter(registry=registry, priority=forced_provider or "")
        task_text = messages[-1].get("content", "") if messages else ""
        profile = TaskClassifier().classify(task_text or "chat")

        pairs: list[tuple[str, Optional[str]]] = []
        if forced_provider is not None:
            adapter = registry.get(forced_provider)
            if adapter is None or not adapter.configured:
                return [], forced_provider, registry
            pairs.append((forced_provider, resolved_model))
        else:
            decision = router.route(profile)
            if not decision.selected_provider:
                return [], None, registry
            pairs.append((
                decision.selected_provider,
                _model_for_adapter(decision.selected_provider, decision.selected_model),
            ))
            for fallback in decision.fallback_chain:
                provider = fallback.get("provider")
                if provider:
                    pairs.append((
                        provider,
                        _model_for_adapter(provider, fallback.get("model")),
                    ))

        candidates: list[tuple[str, Any, Optional[str]]] = []
        for provider_id, selected_model in pairs:
            adapter = registry.get(provider_id)
            if adapter is None or not adapter.configured:
                continue
            candidates.append((provider_id, adapter, selected_model))
        return candidates, forced_provider, registry

    @staticmethod
    def _build_fabric_messages(
        messages: list[dict[str, Any]], system: str | None
    ) -> list[Any]:
        from providers.base import Message  # type: ignore[import-not-found]

        msgs: list[Message] = [
            Message.from_mapping(m) if isinstance(m, dict) else m
            for m in messages
        ]
        if system:
            msgs.insert(0, Message(role="system", content=system))
        return msgs

    async def stream_chat_via_fabric(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        system: str | None,
        deadline: float,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a reply from the provider fabric, one real delta at a time.

        Yields ``{"type": "delta", "text": ...}`` for genuine provider output and
        exactly one terminal ``{"type": "done", ...}`` carrying provenance.

        Honesty rules:
        * Only adapters that declare ``Capability.STREAMING`` are streamed.
        * An adapter that cannot stream is reported as ``streamed: False`` and
          its reply is delivered as a single terminal result - the gateway never
          slices an already-complete answer into fake incremental chunks.
        """
        _ensure_provider_fabric_import_path()

        from providers.base import ProviderRequest  # type: ignore[import-not-found]
        from providers.capabilities import Capability  # type: ignore[import-not-found]
        from providers.errors import (  # type: ignore[import-not-found]
            ProviderAuthenticationError,
            ProviderError,
        )

        candidates, forced_provider, _registry = self._resolve_fabric_candidates(
            messages, model
        )
        if not candidates:
            return

        msgs = self._build_fabric_messages(messages, system)
        last_error: BaseException | None = None

        for provider_id, adapter, selected_model in candidates:
            if forced_provider is None:
                health = await _run_blocking(lambda: adapter.health(force=False))
                if not health.is_healthy or health.models_found <= 0:
                    continue

            if not adapter.supports(Capability.STREAMING):
                logger.info(
                    "provider %s does not declare streaming capability", provider_id
                )
                continue

            req = ProviderRequest(
                messages=msgs,
                model=selected_model,
                stream=True,
                timeout=deadline,
            )
            started = time.monotonic()
            parts: list[str] = []
            tool_calls: dict[int, dict[str, str]] = {}
            usage = None
            finish_reason = None
            try:
                async for chunk in _aiter_blocking(lambda: adapter.stream(req)):
                    reasoning = getattr(chunk, "reasoning", "") or ""
                    if reasoning:
                        yield {"type": "reasoning", "text": reasoning}
                    text = getattr(chunk, "text", "") or ""
                    if text:
                        parts.append(text)
                        yield {"type": "delta", "text": text}
                    for call in getattr(chunk, "tool_calls", None) or []:
                        index = int(getattr(call, "index", 0))
                        state = tool_calls.setdefault(
                            index, {"id": "", "name": "", "arguments": ""}
                        )
                        call_id = getattr(call, "id", "") or ""
                        name = getattr(call, "name", "") or ""
                        arguments = getattr(call, "arguments", "") or ""
                        state["id"] = call_id or state["id"]
                        state["name"] += name
                        state["arguments"] += arguments
                        yield {
                            "type": "tool_call_delta",
                            "index": index,
                            "id": state["id"],
                            "name": name,
                            "arguments": arguments,
                        }
                    if getattr(chunk, "done", False):
                        chunk_usage = getattr(chunk, "usage", None)
                        if chunk_usage is not None:
                            usage = chunk_usage
                        finish_reason = (
                            getattr(chunk, "finish_reason", None) or finish_reason
                        )
            except ProviderAuthenticationError as exc:
                mark_failed = getattr(adapter, "mark_inference_failed", None)
                if mark_failed is not None:
                    mark_failed(detail="inference credential rejected")
                logger.warning(
                    "provider %s rejected streaming credentials", provider_id
                )
                last_error = exc
                continue
            except ProviderError as exc:
                logger.info(
                    "provider %s failed while streaming: %s", provider_id, exc
                )
                mark_failed = getattr(adapter, "mark_inference_failed", None)
                if mark_failed is not None:
                    mark_failed(detail=f"streaming failed: {exc}")
                last_error = exc
                continue
            except Exception as exc:
                logger.exception("provider %s raised while streaming", provider_id)
                last_error = exc
                continue

            content = "".join(parts)
            if not content.strip() and not tool_calls:
                continue

            mark_verified = getattr(adapter, "mark_inference_verified", None)
            if mark_verified is not None:
                mark_verified(models_found=1)
            _STREAMING_PROVIDER_VERIFIED.add(provider_id)
            if usage is not None and hasattr(usage, "to_dict"):
                usage = usage.to_dict()
            completed_tool_calls = []
            for index, call in sorted(tool_calls.items()):
                try:
                    arguments = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = {"_raw_arguments": call["arguments"]}
                completed_tool_calls.append({
                    "index": index,
                    "id": call["id"],
                    "name": call["name"],
                    "arguments": arguments if isinstance(arguments, dict) else {"value": arguments},
                })
            yield {
                "type": "done",
                "content": content,
                "provider": getattr(adapter, "provider_id", provider_id),
                "model": selected_model or "",
                "streamed": True,
                "tool_calls": completed_tool_calls,
                "finish_reason": finish_reason,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "usage": usage,
            }
            return

        # Every candidate failed. Surface the real reason instead of returning
        # silence, so the client can distinguish RATE_LIMITED from
        # PROVIDER_UNAVAILABLE rather than showing a generic failure.
        if last_error is not None:
            raise from_provider_exception(last_error)
        raise ChatError(
            ErrorCategory.PROVIDER_UNAVAILABLE,
            "No configured provider could serve this request. "
            "Your request was not answered by a model.",
            retryable=True,
        )

    async def stream_chat(
        self,
        prompt: str | None = None,
        *,
        model: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        system: str | None = None,
        timeout: float | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a reply, preferring genuine provider streaming.

        Yields ``reasoning`` / ``delta`` events as they arrive and exactly one
        terminal ``done`` event. If the fabric cannot stream (no streaming-capable
        provider, or only the non-streaming Brain/Silverwing paths are viable),
        the buffered result is delivered as a single ``done`` event with
        ``streamed: False`` - the reply is never sliced into fake deltas.

        ``messages`` carries the full conversation history (so the provider can
        maintain continuity across turns). When omitted, only ``prompt`` is sent
        as a single user message (backward compatibility).
        """
        deadline = float(timeout if timeout is not None else self.timeout)
        # Use the full conversation history when provided so the provider can
        # maintain conversation continuity; otherwise fall back to the single
        # prompt (preserving backward compatibility for callers that only pass
        # a prompt string).
        messages: list[dict[str, Any]] = list(messages) if messages else [
            {"role": "user", "content": prompt or ""}
        ]

        forced_provider, _ = _parse_model_reference(model)
        explicit_silverwing = forced_provider == "silverwing"

        if not explicit_silverwing:
            try:
                produced = False
                async for event in self.stream_chat_via_fabric(
                    messages, model, system, deadline
                ):
                    produced = True
                    yield event
                if produced:
                    return
            except ChatError:
                # Fabric could not serve the request. Fall through to the other
                # gateway paths; the final failure is reported honestly below.
                logger.info("streaming via fabric unavailable; trying other paths")

        result = await self.chat(messages, model=model, system=system, timeout=deadline)
        content = result.get("content") or ""
        yield {
            "type": "done",
            "content": content,
            "provider": result.get("provider"),
            "model": result.get("model"),
            "streamed": False,
            "latency_ms": result.get("latency_ms"),
            "usage": result.get("usage"),
        }

    async def _chat_via_phase6_fabric(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        system: str | None,
        deadline: float,
    ) -> Optional[dict[str, Any]]:
        """Route ``messages`` through the existing Phase 6 provider fabric."""
        _ensure_provider_fabric_import_path()

        try:
            from providers.base import Message, ProviderRequest  # type: ignore[import-not-found]
            from providers.bootstrap import bootstrap_fabric  # type: ignore[import-not-found]
            from providers.errors import (  # type: ignore[import-not-found]
                ProviderAuthenticationError,
                ProviderError,
            )
            from providers.routing import (  # type: ignore[import-not-found]
                ProviderRouter,
                TaskClassifier,
            )
        except ImportError:
            return None

        forced_provider, resolved_model = _parse_model_reference(model)
        if forced_provider == "silverwing":
            return None

        try:
            registry = bootstrap_fabric()
            router = ProviderRouter(registry=registry, priority=forced_provider or "")
            task_text = messages[-1].get("content", "") if messages else ""
            profile = TaskClassifier().classify(task_text or "chat")

            candidates: list[tuple[str, Optional[str]]] = []
            if forced_provider is not None:
                adapter = registry.get(forced_provider)
                if adapter is None or not adapter.configured:
                    return None
                candidates.append((forced_provider, resolved_model))
            else:
                decision = router.route(profile)
                if not decision.selected_provider:
                    return None
                candidates.append((
                    decision.selected_provider,
                    _model_for_adapter(
                        decision.selected_provider,
                        decision.selected_model,
                    ),
                ))
                for fallback in decision.fallback_chain:
                    provider = fallback.get("provider")
                    if provider:
                        candidates.append((
                            provider,
                            _model_for_adapter(provider, fallback.get("model")),
                        ))

            msgs: list[Message] = [
                Message.from_mapping(m) if isinstance(m, dict) else m
                for m in messages
            ]
            if system:
                msgs.insert(0, Message(role="system", content=system))

            for provider_id, selected_model in candidates:
                adapter = registry.get(provider_id)
                if adapter is None or not adapter.configured:
                    continue
                if forced_provider is None:
                    health = adapter.health(force=False)
                    if not health.is_healthy or health.models_found <= 0:
                        continue
                req = ProviderRequest(
                    messages=msgs,
                    model=selected_model,
                    stream=False,
                    timeout=deadline,
                )
                try:
                    resp = adapter.chat(req)
                    if inspect.isawaitable(resp):
                        # Adapters in the canonical fabric are synchronous; await
                        # only if an adapter ever returns a coroutine.
                        resp = await resp
                except ProviderAuthenticationError:
                    mark_failed = getattr(adapter, "mark_inference_failed", None)
                    if mark_failed is not None:
                        mark_failed(detail="inference credential rejected")
                    logger.warning(
                        "provider %s rejected inference credentials", provider_id
                    )
                    continue
                except ProviderError as exc:
                    logger.info("provider %s unavailable for inference: %s", provider_id, exc)
                    continue
                except Exception:
                    logger.exception(
                        "provider %s raised during inference", provider_id
                    )
                    continue
                # Handle both sync and async response patterns
                content = getattr(resp, "content", None) or getattr(resp, "text", None)
                if not (content or "").strip():
                    continue
                mark_verified = getattr(adapter, "mark_inference_verified", None)
                if mark_verified is not None:
                    mark_verified(models_found=1)
                usage = getattr(resp, "usage", None)
                if usage is not None and hasattr(usage, "to_dict"):
                    usage = usage.to_dict()
                return {
                    "content": content,
                    "model": getattr(resp, "model", None) or selected_model or "",
                    "provider": getattr(resp, "provider", ""),
                    "latency_ms": int(getattr(resp, "latency_ms", 0) or 0),
                    "usage": usage,
                }

            return None
        except Exception:
            logger.exception("provider fabric routing failed")
            # Any unexpected error - let the honesty guard handle it
            return None

    async def _chat_via_model_gateway(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        system: str | None,
        deadline: float,
    ) -> dict[str, Any]:
        """Call the configured Silverwing runtime through its OpenAI-compatible API.

        This path intentionally does not depend on the missing legacy
        ``backend.model_gateway`` package. Silverwing exposes the real model
        through ``/v1/chat/completions``.
        """
        import httpx

        base = (_silverwing_endpoint() or "").strip().rstrip("/")
        if not base:
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "Silverwing runtime is not configured.",
                retryable=False,
            )

        if base.endswith("/chat/completions"):
            post_url = base
        elif base.endswith("/v1"):
            post_url = f"{base}/chat/completions"
        else:
            post_url = f"{base}/v1/chat/completions"

        request_messages = list(messages or [])

        if system:
            has_system = any(
                isinstance(item, dict) and item.get("role") == "system"
                for item in request_messages
            )
            if not has_system:
                request_messages.insert(
                    0,
                    {"role": "system", "content": system},
                )

        selected_model = (
            (model or "").strip()
            or os.environ.get(
                "SILVERWING_MODEL",
                "silverwing-120m-base-v1",
            )
        )

        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": request_messages,
            "stream": False,
        }

        timeout_seconds = max(float(deadline), 1.0)

        headers = {"content-type": "application/json"}
        silverwing_key = os.environ.get("SILVERWING_API_KEY", "").strip()
        if silverwing_key:
            headers["Authorization"] = f"Bearer {silverwing_key}"

        # Use a separate connect timeout so a Silverwing runtime that accepts
        # TCP connections but never responds (e.g. a hung inference worker) fails
        # fast instead of blocking for the full 300s deadline. The total timeout
        # still honours the configured deadline for genuine inference latency.
        connect_timeout = min(float(deadline), 10.0)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout)
            ) as client:
                response = await client.post(
                    post_url,
                    json=payload,
                    headers=headers,
                )


        except httpx.TimeoutException as exc:
            raise ChatError(
                ErrorCategory.TIMEOUT,
                "The Silverwing runtime did not respond within the time limit.",
                retryable=True,
            ) from exc

        except httpx.HTTPError as exc:
            raise ChatError(
                ErrorCategory.NETWORK_ERROR,
                "The Silverwing runtime could not be reached.",
                retryable=True,
                detail=type(exc).__name__,
            ) from exc

        status = response.status_code

        if status in (401, 403):
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "Silverwing rejected the request.",
                retryable=False,
            )

        if status == 429:
            raise ChatError(
                ErrorCategory.RATE_LIMITED,
                "Silverwing is rate limited. Please retry shortly.",
                retryable=True,
            )

        if status >= 500:
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "Silverwing returned a server error.",
                retryable=True,
                detail=f"http_{status}",
            )

        if status >= 400:
            raise ChatError(
                ErrorCategory.MODEL_ERROR,
                "Silverwing rejected the request.",
                retryable=False,
                detail=f"http_{status}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ChatError(
                ErrorCategory.MODEL_ERROR,
                "Silverwing returned invalid JSON.",
                retryable=False,
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "Silverwing returned no model choices.",
                retryable=False,
            )

        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content")

        if isinstance(content, list):
            content = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )

        content = str(content or "").strip()

        if not content:
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "Silverwing returned an empty model response.",
                retryable=False,
            )

        usage = data.get("usage") or {}
        metadata = data.get("metadata") or {}

        return {
            "content": content,
            "model": data.get("model") or selected_model,
            "provider": "silverwing",
            "revision": data.get("revision") or metadata.get("revision") or "",
            "backend": data.get("backend") or metadata.get("backend") or "",
            "device": data.get("device") or metadata.get("device") or "",
            "latency_ms": None,
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            },
        }

    def _brain_client_for(self, endpoint: str) -> Any:
        """Build/reuse a :class:`BrainClient` for the configured endpoint + key.

        The API key comes from the vault (never a raw env var, never logged).
        Tests inject a fake client via ``brain_client=``.
        """
        from backend.model_gateway.brain_client import BrainClient

        if self._brain_client is not None:
            return self._brain_client
        return BrainClient(
            endpoint=endpoint,
            api_key=_jarvis_brain_api_key(),
            model=os.environ.get("JARVIS_BRAIN_MODEL", "jarvis-brain-qwen3-4b-v1"),
        )

    async def _chat_via_remote_brain(
        self,
        endpoint: str,
        messages: list[dict[str, Any]],
        model: str | None,
        system: str | None,
        deadline: float,
    ) -> dict[str, Any]:
        """Call the remote JARVIS Brain via the existing OpenAI-compatible transport.

        Reuses :func:`extensions._openai_compatible_post` -- the same shared
        transport used by the OpenAI/NVIDIA adapter fabric -- so no second HTTP
        client is introduced (spec section 6). The upstream credential is chosen
        per endpoint by :func:`_brain_upstream_key`: ``NVIDIA_API_KEY`` when the
        endpoint is NVIDIA NIM (spec section 33, distinct from
        ``JARVIS_BRAIN_API_KEY``), the local Brain boundary key otherwise.

        Health is proven by an actual (tiny) inference in :meth:`probe_brain`;
        here a stub/unreachable/401 Brain raises PROVIDER_UNAVAILABLE so
        :meth:`chat` honestly falls back to Silverwing instead of presenting a
        stub reply as real.
        """
        from fastapi import HTTPException

        from .routers import extensions as _ext

        provider = _brain_provider(endpoint)
        # Tolerate either "https://host/v1" or a bare host.
        ep = (endpoint or "").strip()
        if ep.lower().startswith(("http://", "https://")):
            base = ep.rstrip("/")
        else:
            base = f"https://{ep.rstrip('/')}"
        if not base.lower().endswith("/v1"):
            base += "/v1"
        post_url = f"{base}/chat/completions"

        key = _brain_upstream_key(endpoint)
        if not key:
            raise ChatError(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "The JARVIS Brain endpoint is configured but no upstream API key "
                "is set. Set NVIDIA_API_KEY (for the NVIDIA NIM backend) or "
                "JARVIS_BRAIN_API_KEY (for a custom Brain endpoint) in the secure "
                "environment / vault.",
                detail=f"provider={provider}",
                retryable=False,
            )

        resolved_model = model or _brain_model()
        payload: Dict[str, Any] = {"model": resolved_model,
                                   "messages": list(messages)}
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]
        start = time.perf_counter()
        try:
            data = await asyncio.to_thread(
                _ext._openai_compatible_post, post_url, payload, key,
                provider=provider, timeout=float(deadline),
            )
        except HTTPException as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            code = e.status_code
            if code in (401, 403):
                raise ChatError(
                    ErrorCategory.PROVIDER_UNAVAILABLE,
                    "The JARVIS Brain endpoint rejected the upstream credentials.",
                    detail=f"provider={provider} code={code} latency_ms={latency_ms}",
                    retryable=False,
                ) from e
            if code == 503:
                raise ChatError(
                    ErrorCategory.PROVIDER_UNAVAILABLE,
                    "The JARVIS Brain endpoint is unreachable "
                    "(connection / DNS / TLS failure).",
                    detail=f"provider={provider} latency_ms={latency_ms}",
                    retryable=False,
                ) from e
            if code == 429:
                raise ChatError(
                    ErrorCategory.RATE_LIMITED,
                    "The AI provider is rate-limiting requests.",
                    retryable=True,
                ) from e
            if code >= 500:
                raise ChatError(
                    ErrorCategory.TIMEOUT,
                    "The JARVIS Brain endpoint returned a server error.",
                    detail=f"provider={provider} code={code}",
                    retryable=True,
                ) from e
            raise ChatError(
                ErrorCategory.MODEL_ERROR,
                "The JARVIS Brain endpoint returned an error.",
                detail=f"provider={provider} code={code}",
                retryable=False,
            ) from e
        except asyncio.TimeoutError:
            raise ChatError(
                ErrorCategory.TIMEOUT,
                "The JARVIS Brain endpoint timed out. Please retry.",
                retryable=True,
            )
        except Exception as exc:  # noqa: BLE001 -- network / transport
            raise from_provider_exception(exc) from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or prompt_tokens + completion_tokens
        )

        # Cost attribution + LangSmith LLM trace (non-blocking)
        cost_usd = 0.0
        try:
            from jarvis_backend.langsmith_integration import (
                get_langsmith_tracer, calculate_cost
            )
            ls = get_langsmith_tracer()
            cost_usd = calculate_cost(
                data.get("model") or resolved_model,
                prompt_tokens,
                completion_tokens,
            )
            # Record LLM call trace with cost
            _prompt_text = ""
            try:
                _prompt_text = " ".join(
                    m.get("content", "") for m in messages
                    if isinstance(m, dict) and m.get("role") != "assistant"
                )
            except Exception:
                pass
            _response_text = ((data.get("choices") or [{}])[0]
                              .get("message", {}).get("content", "")) or ""
            ls.record_llm_call(
                model=data.get("model") or resolved_model,
                prompt=_prompt_text,
                response=_response_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                correlation_id="",
            )
        except Exception:
            pass  # Cost tracing is non-blocking

        return {
            "content": ((data.get("choices") or [{}])[0]
                        .get("message", {}).get("content", "")) or "",
            "model": data.get("model") or resolved_model,
            # Prefer the actual provider reported by the Brain upstream (e.g.
            # "nvidia" for an NVIDIA-hosted Brain); never fabricated by us.
            "provider": (data.get("provider") or "").strip() or provider,
            "revision": ((data.get("choices") or [{}])[0]
                         .get("finish_reason", "")) or "",
            "backend": "remote-openai-compatible",
            "device": "gpu-remote",
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }

    async def probe_brain(self, timeout: float = 15.0) -> dict[str, Any]:
        """Real health probe of the remote JARVIS Brain.

        Health is only reported healthy after an actual (tiny) inference
        succeeds on the GPU host â€” never by assumption.  Reports the endpoint
        and measured latency (ms) so the /ai/status panel can show it.
        """
        endpoint = _jarvis_brain_endpoint()
        if not endpoint:
            return {
                "configured": False,
                "healthy": False,
                "endpoint": None,
                "latency_ms": None,
                "detail": "JARVIS_BRAIN_ENDPOINT not set",
            }
        probe_messages = [{"role": "user", "content": "Reply with the single word: ok"}]
        try:
            result = await self._chat_via_remote_brain(
                endpoint, probe_messages, None, None, timeout,
            )
            if not (result.get("content") or "").strip():
                # Honesty gate: an empty / stub inference is never "healthy".
                return {
                    "configured": True,
                    "healthy": False,
                    "endpoint": endpoint,
                    "latency_ms": result.get("latency_ms"),
                    "category": ErrorCategory.PROVIDER_UNAVAILABLE.value,
                    "detail": "live probe returned an empty inference",
                }
            return {
                "configured": True,
                "healthy": True,
                "endpoint": endpoint,
                "backend": result.get("backend", "remote"),
                "provider": result.get("provider", _brain_provider(endpoint)),
                "model": result.get("model"),
                "latency_ms": result.get("latency_ms"),
                "detail": "live probe succeeded",
            }
        except ChatError as exc:
            return {
                "configured": True,
                "healthy": False,
                "endpoint": endpoint,
                "latency_ms": None,
                "category": exc.category.value,
                "detail": str(exc),
            }


# Module-level default gateway used by ChatService.
provider_gateway = ProviderGateway()
