"""IMAP read helpers (real imaplib against the configured mailbox).

Open-per-action: connect + login + act + logout.  TLS/SSL selected by config.
Message body data exists only in the transient response (never written to
disk) and is truncated to ``preview_chars``; only an explicit ``email.read``
returns a full body.
"""

from __future__ import annotations

import imaplib
import socket
import time
from email import message_from_bytes
from email.policy import default as default_policy
from typing import Any, Dict, List

from ..base import ConnectorError

_PREVIEW_CHARS = 8_000
_CONNECT_TIMEOUT = 10.0

_HEADER_FIELDS = "(FROM SUBJECT DATE MESSAGE-ID)"


def _connect(config: Dict[str, Any]) -> imaplib.IMAP4:
    host = str(config.get("imap_host") or "").strip()
    port = int(config.get("imap_port") or 993)
    user = str(config.get("imap_user") or "").strip()
    password = str(config.get("password") or "")
    use_ssl = bool(config.get("imap_ssl", True))
    if not host or not user or not password:
        raise ConnectorError(f"mail connector misconfigured (kind={config.get('kind')})")
    try:
        if use_ssl:
            conn = imaplib.IMAP4_SSL(host, port, timeout=_CONNECT_TIMEOUT)
        else:
            conn = imaplib.IMAP4(host, port)
            conn.sock.settimeout(_CONNECT_TIMEOUT)
    except socket.error as exc:
        raise ConnectorError(f"IMAP connect failed: {exc}") from exc
    try:
        conn.login(user, password)
    except imaplib.IMAP4.error as exc:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
        raise ConnectorError(f"IMAP login failed: {exc}") from exc
    return conn


def _close(conn: imaplib.IMAP4) -> None:
    try:
        conn.logout()
    except Exception:  # noqa: BLE001
        conn.shutdown()


def _join_data(data: List[bytes]) -> bytes:
    out = bytearray()
    for part in data:
        if isinstance(part, (bytes, bytearray)):
            out.extend(part)
        elif part is not None:
            try:
                out.extend(str(part).encode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
    return bytes(out)


def _is_ok(typ) -> bool:
    if isinstance(typ, bytes):
        return typ.upper() == b"OK"
    return str(typ).upper() == "OK"


import re


def _extract_literals(data: List[bytes]) -> List[bytes]:
    """Get the literal body parts of an IMAP FETCH response.

    imaplib represents ``{n}`` literals as ``(declaration, literal_bytes)``
    tuples nested in the data list; plain parts are bytes.  Flatten into a
    single byte stream, then pull the ``n`` bytes that follow each ``{n}``.
    """
    flat: List[bytes] = []

    def walk(items):
        for item in items:
            if isinstance(item, (tuple, list)):
                walk(item)
            elif isinstance(item, bytes):
                flat.append(item)
            elif isinstance(item, str):
                flat.append(item.encode("utf-8", "replace"))

    walk(data)
    literals: List[bytes] = []
    for i, chunk in enumerate(flat):
        # imaplib ends the declaration chunk with `{<size>` (the trailing `}`
        # is consumed while reading the literal stream).
        m = re.search(rb"\{(\d+)\}\s*$", chunk) or re.search(rb"\{(\d+)$", chunk)
        if m and i + 1 < len(flat):
            size = int(m.group(1))
            nxt = flat[i + 1]
            if size <= len(nxt):
                literals.append(nxt[:size])
    return literals


def imap_test(config: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    try:
        conn = _connect(config)
        folders = list_folders(conn)
        conn.select("INBOX", readonly=True)
        _close(conn)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)}
    return {
        "ok": True,
        "message": f"IMAP login OK ({(time.time() - start) * 1000:.0f} ms), "
                   f"{len(folders)} folders, INBOX {'present' if any(f['name'].upper() == 'INBOX' for f in folders) else 'missing'}",
    }


def select(conn: imaplib.IMAP4, folder: str) -> None:
    try:
        raws = conn.select(folder, readonly=True)
    except imaplib.IMAP4.error as exc:
        raise ConnectorError(f"IMAP SELECT '{folder}' failed: {exc}") from exc
    if not raws or not _is_ok(raws[0]):
        raise ConnectorError(f"IMAP SELECT '{folder}' failed: {raws}")


def list_folders(conn: imaplib.IMAP4) -> List[Dict[str, str]]:
    typ, data = conn.list()
    if not _is_ok(typ):
        raise ConnectorError(f"IMAP LIST failed: {typ} {_join_data(data).decode('utf-8', 'replace')[:200]}")
    folders: List[Dict[str, str]] = []
    for line in data:
        if not isinstance(line, bytes):
            continue
        text = line.decode("utf-8", "replace")
        # e.g. "(\HasNoChildren) "/" "INBOX"
        parts = text.split()
        if len(parts) >= 3:
            folders.append({"name": parts[-1].strip('"'), "flags": parts[0]})
    return folders


def search_uids(conn: imaplib.IMAP4, folder: str, query: str, limit: int) -> List[str]:
    select(conn, folder)
    try:
        typ, data = conn.uid("SEARCH", None, query or "ALL")
    except imaplib.IMAP4.error as exc:
        raise ConnectorError(f"IMAP UID SEARCH failed: {exc}") from exc
    if not _is_ok(typ):
        raise ConnectorError(f"IMAP UID SEARCH failed: {typ}")
    uids = _join_data(data).decode("utf-8", "replace").split()
    return uids[::-1][:limit]


def fetch_headers(conn: imaplib.IMAP4, uid: str) -> Dict[str, Any]:
    typ, data = conn.uid("FETCH", uid, f"(BODY.PEEK[{_HEADER_FIELDS}] FLAGS)")
    if not _is_ok(typ):
        raise ConnectorError(f"IMAP FETCH failed on uid {uid}: {typ}")
    literals = _extract_literals(data)
    msg_text = literals[0] if literals else _join_data(data)
    msg = message_from_bytes(msg_text or b"", policy=default_policy)
    return {
        "uid": uid,
        "from": str(msg.get("From", "")),
        "subject": str(msg.get("Subject", "")),
        "date": str(msg.get("Date", "")),
        "message_id": str(msg.get("Message-ID", "")),
        "flags": _flags_probe(data, uid),
    }


def _flags_probe(data: List[bytes], uid: str) -> str:
    for chunk in data:
        if not isinstance(chunk, bytes):
            continue
        text = chunk.decode("utf-8", "replace")
        if "FLAGS" in text.upper():
            start = text.upper().find("FLAGS")
            if start >= 0:
                return text[start:]
    return str(uid)


def fetch_body(conn: imaplib.IMAP4, uid: str, preview_chars: int = _PREVIEW_CHARS) -> Dict[str, Any]:
    meta = fetch_headers(conn, uid)
    typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
    if not _is_ok(typ):
        raise ConnectorError(f"IMAP FETCH failed on uid {uid}: {typ}")
    literals = _extract_literals(data)
    msg_text = literals[0] if literals else _join_data(data)
    msg = message_from_bytes(msg_text or b"", policy=default_policy)
    body_parts: List[str] = []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() in ("text/plain", "text/html"):
            try:
                payload = part.get_content()
            except Exception:  # noqa: BLE001
                payload = ""
            if isinstance(payload, str):
                body_parts.append(payload)
    text = "\n".join(body_parts)
    meta["body"] = text[:preview_chars]
    meta["body_preview"] = text[:128]
    meta["truncated"] = len(text) > preview_chars
    return meta