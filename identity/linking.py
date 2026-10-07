"""Account linking for OIDC identity providers (spec §53/§17).

Uses account linking rather than creating duplicate users per provider.  When
a user signs in with Google, Microsoft, or GitHub, we either:

  * attach that provider identity to an *existing* JARVIS user (if the email
    matches), or
  * create a new JARVIS local account and link the provider identity to it.

Provider tokens are NOT stored here — only an opaque reference to the vault
key name.  The actual token lives in :class:`~providers.secrets.SecretManager`.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional


class AccountLinker:
    """Links OIDC provider identities to local JARVIS user accounts.

    Parameters
    ----------
    store
        Pluggable dict-like store with ``load()`` / ``save()`` methods that
        round-trip ``{key: dict}``.  The backend injects its SQL KV store;
        tests use an in-memory dict store.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    # The store is keyed by account-link records; we use a composite key.
    _COLLECTION = "account_links"

    def _all(self) -> dict[str, dict]:
        return self._store.load()

    def _save(self) -> None:
        self._store.save()

    @staticmethod
    def _composite_key(provider: str, provider_user_id: str) -> str:
        """Stable composite key: ``<provider>:<sha256(sub)>``."""
        digest = hashlib.sha256(
            f"{provider}:{provider_user_id}".encode("utf-8")
        ).hexdigest()[:32]
        return f"{provider}:{digest}"

    # ------------------------------------------------------------------ #
    # Linking operations
    # ------------------------------------------------------------------ #
    def link(
        self,
        jarvis_user_id: str,
        provider: str,
        provider_user_id: str,
        email: Optional[str] = None,
        token_vault_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """Link a provider identity to an existing JARVIS user.

        If a link already exists, it is updated (last-seen refresh).
        """
        from .models import AccountLink

        key = self._composite_key(provider, provider_user_id)
        links = self._all()
        now = self._iso_now()
        record = links.get(key)
        if record is None:
            record = {
                "id": str(uuid.uuid4()),
                "provider": provider,
                "provider_user_id": provider_user_id,
                "jarvis_user_id": jarvis_user_id,
                "email": email,
                "created_at": now,
            }
        record["last_seen_at"] = now
        record["access_token_ref"] = token_vault_ref
        links[key] = record
        self._save()
        return record

    def find_by_provider(self, provider: str, provider_user_id: str) -> Optional[dict]:
        """Look up the JARVIS user linked to a provider identity."""
        key = self._composite_key(provider, provider_user_id)
        return self._all().get(key)

    def find_by_email(self, email: str) -> Optional[dict]:
        """Find any existing link whose stored email matches (for dedup)."""
        norm = (email or "").lower().strip()
        if not norm:
            return None
        for rec in self._all().values():
            if (rec.get("email") or "").lower() == norm:
                return rec
        return None

    def unlink(self, provider: str, provider_user_id: str) -> bool:
        """Remove a provider link.  The JARVIS user is NOT deleted."""
        key = self._composite_key(provider, provider_user_id)
        links = self._all()
        if key in links:
            del links[key]
            self._save()
            return True
        return False

    def links_for_user(self, jarvis_user_id: str) -> list[dict[str, Any]]:
        """All provider identities linked to a JARVIS user (spec §53)."""
        result = []
        for rec in self._all().values():
            if rec.get("jarvis_user_id") == jarvis_user_id:
                result.append(self._safe(rec))
        return result

    # ------------------------------------------------------------------ #
    # Resolution strategy (spec §53 — account linking, not duplication)
    # ------------------------------------------------------------------ #
    def resolve_or_create(
        self,
        provider: str,
        userinfo: Any,
        user_store: Any,
        create_user_fn: Optional[callable] = None,
    ) -> tuple[dict[str, Any], bool]:
        """Resolve a provider login to a JARVIS user.

        Returns ``(user_record, created)``.  If no link or matching email exists,
        a new local account is created (if ``create_user_fn`` is provided) and
        the provider is linked to it.

        Parameters
        ----------
        provider
            IdentityProvider value, e.g. ``"google"``.
        userinfo
            :class:`OidcUserInfo` (or duck-typed object with ``sub``,
            ``email``, ``display_name``).
        user_store
            The user store (with ``load()``/``save()``), used for email lookup.
        create_user_fn
            Optional factory ``(email, name, provider) -> dict`` that creates a
            local user record.  If ``None`` and no match is found, raises
            ``ValueError``.
        """
        sub = getattr(userinfo, "sub", "")
        email = getattr(userinfo, "email", None)

        # 1. Direct link by (provider, sub) — preferred.
        existing = self.find_by_provider(provider, sub)
        if existing:
            users = user_store.load()
            user = users.get(existing["jarvis_user_id"])
            if user:
                return user, False

        # 2. Email match — link to existing local account.
        #    Search both the link store (existing provider→user link) and
        #    the user store (existing local account with same email).
        if email:
            email_link = self.find_by_email(email)
            if email_link:
                users = user_store.load()
                user = users.get(email_link["jarvis_user_id"])
                if user:
                    self.link(
                        user["id"], provider, sub, email=email,
                    )
                    return user, False
            # Also check the user store directly (a local user may exist
            # whose email was set before any provider link was created).
            users = user_store.load()
            for uid, u in users.items():
                if isinstance(u, dict) and (u.get("email") or "").lower() == email.lower():
                    self.link(uid, provider, sub, email=email)
                    return u, False

        # 3. Create a new local account.
        if create_user_fn is None:
            raise ValueError(
                f"no existing JARVIS account for provider '{provider}' identity "
                f"and no auto-create callback supplied"
            )
        user = create_user_fn(
            email=email or f"{sub}@{provider}.local",
            name=userinfo.display_name if hasattr(userinfo, "display_name") else str(sub),
            provider=provider,
        )
        users = user_store.load()
        users[user["id"]] = user
        if hasattr(user_store, "save"):
            user_store.save()
        self.link(
            user["id"],
            provider,
            sub,
            email=email,
        )
        return user, True

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe(rec: dict[str, Any]) -> dict[str, Any]:
        """Return a copy with token references stripped (never expose refs)."""
        out = {k: v for k, v in rec.items() if k not in ("access_token_ref", "refresh_token_ref")}
        out["connected"] = True  # a link record existing means connected
        out["provider"] = rec.get("provider", "")
        out["email"] = rec.get("email")
        return out

    @staticmethod
    def _iso_now() -> str:
        import datetime as _dt

        return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
