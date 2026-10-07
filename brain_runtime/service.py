"""Brain inference service.

Owns the active backend (real ``TransformersBackend`` or the explicitly-labeled
``StubBackend``) and the health monitor.  Mirrors the role of
``silverwing_runtime.inference.InferenceService`` but chat-native and provider-
agnostic: the *same* service loads either the Qwen3-4B Base or the SFT candidate
purely from configuration (spec section 21-22).
"""

from __future__ import annotations

import logging
import threading
import time

from brain_runtime.backends.base import BrainBackend
from brain_runtime.config import BrainConfig
from brain_runtime.health import BrainHealthMonitor, BrainHealthStatus, BrainHealthState
from brain_runtime.generation import BrainGenerationConfig, BrainResult
from brain_runtime.model_registry import BRAIN_MODEL_LINEAGE, BrainCatalog
from brain_runtime.routing import BrainRouter

log = logging.getLogger("brain_runtime.service")


class BrainService:
    """In-process orchestrator for the JARVIS Brain runtime."""

    def __init__(
        self,
        config: BrainConfig | None = None,
        catalog: BrainCatalog | None = None,
        backend: BrainBackend | None = None,
        routing_mode: str = "strict",
    ) -> None:
        self.config = config or BrainConfig()
        self.catalog = catalog or BrainCatalog(self.config.model_repo)
        self.routing_mode = routing_mode
        self.health = BrainHealthMonitor()
        self._backend: BrainBackend | None = backend  # injected (tests)
        self._lock = threading.Lock()
        self._started = False
        if backend is not None:
            # An injected backend (e.g. a stub for tests) is already "loaded".
            self._backend = backend
            self._sync_health_from_backend()

    # -- backend construction ----------------------------------------------
    def build_backend(self) -> BrainBackend:
        """Construct the backend implied by ``config``.

        Dispatches on the *normalized backend type* so named providers
        (nvidia/huggingface) and the generic remote/local/stub paths are all
        honored (spec Part C/D/E).  ``priority`` routing mode prefers
        :meth:`build_backend_routed` instead.
        """
        bt = self.config.backend_type
        if bt == "stub":
            entry = self.catalog.lookup(self.config.model)
            revision = entry.revision if entry else "stub"
            return _import_stub_backend(self.config.model, revision)
        if bt == "nvidia":
            return _import_nvidia_backend(self.config)
        if bt == "huggingface":
            return _import_huggingface_backend(self.config)
        if self.config.is_remote:
            return _import_remote_backend(self.config)
        return _import_transformers_backend(
            self.catalog, self.config.model, self.config.device, str(self.config.model_cache),
            local_files_only=self.config.local_files_only,
        )

    def build_backend_routed(self) -> tuple[BrainBackend | None, str]:
        """Select a healthy backend via :class:`BrainRouter` (priority mode)."""
        router = BrainRouter(self.config, self.catalog)
        backend, reason = router.select()
        return backend, reason

    def prepare(self) -> bool:
        """Acquire + warm up the configured model. Returns True on success."""
        with self._lock:
            self._started = True
            if self._backend is not None:
                # Injected backend (tests); assume prepared.
                self._sync_health_from_backend()
                return True
            if self.routing_mode == "priority":
                backend, reason = self.build_backend_routed()
                if backend is None:
                    # Honest offline: never silently fall back to a stub mask.
                    self.health.transition(
                        BrainHealthState.OFFLINE,
                        f"routing: {reason}",
                        backend="", device="", model=self.config.model, stub=False,
                    )
                    self._backend = None
                    return False
            else:
                backend = self.build_backend()
            self._backend = backend
            self.health.transition(BrainHealthState.LOADING, "acquiring model weights")
            try:
                backend.load()
            except Exception as exc:
                log.warning("Brain model load failed: %s", type(exc).__name__)
                self.health.transition(
                    BrainHealthState.OFFLINE,
                    f"model load failed: {type(exc).__name__}",
                    backend=backend.backend,
                    device=backend.device,
                    model=backend.model_id or self.config.model,
                    stub=self.config.is_stub,
                )
                self._backend = None
                return False
            # Warmup (a tiny real inference) confirms the model is servable.
            self.health.transition(BrainHealthState.WARMUP, "warming up")
            try:
                backend.warmup(self.config.warmup_prompt)
            except Exception as exc:
                log.warning("Brain warmup failed: %s", type(exc).__name__)
                self.health.transition(
                    BrainHealthState.DEGRADED,
                    f"warmup failed: {type(exc).__name__}",
                    backend=backend.backend,
                    device=backend.device,
                    model=backend.model_id,
                    loaded=True,
                )
                return False
            self._sync_health_from_backend(warmup_ok=True)
            return True

    # -- inference ---------------------------------------------------------
    def _ensure_backend(self) -> BrainBackend:
        if self._backend is None:
            if not self.prepare():
                raise RuntimeError("Brain backend is not available (see /health)")
        return self._backend  # type: ignore[return-value]

    def chat(
        self,
        messages: list[dict],
        configuration: BrainGenerationConfig | None = None,
    ) -> BrainResult:
        """Generate a chat completion (blocks; called via asyncio.to_thread)."""
        backend = self._ensure_backend()
        cfg = configuration or BrainGenerationConfig(
            model=backend.model_id or self.config.model
        )
        return backend.generate(messages, cfg)

    def stream(
        self,
        messages: list[dict],
        configuration: BrainGenerationConfig | None = None,
    ):
        """Yield OpenAI-style chunk dicts token-by-token (spec Part O).

        Requires a backend that advertises ``stream_support``; otherwise the
        server uses the single-content-chunk fallback.  Returns a *synchronous*
        generator that the server bridges to async via ``asyncio.to_thread``.
        """
        backend = self._ensure_backend()
        cfg = configuration or BrainGenerationConfig(
            model=backend.model_id or self.config.model
        )
        if not getattr(backend, "stream_support", False):
            raise RuntimeError("Brain backend does not support streaming")
        return backend.stream(messages, cfg)

    def warmup(self, prompt: str) -> str:
        backend = self._ensure_backend()
        return backend.warmup(prompt)

    # -- introspection -----------------------------------------------------
    def model_info(self) -> dict:
        entry = self.catalog.lookup(self.config.model)
        backend = self._backend
        return {
            "model_id": self.config.model,
            "full_id": entry.full_id if entry else self.config.model,
            "repository": entry.repository if entry else BRAIN_MODEL_LINEAGE.get(
                self.config.model, {}
            ).get("repository", ""),
            "revision": (backend.revision if backend else "") or (
                entry.revision if entry else ""
            ),
            "architecture": entry.architecture if entry else "Qwen3ForCausalLM",
            "parameters": (backend.parameters if backend else 0) or (
                entry.parameter_count if entry else 0
            ),
            "context_length": entry.context_length if entry else 40960,
            "vocab_size": entry.vocab_size if entry else 151936,
            "capabilities": entry.capabilities if entry else ["text-generation", "chat"],
            "status": entry.status if entry else "experimental",
            "training_method": entry.training_method if entry else "base",
        }

    def shutdown(self) -> None:
        with self._lock:
            backend = self._backend
            if backend is not None:
                try:
                    backend.close()
                finally:
                    self._backend = None
            self._started = False

    # -- health helpers ----------------------------------------------------
    def _sync_health_from_backend(self, *, warmup_ok: bool = False) -> None:
        backend = self._backend
        is_stub = self.config.is_stub
        is_remote = self.config.is_remote
        state = BrainHealthState.HEALTHY
        if is_stub:
            state = BrainHealthState.STUB
        # The provider/model reported are the ones actually serving inference
        # (spec sections 14-15): a remote NVIDIA backend reports the upstream
        # provider + model id, never the stub-era registry id.
        if self.config.is_nvidia:
            provider = "nvidia"
        elif self.config.is_huggingface:
            provider = "hf-inference"
        elif is_remote:
            provider = self.config.remote_provider
        elif is_stub:
            provider = "stub"
        else:
            provider = "local"
        h = BrainHealthStatus(
            status=state,
            model=backend.model_id if backend else self.config.model,
            revision=backend.revision if backend else "",
            loaded=True,
            device=backend.device if backend else "cpu",
            backend=backend.backend if backend else "",
            provider=provider,
            parameters=backend.parameters if backend else 0,
            warmup_ok=warmup_ok or is_stub,
            stub=is_stub,
            available=bool(backend is not None and not is_stub),
            authorized=bool(self.config.api_key),
            production_health=bool(backend is not None and not is_stub),
            # Honest capability flags for the control plane / manifest.
            stream_support=bool(getattr(backend, "stream_support", False)),
        )
        self.health.set(h)


