"""Outlook / Microsoft 365 connector over OAuth 2.0 (Microsoft Graph).

Spec §8: use the Microsoft identity platform (v2.0) OAuth 2.0 flow and the
Microsoft Graph API.  Credentials are stored via the shared
``connectors.oauth`` Fernet vault (server-side only); Silverwing/JARVIS never
sees a token — it only sees structured action results.

Permission tiers (registered in start_all.ps1 -> JARVIS_OAUTH_MICROSOFT_*):
  outlook:read  -> Mail.Read                 (list/search/read)
  outlook:send  -> Mail.Send                 (send, reply — requires_confirmation)
  outlook:draft -> Mail.ReadWrite            (create drafts)

The tenant in the client config should be a v1.0 GUID, ``organizations`` or
``common`` — ``common`` lets any MSA/work account finish the consent flow.
"""
from __future__ import annotations

import base64
import email.message
import email.utils
from typing import Any, Dict, List, Optional

import httpx

from ..base import ActionSpec, CAP_DRAFT, CAP_READ, CAP_SEND, CAP_SUMMARIZE, Connector, ConnectorError
from .. import oauth as oauth_store

GRAPH = "https://graph.microsoft.com/v1.0"


def _to_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]
    return []


def _raw_rfc822(to: List[str], subject: str, body: str,
                cc: Optional[List[str]] = None,
                bcc: Optional[List[str]] = None) -> str:
    msg = email.message.EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localname="localhost")
    msg.set_type("text/plain", cte="utf-8")
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")


