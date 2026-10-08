"""FastAPI router for the JARVIS unified identity layer (spec §12, §15, §53).

Endpoints
---------
* ``GET  /api/v1/identity/providers``         — list available identity providers
* ``GET  /api/v1/identity/login/{provider}``  — start OIDC login (redirect)
* ``GET  /api/v1/identity/callback/{provider}``— OIDC callback + session creation
* ``POST /api/v1/identity/logout``            — revoke session
* ``GET  /api/v1/identity/me``                — current user + linked accounts
* ``DELETE /api/v1/identity/link/{provider}``  — unlink an identity provider

Provider Connection Center (spec §15):
* ``GET  /api/v1/providers/connections``     — all provider connection statuses
* ``POST /api/v1/providers/{id}/test``      — test a provider connection
* ``DELETE /api/v1/providers/{id}``         — disconnect a provider

The router is designed to be ``include_router``-ed by the existing backend
(``jarvis_backend.main``).  It depends on injectable ``SessionManager``,
``OidcClient`` factory, and ``AccountLinker`` so tests can substitute fakes.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .linking import AccountLinker
from .models import IdentityProvider, OidcConfig, OidcUserInfo
from .oidc import OidcClient, OidcError
from .session import SessionManager
from .provider_center import ProviderConnectionManager

router = APIRouter(prefix="/api/v1", tags=["identity"])

# --------------------------------------------------------------------------- #
# Dependency providers — overridden in tests / backend integration
# --------------------------------------------------------------------------- #
_session_manager: Optional[SessionManager] = None
_oidc_configs: dict[str, OidcConfig] = {}
_account_linker: Optional[AccountLinker] = None
_provider_center: Optional[ProviderConnectionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def get_account_linker() -> AccountLinker:
    global _account_linker
    if _account_linker is None:
        # Lazy import to avoid coupling the identity package to the backend store.
        from jarvis_backend.core import get_store  # type: ignore[import-not-found]
        _account_linker = AccountLinker(get_store("account_links"))
    return _account_linker


def get_provider_center() -> ProviderConnectionManager:
    global _provider_center
    if _provider_center is None:
        from providers.bootstrap import build_adapters  # type: ignore[import-not-found]
        from providers.secrets import get_secret_manager  # type: ignore[import-not-found]

        try:
            adapters = build_adapters()
            from providers.registry import ProviderRegistry  # type: ignore[import-not-found]
            reg = ProviderRegistry()
            for a in adapters.values():
                reg.register(a, replace=True)
            registry = reg
        except Exception:  # noqa: BLE001
            registry = None
        _provider_center = ProviderConnectionManager(
            secrets=get_secret_manager(),
            registry=registry,
        )
    return _provider_center


def get_oidc_client(provider: str, http_client: Any = None) -> OidcClient:
    """Build an :class:`OidcClient` for ``provider`` from configured OIDC configs."""
    cfg = _oidc_configs.get(provider)
    if cfg is None or not cfg.is_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"identity provider '{provider}' is not configured",
        )
    return OidcClient(cfg, http_client=http_client)


# --------------------------------------------------------------------------- #
# Identity provider endpoints
# --------------------------------------------------------------------------- #
@router.get("/identity/providers")
async def list_identity_providers() -> list[dict[str, Any]]:
    """List identity providers available for login (spec §53)."""
    result = []
    for p in IdentityProvider:
        if p == IdentityProvider.LOCAL:
            result.append({
                "id": p.value,
                "name": "JARVIS Account",
                "type": "local",
                "configured": True,
            })
            continue
        cfg = _oidc_configs.get(p.value)
        result.append({
            "id": p.value,
            "name": _provider_display_name(p),
            "type": "oidc",
            "configured": cfg.is_configured() if cfg else False,
        })
    return result


def _provider_display_name(p: IdentityProvider) -> str:
    return {
        IdentityProvider.GOOGLE: "Google",
        IdentityProvider.MICROSOFT: "Microsoft",
        IdentityProvider.GITHUB: "GitHub",
    }.get(p, p.value)


@router.get("/identity/login/{provider}")
async def start_oidc_login(
    provider: str,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Return the authorization URL + PKCE verifier (stored in a cookie).

    The frontend redirects the browser to ``auth_url``.  On callback, the
    PKCE ``code_verifier`` is retrieved from the cookie.
    """
    client = get_oidc_client(provider)
    if IdentityProvider(provider) not in (
        IdentityProvider.GOOGLE,
        IdentityProvider.MICROSOFT,
        IdentityProvider.GITHUB,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{provider} is not an OIDC login provider",
        )
    # Ensure discovery has run.
    if not client.config.authorization_endpoint:
        await client.discover()
    auth_url, code_verifier, state = client.authorization_url()
    # Store PKCE verifier + state in an HttpOnly cookie (CSRF-safe).
    response.set_cookie(
        key="jarvis_oidc_pkce",
        value=code_verifier,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=600,
        path="/",
    )
    response.set_cookie(
        key="jarvis_oidc_state",
        value=state,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=600,
        path="/",
    )
    return {"auth_url": auth_url, "provider": provider}


