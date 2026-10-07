"""Provider registry for the JARVIS Provider Fabric (spec §10, §15, §67).

Holds every registered :class:`ProviderAdapter`, answers capability queries, and
takes health snapshots across providers so the Provider Center / router can reason
about what is actually available instead of assuming.
"""

from __future__ import annotations

import threading
from typing import Optional

from .base import ProviderAdapter
from .capabilities import Capability
from .health import ProviderHealth
from .models import PrivacyClass, ProviderModel


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}
        self._lock = threading.Lock()

    def register(self, adapter: ProviderAdapter, *, replace: bool = False) -> ProviderAdapter:
        if not adapter.provider_id:
            raise ValueError("adapter has no provider_id")
        with self._lock:
            existing = self._adapters.get(adapter.provider_id)
            if existing is not None and existing is not adapter and not replace:
                raise ValueError(
                    f"provider {adapter.provider_id!r} already registered "
                    f"(registering a second adapter for the same provider would "
                    f"make routing ambiguous)"
                )
            self._adapters[adapter.provider_id] = adapter
        return adapter

    def get(self, provider_id: str) -> Optional[ProviderAdapter]:
        return self._adapters.get(provider_id)

    def providers(self) -> list[ProviderAdapter]:
        with self._lock:
            return list(self._adapters.values())

    def provider_ids(self) -> list[str]:
        return sorted(self._adapters.keys())

    def by_capability(self, capability: Capability) -> list[ProviderAdapter]:
        return [a for a in self.providers() if a.supports(capability)]

    def configured(self) -> list[ProviderAdapter]:
        return [a for a in self.providers() if a.configured]

    def all_capabilities(self) -> list[str]:
        caps: set[str] = set()
        for adapter in self.providers():
            caps.update(c.value for c in adapter.declared_capabilities)
        return sorted(caps)

    def catalog(self) -> list[ProviderModel]:
        models: list[ProviderModel] = []
        for adapter in self.providers():
            models.extend(adapter.models)
        return models

    def health_snapshot(self, force: bool = False) -> dict[str, ProviderHealth]:
        return {a.provider_id: a.health(force=force) for a in self.providers()}

    def health_summary(self, force: bool = False) -> list[dict]:
        return [h.to_dict() for h in self.health_snapshot(force=force).values()]

    def providers_matching(
        self,
        *,
        capabilities: Optional[frozenset[Capability]] = None,
        privacy: Optional[PrivacyClass] = None,
        configured: bool = True,
    ) -> list[ProviderAdapter]:
        result = self.configured() if configured else self.providers()
        if capabilities:
            result = [a for a in result if all(a.supports(c) for c in capabilities)]
        if privacy is not None:
            result = [a for a in result if _privacy_allows(a, privacy)]
        return result


def _privacy_allows(adapter: ProviderAdapter, required: PrivacyClass) -> bool:
    """A provider is allowed only if its *most capable* declared privacy allows it.

    LOCAL_ONLY work may only use local deployments; PUBLIC work may use anything;
    INTERNAL/PRIVATE/SENSITIVE may not use LOCAL_ONLY-only or lowest-trust models
    unless the model privacy declaration permits.
    """
    models = adapter.models
    if not models:  # unknown privacy -> stay strict
        return required is not PrivacyClass.LOCAL_ONLY
    worst = PrivacyClass.SENSITIVE
    order = [PrivacyClass.PUBLIC, PrivacyClass.INTERNAL, PrivacyClass.PRIVATE,
             PrivacyClass.SENSITIVE, PrivacyClass.LOCAL_ONLY]
    rank = {p: i for i, p in enumerate(order)}
    for model in models:
        p = model.privacy_class
        if rank.get(p, 0) > rank.get(worst, 0):
            worst = p
    if required is PrivacyClass.LOCAL_ONLY:
        return worst is PrivacyClass.LOCAL_ONLY
    # required INTERNAL/PRIVATE/SENSITIVE: model worst-privacy must be <= required
    return rank.get(worst, 0) <= rank.get(required, 0)


_default_registry: ProviderRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ProviderRegistry:
    global _default_registry
    with _registry_lock:
        if _default_registry is None:
            _default_registry = ProviderRegistry()
        return _default_registry


def reset_registry(registry: ProviderRegistry | None = None) -> ProviderRegistry:
    global _default_registry
    with _registry_lock:
        _default_registry = registry if registry is not None else ProviderRegistry()
        return _default_registry