def _import_stub_backend(model_id: str, revision: str) -> BrainBackend:
    from brain_runtime.backends.stub import StubBackend

    return StubBackend(model_id=model_id, revision=revision)


def _import_remote_backend(config: "BrainConfig") -> BrainBackend:
    """Lazy import keeps httpx out of the test import graph."""
    from brain_runtime.backends.remote import RemoteBrainBackend

    return RemoteBrainBackend(
        endpoint=config.remote_endpoint,
        api_key=config.remote_api_key,
        model=config.remote_model or config.model,
        timeout=config.remote_timeout,
        retries=config.remote_retries,
    )


def _import_nvidia_backend(config: "BrainConfig") -> BrainBackend:
    """Lazy import keeps httpx out of the test import graph."""
    from brain_runtime.backends.nvidia_backend import NvidiaBrainBackend

    return NvidiaBrainBackend(
        endpoint=config.remote_endpoint or config.nvidia_endpoint,
        api_key=config.remote_api_key or config.nvidia_api_key,
        model=config.remote_model or config.nvidia_model,
        timeout=config.remote_timeout,
        retries=config.remote_retries,
    )


def _import_huggingface_backend(config: "BrainConfig") -> BrainBackend:
    """Lazy import keeps httpx out of the test import graph."""
    from brain_runtime.backends.huggingface_backend import HuggingFaceBrainBackend

    return HuggingFaceBrainBackend(
        endpoint=config.huggingface_endpoint or config.remote_endpoint,
        api_key=config.huggingface_api_key or config.remote_api_key,
        model=config.huggingface_model or config.remote_model or config.model,
        timeout=config.remote_timeout,
        retries=config.remote_retries,
    )


def _import_transformers_backend(
    catalog: BrainCatalog, model_id: str, device: str, cache: str, local_files_only: bool = False
) -> BrainBackend:
    """Lazy import keeps torch/transformers out of the test import graph."""
    from brain_runtime.backends.transformers_backend import TransformersBackend

    return TransformersBackend(
        model_catalog=catalog, model_id=model_id, device=device,
        model_cache=cache, local_files_only=local_files_only,
    )
