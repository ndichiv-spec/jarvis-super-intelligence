"""Inference service.

Implements the runtime-side ``generate`` / ``chat`` entry points against a
pluggable :class:`InferenceBackend`.

Production default is :class:`TorchBackend` (``SILVERWING_BACKEND=torch``) —
real weights, loaded once and reused.  ``EchoBackend`` activates ONLY via
``SILVERWING_BACKEND=echo`` (tests/development); it is never used as a silent
fallback when the torch backend fails (sections 16).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from silverwing_runtime.backends import EchoBackend, InferenceBackend, TorchBackend
from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.generation import (
    ChatMessage,
    ChatResult,
    GenerationConfig,
    GenerationRequest,
    GenerationResult,
)
from silverwing_runtime.generation import (
    chat as build_chat,
)
from silverwing_runtime.health import HealthMonitor, HealthState, HealthStatus
from silverwing_runtime.model_loader import LoadedModel, ModelLoader

log = logging.getLogger("silverwing_runtime.inference")


class InferenceService:
    """Runtime service: load, warmup, serve, report health.

    Constructor follows the startup flow (spec section 12): query registry,
    locate model, verify hash, load model, run warmup inference, expose health.
    """

    def __init__(
        self,
        loader: ModelLoader,
        config: RuntimeConfig | None = None,
        health: HealthMonitor | None = None,
        backend_factory: Any | None = None,
    ):
        self.loader = loader
        self.config = config or RuntimeConfig()
        self.health = health or HealthMonitor()
        self._loaded: dict[str, LoadedModel] = {}
        self._backends: dict[str, InferenceBackend] = {}
        # backend_factory(model: LoadedModel, cfg) -> InferenceBackend
        self._backend_factory = backend_factory or self._default_backend

    # -- startup ----------------------------------------------------------
    def load_model(self, model_ref: str) -> LoadedModel:
        self.health.transition(HealthState.LOADING, model=model_ref)
        try:
            loaded = self.loader.load(model_ref)
        except Exception as exc:
            self.health.transition(
                HealthState.ERROR,
                detail=f"load failed: {exc}",
                model=model_ref,
            )
            raise
        self._loaded[loaded.full_id] = loaded
        return loaded

    def _default_backend(self, loaded: LoadedModel) -> InferenceBackend:
        """Torch by default; echo ONLY on explicit ``SILVERWING_BACKEND=echo``.

        A torch load failure surfaces as an error (health -> error/unhealthy);
        there is no silent EchoBackend fallback.
        """
        if self.config.backend.lower() == "echo":
            log.info("SILVERWING_BACKEND=echo -> EchoBackend (dev/test only)")
            return EchoBackend(marker="sw-echo")
        log.info("SILVERWING_BACKEND default -> TorchBackend for %s", loaded.full_id)
        return TorchBackend(loaded, self.config)

    def warmup(self, model_ref: str) -> str:
        """Run one warmup inference; called before reporting healthy."""
        loaded = self._loaded.get(model_ref) or self.load_model(model_ref)
        backend = self._backends.get(loaded.full_id)
        if backend is None:
            backend = self._backend_factory(loaded)
            self._backends[loaded.full_id] = backend
        self.health.transition(
            HealthState.WARMUP,
            model=loaded.full_id,
            revision=loaded.entry.revision,
            loaded=True,
            device=getattr(backend, "device", ""),
            backend=getattr(backend, "backend", ""),
            parameters=loaded.entry.parameter_count,
            warmup_ok=False,
        )
        try:
            result = backend.warmup(self.config.warmup_prompt)
        except Exception as exc:
            self.health.transition(
                HealthState.ERROR,
                detail=f"warmup failed: {exc}",
                model=loaded.full_id,
                revision=loaded.entry.revision,
                loaded=False,
                backend=getattr(backend, "backend", ""),
                warmup_ok=False,
            )
            raise
        self.health.transition(
            HealthState.HEALTHY,
            model=loaded.full_id,
            revision=loaded.entry.revision,
            loaded=True,
            device=getattr(backend, "device", ""),
            backend=getattr(backend, "backend", ""),
            parameters=loaded.entry.parameter_count,
            warmup_ok=bool(result),
            detail=None,
        )
        self.loader.registry.mark_deployed(
            loaded.full_id,
            endpoint=self.config.registry_path.name,
            device=getattr(backend, "device", ""),
            loaded=True,
            healthy=True,
        )
        return result

    # -- serving ----------------------------------------------------------
    def _backend_for(self, model_ref: str) -> tuple[InferenceBackend, LoadedModel]:
        loaded = self._loaded.get(model_ref) or self.load_model(model_ref)
        backend = self._backends.get(loaded.full_id)
        if backend is None:
            backend = self._backend_factory(loaded)
            self._backends[loaded.full_id] = backend
        return backend, loaded

    async def generate(
        self, request: GenerationRequest, model_ref: str | None = None
    ) -> GenerationResult:
        ref = model_ref or self._default_ref()
        return await asyncio.to_thread(self._generate_sync, request, ref)

    def _generate_sync(self, request: GenerationRequest, ref: str) -> GenerationResult:
        backend, loaded = self._backend_for(ref)
        start = time.monotonic()
        try:
            result = backend.generate(request)
        except Exception:
            self.health.transition(
                HealthState.ERROR,
                detail="generation failed",
                model=loaded.full_id,
                loaded=True,
                warmup_ok=True,
            )
            raise
        result.model = result.model or loaded.full_id or ref
        result.revision = result.revision or loaded.entry.revision
        result.latency_ms = round((time.monotonic() - start) * 1000, 2)
        return result

    async def chat(
        self,
        messages: list[dict[str, str]],
        generation_config: GenerationConfig | None = None,
        tools: list[dict[str, Any]] | None = None,
        memory: dict[str, Any] | None = None,
        model_ref: str | None = None,
    ) -> ChatResult:
        payload = build_chat(messages, generation_config, tools, memory)
        req = GenerationRequest(prompt=payload["prompt"], config=generation_config)
        res = await self.generate(req, model_ref=model_ref)
        return ChatResult(
            message=ChatMessage(role="assistant", content=res.text),
            finish_reason=res.finish_reason,
            model=res.model,
            revision=res.revision,
            latency_ms=res.latency_ms,
            usage={
                "input_tokens": res.tokens_input,
                "output_tokens": res.tokens_generated,
                "total_tokens": res.tokens_input + res.tokens_generated,
            },
            metadata={**res.metadata, "tools": tools or [], "memory": bool(memory)},
        )

    def _default_ref(self) -> str:
        entries = [e for e in self.loader.registry.list_models() if e.status not in ("archived",)]
        if not entries:
            raise KeyError("no models registered; cannot infer default model")
        # Prefer a model whose weights are stored locally (offline-loadable)
        # so the runtime never defaults to a remote-only manifest (e.g. a
        # staged config with no local weights) that fails to load at request
        # time and returns 500. Falls back to the full registry order when
        # nothing is stored locally.
        local = [e for e in entries if e.storage_uri.startswith("local://")]
        pool = local or entries
        return sorted(pool, key=lambda e: e.version, reverse=True)[0].full_id

    def shutdown(self) -> None:
        for backend in self._backends.values():
            with contextlib.suppress(Exception):
                backend.close()
        self._backends.clear()

    async def health_status(self) -> HealthStatus:
        return self.health.current()