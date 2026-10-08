"""Dispatch layer: one entry point for the AI to act on connectors.

Enforces, in order:

1. connector configured?  (else an honest refusal, no invented state)
2. connector enabled?     (kill switch)
3. capability allowed?    (consent set from Connections)
4. action exists?         (registered ActionSpec)

Every invocation is audited to jarvis_data/audit/connectors.jsonl.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import ActionSpec, CapabilityDenied, Connector, ConnectorError
from .mail.connector import MailConnector
from .mail.gmail_oauth import GmailOAuthConnector
from .mail.outlook_oauth import OutlookOAuthConnector
from . import registry
from . import oauth as oauth_store
from ..core import now_iso


class CalendarConnector(Connector):
    kind = "calendar"
    label = "Calendar"
    possible_capabilities = ["read", "write", "delete"]
    actions = [
        ActionSpec("calendar.list", "read", "List calendar events", {}),
        ActionSpec("calendar.create", "write", "Create an event", {"title": [], "date": [], "time": []}),
        ActionSpec("calendar.delete", "delete", "Delete an event", {"event_id": []}),
    ]

    def test(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "NOT_IMPLEMENTED",
            "message": "Calendar API operations are not implemented.",
        }

    async def run_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "NOT_IMPLEMENTED",
            "error": f"Calendar action '{name}' has no executable handler.",
        }


class FilesConnector(Connector):
    kind = "files"
    label = "Files"
    possible_capabilities = ["read", "write", "delete"]
    actions = [
        ActionSpec("files.list", "read", "List files", {"path": []}),
        ActionSpec("files.read", "read", "Read a file", {"path": []}),
        ActionSpec("files.write", "write", "Write a file", {"path": [], "content": []}),
    ]

    def test(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "NOT_IMPLEMENTED",
            "message": "File operations are not implemented for this connector.",
        }

    async def run_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "NOT_IMPLEMENTED",
            "error": f"File action '{name}' has no executable handler.",
        }


_CONNECTORS: Dict[str, type] = {
    "email": MailConnector,
    "gmail": GmailOAuthConnector,
    "outlook": OutlookOAuthConnector,
    "calendar": CalendarConnector,
    "files": FilesConnector,
}


def connector_class(kind: str) -> Optional[type]:
    return _CONNECTORS.get(kind)


def list_connectors() -> list:
    from jarvis_backend.connectors import registry as reg

    out = []
    for kind in _CONNECTORS:
        raw = reg.load(kind)
        cls = _CONNECTORS[kind]
        is_oauth = kind in ("gmail", "outlook")
        oauth_user_id = (raw or {}).get("oauth_user_id")
        configured = raw is not None and (
            bool(raw.get("password")) or bool(raw.get("api_key")) or bool(oauth_user_id)
        )
        executable = kind not in {"calendar", "files"}
        status: Dict[str, Any] = {}
        if is_oauth and oauth_user_id:
            status = oauth_store.connection_metadata(kind, oauth_user_id)
        out.append({
            "kind": kind,
            "label": cls.label if cls else kind,
            "possible_capabilities": cls.possible_capabilities if cls else [],
            "actions": [
                {**a.__dict__, "executable": executable}
                for a in cls.actions
            ] if cls else [],
            "config": reg.public_config(raw),
            "configured": configured,
            "executable": executable and configured and bool((raw or {}).get("enabled")),
            "connection_status": status.get("status") or (
                "Connected" if status.get("connected") else None),
            "token_expires_at": status.get("token_expires_at"),
            "account": status.get("account"),
            "enabled": bool((raw or {}).get("enabled")) if raw else False,
            "capabilities": (
                [c for c in ((raw or {}).get("capabilities") or [])]
                if executable else []
            ),
        })
    return out


async def execute_connector_action(
    kind: str,
    action: str,
    params: Dict[str, Any],
    actor: str = "user",
    user_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run ``action`` on connector ``kind`` with the provided parameters.

    Returns a result dict with ``ok``; never raises for policy failures (they
    are surfaced honestly in ``error`` so the AI can tell the user what is
    missing).
    """
    cls = connector_class(kind)
    if cls is None:
        return {"ok": False, "error": f"unknown connector kind: {kind}"}

    raw = registry.load(kind)
    if raw is None:
        return {
            "ok": False,
            "connector": kind,
            "error": f"{cls.label} is not configured. Connect it in Connections "
                     "(dashboard → Connections) before asking the AI to touch it.",
        }
    config = dict(raw)

    if not config.get("enabled"):
        return {"ok": False, "connector": kind,
                "error": f"{cls.label} is disabled (kill switch off in Connections)."}

    instance = cls(config)
    spec = instance.action_spec(action)
    if spec is None:
        return {"ok": False, "connector": kind, "error": f"unknown action '{action}' for {kind}."}

    if not instance.allows(spec.capability):
        return {
            "ok": False,
            "connector": kind,
            "error": f"action '{action}' needs capability '{spec.capability}', which is "
                     f"disabled for this connector. Enable it in Connections.",
        }

    # ------------------------------------------------------------------ #
    # Human-in-the-loop gate (spec §10/§34/§40).
    # HIGH/CRITICAL actions, or any action flagged ``requires_confirmation``,
    # must be confirmed by the developer before execution.  The AI may propose
    # the call, but it can only execute it by re-issuing the same action with
    # ``confirm=true`` in params — and that re-issue is itself audited.
    # ------------------------------------------------------------------ #
    confirmation_required = spec.requires_confirmation or spec.risk_level in ("HIGH", "CRITICAL")
    confirmed = bool((params or {}).pop("confirm", False))

    if confirmation_required and not confirmed:
        registry.audit({
            "ts": now_iso(), "actor": actor, "user_id": user_id,
            "kind": kind, "action": action,
            "params": _summarize_params(action, params or {}),
            "ok": False, "confirmation_required": True,
            "risk_level": spec.risk_level, "error": "requires_confirmation",
            "meta": {"meta": meta or {}},
        })
        return {
            "ok": False,
            "connector": kind,
            "action": action,
            "confirmation_required": True,
            "risk_level": spec.risk_level,
            "summary": spec.summary,
            "preview": _summarize_params(action, params or {}),
            "hint": (f"This action is {spec.risk_level} risk and requires confirmation. "
                     "Re-issue the same request with params['confirm']=true after review."),
        }

    try:
        result = await instance.run_action(action, params or {})
        if isinstance(result, dict):
            ok = not (result.get("error") or result.get("ok") is False)
        else:
            ok = True
    except CapabilityDenied as exc:  # pragma: no cover - reserved
        ok, result = False, {"error": str(exc)}
    except ConnectorError as exc:
        ok, result = False, {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        ok, result = False, {"error": f"{kind}.{action} failed: {exc}"}

    if isinstance(result, dict):
        result["ok"] = bool(ok)
        result.setdefault("connector", kind)
        result.setdefault("action", action)
    else:
        result = {"ok": bool(ok), "connector": kind, "action": action, "data": result}

    audit_payload = {
        "ts": now_iso(),
        "actor": actor,
        "user_id": user_id,
        "kind": kind,
        "action": action,
        "params": _summarize_params(action, params or {}),
        "ok": bool(ok),
        "confirmation_required": confirmation_required,
        "confirmed": confirmed,
        "risk_level": spec.risk_level,
        "error": result.get("error") if isinstance(result, dict) else None,
        "meta": meta or {},
    }
    registry.audit(audit_payload)
    return result


def _summarize_params(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ("folder", "query", "uid"):
        if key in params:
            out[key] = params[key]
    if "to" in params:
        out["to"] = _to_list(params["to"])[:10]
    if "subject" in params:
        out["subject"] = str(params["subject"])[:120]
    if "send_from" in params:
        out["send_from"] = str(params["send_from"])[:120]
    if "body" in params:
        out["body_chars"] = len(str(params["body"]))
    return out


def _to_list(value: Any) -> list:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
    return []