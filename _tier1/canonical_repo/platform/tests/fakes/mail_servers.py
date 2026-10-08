"""Realistic minimal IMAP4rev1 + SMTP servers for connector tests.

These are REAL protocol servers (TCP sockets on 127.0.0.1) speaking the actual
IMAP/SMTP wire dialects that `imaplib` and `smtplib` use, so the connector
tests exercise the same code path a real mailbox (Gmail/Outlook/iCloud) would:
greeting, tagged commands, literals, `* SEARCH`, `* FETCH (...)` with
`{n}` literal bodies, EHLO, MAIL FROM / RCPT TO / DATA / ., etc.

They are intentionally small but protocol-correct for the subset the IMAP/SMTP
connectors use.  Messages are held in memory (nothing touches disk).
"""

from __future__ import annotations

import socketserver
import threading
import time
from email.utils import formatdate, make_msgid
from typing import Dict, List

CRLF = b"\r\n"


def _seed_messages() -> List[Dict]:
    now = formatdate(time.time(), localtime=False)
    return [
        {
            "uid": 1,
            "fromfld": "Alice <alice@example.com>",
            "subject": "Project status update",
            "date": now,
            "message_id": make_msgid(),
            "body": "Hi, the release is on track. We shipped today. Regards, Alice.\r\n",
            "flags": "",
        },
        {
            "uid": 2,
            "fromfld": "Bob <bob@example.com>",
            "subject": "Invoice attached",
            "date": now,
            "message_id": make_msgid(),
            "body": "Please find the invoice for March below.\r\nTotal: 1200 USD.\r\n",
            "flags": r"\Seen",
        },
        {
            "uid": 3,
            "fromfld": "Carol <carol@example.com>",
            "subject": "Meeting rescheduled",
            "date": now,
            "message_id": make_msgid(),
            "body": "The sync moves to Friday 10:00. Bring the numbers.\r\n",
            "flags": "",
        },
    ]


def _raw_headers(m: Dict) -> bytes:
    lines = [
        f"From: {m['fromfld']}",
        f"Subject: {m['subject']}",
        f"Date: {m['date']}",
        f"Message-ID: {m['message_id']}",
    ]
    return (CRLF.join(s.encode("utf-8") for s in lines) + CRLF)


def _raw_full(m: Dict) -> bytes:
    return _raw_headers(m) + CRLF + m["body"].encode("utf-8")


# --------------------------------------------------------------------------- #
# SMTP
# --------------------------------------------------------------------------- #
class _SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:  # noqa: C901 - tiny protocol interpreter
        sink = self.server.sink  # type: ignore[attr-defined]
        self._send(b"220 fake-smtp ESMTP ready")
        while True:
            line = self._readline()
            if line is None:
                return
            verb, _, rest = line.partition(b" ")
            verb = verb.upper()
            rest = rest.rstrip(b"\r\n")
            if verb in (b"HELO", b"EHLO"):
                self._send(b"250-fake-smtp")
                self._send(b"250 PIPELINING")
            elif verb == b"MAIL":
                self._send(b"250 OK")
            elif verb == b"RCPT":
                self._send(b"250 OK")
            elif verb == b"DATA":
                self._send(b"354 End data with <CR><LF>.<CR><LF>")
                data_parts = [self._readline()]
                while True:
                    chunk = self._readline()
                    if chunk == b".":
                        break
                    data_parts.append(chunk)
                sink.append(b"\r\n".join(data_parts))
                self._send(b"250 OK message accepted")
            elif verb == b"RSET":
                self._send(b"250 OK")
            elif verb == b"NOOP":
                self._send(b"250 OK")
            elif verb == b"QUIT":
                self._send(b"221 Bye")
                return
            else:
                self._send(b"500 Command unrecognized")

    def _readline(self) -> bytes | None:
        data = self.rfile.readline()
        if not data:
            return None
        return data.rstrip(b"\r\n")

    def _send(self, line: bytes) -> None:
        self.wfile.write(line + CRLF)
        self.wfile.flush()


class FakeSMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    sink: List[bytes] = []

    def __init__(self):
        self.sink = []
        super().__init__(("127.0.0.1", 0), _SMTPHandler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def start(self) -> "FakeSMTPServer":
        self._t = threading.Thread(target=self.serve_forever, daemon=True)
        self._t.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()


# --------------------------------------------------------------------------- #
# IMAP4rev1
# --------------------------------------------------------------------------- #
class _IMAPHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:  # noqa: C901 - tiny protocol interpreter
        msgs = self.server.msgs  # type: ignore[attr-defined]
        folders = self.server.folders  # type: ignore[attr-defined]
        self._send(b"* OK fake-imap ready")
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            try:
                tag, _sep, rest = raw.rstrip(b"\r\n").partition(b" ")
                cmd, _, args = rest.partition(b" ")
                cmd = cmd.decode("ascii", "replace").upper()
            except Exception:  # noqa: BLE001
                self._send(b"* BAD parse error")
                continue
            args = args.strip()
            if cmd == "CAPABILITY":
                self._send(b"* CAPABILITY IMAP4rev1")
                self._ok(tag, "CAPABILITY completed")
            elif cmd == "NOOP":
                self._ok(tag, "NOOP completed")
            elif cmd == "LOGIN":
                self._ok(tag, "LOGIN completed")
            elif cmd == "LOGOUT":
                self._send(b"* BYE logging out")
                self._ok(tag, "LOGOUT completed")
                return
            elif cmd == "LIST":
                for f in folders:
                    self._send(f'* LIST (\\HasNoChildren) "/" "{f}"'.encode("utf-8"))
                self._ok(tag, "LIST completed")
            elif cmd == "SELECT":
                self._send(b"* 3 EXISTS")
                self._send(b"* 0 RECENT")
                self._send(b"* FLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft)")
                self._send(b"* OK [UIDVALIDITY 42] UIDs valid")
                self._ok(tag, "SELECT completed")
            elif cmd == "UID":
                self._uid(tag, args, msgs)
            else:
                self._send(b"* BAD unsupported command")
                self._ok(tag, "BAD")

    def _uid(self, tag: bytes, args: bytes, msgs: List[Dict]) -> None:
        sub_cmd, _, sub_args = args.partition(b" ")
        sub = sub_cmd.decode("ascii", "replace").upper()
        if sub == "SEARCH":
            uids = " ".join(str(m["uid"]) for m in msgs)
            self._send(f"* SEARCH {uids}".encode("utf-8"))
            self._ok(tag, "UID SEARCH completed")
            return
        if sub == "FETCH":
            rest = sub_args.split(b" ", 1)[1] if b" " in sub_args else b""
            spec = rest.upper()
            target = sub_args.partition(b" ")[0].decode("ascii", "replace")
            try:
                uid = int(target)
            except ValueError:
                self._ok(tag, "UID FETCH failed")
                return
            m = next((x for x in msgs if x["uid"] == uid), None)
            if m is None:
                self._ok(tag, "UID FETCH completed")
                return
            seq = msgs.index(m) + 1
            headers_only = b"HEADER.FIELDS" in spec.upper()
            if headers_only:
                payload = _raw_headers(m)
                section_label = b"BODY[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]"
            else:
                payload = _raw_full(m)
                section_label = b"BODY[]"
            self._send(b"* %d FETCH (FLAGS (%s) %s {%d}" % (
                seq, m["flags"].encode("ascii"), section_label, len(payload)))
            self.wfile.write(payload)
            self.wfile.write(b")")
            self.wfile.write(CRLF)
            self.wfile.flush()
            self._ok(tag, "UID FETCH completed")
        else:
            self._ok(tag, "UID command failed")

    def _ok(self, tag: bytes, text: str, bracket: bool = False) -> None:
        line = f"{tag.decode('ascii')} OK {text}"
        self._send(line.encode("ascii"))

    def _send(self, data: bytes) -> None:
        self.wfile.write(data + CRLF)
        self.wfile.flush()


class FakeIMAPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.msgs = _seed_messages()
        self.folders = ["INBOX", "Sent", "Trash"]
        super().__init__(("127.0.0.1", 0), _IMAPHandler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    def start(self) -> "FakeIMAPServer":
        self._t = threading.Thread(target=self.serve_forever, daemon=True)
        self._t.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()