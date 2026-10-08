"""Gmail connector over OAuth 2.0 (Gmail REST API).

Spec §7: connect with OAuth 2.0, do NOT ask for / store the Gmail password.
This connector speaks the Gmail REST API using the access token persisted by
``connectors.oauth`` (Fernet-encrypted, server-side only).  Silverwing/JARVIS
never sees the token — it only ever sees the *structured result* of an action.

Scopes (registered in start_all.ps1 -> JARVIS_OAUTH_GOOGLE_*):
  gmail:read  -> gmail.readonly            (list/search/read/headers)
  gmail:send  -> gmail.send                (send, reply — requires_confirmation)
  gmail:draft -> gmail.compose            (create drafts)
"""
from __future__ import annotations

import base64
import email.message
import email.utils
from typing import Any, Dict, List, Optional

import httpx

from ..base import ActionSpec, CAP_DRAFT, CAP_READ, CAP_SEND, CAP_SUMMARIZE, Connector, ConnectorError
from .. import oauth as oauth_store

GAPI = "https://gmail.googleapis.com/gmail/v1/users/me"


def _raw_rfc822(to: List[str], subject: str, body: str,
                cc: Optional[List[str]] = None,
                bcc: Optional[List[str]] = None) -> str:
    """Build a minimal raw RFC822 message and return it base64url-encoded."""
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


def _to_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]
    return []


def _b64decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _header_dict(msg: Dict[str, Any]) -> Dict[str, str]:
    """Flatten a Gmail message into a {lowercased-header-name: value} dict."""
    out: Dict[str, str] = {}
    src = msg.get("payload", {}).get("headers") or msg.get("headers", [])
    for h in src or []:
        if isinstance(h, dict):
            out[(h.get("name") or "").lower()] = h.get("value", "")
    return out


