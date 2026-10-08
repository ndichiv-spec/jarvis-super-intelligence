"""Provider fabric bootstrap — constructs and registers all adapters.

Spec §10/§67: the fabric starts with an empty :class:`~providers.registry.ProviderRegistry`.
This module is the factory that reads provider credentials via
:class:`~providers.secrets.SecretManager` (never raw env vars, never the model
context), constructs each :class:`~providers.base.ProviderAdapter`, and registers
it into the shared :func:`~providers.registry.get_registry`.

Each adapter is constructed even when unconfigured — the adapter then honestly
reports ``configured=False`` / health ``unconfigured`` rather than crashing.
This guarantees the registry *always* reflects reality: "no provider" is never
pretended to be "a provider that works".

Usage::

    from providers.bootstrap import bootstrap_fabric
    registry = bootstrap_fabric()          # reads env + .env
    router = ProviderRouter(registry)
    decision = router.route_text("research...")

    # or inject a custom SecretManager (for tests / vault-backed mode)
    from providers.secrets import SecretManager
    registry = bootstrap_fabric(secrets=SecretManager(...))
"""

from __future__ import annotations

import logging
from typing import Optional

from .secrets import SecretManager, get_secret_manager
from .registry import ProviderRegistry, get_registry

log = logging.getLogger("providers.bootstrap")


def bootstrap_fabric(
    registry: Optional[ProviderRegistry] = None,
    secrets: Optional[SecretManager] = None,
    *,
    register: bool = True,
) -> ProviderRegistry:
    """Build and (optionally) register all provider adapters from the environment.

    Parameters
    ----------
    registry
        Target registry. Defaults to the shared :func:`get_registry` singleton.
    secrets
        Secret manager for credential resolution. Defaults to
        :func:`get_secret_manager`. Tests may inject a pre-populated
        ``SecretManager(overrides=...)`` to control which adapters are
        configured without touching env vars.
    register
        When ``True`` (default), each constructed adapter is registered into
        ``registry``. When ``False``, adapters are built but not registered
        (useful for unit-testing construction).

    Returns
    -------
    ProviderRegistry
        The registry with adapters registered (if ``register=True``).
    """
    sm = secrets or get_secret_manager()
    registry = registry or get_registry()

    # Import lazily so the fabric stays import-safe (SDKs are optional).
    # Each adapter module is self-contained; a missing optional SDK does not
    # prevent construction — the adapter simply reports ``configured=False``.
    from .openai.client import OpenAIAdapter
    from .nvidia.client import NvidiaAdapter
    from .google.client import GoogleAdapter
    from .aws.client import AwsBedrockAdapter
    from .huggingface.client import HuggingFaceAdapter

    adapters = [
        OpenAIAdapter(secrets=sm),
        NvidiaAdapter(secrets=sm),
        GoogleAdapter(secrets=sm),
        AwsBedrockAdapter(secrets=sm),
        HuggingFaceAdapter(secrets=sm),
    ]

    for adapter in adapters:
        try:
            if register:
                registry.register(adapter, replace=True)
            log.debug(
                "provider %s configured=%s models=%d",
                adapter.provider_id, adapter.configured, len(adapter.models),
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("failed to register %s: %s", adapter.provider_id, exc)

    return registry


def build_adapters(
    secrets: Optional[SecretManager] = None,
) -> dict[str, "object"]:
    """Construct all adapters without registering them (for tests).

    Returns a dict keyed by ``provider_id``. Useful when callers want to
    inspect individual adapter state (capabilities, health, configured) without
    touching the shared registry singleton.
    """
    sm = secrets or get_secret_manager()
    from .openai.client import OpenAIAdapter
    from .nvidia.client import NvidiaAdapter
    from .google.client import GoogleAdapter
    from .aws.client import AwsBedrockAdapter
    from .huggingface.client import HuggingFaceAdapter

    all_adapters = [
        OpenAIAdapter(secrets=sm),
        NvidiaAdapter(secrets=sm),
        GoogleAdapter(secrets=sm),
        AwsBedrockAdapter(secrets=sm),
        HuggingFaceAdapter(secrets=sm),
    ]
    return {adapter.provider_id: adapter for adapter in all_adapters}


def fabric_status(secrets: Optional[SecretManager] = None) -> dict:
    """Return a provider-id -> configured bool snapshot (no secrets exposed)."""
    adapters = build_adapters(secrets=secrets)
    return {
        provider_id: {
            "provider": adapter.provider_id,
            "display_name": adapter.display_name,
            "configured": adapter.configured,
            "capabilities": [c.value for c in adapter.declared_capabilities],
            "model_count": len(adapter.models),
        }
        for provider_id, adapter in adapters.items()
    }