class OutlookOAuthConnector(Connector):
    kind = "outlook"
    label = "Outlook / Microsoft 365 (OAuth)"
    possible_capabilities = [CAP_READ, CAP_SUMMARIZE, CAP_DRAFT, CAP_SEND]

    actions = [
        ActionSpec("outlook.search", CAP_READ, "Search Outlook messages",
                   {"q": ["search string"], "limit": ["20"]}, risk_level="LOW"),
        ActionSpec("outlook.read", CAP_READ, "Read a message",
                   {"message_id": ["graph message id"]}, risk_level="LOW"),
        ActionSpec("outlook.summarize", CAP_SUMMARIZE, "Digest recent mail",
                   {"limit": ["10"]}, risk_level="LOW"),
        ActionSpec("outlook.draft", CAP_DRAFT, "Create a draft (does not send)",
                   {"to": [], "subject": [], "body": [], "cc": []},
                   risk_level="MEDIUM", requires_confirmation=False),
        ActionSpec("outlook.send", CAP_SEND, "Send an email (audited, requires confirmation)",
                   {"to": [], "subject": [], "body": [], "cc": [], "bcc": []},
                   risk_level="HIGH", requires_confirmation=True),
        ActionSpec("outlook.reply", CAP_SEND, "Reply to a message (requires confirmation)",
                   {"message_id": [], "body": [], "cc": []},
                   risk_level="HIGH", requires_confirmation=True),
    ]

    # -- connection probe -------------------------------------------------
    def test(self) -> Dict[str, Any]:
        token = self._token()
        if not token:
            return {"ok": False, "message": "No OAuth token stored; connect via OAuth first"}
        try:
            r = httpx.get(f"{GRAPH}/me",
                          headers=self._hdr(token), timeout=10)
        except httpx.HTTPError as exc:
            return {"ok": False, "message": f"Outlook connection error: {exc}"}
        if r.status_code == 200:
            me = r.json()
            return {"ok": True, "message": f"Outlook OAuth connected ({me.get('mail') or me.get('userPrincipalName')})"}
        return {"ok": False, "message": f"Outlook token rejected (HTTP {r.status_code})"}

    # -- helpers ----------------------------------------------------------
    def _uid(self) -> str:
        uid = self.config.get("oauth_user_id")
        if not uid:
            raise ConnectorError("outlook connector has no oauth_user_id configured")
        return uid

    def _token(self) -> Optional[str]:
        return oauth_store.access_token("outlook", self._uid())

    def _hdr(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _headers(self, client: httpx.AsyncClient, token: str, message_id: str) -> Dict[str, str]:
        p = {"$select": "id,from,subject,receivedDateTime,hasAttachments"}
        r = client.get(f"{GRAPH}/me/messages/{message_id}", params=p)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {"id": d.get("id"), "from": (d.get("from", {}) or {}).get("emailAddress", {}).get("name", ""),
                "fromAddress": (d.get("from", {}) or {}).get("emailAddress", {}).get("address", ""),
                "subject": d.get("subject", ""), "received": d.get("receivedDateTime", "")}

    # -- actions ----------------------------------------------------------
    async def run_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        token = self._token()
        if not token:
            raise ConnectorError("outlook OAuth token missing; reconnect via /connectors/outlook/oauth/authorize")
        h = self._hdr(token)
        async with httpx.AsyncClient(timeout=20) as client:
            if name == "outlook.search":
                limit = max(1, min(int(params.get("limit", 20)), 50))
                p = {"$top": limit, "$orderby": "receivedDateTime DESC",
                     "$select": "id,subject,from,receivedDateTime,hasAttachments,isRead"}
                q = str(params.get("q") or "")
                if q:
                    p["$search"] = f'"{q}"'  # requires ConsistencyLevel: low
                    headers = {**h, "ConsistencyLevel": "low"}
                else:
                    headers = h
                r = await client.get(f"{GRAPH}/me/messages", params=p, headers=headers)
                if r.status_code != 200:
                    raise ConnectorError(f"outlook.search failed: HTTP {r.status_code}")
                rows = []
                for m in r.json().get("value", []):
                    fr = (m.get("from", {}) or {}).get("emailAddress", {}) or {}
                    rows.append({"id": m.get("id"), "subject": m.get("subject", ""),
                                 "from": fr.get("name", ""), "fromAddress": fr.get("address", ""),
                                 "received": m.get("receivedDateTime", ""),
                                 "hasAttachments": m.get("hasAttachments", False)})
                return {"results": rows, "count": len(rows)}

            if name == "outlook.read":
                mid = str(params.get("message_id") or "")
                if not mid:
                    raise ConnectorError("outlook.read requires 'message_id'")
                r = await client.get(f"{GRAPH}/me/messages/{mid}",
                                     params={"$select": "id,subject,from,toRecipients,ccRecipients,"
                                                        "bccRecipients,receivedDateTime,hasAttachments,"
                                                        "isRead,internetMessageId,bodyPreview,body"},
                                     headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"outlook.read failed: HTTP {r.status_code}")
                return self._dump(r.json())

            if name == "outlook.summarize":
                limit = max(1, min(int(params.get("limit", 10)), 50))
                r = await client.get(f"{GRAPH}/me/messages",
                                     params={"$top": limit, "$orderby": "receivedDateTime DESC",
                                             "$select": "id,subject,from,receivedDateTime"},
                                     headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"outlook.summarize failed: HTTP {r.status_code}")
                rows = []
                for m in r.json().get("value", []):
                    fr = (m.get("from", {}) or {}).get("emailAddress", {}) or {}
                    rows.append({"id": m.get("id"), "from": fr.get("name", ""),
                                 "subject": m.get("subject", ""),
                                 "received": m.get("receivedDateTime", "")})
                return {"digest": rows, "count": len(rows)}

            if name == "outlook.draft":
                to = _to_list(params.get("to"))
                if not to:
                    raise ConnectorError("outlook.draft requires 'to'")
                msg = {"message": {"subject": str(params.get("subject") or ""),
                                   "body": {"contentType": "text", "content": str(params.get("body") or "")},
                                   "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                                   "ccRecipients": [{"emailAddress": {"address": a}} for a in _to_list(params.get("cc"))]},
                       "saveToDrafts": True}
                r = await client.post(f"{GRAPH}/me/messages", json=msg, headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"outlook.draft failed: HTTP {r.status_code}")
                d = r.json()
                return {"draft": True, "message_id": d.get("id"), "note": "draft saved; nothing sent"}

            if name == "outlook.send":
                to = _to_list(params.get("to"))
                if not to:
                    raise ConnectorError("outlook.send requires 'to'")
                msg = {"message": {"subject": str(params.get("subject") or ""),
                                   "body": {"contentType": "text", "content": str(params.get("body") or "")},
                                   "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                                   "ccRecipients": [{"emailAddress": {"address": a}} for a in _to_list(params.get("cc"))],
                                   "bccRecipients": [{"emailAddress": {"address": a}} for a in _to_list(params.get("bcc"))]},
                       "saveToDrafts": False}
                r = await client.post(f"{GRAPH}/sendMail", json={"message": msg["message"]},
                                      headers=h)
                # Graph sendMail returns 200/202 with no body on success.
                if r.status_code not in (200, 202):
                    raise ConnectorError(f"outlook.send failed: HTTP {r.status_code}")
                return {"sent": True, "thread_id": params.get("thread_id", "")}

            if name == "outlook.reply":
                mid = str(params.get("message_id") or "")
                if not mid:
                    raise ConnectorError("outlook.reply requires 'message_id'")
                body = str(params.get("body") or "")
                if not body:
                    raise ConnectorError("outlook.reply requires 'body'")
                r = await client.post(f"{GRAPH}/me/messages/{mid}/reply",
                                      json={"comment": body,
                                            "toRecipients": [{"emailAddress": {"address": a}}
                                                             for a in _to_list(params.get("to"))]},
                                      headers=h)
                if r.status_code not in (200, 202):
                    raise ConnectorError(f"outlook.reply failed: HTTP {r.status_code}")
                return {"replied": True, "message_id": mid}

            raise ConnectorError(f"unknown outlook action: {name}")

    # -- helpers ----------------------------------------------------------
    def _dump(self, d: Dict[str, Any]) -> Dict[str, Any]:
        def _addr_list(recips):
            return [((r.get("emailAddress") or {}).get("name", ""),
                     (r.get("emailAddress") or {}).get("address", "")) for r in recips or []]
        body = (d.get("body") or {})
        return {
            "id": d.get("id"),
            "internet_message_id": d.get("internetMessageId"),
            "from": _addr_list(d.get("from", [])),
            "to": _addr_list(d.get("toRecipients", [])),
            "cc": _addr_list(d.get("ccRecipients", [])),
            "bcc": _addr_list(d.get("bccRecipients", [])),
            "subject": d.get("subject", ""),
            "received": d.get("receivedDateTime", ""),
            "hasAttachments": d.get("hasAttachments", False),
            "isRead": d.get("isRead", False),
            "bodyPreview": d.get("bodyPreview", "")[:2000],
            "body_chars": len(body.get("content", "")) if isinstance(body, dict) else 0,
        }