class GmailOAuthConnector(Connector):
    kind = "gmail"
    label = "Gmail (OAuth)"
    possible_capabilities = [CAP_READ, CAP_SUMMARIZE, CAP_DRAFT, CAP_SEND]

    actions = [
        ActionSpec("gmail.search", CAP_READ, "Search Gmail messages",
                   {"q": ["gmail search string"], "limit": ["20"]},
                   risk_level="LOW"),
        ActionSpec("gmail.read", CAP_READ, "Read a message",
                   {"message_id": ["gmail message id"]}, risk_level="LOW"),
        ActionSpec("gmail.summarize", CAP_SUMMARIZE, "Digest recent inbox",
                   {"limit": ["10"]}, risk_level="LOW"),
        ActionSpec("gmail.draft", CAP_DRAFT, "Create a draft (does not send)",
                   {"to": [], "subject": [], "body": [], "cc": []},
                   risk_level="MEDIUM", requires_confirmation=False),
        ActionSpec("gmail.send", CAP_SEND, "Send an email (audited, requires confirmation)",
                   {"to": [], "subject": [], "body": [], "cc": [], "bcc": []},
                   risk_level="HIGH", requires_confirmation=True),
        ActionSpec("gmail.reply", CAP_SEND, "Reply to a message (requires confirmation)",
                   {"message_id": [], "body": [], "cc": []},
                   risk_level="HIGH", requires_confirmation=True),
    ]

    # -- connection probe (sync, like the existing MailConnector.test) ----
    def test(self) -> Dict[str, Any]:
        token = self._token()
        if not token:
            return {"ok": False, "message": "No OAuth token stored; connect via OAuth first"}
        try:
            r = httpx.get(f"{GAPI}/labels", headers=self._hdr(token), timeout=10)
        except httpx.HTTPError as exc:
            return {"ok": False, "message": f"Gmail connection error: {exc}"}
        if r.status_code == 200:
            return {"ok": True, "message": f"Gmail OAuth connected (labels: {len(r.json().get('labels', []))})"}
        return {"ok": False, "message": f"Gmail token rejected (HTTP {r.status_code})"}

    # -- helpers ----------------------------------------------------------
    def _uid(self) -> str:
        uid = self.config.get("oauth_user_id")
        if not uid:
            raise ConnectorError("gmail connector has no oauth_user_id configured")
        return uid

    def _token(self) -> Optional[str]:
        return oauth_store.access_token("gmail", self._uid())

    def _hdr(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _headers(self, client: httpx.AsyncClient, token: str, message_id: str) -> Dict[str, str]:
        params = {"metadataHeaders": "From,To,Cc,Bcc,Subject,Date,Message-ID,References,Reply-To",
                  "format": "METADATA"}
        r = client.get(f"{GAPI}/messages/{message_id}", params=params)
        if r.status_code != 200:
            return {}
        return _header_dict(r.json())

    def _dump(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        body = ""
        parts = (msg.get("payload", {}) or {}).get("parts") or []
        for p in parts:
            if (p.get("mimeType") or "").lower() == "text/plain":
                body += _b64decode(p.get("body", {}).get("data", "")).decode("utf-8", "replace")
        if not body:
            data = (msg.get("payload", {}) or {}).get("body", {}).get("data", "")
            if data:
                body = _b64decode(data).decode("utf-8", "replace")
        hdrs = _header_dict(msg)
        return {
            "id": msg.get("id"), "thread_id": msg.get("threadId"),
            "from": hdrs.get("from", ""), "to": hdrs.get("to", ""),
            "cc": hdrs.get("cc", ""), "subject": hdrs.get("subject", ""),
            "date": hdrs.get("date", ""), "snippet": msg.get("snippet", ""),
            "body_chars": len(body),
        }

    # -- actions (async, non-blocking) -------------------------------------
    async def run_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        token = self._token()
        if not token:
            raise ConnectorError("gmail OAuth token missing; reconnect via /connectors/gmail/oauth/authorize")
        h = self._hdr(token)
        async with httpx.AsyncClient(timeout=20) as client:
            if name == "gmail.search":
                q = str(params.get("q") or "")
                limit = max(1, min(int(params.get("limit", 20)), 50))
                p = {"maxResults": limit}
                if q:
                    p["q"] = q
                r = await client.get(f"{GAPI}/messages", params=p, headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"gmail.search failed: HTTP {r.status_code}")
                results = []
                for m in r.json().get("messages", []):
                    hd = await self._headers(client, token, m["id"])
                    results.append({"id": m["id"], **hd})
                return {"results": results, "count": len(results)}

            if name == "gmail.read":
                mid = str(params.get("message_id") or "")
                if not mid:
                    raise ConnectorError("gmail.read requires 'message_id'")
                r = await client.get(f"{GAPI}/messages/{mid}", params={"format": "FULL"}, headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"gmail.read failed: HTTP {r.status_code}")
                return self._dump(r.json())

            if name == "gmail.summarize":
                limit = max(1, min(int(params.get("limit", 10)), 50))
                r = await client.get(f"{GAPI}/messages",
                                     params={"maxResults": limit, "q": "in:inbox"}, headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"gmail.summarize failed: HTTP {r.status_code}")
                rows = []
                for m in r.json().get("messages", []):
                    hd = await self._headers(client, token, m["id"])
                    rows.append({"id": m["id"], "from": hd.get("from", ""),
                                 "subject": hd.get("subject", ""), "date": hd.get("date", "")})
                return {"digest": rows, "count": len(rows)}

            if name == "gmail.draft":
                to = _to_list(params.get("to"))
                if not to:
                    raise ConnectorError("gmail.draft requires 'to'")
                raw = _raw_rfc822(to, str(params.get("subject") or ""),
                                  str(params.get("body") or ""),
                                  cc=_to_list(params.get("cc")))
                r = await client.post(f"{GAPI}/drafts",
                                      json={"message": {"raw": raw, "labelIds": ["DRAFT"]}},
                                      headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"gmail.draft failed: HTTP {r.status_code}")
                d = r.json()
                return {"draft": True, "draft_id": d.get("id"),
                        "thread_id": d.get("threadId"), "note": "draft saved; nothing sent"}

            if name == "gmail.send":
                to = _to_list(params.get("to"))
                if not to:
                    raise ConnectorError("gmail.send requires 'to'")
                raw = _raw_rfc822(to, str(params.get("subject") or ""),
                                  str(params.get("body") or ""),
                                  cc=_to_list(params.get("cc")),
                                  bcc=_to_list(params.get("bcc")))
                r = await client.post(f"{GAPI}/messages/send",
                                      json={"raw": raw, "threadId": str(params.get("thread_id") or "")},
                                      headers=h)
                if r.status_code != 200:
                    raise ConnectorError(f"gmail.send failed: HTTP {r.status_code}")
                g = r.json()
                return {"sent": True, "message_id": g.get("messageId"),
                        "thread_id": g.get("threadId")}

            if name == "gmail.reply":
                mid = str(params.get("message_id") or "")
                if not mid:
                    raise ConnectorError("gmail.reply requires 'message_id'")
                body = str(params.get("body") or "")
                if not body:
                    raise ConnectorError("gmail.reply requires 'body'")
                r = await client.get(f"{GAPI}/messages/{mid}",
                                     params={"format": "METADATA",
                                             "metadataHeaders": "From,Subject,Message-ID,References,Reply-To"},
                                     headers=h)
                hdrs = _header_dict(r.json()) if r.status_code == 200 else {}
                msg = email.message.EmailMessage()
                to = _to_list(params.get("to")) or [hdrs.get("from", "")]
                msg["To"] = ", ".join(to)
                msg["Subject"] = hdrs.get("subject", "")
                msg["In-Reply-To"] = hdrs.get("message-id", "")
                msg["References"] = hdrs.get("references") or hdrs.get("message-id", "")
                msg.set_type("text/plain", cte="utf-8")
                msg.set_content(body)
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
                send = await client.post(f"{GAPI}/messages/send", json={"raw": raw}, headers=h)
                if send.status_code != 200:
                    raise ConnectorError(f"gmail.reply failed: HTTP {send.status_code}")
                g = send.json()
                return {"replied": True, "message_id": g.get("messageId"),
                        "thread_id": g.get("threadId")}

            raise ConnectorError(f"unknown gmail action: {name}")
