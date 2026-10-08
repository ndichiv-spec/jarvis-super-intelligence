"""Mail connector: IMAP read actions + SMTP send actions on one mailbox.

Consent model lives here too: the connector's *enabled capabilities* gate
every action, so the AI can do everything the developer allows (default: all
four capabilities on), and the global kill switch + per-capability toggles in
Connections govern it at runtime.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import (
    ActionSpec,
    CAP_DRAFT,
    CAP_READ,
    CAP_SEND,
    CAP_SUMMARIZE,
    Connector,
    ConnectorError,
)
from . import imap_connector as imap
from . import smtp_connector as smtp

ALL_ACTIONS = [
    ActionSpec("email.folders", CAP_READ, "List mailbox folders", {}),
    ActionSpec("email.search", CAP_READ, "Search messages (headers)",
               {"folder": ["INBOX"], "query": ["ALL"], "limit": ["20"]}),
    ActionSpec("email.read", CAP_READ, "Read one message body",
               {"folder": ["INBOX"], "uid": ["<uid from search>"]}),
    ActionSpec("email.summarize", CAP_SUMMARIZE, "Structured mailbox digest",
               {"folder": ["INBOX"], "limit": ["10"]}),
    ActionSpec("email.draft", CAP_DRAFT, "Compose a draft (no send)",
               {"to": [], "subject": [], "body": []}),
    ActionSpec("email.send", CAP_SEND, "Send an email (audited, rate-limited)",
               {"to": [], "subject": [], "body": [], "cc": [], "send_from": []}),
    ActionSpec("email.reply", CAP_SEND, "Reply to an existing message",
               {"folder": ["INBOX"], "uid": [], "body": [], "cc": []}),
]


class MailConnector(Connector):
    kind = "email"
    label = "Email (IMAP + SMTP)"
    possible_capabilities = [CAP_READ, CAP_SUMMARIZE, CAP_DRAFT, CAP_SEND]
    actions = ALL_ACTIONS

    def test(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        im = imap.imap_test(self.config)
        sm = smtp.smtp_test(self.config)
        ok = bool(im["ok"] and sm["ok"]) if self.config.get("smtp_host") else bool(im["ok"])
        results["imap"] = im
        results["smtp"] = sm
        results["ok"] = ok
        results["message"] = " | ".join(
            f"{k}: {v['message']}" for k, v in results.items() if isinstance(v, dict) and "message" in v
        )
        return results

    async def run_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if name == "email.folders":
            conn = imap._connect(self.config)
            try:
                folders = imap.list_folders(conn)
                return {"folders": folders, "count": len(folders)}
            finally:
                imap._close(conn)

        if name == "email.search":
            folder = str(params.get("folder") or "INBOX")
            query = str(params.get("query") or "ALL")
            limit = max(1, min(int(params.get("limit", 20)), 100))
            conn = imap._connect(self.config)
            try:
                uids = imap.search_uids(conn, folder, query, limit)
                items = [imap.fetch_headers(conn, uid) for uid in uids]
                return {"folder": folder, "query": query, "results": items, "count": len(items)}
            finally:
                imap._close(conn)

        if name == "email.read":
            folder = str(params.get("folder") or "INBOX")
            uid = str(params.get("uid") or "")
            if not uid:
                raise ConnectorError("email.read requires 'uid'")
            conn = imap._connect(self.config)
            try:
                imap.select(conn, folder)
                return imap.fetch_body(conn, uid)
            finally:
                imap._close(conn)

        if name == "email.summarize":
            folder = str(params.get("folder") or "INBOX")
            limit = max(1, min(int(params.get("limit", 10)), 50))
            conn = imap._connect(self.config)
            try:
                uids = imap.search_uids(conn, folder, "ALL", limit)
                digest = []
                for uid in uids:
                    m = imap.fetch_headers(conn, uid)
                    digest.append({
                        "from": m["from"][:160],
                        "subject": m["subject"][:160],
                        "date": m["date"][:80],
                        "uid": m["uid"],
                    })
                return {
                    "folder": folder,
                    "digest": digest,
                    "count": len(digest),
                    "note": "rule-based digest of message headers; use email.read for full bodies",
                }
            finally:
                imap._close(conn)

        if name == "email.draft":
            to = _to_list(params.get("to"))
            subject = str(params.get("subject") or "")
            body = str(params.get("body") or "")
            if not subject and not body:
                raise ConnectorError("email.draft requires a subject or body")
            return {
                "draft": True,
                "to": to,
                "subject": subject,
                "body_chars": len(body),
                "note": "draft validated; nothing was sent",
            }

        if name == "email.reply":
            folder = str(params.get("folder") or "INBOX")
            uid = str(params.get("uid") or "")
            if not uid:
                raise ConnectorError("email.reply requires 'uid'")
            reply_body = str(params.get("body") or "")
            if not reply_body:
                raise ConnectorError("email.reply requires a 'body'")
            conn = imap._connect(self.config)
            try:
                imap.select(conn, folder)
                original = imap.fetch_headers(conn, uid)
                subject = str(original.get("subject") or "")
                reply_ref = str(original.get("message_id") or "")
            finally:
                imap._close(conn)
            to = _to_list(params.get("to")) or [original["from"]]
            subject = ("Re: " + subject) if subject and not subject.lower().startswith("re:") else subject
            return smtp.smtp_send(
                self.config,
                to_addrs=to,
                subject=subject,
                body=reply_body,
                cc=_to_list(params.get("cc")),
                reply_in_reply_to=reply_ref or None,
            )

        if name == "email.send":
            return smtp.smtp_send(
                self.config,
                to_addrs=_to_list(params.get("to")),
                subject=str(params.get("subject") or ""),
                body=str(params.get("body") or ""),
                cc=_to_list(params.get("cc")),
                send_from=str(params.get("send_from") or "").strip() or None,
            )

        raise ConnectorError(f"unknown mail action: {name}")


def _to_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
    return []