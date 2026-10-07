"""Capability-aware Brain backend routing (spec Part F).

The Brain runtime is a *runtime boundary* (Part C): it must not be hard-wired
to a single provider.  :class:`BrainRouter` inspects the configured Brain
backends — in a fixed priority order — health-gates each one with a real
load + warmup probe (never a fabricated heartbeat), and selects the first
healthy candidate.  Selection is logged so a platform operator can see
*why* a given backend was chosen (or skipped).

Priority (best-quality first, honesty-ordered):

    nvidia -> huggingface -> remote(openai-compatible) -> local(transformers) -> stub/offline

Notes
-----
* The router is *opt-in*.  ``BrainService`` runs in ``"strict"`` mode by
  default (the single configured backend), which preserves the existing
  single-backend contract.  ``"priority"`` mode engages this router so the
  runtime can fall across providers when credentials overlap.
* ``stub`` is never selected as a production backend by default: it is only
  returned when explicitly the configured backend (``JARVIS_BRAIN_BACKEND=stub``)
  and flagged ``stub=True`` by the caller (see :class:`BrainHealthStatus`).
* The platform gateway (``jarvis_backend.gateway.ProviderGateway``) owns the
  brain <-> Silverwing fallback; this router only selects among *Brain*
  backends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("brain_runtime.routing")


@dataclass
class RouteDecision:
    """Outcome of attempting one candidate backend."""

    name: str
    provider: str
    model: str
    configured: bool
    healthy: bool
    reason: str = ""
    error: str = ""


class BrainRouter:
    """Select a healthy Brain backend from the configured candidates.

    Pass ``candidates`` to override the default priority-ordered set (used by
    tests).  When omitted, candidates are derived from ``config``: each named
    backend is *configured* only when its credential + endpoint are present so
    the router never probes a credential it does not have (honesty, spec §13).
    """

    def __init__(
        self,
        config,
        catalog=None,
        *,
        candidates: list[tuple[str, Callable, bool]] | None = None,
    ) -> None:
        self.config = config
        self.catalog = catalog
        self._candidates = candidates or self._default_candidates(config, catalog)

    @staticmethod
    def _default_candidates(config, catalog) -> list[tuple[str, Callable, bool]]:
        """Build (name, build_callable, configured) in priority order."""
        # Lazy imports keep torch/transformers out of the test import graph.

        def _nvidia():
            from brain_runtime.backends.nvidia_backend import NvidiaBrainBackend

            return NvidiaBrainBackend(
                endpoint=config.remote_endpoint or config.nvidia_endpoint,
                api_key=config.remote_api_key or config.nvidia_api_key,
                model=config.remote_model or config.nvidia_model,
                timeout=config.remote_timeout,
                retries=config.remote_retries,
            )

        def _hf():
            from brain_runtime.backends.huggingface_backend import HuggingFaceBrainBackend

            return HuggingFaceBrainBackend(
                endpoint=config.huggingface_endpoint,
                api_key=config.huggingface_api_key,
                model=config.huggingface_model,
                timeout=config.remote_timeout,
                retries=config.remote_retries,
            )

        def _remote():
            from brain_runtime.backends.remote import RemoteBrainBackend

            return RemoteBrainBackend(
                endpoint=config.remote_endpoint,
                api_key=config.remote_api_key,
                model=config.remote_model or config.model,
                timeout=config.remote_timeout,
                retries=config.remote_retries,
            )

        def _local():
            from brain_runtime.service import _import_transformers_backend

            return _import_transformers_backend(
                catalog,
                config.model,
                config.device,
                str(config.model_cache),
                local_files_only=config.local_files_only,
            )

        def _stub():
            from brain_runtime.backends.stub import StubBackend

            entry = catalog.lookup(config.model) if catalog is not None else None
            revision = entry.revision if entry else "stub"
            return StubBackend(model_id=config.model, revision=revision)

        return [
            ("nvidia", _nvidia, config.is_nvidia and bool(config.nvidia_api_key)),
            ("huggingface", _hf, config.is_huggingface and bool(config.huggingface_api_key)),
            ("remote", _remote, config.is_remote and bool(config.remote_endpoint) and bool(config.remote_api_key)),
            ("local", _local, config.is_local),
            ("stub", _stub, config.is_stub),
        ]

    def select(self, warmup_prompt: str = "The capital of France is") -> tuple[object | None, str]:
        """Return ``(backend, reason)`` for the first healthy configured
        candidate, else ``(None, reason)``.

        Each candidate is probed with a real ``load()`` + ``warmup()``; a
        failure records the reason and falls through to the next candidate
        (never fabricates success).
        """
        for name, build, configured in self._candidates:
            if not configured:
                log.info("brain-router: skip %s (not configured)", name)
                continue
            try:
                backend = build()
                backend.load()
                backend.warmup(warmup_prompt)
            except Exception as exc:  # noqa: BLE001 - honest probe failure
                log.warning(
                    "brain-router: %s unavailable (%s): %s",
                    name,
                    type(exc).__name__,
                    getattr(exc, "safe_message", str(exc))[:120],
                )
                continue
            provider = getattr(backend, "provider", "") or name
            model = getattr(backend, "model_id", "") or self.config.model
            log.info(
                "brain-router: selected %s (provider=%s, model=%s)",
                name,
                provider,
                model,
            )
            return backend, f"selected:{name}"
        return None, "no healthy configured backend"

    # Convenience for the service health monitor / diagnostics.
    def candidate_names(self) -> list[str]:
        return [name for name, _, configured in self._candidates if configured]
