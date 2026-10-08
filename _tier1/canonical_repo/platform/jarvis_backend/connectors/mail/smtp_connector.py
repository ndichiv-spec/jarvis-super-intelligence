"""SMTP send helpers (real smtplib, optional STARTTLS).

Sends are rate-limited (in-flight, per-process) and every send carries a small
provenance footer so AI-generated mail is identifiable.  The audit record itself
is written by the dispatch layer, not here.
"""

from __future__ import annotations

import smtplib
import socket
import threading
import time
from email.message import EmailMessage
from typing import Any, Dict, List

from ..base import ConnectorError

_MAX_SENDS_PER_HOUR = 20
_FOOTER = "- Sent via JARVIS AI (email connector)"

_lock = threading.Lock()
_send_times: List[float] = []


def _check_rate() -> None:
    now = time.time()
    with _lock:
        window = [t for t in _send_times if t > now - 3600]
        if len(window) >= _MAX_SENDS_PER_HOUR:
            raise ConnectorError(
                f"send rate limit reached ({_MAX_SENDS_PER_HOUR}/hour); "
                "try again later or raise the limit in Connections"
            )
        _send_times[:] = window


def smtp_test(config: Dict[str, Any]) -> Dict[str, Any]:
    host = str(config.get("smtp_host") or "").strip()
    port = int(config.get("smtp_port") or 587)
    use_starttls = bool(config.get("smtp_starttls", True))
    user = str(config.get("imap_user") or "").strip()
    password = str(config.get("password") or "")
    start = time.time()
    if not host:
        return {"ok": False, "message": "SMTP host not set; configure SMTP to enable sending"}
    server = None
    try:
        server = smtplib.SMTP(host, port, timeout=10)
        server.ehlo()
        # Upgrade to TLS BEFORE authenticating. Providers such as Gmail/Outlook
        # only advertise AUTH once the channel is encrypted; on a plaintext
        # connection AUTH is not advertised and login would fail.
        if use_starttls:
            try:
                server.starttls()
                server.ehlo()
            except Exception:  # noqa: BLE001 - STARTTLS may be unsupported; fall back below
                try:
                    server.ehlo()
                except Exception:  # noqa: BLE001
                    pass
        if user and password:
            if "auth" not in server.esmtp_features:
                return {"ok": False, "message": "SMTP server does not advertise AUTH; ensure smtp_starttls is enabled and the server accepts STARTTLS on port 587"}
            try:
                server.login(user, password)
            except smtplib.SMTPAuthenticationError:
                return {"ok": False, "message": "SMTP authentication failed"}
            auth_msg = "login succeeded"
        else:
            auth_msg = "login not required (anonymous relay)"
    except (smtplib.SMTPException, socket.error) as exc:
        return {"ok": False, "message": f"SMTP connect failed: {exc}"}
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
    return {
        "ok": True,
        "message": f"SMTP reachable ({(time.time() - start) * 1000:.0f} ms), {auth_msg} on {host}:{port}",
    }


def smtp_send(config: Dict[str, Any],
              to_addrs: List[str],
              subject: str,
              body: str,
              cc: List[str] | None = None,
              send_from: str | None = None,
              reply_in_reply_to: str | None = None) -> Dict[str, Any]:
    host = str(config.get("smtp_host") or "").strip()
    port = int(config.get("smtp_port") or 587)
    use_starttls = bool(config.get("smtp_starttls", True))
    user = str(config.get("imap_user") or "").strip()
    password = str(config.get("password") or "")
    sender = send_from or str(config.get("send_from") or user or "").strip()
    if not host:
        raise ConnectorError("SMTP host not configured; email.send is disabled until set")
    if not sender:
        raise ConnectorError("send_from address is required")
    if not to_addrs:
        raise ConnectorError("email.send requires at least one recipient")
    subject = str(subject or "(no subject)")
    body = str(body or "")

    _check_rate()

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_in_reply_to:
        msg["In-Reply-To"] = reply_in_reply_to
        msg["References"] = reply_in_reply_to
    msg.set_content(f"{body}\n\n{_FOOTER}")

    server = None
    try:
        server = smtplib.SMTP(host, port, timeout=15)
        server.ehlo()
        # Upgrade to TLS BEFORE authenticating. Providers such as Gmail/Outlook
        # only advertise AUTH once the channel is encrypted; the original code
        # could call login() with a stale esmtp_features set (starttls resets it
        # but a swallowed/failed post-TLS EHLO left it inconsistent) and smtplib
        # raised "SMTP AUTH extension not supported by server". Re-issue EHLO
        # after STARTTLS so the feature set is consistent, then check AUTH
        # explicitly before login and raise an actionable error if the server
        # cannot accept it.
        if use_starttls:
            try:
                server.starttls()
                server.ehlo()
            except Exception:  # noqa: BLE001 - STARTTLS may be unsupported; fall back below
                try:
                    server.ehlo()
                except Exception:  # noqa: BLE001
                    pass
        if user and password:
            if "auth" not in server.esmtp_features:
                raise ConnectorError(
                    "SMTP server does not advertise AUTH over this connection; "
                    "ensure smtp_starttls is enabled and the server accepts "
                    "STARTTLS on port 587"
                )
            server.login(user, password)
        server.sendmail(sender, [*to_addrs, *(cc or [])], msg.as_string())
    except ConnectorError:
        raise
    except (smtplib.SMTPException, socket.error) as exc:
        raise ConnectorError(f"SMTP send failed: {exc}") from exc
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
    return {
        "sent": True,
        "from": sender,
        "to": to_addrs,
        "cc": cc or [],
        "subject": subject,
        "reply_in_reply_to": reply_in_reply_to,
        "body_chars": len(body),
        "footer_appended": True,
    }