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

import ipaddress
import os
import socketserver
import ssl as _ssl
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
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
                self._send(b"250-AUTH PLAIN")
                self._send(b"250 PIPELINING")
            elif verb == b"AUTH":
                self._send(b"235 2.7.0 Authentication successful")
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
# SMTP with STARTTLS / SMTP_SSL support
# --------------------------------------------------------------------------- #
class _SMTPHandlerSTARTTLS(_SMTPHandler):
    """SMTP handler that supports the STARTTLS command.

    After the client issues STARTTLS, the handler wraps the socket with SSL
    (server-side) and the conversation continues encrypted.
    """

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
                self._send(b"250-AUTH PLAIN")
                self._send(b"250-STARTTLS")
                self._send(b"250 PIPELINING")
            elif verb == b"STARTTLS":
                self._send(b"220 Ready to start TLS")
                self.request = self.server._ssl_context.wrap_socket(  # type: ignore[attr-defined]
                    self.request, server_side=True
                )
                # Recreate file objects over the encrypted socket.
                self.rfile = self.request.makefile("rb")
                self.wfile = self.request.makefile("wb")
            elif verb == b"AUTH":
                self._send(b"235 2.7.0 Authentication successful")
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


class FakeSMTPServerSTARTTLS(FakeSMTPServer):
    """Fake SMTP server that supports STARTTLS **and** SMTP_SSL.

    Generates a self-signed certificate (via ``cryptography``) for
    ``localhost`` / ``127.0.0.1``.  Tests that want the client to trust this
    cert should monkey-patch ``ssl.create_default_context`` to return
    ``fake.client_ssl_context``:

    .. code-block:: python

        monkeypatch.setattr(
            alerting_system.ssl, "create_default_context",
            lambda: fake.client_ssl_context,
        )
    """

    def __init__(self, use_ssl: bool = False):
        self.use_ssl = use_ssl
        cert_pem, key_pem = self._generate_self_signed_cert()
        # Write combined cert+key to a temp file (load_cert_chain needs a path).
        self._cert_fd, self._cert_path = tempfile.mkstemp(suffix=".pem")
        with os.fdopen(self._cert_fd, "wb") as f:
            f.write(cert_pem + key_pem)
        # Server-side SSL context
        self._ssl_context = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
        self._ssl_context.load_cert_chain(self._cert_path)
        # Client-side SSL context that trusts the self-signed cert
        self._client_context = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
        self._client_context.load_verify_locations(cadata=cert_pem.decode("ascii"))
        self._client_context.check_hostname = False
        self._client_context.verify_mode = _ssl.CERT_REQUIRED
        # Initialise parent server, then swap the handler class
        super().__init__()
        self.RequestHandlerClass = _SMTPHandlerSTARTTLS

    @staticmethod
    def _generate_self_signed_cert() -> tuple[bytes, bytes]:
        """Generate a self-signed cert/key pair (PEM) for localhost."""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        return cert_pem, key_pem

    @property
    def client_ssl_context(self) -> _ssl.SSLContext:
        """SSLContext that trusts the self-signed cert (for monkey-patching)."""
        return self._client_context

    def get_request(self):
        """Wrap the socket with SSL if SMTP_SSL mode is enabled."""
        sock, addr = super().get_request()
        if self.use_ssl:
            sock = self._ssl_context.wrap_socket(sock, server_side=True)
        return sock, addr

    def stop(self) -> None:
        super().stop()
        try:
            os.unlink(self._cert_path)
        except (OSError, AttributeError):
            pass


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