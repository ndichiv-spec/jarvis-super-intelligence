"""Provider Connection Center (spec §15/§38).

Provides a single admin-facing surface to inspect and manage every provider
connection — OpenAI, NVIDIA, Google, AWS, Hugging Face, GitHub, Microsoft —
without ever exposing credentials.

Each connection exposes one of:
  * ``connected``    — credential is present AND the provider health-checks OK
  * ``not_connected``— no credential is configured
  * ``expired``      — OAuth token is present but expired
  * ``error``        — credential present but health check reports a fault
  * ``testing``      — a test is in progress

Actions: Connect, Test, Disconnect, Rotate, Revoke.

The center wraps the existing :mod:`providers` fabric (``bootstrap_fabric``,
``SecretManager``, ``ProviderRegistry``) for API-key providers, and the
:mod:`identity` OAuth layer for OIDC-based identity-provider connections.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .models import ConnectionStatus, ProviderConnection


# Mapping: provider_id -> (secret_env_name, display_name, identity_provider?)
_PROVIDER_META: dict[str, tuple[str, str, bool]] = {
    "openai":   ("JARVIS_OPENAI_API_KEY",   "OpenAI",              False),
    "nvidia":   ("JARVIS_NVIDIA_API_KEY",   "NVIDIA NIM",          False),
    "google":   ("JARVIS_GOOGLE_API_KEY",   "Google Vertex/Gemini", False),
    "aws":      ("AWS_ACCESS_KEY_ID",       "AWS Bedrock",          False),
    "hf":       ("JARVIS_HF_TOKEN",         "Hugging Face",         False),
    # Identity-provider connections (OAuth-based, not inference providers).
    "github":   ("JARVIS_OAUTH_GITHUB_CLIENT_ID", "GitHub",        True),
    "microsoft":("JARVIS_OAUTH_MICROSOFT_CLIENT_ID", "Microsoft",   True),
}


class ProviderConnectionManager:
    """Inspects and manages provider connections using the fabric + identity layer.

    Parameters
    ----------
    secrets
        The :class:`~providers.secrets.SecretManager` (or compatible) used to
        check whether a credential is present.  The manager never returns raw
        secret values — only ``configured`` booleans and health snapshots.
    registry
        Optional pre-built :class:`~providers.registry.ProviderRegistry`.  When
        ``None``, the connection center reports ``configured`` based on the
        SecretManager alone (no model discovery / health probing).
    """

    def __init__(
        self,
        secrets: Any,
        registry: Optional[Any] = None,
        *,
        link_store: Optional[Any] = None,
    ) -> None:
        self._secrets = secrets
        self._registry = registry
        self._link_store = link_store  # for identity provider connection status
        self._testing: set[str] = set()

    # ------------------------------------------------------------------ #
    # Catalog
    # ------------------------------------------------------------------ #
    def provider_ids(self) -> list[str]:
        """All provider IDs the center knows about."""
        return list(_PROVIDER_META.keys())

    # ------------------------------------------------------------------ #
    # Connection status (spec §15 — never expose credentials)
    # ------------------------------------------------------------------ #
    def status(self, provider_id: str) -> ProviderConnection:
        """Return the runtime :class:`ProviderConnection` for a provider."""
        meta = _PROVIDER_META.get(provider_id)
        if meta is None:
            return ProviderConnection(
                provider_id=provider_id,
                display_name=provider_id,
                connected=False,
                status=ConnectionStatus.NOT_CONNECTED,
                detail="unknown provider",
            )
        secret_name, display_name, is_identity = meta
        configured = bool(self._secrets.get(secret_name))

        if provider_id in self._testing:
            return ProviderConnection(
                provider_id=provider_id,
                display_name=display_name,
                connected=False,
                status=ConnectionStatus.TESTING,
                detail="test in progress",
                configured=configured,
            )

        if not configured:
            return ProviderConnection(
                provider_id=provider_id,
                display_name=display_name,
                connected=False,
                status=ConnectionStatus.NOT_CONNECTED,
                detail=secret_name.replace("JARVIS_", "").replace("_", " ").lower()
                + " not set",
                configured=False,
            )

        # Credential is present — probe health via the registry if available.
        if self._registry is not None:
            adapter = self._registry.get(provider_id)
            if adapter is not None and adapter.configured:
                health = adapter.health(force=False)
                from providers.health import HealthStatus

                if health.status is HealthStatus.HEALTHY:
                    capability_ids = [c.value for c in adapter.declared_capabilities]
                    return ProviderConnection(
                        provider_id=provider_id,
                        display_name=display_name,
                        connected=True,
                        status=ConnectionStatus.CONNECTED,
                        capabilities=capability_ids,
                        model_count=len(adapter.models),
                        detail="healthy" if not health.detail else health.detail,
                        last_tested=health.checked_at_iso
                        if hasattr(health, "checked_at_iso")
                        else None,
                        configured=True,
                    )
                elif health.status is provider_health_unconfigured():
                    return ProviderConnection(
                        provider_id=provider_id,
                        display_name=display_name,
                        connected=False,
                        status=ConnectionStatus.NOT_CONNECTED,
                        detail="configured but health check unconfigured",
                        configured=True,
                    )
                else:
                    return ProviderConnection(
                        provider_id=provider_id,
                        display_name=display_name,
                        connected=False,
                        status=ConnectionStatus.ERROR,
                        detail=health.detail or health.status.value,
                        configured=True,
                    )

        # No registry (identity providers) — check link store for expiry.
        if is_identity and self._link_store is not None:
            links = self._load_links()
            any_link = any(
                l.get("provider") == provider_id for l in links
            )
            if any_link:
                return ProviderConnection(
                    provider_id=provider_id,
                    display_name=display_name,
                    connected=True,
                    status=ConnectionStatus.CONNECTED,
                    detail="OAuth connection present",
                    configured=True,
                )
            # Client ID is set but no OAuth callback completed.
            return ProviderConnection(
                provider_id=provider_id,
                display_name=display_name,
                connected=False,
                status=ConnectionStatus.NOT_CONNECTED,
                detail="client registered, no OAuth callback completed",
                configured=True,
            )

        # Credential present but no registry — assume connected at config level.
        return ProviderConnection(
            provider_id=provider_id,
            display_name=display_name,
            connected=True,
            status=ConnectionStatus.CONNECTED,
            detail="configured (health probe requires fabric registry)",
            configured=True,
        )

    def all_status(self) -> list[ProviderConnection]:
        """Status of every known provider (spec §38 — Provider Center view)."""
        return [self.status(pid) for pid in self.provider_ids()]

    def all_status_safe(self) -> list[dict[str, Any]]:
        """Safe-to-serialize view: no secrets, no token references."""
        out = []
        for conn in self.all_status():
            out.append(
                {
                    "provider": conn.provider_id,
                    "display_name": conn.display_name,
                    "connected": conn.connected,
                    "status": conn.status.value,
                    "capabilities": conn.capabilities,
                    "model_count": conn.model_count,
                    "detail": conn.detail,
                    "last_tested": conn.last_tested,
                    "expires_at": conn.expires_at,
                    "configured": conn.configured,
                }
            )
        return out

    def credential_refs(self) -> list[dict[str, Any]]:
        """List credential references without exposing secret values.

        For each known provider this reports whether the backing env var /
        vault key is present and from where the credential is sourced.
        The **raw secret value is never returned** — callers (frontend,
        audit logs, diagnostics) only ever see ``status: "set"|"unset"``.
        """
        out: list[dict[str, Any]] = []
        for pid, (secret_name, display_name, is_identity) in _PROVIDER_META.items():
            configured = bool(self._secrets.get(secret_name))
            source = "vault"
            if hasattr(self._secrets, "has_vault") and not self._secrets.has_vault():
                source = "env"
            if self._secrets.get(secret_name, default=None) is None and configured:
                source = "override"
            out.append(
                {
                    "provider": pid,
                    "display_name": display_name,
                    "key": secret_name,
                    "label": display_name,
                    "status": "set" if configured else "unset",
                    "source": source,
                    "identity_provider": is_identity,
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Actions (spec §15)
    # ------------------------------------------------------------------ #
    def test(self, provider_id: str) -> dict[str, Any]:
        """Run a health check on a provider.  Returns a result dict."""
        self._testing.add(provider_id)
        try:
            # Temporarily clear the TESTING flag so _probe gets a real status.
            self._testing.discard(provider_id)
            conn = self._probe(provider_id)
        finally:
            self._testing.discard(provider_id)
        return {
            "provider": provider_id,
            "status": conn.status.value,
            "connected": conn.connected,
            "detail": conn.detail,
            "timestamp": time.time(),
        }

    def _probe(self, provider_id: str) -> ProviderConnection:
        """Force a fresh health probe through the registry."""
        if self._registry is None:
            return self.status(provider_id)
        adapter = self._registry.get(provider_id)
        if adapter is None:
            return self.status(provider_id)
        adapter.health(force=True)
        return self.status(provider_id)

    def disconnect(self, provider_id: str) -> dict[str, Any]:
        """Disconnect a provider (clear the credential, revoke OAuth if linked).

        For API-key providers this clears the key from the SecretManager
        overrides.  For identity providers, it removes the OAuth link.
        """
        meta = _PROVIDER_META.get(provider_id)
        if meta is None:
            return {"provider": provider_id, "ok": False, "error": "unknown provider"}
        secret_name, _, is_identity = meta

        if not is_identity and self._secrets is not None:
            # Set an override to empty string to shadow the env value.
            # (We never mutate env / .env; overrides are the SecretManager's
            #  own per-process mechanism.)
            if hasattr(self._secrets, "set_override"):
                self._secrets.set_override(secret_name, "")
            elif hasattr(self._secrets, "_overrides"):
                self._secrets._overrides[secret_name] = ""

        if is_identity and self._link_store is not None:
            links = self._load_links()
            to_remove = [
                k for k, v in links.items() if v.get("provider") == provider_id
            ]
            for k in to_remove:
                del links[k]
            self._save_links(links)

        return {
            "provider": provider_id,
            "ok": True,
            "action": "disconnected",
            "timestamp": time.time(),
        }

    def rotate(self, provider_id: str) -> dict[str, Any]:
        """Mark a provider credential for rotation.

        In a full implementation this would trigger a credential-rotation
        workflow via the SecretManager vault.  Here it records the intent and
        returns the vault key name to update.
        """
        meta = _PROVIDER_META.get(provider_id)
        if meta is None:
            return {"provider": provider_id, "ok": False, "error": "unknown provider"}
        secret_name, _, _ = meta
        return {
            "provider": provider_id,
            "ok": True,
            "action": "rotate",
            "vault_key": secret_name,
            "detail": "submit a new credential value via the secret vault",
            "timestamp": time.time(),
        }

    def revoke(self, provider_id: str) -> dict[str, Any]:
        """Revoke an OAuth identity-provider connection (no-op for API-key providers)."""
        meta = _PROVIDER_META.get(provider_id)
        if meta is None:
            return {"provider": provider_id, "ok": False, "error": "unknown provider"}
        _, _, is_identity = meta
        if not is_identity:
            return {"provider": provider_id, "ok": False, "error": "revoke requires an OAuth connection"}
        return self.disconnect(provider_id)

    # ------------------------------------------------------------------ #
    # Link store helpers (for identity providers)
    # ------------------------------------------------------------------ #
    def _load_links(self) -> dict[str, dict]:
        if self._link_store is None:
            return {}
        return self._link_store.load()

    def _save_links(self, links: dict[str, dict]) -> None:
        if self._link_store is None:
            return
        # Replace all links
        current = self._link_store.load()
        current.clear()
        current.update(links)
        self._link_store.save()


def provider_health_unconfigured() -> Any:
    """Resolve the HealthStatus.UNCONFIGURED enum value lazily."""
    from providers.health import HealthStatus

    return HealthStatus.UNCONFIGURED