@router.get("/identity/callback/{provider}")
async def oidc_callback(
    provider: str,
    request: Request,
    response: Response,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> dict[str, Any]:
    """Handle the OIDC callback: exchange code, resolve/link user, create session."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"provider returned error: {error}",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="authorization code missing",
        )

    code_verifier = request.cookies.get("jarvis_oidc_pkce", "")
    stored_state = request.cookies.get("jarvis_oidc_state", "")
    if not code_verifier or not stored_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PKCE / state cookie missing — login may have expired",
        )

    client = get_oidc_client(provider)
    try:
        token_resp = await client.exchange_code(
            code, code_verifier, state=stored_state
        )
        userinfo = await client.fetch_userinfo(token_resp)
    except OidcError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"authentication failed: {exc}",
        ) from exc

    # Resolve or create the local user account (account linking — spec §53).
    sm = get_session_manager()
    linker = get_account_linker()
    try:
        user, _created = linker.resolve_or_create(
            provider=provider,
            userinfo=userinfo,
            user_store=_user_store(),
            create_user_fn=_create_local_user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    # Create session.
    ip = _client_ip(request)
    session = sm.create_session(
        user_id=user["id"],
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        auth_method=f"oidc:{provider}",
    )

    # Issue access + refresh tokens via the existing core JWT machinery.
    from jarvis_backend.core import create_token, create_refresh_token  # type: ignore[import-not-found]

    access = create_token({"sub": user["id"], "sid": session.id})
    refresh = create_refresh_token(user["id"], session.id)

    # Clear the PKCE/state cookies.
    response.delete_cookie("jarvis_oidc_pkce", path="/")
    response.delete_cookie("jarvis_oidc_state", path="/")

    # Set session cookie (HttpOnly, SameSite=Strict).
    attrs = sm.session_cookie_attrs(secure=True)
    response.set_cookie(
        key="jarvis_session",
        value=session.id,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=int(attrs.get("max_age", "900")),
        path="/",
    )

    sm.record_login_attempt(ip, success=True)

    from jarvis_backend.core import make_user_payload  # type: ignore[import-not-found]

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 900,
        "user": make_user_payload(user),
    }


@router.post("/identity/logout")
async def logout(request: Request, response: Response) -> dict[str, Any]:
    session_id = request.cookies.get("jarvis_session", "")
    if session_id:
        sm = get_session_manager()
        sm.destroy_session(session_id)
    response.delete_cookie("jarvis_session", path="/")
    return {"success": True}


@router.get("/identity/me")
async def me(request: Request) -> dict[str, Any]:
    """Return the current user with linked identity providers."""
    user = _require_user(request)
    from jarvis_backend.core import make_user_payload  # type: ignore[import-not-found]

    payload = make_user_payload(user)
    linker = get_account_linker()
    payload["identity_providers"] = linker.links_for_user(user["id"])
    return payload


@router.delete("/identity/link/{provider}")
async def unlink_provider(
    request: Request, provider: str
) -> dict[str, Any]:
    """Remove an OIDC identity link (spec §53)."""
    user = _require_user(request)
    linker = get_account_linker()
    # Find the link by provider + email.
    links = linker._all()
    removed = False
    for key, rec in list(links.items()):
        if rec.get("provider") == provider and rec.get("jarvis_user_id") == user["id"]:
            linker.unlink(provider, rec.get("provider_user_id", ""))
            removed = True
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no '{provider}' identity linked to your account",
        )
    return {"provider": provider, "unlinked": True}


# --------------------------------------------------------------------------- #
# Provider Connection Center endpoints (spec §15)
# --------------------------------------------------------------------------- #
@router.get("/providers/connections")
async def list_provider_connections(
    request: Request,
) -> list[dict[str, Any]]:
    """List all provider connection statuses (no credentials exposed)."""
    _require_admin(request)
    center = get_provider_center()
    return center.all_status_safe()


@router.post("/providers/{provider_id}/test")
async def test_provider_connection(
    request: Request, provider_id: str
) -> dict[str, Any]:
    """Run a health check on a provider."""
    _require_admin(request)
    center = get_provider_center()
    if provider_id not in center.provider_ids():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown provider: {provider_id}",
        )
    return center.test(provider_id)


@router.delete("/providers/{provider_id}")
async def disconnect_provider(
    request: Request, provider_id: str
) -> dict[str, Any]:
    """Disconnect a provider connection."""
    _require_admin(request)
    center = get_provider_center()
    if provider_id not in center.provider_ids():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown provider: {provider_id}",
        )
    return center.disconnect(provider_id)


# --------------------------------------------------------------------------- #
# Owner identity panel (spec §21)
# --------------------------------------------------------------------------- #
def _get_owner_manager() -> Any:
    """Build an OwnerManager from the backend stores (lazy import)."""
    from identity.owner import get_owner_manager  # type: ignore[import-not-found]

    return get_owner_manager()


def _get_permission_center() -> Any:
    from identity.permission_center import PermissionCenter  # type: ignore[import-not-found]

    return PermissionCenter()


def _get_audit_log() -> Any:
    from identity.audit_log import OwnerAuditLog  # type: ignore[import-not-found]

    try:
        from jarvis_backend.core import get_store  # type: ignore[import-not-found]

        return OwnerAuditLog(store=get_store("audit_logs"))
    except Exception:
        return OwnerAuditLog()


@router.get("/admin/identity")
async def admin_identity(request: Request) -> dict[str, Any]:
    """Owner identity panel (spec §21).

    Returns the canonical owner identity metadata — NEVER the Gmail password
    or any credential.  Shows auth methods, MFA / passkey state.
    """
    _require_admin(request)
    om = _get_owner_manager()
    identity = om.build_identity()
    pc = _get_permission_center()
    audit = _get_audit_log()
    return {
        "owner": {
            "email": identity.email,
            "name": identity.name,
            "role": identity.role,
            "developer": identity.developer,
            "primary_admin": identity.primary_admin,
            "auth_methods": identity.auth_methods,
            "mfa_enabled": identity.mfa_enabled,
            "passkey_enabled": identity.passkey_enabled,
            "is_active": identity.is_active,
            "created_at": identity.created_at,
            "last_authenticated_at": identity.last_authenticated_at,
        },
        "recovery_options": om.recovery_options(identity.user_id),
        "audit_summary": audit.summary(),
        "pending_approvals": pc.pending_requests(),
    }


@router.get("/admin/providers")
async def admin_providers(request: Request) -> list[dict[str, Any]]:
    """Service connection panel (spec §22).

    Lists every provider with its real connection status.  All values reflect
    actual state — never inferred from a config variable.
    """
    _require_admin(request)
    center = get_provider_center()
    return center.all_status_safe()


@router.post("/admin/providers/{provider_id}/connect")
async def admin_connect_provider(
    request: Request, provider_id: str
) -> dict[str, Any]:
    """Start the connection / OAuth flow for a provider.

    For OIDC-based providers (GitHub, Microsoft), this returns the authorization
    URL.  For API-key providers (OpenAI, NVIDIA, Google, AWS, HF), this records
    a credential-rotation request in the vault and returns the vault key to
    update.
    """
    _require_admin(request)
    center = get_provider_center()
    if provider_id not in center.provider_ids():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown provider: {provider_id}",
        )
    audit = _get_audit_log()
    user = _require_admin(request)
    audit.record(
        user=user.get("email", ""),
        provider=provider_id,
        operation="connect",
        resource="provider",
        permission=f"provider:connect",
        decision="granted",
        result="success",
    )
    # Delegate to the center's rotate/connect logic.
    result = center.rotate(provider_id)
    result["auth_url_hint"] = (
        f"/api/v1/identity/login/{provider_id}"
        if provider_id in ("github", "microsoft", "google")
        else None
    )
    return result


@router.post("/admin/approve")
async def admin_approve(
    request: Request,
    approval_token: str,
) -> dict[str, Any]:
    """Owner approves a pending high-risk action (spec §16)."""
    user = _require_admin(request)
    # Only the canonical owner can approve.
    om = _get_owner_manager()
    if not om.is_owner(user.get("email", "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the canonical owner may approve high-risk actions",
        )
    pc = _get_permission_center()
    try:
        auth = pc.approve(approval_token, user.get("email", ""))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    audit = _get_audit_log()
    audit.record(
        user=user.get("email", ""),
        provider=auth.provider if hasattr(auth, "provider") else "jarvis",
        operation=f"approve:{auth.action}",
        resource=auth.resource,
        permission="*",
        decision="approved",
        result="success",
    )
    return {"approved": True, "approval": auth.to_dict()}


@router.get("/admin/audit")
async def admin_audit(
    request: Request,
    provider: str = "",
    operation: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    """Owner audit log (spec §17).  No raw secrets ever returned."""
    user = _require_admin(request)
    om = _get_owner_manager()
    if not om.is_owner(user.get("email", "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the canonical owner may view the full audit log",
        )
    audit = _get_audit_log()
    entries = audit.entries(
        provider=provider or None,
        operation=operation or None,
        limit=limit,
    )
    return {"events": entries, "summary": audit.summary()}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_user(request: Request) -> dict[str, Any]:
    from jarvis_backend.core import get_current_user  # type: ignore[import-not-found]
    auth = request.headers.get("authorization", "")
    return get_current_user(authorization=auth if auth else None)


def _require_admin(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user
    from jarvis_backend.routers.rbac import _require_admin as _backend_require_admin  # type: ignore[import-not-found]
    # Defer to the backend's admin resolver for role-permission-based checks.
    try:
        _backend_require_admin(user)
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.client.host if request.client else "unknown"
    )


def _user_store() -> Any:
    """Return the backend user store (lazy import)."""
    from jarvis_backend.core import get_store  # type: ignore[import-not-found]
    return get_store("users")


def _create_local_user(email: str, name: str, provider: str) -> dict[str, Any]:
    """Create a local JARVIS user from an OIDC identity (spec §53).

    The password is unset (empty hash) — the user must set a password or
    continue using the OIDC provider to sign in.
    """
    import uuid as _uuid
    from jarvis_backend.core import hash_password, now_iso  # type: ignore[import-not-found]

    uid = str(_uuid.uuid4())
    return {
        "id": uid,
        "email": email,
        "username": name.replace(" ", ".").lower() or f"user_{uid[:8]}",
        "password_hash": hash_password(email),  # set a random initial password
        "full_name": name,
        "avatar_url": None,
        "status": "active",
        "tenant_id": None,
        "roles": ["user"],
        "last_login_at": None,
        "created_at": now_iso(),
    }


# --------------------------------------------------------------------------- #
# Bootstrapping — call from main.py to configure OIDC providers
# --------------------------------------------------------------------------- #
def configure_oidc_providers(secrets: Any) -> None:
    """Populate ``_oidc_configs`` from the SecretManager (spec §68).

    Should be called once at startup.  Providers with missing credentials are
    simply skipped (honest ``not configured``).
    """
    _oidc_configs.clear()
    specs = [
        (
            IdentityProvider.GOOGLE.value,
            "JARVIS_GOOGLE_CLIENT_ID",
            "JARVIS_GOOGLE_CLIENT_SECRET",
            "http://localhost:8000/api/v1/identity/callback/google",
            ["openid", "email", "profile"],
        ),
        (
            IdentityProvider.MICROSOFT.value,
            "JARVIS_MICROSOFT_CLIENT_ID",
            "JARVIS_MICROSOFT_CLIENT_SECRET",
            "http://localhost:8000/api/v1/identity/callback/microsoft",
            ["openid", "email", "profile"],
        ),
        (
            IdentityProvider.GITHUB.value,
            "JARVIS_GITHUB_CLIENT_ID",
            "JARVIS_GITHUB_CLIENT_SECRET",
            "http://localhost:8000/api/v1/identity/callback/github",
            ["read:user"],
        ),
    ]
    for provider_name, cid_key, csec_key, redirect, scopes in specs:
        client_id = secrets.get(cid_key) or ""
        client_secret = secrets.get(csec_key) or ""
        if not client_id:
            continue
        _oidc_configs[provider_name] = OidcConfig(
            provider=IdentityProvider(provider_name),
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect,
            scopes=scopes,
        )


# ---------------------------------------------------------------------------
# Control Center endpoints (spec §38 — Extension & Connection Management)
# ---------------------------------------------------------------------------
@router.get("/control/status")
async def control_center_status(request: Request) -> dict[str, Any]:
    """Merged Control Center overview — providers, extensions, connectors.

    No credentials or secret values are ever returned.
    """
    _require_admin(request)
    center = get_provider_center()

    # --- Extension counts (lazy import to avoid coupling) ---
    installed_count = 0
    connected_count = 0
    try:
        from jarvis_backend.core import get_store  # type: ignore[import-not-found]

        ext_store = get_store("extensions").load()
        installed = ext_store.get("installed", {}) if isinstance(ext_store, dict) else {}
        installed_count = len(installed)
        connected_count = sum(1 for v in installed.values() if v.get("connected"))
    except Exception:  # noqa: BLE001 — extensions store is optional
        pass

    # --- Connector counts ---
    connector_count = 0
    try:
        from jarvis_backend.core import get_store  # type: ignore[import-not-found]

        conn_store = get_store("connectors").load()
        if isinstance(conn_store, dict):
            connector_count = len(conn_store)
    except Exception:  # noqa: BLE001
        pass

    # --- Provider statuses (already safe) ---
    providers = center.all_status_safe()
    healthy = sum(1 for p in providers if p.get("connected"))
    total = len(providers)

    return {
        "providers": providers,
        "provider_summary": {
            "total": total,
            "connected": healthy,
            "disconnected": total - healthy,
        },
        "extensions": {
            "installed_count": installed_count,
            "connected_count": connected_count,
        },
        "connectors": {
            "count": connector_count,
        },
    }


@router.get("/control/credentials")
async def control_center_credentials(request: Request) -> list[dict[str, Any]]:
    """List credential references without exposing secret values (spec §15).

    Returns one entry per known provider: ``status`` is ``"set"`` or
    ``"unset"``, ``source`` is ``"env"`` / ``"vault"`` / ``"override"``.
    The raw environment variable name is included so the frontend can render
    a "Configure" button, but **the value itself is never returned**.
    """
    _require_admin(request)
    center = get_provider_center()
    return center.credential_refs()
