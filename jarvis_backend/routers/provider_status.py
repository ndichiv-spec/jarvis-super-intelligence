"""Runtime provider-capability discovery (spec sections 9 / 17 / 41 / 45 / 46).

This endpoint is a *diagnostic reflector*, not a new auth/provider framework.
It reports the real, current state of every provider JARVIS can address by
composing the primitives that already exist in the codebase:

* API-key fabric providers  -> ``extensions._API_KEY_PROVIDERS`` +
  ``_env_api_key`` (env-var presence) + ``_validate_api_key`` (live probe that
  hits the real provider API at ``api.openai.com`` / ``generativelanguage.
  googleapis.com`` / ``api.anthropic.com`` / ``huggingface.co``).
* OAuth mail/connectors     -> ``connectors.oauth.client_config`` (a client is
  registered in ``JARVIS_OAUTH_CLIENTS``) + ``connection_metadata`` (per-user
  token vault status).
* Audited capability gaps   -> the ``_NOT_IMPLEMENTED`` table below, which the
  audit (spec sections 3 / 6 / 7) confirmed are *not present* in the code.

Truth rule (spec section 62): a provider is NEVER reported as connected/healthy
unless the real configured capability was actually exercised. Providers with no
credentials report NOT_CONFIGURED / AUTHENTICATION_REQUIRED; capabilities that
exist only as un-wired intentions report NOT_IMPLEMENTED. No API key value or
token is ever returned -- only masked presence and validator outcomes.

The route is admin-gated (consistent with the Extensions/Connectors
"install/enable/connect" surface) and defaults to ``probe=false`` (no network)
so the Connections UI loads fast; an admin passes ``?probe=true`` to validate
configured keys live against their providers.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from ..core import now_iso
from ..core import _require_admin
from . import extensions as ext
from ..connectors import oauth as oauth_store

router = APIRouter(prefix="/api/v1/integrations", tags=["extensions"])

# OAuth connector kinds the platform currently ships (connectors/mail + the
# generic oauth.py flow keyed on ``kind`` in JARVIS_OAUTH_CLIENTS).
_OAUTH_SPECS: Dict[str, Dict[str, Any]] = {
    "gmail": {
        "name": "Google Gmail (OAuth)",
        "category": "google",
        "capabilities": ["mail.read", "mail.send", "mail.compose"],
        "console_url": "https://console.cloud.google.com/apis/credentials",
    },
    "outlook": {
        "name": "Microsoft Outlook / Graph Mail (OAuth)",
        "category": "microsoft",
        "capabilities": ["mail.read", "mail.send", "mail.compose"],
        "console_url": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps",
    },
}

# Human-readable marketplace names for the API-key provider fabric, sourced
# from the same catalog the Extensions page uses.
_NAME_BY_EXT: Dict[str, str] = dict((r[0], r[1]) for r in ext._rows())

# Microsoft capability separation (spec section 3). Only Outlook Graph Mail is
# implemented today; the remaining Microsoft 365 / Copilot surfaces are
# explicitly tracked here as NOT_IMPLEMENTED so the matrix never over-claims a
# provider that the code has not wired. Each entry maps to a spec section that
# describes the gap.
_NOT_IMPLEMENTED: List[Dict[str, Any]] = [
    {
        "id": "microsoft_copilot",
        "name": "Microsoft 365 Copilot",
        "category": "microsoft",
        "connect_type": "oauth",
        "capabilities": [],
        "configured": False,
        "connected": False,
        "status": "NOT_IMPLEMENTED",
        "reason": ("Microsoft 365 Copilot Retrieval/Chat APIs (Graph v1.0 beta "
                   "copilot endpoints) are not implemented in this build. "
                   "Requires qualifying M365 Copilot licensing + a registered "
                   "Microsoft identity; see spec sections 6/7/10/11."),
        "license_required": True,
        "console_url": "https://learn.microsoft.com/microsoft-365-copilot/extensibility/apis",
    },
    {
        "id": "azure_ai",
        "name": "Azure AI / Azure-hosted AI",
        "category": "microsoft",
        "connect_type": "api_key",
        "capabilities": [],
        "configured": False,
        "connected": False,
        "status": "NOT_IMPLEMENTED",
        "reason": "Azure AI endpoints are not wired in this build (spec section 3).",
        "license_required": False,
        "console_url": "https://portal.azure.com/",
    },
    {
        "id": "github_copilot",
        "name": "GitHub Copilot",
        "category": "microsoft",
        "connect_type": "api_key",
        "capabilities": [],
        "configured": False,
        "connected": False,
        "status": "NOT_IMPLEMENTED",
        "reason": "GitHub Copilot is not wired in this build (spec section 3).",
        "license_required": False,
        "console_url": "https://github.com/features/copilot",
    },
    {
        "id": "google_vertexai",
        "name": "Google Vertex AI",
        "category": "google",
        "connect_type": "api_key",
        "capabilities": [],
        "configured": False,
        "connected": False,
        "status": "NOT_IMPLEMENTED",
        "reason": "Vertex AI is not implemented; use Google Gemini (API key) instead.",
        "license_required": False,
        "console_url": "https://cloud.google.com/vertex-ai",
    },
]


def _api_key_entry(ext_id: str, probe: bool) -> Dict[str, Any]:
    """Real state for an API-key provider (OpenAI / Claude / Gemini / ...)."""
    prov = ext._API_KEY_PROVIDERS.get(ext_id, {})
    key_names: List[str] = prov.get("key_env", [])
    key = ext._env_api_key(ext_id)
    configured = bool(key)
    entry: Dict[str, Any] = {
        "id": ext_id,
        "name": _NAME_BY_EXT.get(ext_id, ext_id),
        "category": "ai",
        "connect_type": "api_key",
        "capabilities": ext._extension_capabilities(ext_id),
        "key_env": key_names,
        "console_url": prov.get("console_url"),
        "configured": configured,
        "connected": False,
        "status": None,
        "validator_result": None,
        "reason": None,
        # code_present lets consumers distinguish "integration exists but needs
        # a key" from "not implemented at all" -- honest, never faked.
        "code_present": ext_id in ext._API_KEY_PROVIDERS,
    }
    if not configured:
        entry["status"] = "NOT_CONFIGURED"
        entry["reason"] = "No API key found in env vars %s" % key_names
        return entry
    if not probe:
        entry["status"] = "CONFIGURED"
        return entry
    # Live probe (server-side only; the raw key is never logged or returned).
    verified, err = ext._validate_api_key(ext_id, key)  # type: ignore[arg-type]
    entry["validator_result"] = {"verified": verified, "error": err}
    entry["connected"] = verified is True
    if verified is True:
        entry["status"] = "HEALTHY"
    elif verified is False:
        entry["status"] = "INVALID_KEY"
    else:
        entry["status"] = "UNVERIFIED"  # probe ran, inconclusive (offline)
    return entry


def _oauth_entry(kind: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Real state for an OAuth mail/identity connector (Gmail / Outlook)."""
    spec = _OAUTH_SPECS[kind]
    cfg = oauth_store.client_config(kind)
    configured = bool(cfg)
    meta = oauth_store.connection_metadata(kind, user.get("id"))
    connected = bool(meta.get("connected"))
    if connected:
        status = meta.get("status") or "Connected"
    elif configured:
        status = "CONFIGURED (awaiting user consent; no token stored for this user)"
    else:
        status = "AUTHENTICATION_REQUIRED"
    return {
        "id": kind,
        "name": spec["name"],
        "category": spec["category"],
        "connect_type": "oauth",
        # Real connector actions live on the connector subclass; the fabric
        # advertises only the read-only mail capability subset up front.
        "capabilities": ["mail.read", "mail.send", "mail.compose"],
        "key_env": [],
        "console_url": spec["console_url"],
        "configured": configured,
        "connected": connected,
        "status": status,
        "scopes": (cfg or {}).get("scope"),
        "validator_result": None,
        "reason": None,
        "code_present": True,
    }


def _build_matrix(probe: bool, user: Dict[str, Any]) -> List[Dict[str, Any]]:
    providers: List[Dict[str, Any]] = []
    for ext_id in ext._API_KEY_PROVIDERS:
        providers.append(_api_key_entry(ext_id, probe))
    for kind in _OAUTH_SPECS:
        providers.append(_oauth_entry(kind, user))
    providers.extend(_NOT_IMPLEMENTED)
    return providers


@router.get("/providers")
async def provider_status(
    probe: bool = Query(
        False,
        description=(
            "Live-validate configured API keys against their providers "
            "(admin only; off by default for fast UI loads)."
        ),
    ),
    user: Dict[str, Any] = Depends(_require_admin),
):
    """Runtime provider-capability matrix (spec sections 9/17/41/45/46).

    Returns the real, non-faked state of every addressable provider:
    NOT_CONFIGURED / AUTHENTICATION_REQUIRED / CONFIGURED / HEALTHY /
    INVALID_KEY / UNVERIFIED / NOT_IMPLEMENTED, plus capabilities, scopes,
    the key env-var names, and console URLs. No secret values are returned.
    """
    return {
        "generated_at": now_iso(),
        "probe": probe,
        "providers": _build_matrix(probe, user),
    }
