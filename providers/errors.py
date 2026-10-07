"""Error hierarchy for the JARVIS Provider Fabric.

Deliberately small and explicit: every failure mode the fabric can hit has a
typed exception so routing/telemetry can classify errors without string matching.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all provider fabric errors."""


class UnsupportedCapability(ProviderError):
    """The provider does not implement the requested capability.

    Raised instead of pretending: this is the "never pretend a provider supports
    something it does not" rule (spec §3).
    """

    def __init__(self, provider: str, capability: str, detail: str = "") -> None:
        self.provider = provider
        self.capability = capability
        msg = f"provider {provider!r} does not support capability {capability!r}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class ProviderUnconfigured(ProviderError):
    """No credentials/endpoint are configured for this provider (it is not usable)."""


class ProviderUnavailable(ProviderError):
    """The provider is reachable but did not answer health/requests successfully."""


class ProviderAuthenticationError(ProviderError):
    """Provider rejected the credentials (401/403 family)."""


class ProviderTimeout(ProviderError):
    """A provider request exceeded its timeout."""


class ProviderContractError(ProviderError):
    """Provider returned something structurally unexpected (malformed JSON etc.)."""


class SecretLeakError(ProviderError):
    """A secret value was found inside outbound model context; request refused."""