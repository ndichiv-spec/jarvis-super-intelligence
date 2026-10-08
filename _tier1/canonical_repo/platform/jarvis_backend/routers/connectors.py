"""Connectors API (admin-managed external integrations, spec design 2026-09-12).

Email (IMAP+SMTP) is shipped first.  Every mutate endpoint requires a logged-in
user that holds the admin role ("*" permission) or an explicit connectors
permission; every action endpoint requires authentication and is audited.

Policy is disclose-and-prove, not claim-and-pretend:
  * GET returns credentials masked (never echoed)
  * a masked value in a PATCH is treated as "keep", never a real secret
  * /test runs a live IMAP login + SMTP EHLO and reports the failure honestly
  * the AI receives a plain refusal when the connector is unconfigured,
    disabled, or missing a capability.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..core import get_current_user, now_iso
from ..connectors import registry
from ..connectors import oauth as oauth_store
from ..connectors.base import EMAIL_CAPABILITIES
from ..connectors.dispatch import connector_class, execute_connector_action, list_connectors
from ..connectors.github import GitHubApiError, GitHubClient

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])

_ALLOWED_TIMEOUT_PORTS = {"imap": [143, 993], "smtp": [25, 465, 587, 2525]}
_CONNECTOR_KINDS = {"email", "calendar", "files"}

# Connector kinds whose credentials come from an OAuth 2.0 flow (Gmail/Outlook).
# These are configured via /oauth/authorize + /oauth/callback rather than the
# IMAP/password form; their tokens are stored encrypted by connectors.oauth and
# never exposed through the API.
_OAUTH_KINDS = {"gmail", "outlook", "github"}


def _oauth_status(kind: str, raw) -> Optional[Dict[str, Any]]:
    """Safe-to-return OAuth connection profile (no token is ever exposed)."""
    uid = (raw or {}).get("oauth_user_id")
    if not uid or kind not in _OAUTH_KINDS:
        return None
    return oauth_store.connection_metadata(kind, uid)


def _require_admin(user: Dict[str, Any]) -> Dict[str, Any]:
    """Reject unless the user holds the admin role or a connectors permission.

    User roles are stored as role *names* (strings).  Resolve those against the
    roles store so role objects can carry ``*`` / ``connectors:*`` permissions.
    """
    names = [r for r in (user.get("roles") or []) if isinstance(r, str)]
    if "admin" in names or user.get("is_admin"):
        return user

    role_names = set(names)
    try:
        from ..core import get_store

        roles = get_store("roles").load()
    except Exception:  # noqa: BLE001
        roles = {}
    for role in roles.values():
        if role.get("name") not in role_names and role.get("id") not in role_names:
            continue
        perms = role.get("permissions") or []
        if "*" in perms or any(str(p).startswith("connectors:") for p in perms):
            return user
    raise HTTPException(status_code=403, detail="Admin access required for connector management")


class ConnectorIn(BaseModel):
    provider: str = "Other"
    imap_host: str = ""
    imap_port: int = Field(993, ge=1, le=65535)
    imap_ssl: bool = True
    imap_user: str = ""
    password: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(587, ge=1, le=65535)
    smtp_starttls: bool = True
    send_from: str = ""
    capabilities: List[str] = Field(default_factory=lambda: list(EMAIL_CAPABILITIES))
    enabled: bool = True


class ConnectorPatchIn(BaseModel):
    provider: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = Field(None, ge=1, le=65535)
    imap_ssl: Optional[bool] = None
    imap_user: Optional[str] = None
    password: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_starttls: Optional[bool] = None
    send_from: Optional[str] = None
    capabilities: Optional[List[str]] = None
    enabled: Optional[bool] = None


class ActionIn(BaseModel):
    action: str = "email.folders"
    params: Dict[str, Any] = Field(default_factory=dict)


def _clean_patch(existing: Dict[str, Any], patch: ConnectorPatchIn) -> Dict[str, Any]:
    base = dict(existing)

    if patch.provider is not None:
        base["provider"] = patch.provider
    if patch.imap_host is not None:
        base["imap_host"] = patch.imap_host.strip()
    if patch.imap_port is not None:
        base["imap_port"] = patch.imap_port
    if patch.imap_ssl is not None:
        base["imap_ssl"] = patch.imap_ssl
    if patch.imap_user is not None:
        base["imap_user"] = patch.imap_user.strip()
    if patch.smtp_host is not None:
        base["smtp_host"] = patch.smtp_host.strip()
    if patch.smtp_port is not None:
        base["smtp_port"] = patch.smtp_port
    if patch.smtp_starttls is not None:
        base["smtp_starttls"] = patch.smtp_starttls
    if patch.send_from is not None:
        base["send_from"] = patch.send_from.strip()
    if patch.enabled is not None:
        base["enabled"] = patch.enabled
    if patch.capabilities is not None:
        cls = connector_class(base.get("kind", "email"))
        possible = cls.possible_capabilities if cls else []
        base["capabilities"] = [c for c in patch.capabilities if c in possible]

    # password semantics: masked or empty -> keep existing; fresh non-masked -> replace
    if patch.password is not None:
        pwd = patch.password.strip()
        if pwd and pwd != registry.MASK:
            base["password"] = pwd
    return base


@router.get("")
async def get_connectors():
    connectors = list_connectors()
    configured = [c for c in connectors if c.get("configured")]
    return {"connectors": connectors, "count": len(configured)}


@router.get("/activity")
async def connector_activity(limit: int = Query(50)):
    entries = registry.read_audit(limit)
    return {"entries": entries, "total": len(entries)}


def _github_user_id(user: Dict[str, Any]) -> str:
    return str(user.get("id") or user.get("email") or "")


def _github_audit(user: Dict[str, Any], operation: str, ok: bool, detail: str = "") -> None:
    oauth_store.audit_record(
        actor=str(user.get("username") or user.get("email") or "user"),
        kind="github",
        operation=operation,
        ok=ok,
        user_id=_github_user_id(user),
        detail=detail,
    )


def _github_http_error(error: GitHubApiError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/github/connection")
async def github_connection(user: Dict[str, Any] = Depends(get_current_user)):
    """Return safe, user-scoped GitHub authorization metadata only."""
    metadata = oauth_store.connection_metadata("github", _github_user_id(user))
    scopes = metadata.get("scope")
    return {
        "provider": "GitHub",
        "connected": metadata.get("connected", False),
        "status": metadata.get("status", "Authorization required"),
        "account": metadata.get("account"),
        "scopes": [scope for scope in scopes.replace(",", " ").split() if scope] if isinstance(scopes, str) else [],
        "expires_at": metadata.get("token_expires_at"),
        "capabilities": ["Repository.Read"] if metadata.get("connected") else [],
    }


@router.post("/github/test")
async def github_test(user: Dict[str, Any] = Depends(get_current_user)):
    try:
        account = await GitHubClient(_github_user_id(user)).user()
    except GitHubApiError as exc:
        _github_audit(user, "connection.test", False, str(exc.detail.get("code", "GitHub test failed")))
        raise _github_http_error(exc) from exc
    _github_audit(user, "connection.test", True, "GitHub account endpoint verified")
    tokens = oauth_store.load_tokens("github", _github_user_id(user))
    if tokens:
        tokens["account"] = account["login"]
        oauth_store.save_tokens("github", _github_user_id(user), tokens)
    return {"ok": True, "status": "CONNECTED", "account": account}


@router.get("/github/repositories")
async def github_repositories(
    page: int = Query(default=1, ge=1, le=10000),
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        result = await GitHubClient(_github_user_id(user)).repositories(page)
    except GitHubApiError as exc:
        _github_audit(user, "repository.list", False, str(exc.detail.get("code", "GitHub request failed")))
        raise _github_http_error(exc) from exc
    _github_audit(user, "repository.list", True, f"page={page}")
    return result


@router.get("/github/repositories/{owner}/{repository}")
async def github_repository(
    owner: str,
    repository: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        result = await GitHubClient(_github_user_id(user)).repository(owner, repository)
    except GitHubApiError as exc:
        _github_audit(user, "repository.read", False, str(exc.detail.get("code", "GitHub request failed")))
        raise _github_http_error(exc) from exc
    _github_audit(user, "repository.read", True, f"{owner}/{repository}")
    return result


@router.get("/github/repositories/{owner}/{repository}/contents")
async def github_file(
    owner: str,
    repository: str,
    path: str = Query(min_length=1, max_length=1024),
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        result = await GitHubClient(_github_user_id(user)).file(owner, repository, path)
    except GitHubApiError as exc:
        _github_audit(user, "repository.file.read", False, str(exc.detail.get("code", "GitHub request failed")))
        raise _github_http_error(exc) from exc
    _github_audit(user, "repository.file.read", True, f"{owner}/{repository}:{path}")
    return result


@router.delete("/github/connection")
async def github_disconnect(user: Dict[str, Any] = Depends(get_current_user)):
    removed = oauth_store.delete_tokens("github", _github_user_id(user))
    _github_audit(user, "connection.disconnect", True, "OAuth token removed" if removed else "No token was stored")
    return {"disconnected": removed}


@router.get("/{kind}")
async def get_connector(kind: str):
    cls = connector_class(kind)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector kind: {kind}")
    raw = registry.load(kind)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Connector '{kind}' is not configured")
    return {
        "kind": kind,
        "label": cls.label,
        "possible_capabilities": cls.possible_capabilities,
        "actions": [a.__dict__ for a in cls.actions],
        "config": registry.public_config(raw),
        "connection_status": _oauth_status(kind, raw),
    }


@router.post("/{kind}/oauth/authorize")
async def oauth_authorize(
    kind: str,
    body: Optional[Dict[str, Any]] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Start an OAuth 2.0 flow for a connector (Gmail/Outlook, spec §7/#8).

    Admin-gated.  Returns the provider's authorize URL; the developer's browser
    is then redirected through the provider's consent screen and back to the
    (unauthenticated) callback below, which exchanges the code server-side and
    stores the encrypted token.
    """
    if kind in {"gmail", "outlook"}:
        _require_admin(user)
    cls = connector_class(kind)
    if kind not in _OAUTH_KINDS or (cls is None and kind != "github"):
        raise HTTPException(status_code=404, detail=f"No OAuth connector registered for kind '{kind}'")
    cfg = oauth_store.client_config(kind)
    if not cfg:
        raise HTTPException(
            status_code=409,
            detail=(f"No OAuth client is configured for '{kind}'. Register "
                    "JARVIS_OAUTH_CLIENTS (e.g. JARVIS_OAUTH_GOOGLE_*) in start_all.ps1/.env."),
        )
    scope = (body or {}).get("scope") or cfg.get("scope")
    user_id = _github_user_id(user) if kind == "github" else str(user.get("id") or "")
    url = oauth_store.authorize_url(kind, user_id, scope=scope)
    oauth_store.audit_record(
        actor=user.get("username") or "admin", kind=kind, operation="authorize",
        ok=True, user_id=user_id, detail="redirect to provider consent")
    return {"authorize_url": url, "kind": kind}


@router.get("/oauth/callback/{kind}")
async def oauth_callback(kind: str, code: str = "", state: str = "",
                         error: Optional[str] = None):
    """Provider redirect target for the OAuth 2.0 code exchange.

    Public GET (the provider cannot carry our session cookie).  Security comes
    from the HMAC-bound ``state`` token, which encodes ``(kind, user_id, ts)``
    and is validated here.  Tokens are exchanged + encrypted server-side via
    connectors.oauth, then the connector config is written with a read-only
    capability set and a live read-only health probe.
    """
    if kind not in _OAUTH_KINDS:
        raise HTTPException(status_code=404, detail=f"No OAuth callback for kind '{kind}'")
    if error:
        oauth_store.audit_record(actor="oauth-callback", kind=kind,
                                 operation="consent_denied", ok=False, detail=error)
        if kind == "github":
            from urllib.parse import urlencode

            app_url = os.environ.get("JARVIS_APP_URL", "http://127.0.0.1:3000").rstrip("/")
            return RedirectResponse(
                url=f"{app_url}/dashboard/connections?{urlencode({'github_error': error})}",
                status_code=303,
            )
        return {"ok": False, "error": error or "access_denied"}
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")

    # state encodes the user_id that initiated the flow (verified server-side).
    try:
        cfg = oauth_store.client_config(kind)
        if not cfg:
            raise oauth_store.OAuthError("no client configured")
        # We need the user_id from state; verify_state returns (kind, uid).
        _, uid = oauth_store.verify_state(state)
    except oauth_store.OAuthError as exc:
        oauth_store.audit_record(actor="oauth-callback", kind=kind,
                                 operation="callback", ok=False, detail=str(exc))
        return {"ok": False, "error": str(exc)}

    try:
        tokens = oauth_store.exchange_code(kind, code, state, uid)
    except oauth_store.OAuthError as exc:
        oauth_store.audit_record(actor="oauth-callback", kind=kind, uid=uid,
                                 operation="exchange", ok=False, detail=str(exc))
        return {"ok": False, "error": str(exc)}

    if kind == "github":
        verified = False
        try:
            account = await GitHubClient(uid).user()
            tokens["account"] = account["login"]
            oauth_store.save_tokens(kind, uid, tokens)
            verified = True
        except GitHubApiError as exc:
            oauth_store.audit_record(
                actor="oauth-callback",
                kind=kind,
                operation="verify",
                ok=False,
                user_id=uid,
                detail=str(exc.detail.get("code", "GitHub account verification failed")),
            )
        if verified:
            oauth_store.audit_record(
                actor="oauth-callback",
                kind=kind,
                operation="connected",
                ok=True,
                user_id=uid,
                detail="GitHub account endpoint verified",
            )
        app_url = os.environ.get("JARVIS_APP_URL", "http://127.0.0.1:3000").rstrip("/")
        suffix = "?connected=github&verified=1" if verified else "?connected=github&verified=0"
        return RedirectResponse(url=f"{app_url}/dashboard/connections{suffix}", status_code=303)

    # Persist connector config (READ-only first, per §7/#8 smallest scope).
    # NOTE: the access/refresh tokens are NOT stored in the connector config —
    # they live only in the encrypted oauth_tokens vault (connectors.oauth).
    config = {
        "kind": kind,
        "provider": kind,
        "oauth_user_id": uid,
        "scopes": cfg.get("scope", ""),
        "account": tokens.get("account"),
        "capabilities": ["read", "summarize"],
        "enabled": True,
        "connection_status": oauth_store.connection_metadata(kind, uid).get("status"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    registry.save(config)
    test = connector_class(kind)(config).test()
    status = oauth_store.connection_metadata(kind, uid)
    status["status"] = "Connected" if test.get("ok") else (status.get("status") or "Authorization required")
    oauth_store.audit_record(actor="oauth-callback", kind=kind, uid=uid,
                             operation="connected", ok=bool(test.get("ok")),
                             detail=test.get("message", ""))
    app_url = os.environ.get("JARVIS_APP_URL", "http://127.0.0.1:3000").rstrip("/")
    return RedirectResponse(url=f"{app_url}/settings/integrations?connected={kind}",
                             status_code=303)


@router.post("/{kind}/test")
async def test_connector(kind: str, body: ConnectorIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    cls = connector_class(kind)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector kind: {kind}")
    if kind == "email":
        config = {"kind": kind, "provider": body.provider}
        if body.imap_host and body.imap_user and body.password:
            # Fresh credentials supplied (e.g. the Connections form "Test"
            # button, where the user typed their app password) -> test those.
            config.update({
                "imap_host": body.imap_host.strip(),
                "imap_port": body.imap_port,
                "imap_ssl": body.imap_ssl,
                "imap_user": body.imap_user.strip(),
                "password": body.password,
                "smtp_host": body.smtp_host.strip(),
                "smtp_port": body.smtp_port,
                "smtp_starttls": body.smtp_starttls,
                "send_from": body.send_from.strip(),
            })
        else:
            # The Connections list "Test" button posts no credentials: the API
            # only ever returns a masked password flag, never the real value.
            # Re-test the already-configured connector instead. registry.load()
            # decrypts the stored fernet: secret server-side, so the real
            # password never leaves the API boundary.
            stored = registry.load(kind)
            if stored and stored.get("imap_host") and stored.get("imap_user") and stored.get("password"):
                config.update({
                    "imap_host": str(stored.get("imap_host", "")).strip(),
                    "imap_port": int(stored.get("imap_port") or 993),
                    "imap_ssl": bool(stored.get("imap_ssl", True)),
                    "imap_user": str(stored.get("imap_user", "")).strip(),
                    "password": stored.get("password"),
                    "smtp_host": str(stored.get("smtp_host", "")).strip(),
                    "smtp_port": int(stored.get("smtp_port") or 587),
                    "smtp_starttls": bool(stored.get("smtp_starttls", True)),
                    "send_from": str(stored.get("send_from", "")).strip(),
                })
            else:
                raise HTTPException(status_code=400, detail="IMAP host, username, and password are required to test")
    else:
        config = {"kind": kind, "provider": body.provider}
    instance = cls(config)
    result = instance.test()
    result["at"] = now_iso()
    existing = registry.load(kind)
    if existing is not None:
        existing["last_tested_at"] = now_iso()
        existing["last_test_ok"] = bool(result.get("ok"))
        registry.save(existing)
    return result


@router.post("/{kind}")
async def create_connector(kind: str, body: ConnectorIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    cls = connector_class(kind)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector kind: {kind}")
    if kind not in _CONNECTOR_KINDS:
        raise HTTPException(status_code=400, detail=f"kind '{kind}' is not currently supported")
    if kind == "email":
        if not body.imap_host or not body.imap_user:
            raise HTTPException(status_code=400, detail="IMAP host and username are required")
        if not body.password:
            raise HTTPException(status_code=400, detail="An app password is required")
        possible = cls.possible_capabilities if cls else []
        config = {
            "kind": kind,
            "provider": body.provider,
            "imap_host": body.imap_host.strip(),
            "imap_port": body.imap_port,
            "imap_ssl": body.imap_ssl,
            "imap_user": body.imap_user.strip(),
            "password": body.password,
            "smtp_host": body.smtp_host.strip(),
            "smtp_port": body.smtp_port,
            "smtp_starttls": body.smtp_starttls,
            "send_from": body.send_from.strip(),
            "capabilities": [c for c in body.capabilities if c in possible] or list(EMAIL_CAPABILITIES),
            "enabled": body.enabled,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    else:
        config = {
            "kind": kind,
            "provider": body.provider,
            "enabled": body.enabled,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    registry.save(config)
    return {"ok": True, "config": registry.public_config(registry.load(kind))}


@router.patch("/{kind}")
async def update_connector(kind: str, body: ConnectorPatchIn, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    existing = registry.load(kind)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Connector '{kind}' is not configured")
    updated = _clean_patch(existing, body)
    if not existing.get("password") and not patch_has_password(body):
        raise HTTPException(status_code=400, detail="A password is required")
    updated["updated_at"] = now_iso()
    registry.save(updated)
    return {"ok": True, "config": registry.public_config(registry.load(kind))}


def patch_has_password(body: ConnectorPatchIn) -> bool:
    return bool(body.password is not None and body.password.strip() and body.password.strip() != registry.MASK)


@router.delete("/{kind}")
async def delete_connector(kind: str, user: Dict[str, Any] = Depends(get_current_user)):
    _require_admin(user)
    removed = registry.delete(kind)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Connector '{kind}' is not configured")
    return {"ok": True, "removed": kind}


@router.post("/{kind}/actions")
async def run_connector_action(kind: str, body: ActionIn, user: Dict[str, Any] = Depends(get_current_user)):
    result = await execute_connector_action(
        kind=kind,
        action=body.action,
        params=body.params,
        actor="user",
        user_id=user.get("id"),
    )
    result.setdefault("authenticated_as", user.get("username"))
    return result