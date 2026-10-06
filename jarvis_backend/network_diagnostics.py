"""Browser Network Diagnostics — stdlib-only networking and diagnostics layer.

This module implements the JARVIS Browser Network Diagnostics Engine (spec §51).
It provides:

- A normalized browser error taxonomy (``BrowserErrorCategory``)
- Exception-to-taxonomy classification (``classify_urllib_exception``)
- DNS diagnostics via the system resolver and optional alternate-resolver
  UDP probing (does NOT modify OS DNS settings)
- Proxy diagnostics (detection + reachability, non-destructive)
- Transport / TLS / HTTP diagnostics
- A ``NavigationDiagnoser`` orchestrator implementing the diagnostic chain:
    Navigation failed -> Classify -> DNS check -> system resolver ->
    alternate resolver -> proxy state -> network connectivity -> retry policy
    -> final diagnosis
- ``BrowserHealthStatus`` with real, non-faked health checks
- Bounded recovery (no infinite retry loops)

Design constraints (enforced throughout):
- Python stdlib only; no new pip packages.
- NEVER auto-change OS DNS settings.
- NEVER disable firewall / AV / TLS verification.
- NEVER install certificates.
- NEVER modify system routes.
- Never hard-code YouTube (or any specific domain) as a special case.
- Never fake a PASS on health checks.
"""
from __future__ import annotations

import base64
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Normalized error taxonomy (spec §51)
# ---------------------------------------------------------------------------

class BrowserErrorCategory(str, Enum):
    """Normalized browser error taxonomy.

    Every navigation failure is mapped into one of these categories.
    The frontend never sees the raw OS exception; it sees a stable code.
    """
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"
    DNS_TIMEOUT = "DNS_TIMEOUT"
    DNS_SERVER_UNAVAILABLE = "DNS_SERVER_UNAVAILABLE"
    PROXY_RESOLUTION_FAILED = "PROXY_RESOLUTION_FAILED"
    PROXY_CONNECTION_FAILED = "PROXY_CONNECTION_FAILED"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    TLS_HANDSHAKE_FAILED = "TLS_HANDSHAKE_FAILED"
    CERTIFICATE_INVALID = "CERTIFICATE_INVALID"
    HTTP_4XX = "HTTP_4XX"
    HTTP_5XX = "HTTP_5XX"
    REDIRECT_LOOP = "REDIRECT_LOOP"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BROWSER_ENGINE_ERROR = "BROWSER_ENGINE_ERROR"
    SERVICE_WORKER_ERROR = "SERVICE_WORKER_ERROR"
    BROWSER_CRASH = "BROWSER_CRASH"
    REMOTE_BROWSER_UNAVAILABLE = "REMOTE_BROWSER_UNAVAILABLE"
    UNKNOWN_NETWORK_ERROR = "UNKNOWN_NETWORK_ERROR"


# ---------------------------------------------------------------------------
# Exception classification
# ---------------------------------------------------------------------------

# Windows socket error codes for DNS (source: winsock.h / WSAGetLastError)
_WIN_DNS_ERROR_CODES = {
    11001: BrowserErrorCategory.DNS_RESOLUTION_FAILED,   # WSAHOST_NOT_FOUND
    11002: BrowserErrorCategory.DNS_RESOLUTION_FAILED,   # WSATRY_AGAIN (non-authoritative)
    11003: BrowserErrorCategory.DNS_RESOLUTION_FAILED,   # WSANO_DATA
    11004: BrowserErrorCategory.DNS_RESOLUTION_FAILED,   # WSANO_UNIFORM_SERVER
}
# POSIX EAI codes (getaddrinfo return values, also on Windows per RFC 2553)
_EAI_ERROR_CODES = {
    -1: "EAI_UNKNOWN",    # EAI_UNKNOWN / EAI_FAIL
    -2: "EAI_AGAIN",      # EAI_AGAIN / WSANO_DATA — retryable DNS
    -8: "EAI_NONAME",     # EAI_NONAME — host not found
    -9: "EAI_BADFLAGS",
    -4: "EAI_FAMILY",     # EAI_FAMILY
    # gaierror errno for "Name or service not known"
    -11001: "EAI_NONAME",
    -11002: "EAI_AGAIN",
}


def classify_urllib_exception(exc: BaseException) -> BrowserErrorCategory:
    """Map a Python exception chain to a normalized ``BrowserErrorCategory``.

    Inspects the exception type and its ``__cause__`` / ``__context__`` chain
    to find the root-cause socket / SSL / HTTP error.
    """
    # Unwrap common wrappers
    root = exc
    seen_chain = [exc]
    while root:
        cause = root.__cause__ or root.__context__
        if cause is None or cause in seen_chain:
            break
        seen_chain.append(cause)
        root = cause

    # urllib.error.HTTPError -> HTTP status classification
    if isinstance(exc, urllib.error.HTTPError):
        return _classify_http_status(exc.code)

    # urllib.error.URLError — inspect the underlying reason
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLError):
            return _classify_ssl_error(reason)
        if isinstance(reason, socket.gaierror):
            return _classify_gaierror(reason)
        if isinstance(reason, ConnectionRefusedError):
            return BrowserErrorCategory.CONNECTION_REFUSED
        if isinstance(reason, TimeoutError) or isinstance(reason, socket.timeout):
            return BrowserErrorCategory.CONNECTION_TIMEOUT
        # URLError with a string reason (e.g. "timed out")
        rstr = str(reason).lower()
        if "gaierror" in rstr or "getaddrinfo" in rstr or "name or service" in rstr or "nodename" in rstr or "not known" in rstr or "11001" in rstr or "11002" in rstr:
            return BrowserErrorCategory.DNS_RESOLUTION_FAILED
        if "connection refused" in rstr:
            return BrowserErrorCategory.CONNECTION_REFUSED
        if "timed out" in rstr or "timeout" in rstr:
            return BrowserErrorCategory.CONNECTION_TIMEOUT
        if "ssl" in rstr or "tls" in rstr:
            return BrowserErrorCategory.TLS_HANDSHAKE_FAILED
        if "certificate" in rstr:
            return BrowserErrorCategory.CERTIFICATE_INVALID
        if "proxy" in rstr or "proxyconnect" in rstr:
            return BrowserErrorCategory.PROXY_CONNECTION_FAILED
        # If root itself is a known type
        if isinstance(root, ssl.SSLError):
            return _classify_ssl_error(root)
        if isinstance(root, socket.gaierror):
            return _classify_gaierror(root)
        if isinstance(root, ConnectionRefusedError):
            return BrowserErrorCategory.CONNECTION_REFUSED
        if isinstance(root, (TimeoutError, socket.timeout)):
            return BrowserErrorCategory.CONNECTION_TIMEOUT
        return BrowserErrorCategory.UNKNOWN_NETWORK_ERROR

    # Direct low-level exceptions (when called outside urllib path)
    if isinstance(root, ssl.SSLError):
        return _classify_ssl_error(root)
    if isinstance(root, socket.gaierror):
        return _classify_gaierror(root)
    if isinstance(root, ConnectionRefusedError):
        return BrowserErrorCategory.CONNECTION_REFUSED
    if isinstance(root, (TimeoutError, socket.timeout)):
        return BrowserErrorCategory.CONNECTION_TIMEOUT
    if isinstance(root, urllib.error.HTTPError):
        return _classify_http_status(root.code)

    return BrowserErrorCategory.UNKNOWN_NETWORK_ERROR


def _classify_gaierror(err: socket.gaierror) -> BrowserErrorCategory:
    """Classify a ``socket.gaierror`` into DNS taxonomy."""
    args = err.args
    if len(args) >= 2:
        errcode = args[0]
        if isinstance(errcode, int) and errcode in _WIN_DNS_ERROR_CODES:
            return _WIN_DNS_ERROR_CODES[errcode]
        desc = args[1] if isinstance(args[1], str) else str(args[1])
        desc_lower = desc.lower()
        if "again" in desc_lower or "try again" in desc_lower:
            return BrowserErrorCategory.DNS_TIMEOUT
        if "noname" in desc_lower or "not known" in desc_lower or "nodename" in desc_lower:
            return BrowserErrorCategory.DNS_RESOLUTION_FAILED
        if "non-existent" in desc_lower or "nxdomain" in desc_lower:
            return BrowserErrorCategory.DNS_RESOLUTION_FAILED
    return BrowserErrorCategory.DNS_RESOLUTION_FAILED


def _classify_ssl_error(err: ssl.SSLError) -> BrowserErrorCategory:
    """Classify an ``ssl.SSLError`` into TLS / certificate taxonomy."""
    msg = str(err).lower()
    if "certificate" in msg or "cert" in msg or "verify" in msg or "untrusted" in msg:
        return BrowserErrorCategory.CERTIFICATE_INVALID
    if "handshake" in msg or "tls" in msg or "alert" in msg:
        return BrowserErrorCategory.TLS_HANDSHAKE_FAILED
    return BrowserErrorCategory.TLS_HANDSHAKE_FAILED


def _classify_http_status(code: int) -> BrowserErrorCategory:
    """Classify an HTTP status code."""
    if 400 <= code < 500:
        if code == 401 or code == 403:
            return BrowserErrorCategory.AUTH_REQUIRED
        if code == 404:
            return BrowserErrorCategory.HTTP_4XX
        if code == 429:
            return BrowserErrorCategory.HTTP_4XX
        return BrowserErrorCategory.HTTP_4XX
    if 500 <= code < 600:
        return BrowserErrorCategory.HTTP_5XX
    return BrowserErrorCategory.HTTP_4XX if code < 500 else BrowserErrorCategory.HTTP_5XX


# ---------------------------------------------------------------------------
# DNS Diagnostics
# ---------------------------------------------------------------------------

# Approved public resolvers for *diagnostic* mode (never auto-applied to system).
_APPROVED_PUBLIC_RESOLVERS = [
    ("8.8.8.8", 53),       # Google
    ("1.1.1.1", 53),       # Cloudflare
    ("9.9.9.9", 53),       # Quad9
]


@dataclass
class DnsRecord:
    """A single DNS record result."""
    rtype: str       # "A", "AAAA", "CNAME", "NS", "MX"
    value: str       # IP address, hostname, etc.
    ttl: int         # seconds, -1 if unknown


@dataclass
class DnsDiagnosticResult:
    """Result of a DNS diagnostic for a single resolver."""
    resolver: str           # "system" or "8.8.8.8:53"
    hostname: str
    available: bool
    latency_ms: Optional[float]
    records: List[DnsRecord] = field(default_factory=list)
    cache_state: str = "unknown"  # "cache_hit", "cache_miss", "unknown"
    error: Optional[str] = None


@dataclass
class DnsDiagnosticsResult:
    """Aggregate DNS diagnostics across resolvers."""
    hostname: str
    system_resolver: Optional[DnsDiagnosticResult] = None
    alternate_resolvers: List[DnsDiagnosticResult] = field(default_factory=list)
    all_available: bool = False
    records: List[DnsRecord] = field(default_factory=list)
    summary: str = ""
    timestamp: str = ""


class _DnsQuery:
    """Minimal DNS query over UDP (stdlib only, no system changes).

    Constructs a raw DNS query packet, sends it to a specified DNS server,
    and parses the response.  This does NOT touch system resolver settings.
    """

    _TYPE_A = 1
    _TYPE_AAAA = 28
    _TYPE_CNAME = 5
    _TYPE_NS = 2
    _TYPE_MX = 15
    _CLASS_IN = 1

    @classmethod
    def _build_query(cls, hostname: str, qtype: int = _TYPE_A) -> Tuple[bytes, int]:
        """Build a DNS query packet. Returns (packet, transaction_id)."""
        import os as _os
        txid = _os.urandom(2)
        # Flags: 0x0100 = standard query, recursion desired
        flags = 0x0100
        header = txid + struct.pack(
            ">HHHHH", flags, 1, 0, 0, 0  # QDCOUNT=1, others 0
        )
        # Question section
        question = b""
        for label in hostname.encode("ascii").split(b"."):
            question += struct.pack("B", len(label)) + label
        question += b"\x00"  # null terminator
        question += struct.pack(">HH", qtype, cls._CLASS_IN)
        return header + question, int.from_bytes(txid, "big")

    @classmethod
    def _parse_name(cls, data: bytes, offset: int) -> Tuple[str, int]:
        """Parse a DNS name starting at *offset*, handling compression."""
        labels: List[str] = []
        jumped = False
        orig_offset = offset
        while True:
            if offset >= len(data):
                break
            length = data[offset]
            if length == 0:
                offset += 1
                if not jumped:
                    orig_offset = offset
                break
            if (length & 0xC0) == 0xC0:
                # Compression pointer
                if offset + 1 >= len(data):
                    break
                pointer = ((length & 0x3F) << 8) | data[offset + 1]
                offset += 2
                if not jumped:
                    orig_offset = offset
                jumped = True
                offset = pointer
                continue
            # Regular label
            if offset + 1 + length > len(data):
                break
            labels.append(data[offset + 1:offset + 1 + length].decode("ascii", errors="replace"))
            offset += 1 + length
        return ".".join(labels), orig_offset

    @classmethod
    def query(cls, dns_server: str, dns_port: int, hostname: str,
              qtype: int = _TYPE_A, timeout: float = 3.0) -> Optional[List[DnsRecord]]:
        """Send a DNS query to *dns_server*:*dns_port* and return records.

        Returns ``None`` if the server is unreachable; returns ``[]`` if
        the name does not exist (NXDOMAIN).
        """
        packet, txid = cls._build_query(hostname, qtype)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(packet, (dns_server, dns_port))
            start = time.monotonic()
            data, _ = sock.recvfrom(512)
            latency = (time.monotonic() - start) * 1000
            return cls._parse_response(data, txid, hostname, latency)
        except socket.timeout:
            return None
        except (OSError, ConnectionError):
            return None
        finally:
            sock.close()

    @classmethod
    def _parse_response(cls, data: bytes, txid: int, hostname: str,
                        latency_ms: float) -> List[DnsRecord]:
        """Parse a DNS response packet into a list of records."""
        if len(data) < 12:
            return []
        # Verify transaction ID
        resp_txid = int.from_bytes(data[:2], "big")
        if resp_txid != txid:
            return []
        # Flags
        flags = struct.unpack(">H", data[2:4])[0]
        rcode = flags & 0xF
        # ANCOUNT
        ancount = struct.unpack(">H", data[6:8])[0]
        if rcode == 3:
            # NXDOMAIN
            return []
        # Parse answer section
        records: List[DnsRecord] = []
        offset = 12  # skip header
        # Skip question section
        for _ in range(struct.unpack(">H", data[4:6])[0]):
            _, offset = cls._parse_name(data, offset)
            offset += 4  # QTYPE (2) + QCLASS (2)
        for _ in range(ancount):
            if offset >= len(data):
                break
            _, offset = cls._parse_name(data, offset)
            if offset + 10 > len(data):
                break
            rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
            offset += 10
            if offset + rdlength > len(data):
                break
            rdata = data[offset:offset + rdlength]
            offset += rdlength
            rec = cls._parse_rdata(rtype, rdata)
            if rec:
                rec = DnsRecord(rtype=cls._type_name(rtype), value=rec.value, ttl=ttl)
                records.append(rec)
        return records

    @staticmethod
    def _type_name(rtype: int) -> str:
        return {1: "A", 28: "AAAA", 5: "CNAME", 2: "NS", 15: "MX"}.get(rtype, str(rtype))

    @classmethod
    def _parse_rdata(cls, rtype: int, rdata: bytes) -> Optional[DnsRecord]:
        try:
            if rtype == cls._TYPE_A and len(rdata) == 4:
                ip = socket.inet_ntoa(rdata)
                return DnsRecord(rtype="A", value=ip, ttl=-1)
            elif rtype == cls._TYPE_AAAA and len(rdata) == 16:
                ip = socket.inet_ntop(socket.AF_INET6, rdata)
                return DnsRecord(rtype="AAAA", value=ip, ttl=-1)
            elif rtype == cls._TYPE_CNAME:
                name, _ = cls._parse_name(rdata, 0)
                return DnsRecord(rtype="CNAME", value=name, ttl=-1)
            elif rtype == cls._TYPE_NS:
                name, _ = cls._parse_name(rdata, 0)
                return DnsRecord(rtype="NS", value=name, ttl=-1)
            elif rtype == cls._TYPE_MX:
                if len(rdata) >= 3:
                    name, _ = cls._parse_name(rdata[2:], 0)
                    return DnsRecord(rtype="MX", value=name, ttl=-1)
        except (struct.error, ValueError, OSError):
            pass
        return None


class DnsDiagnostics:
    """DNS diagnostics using the system resolver and optional alternate resolvers.

    Does NOT modify the OS DNS configuration.  Alternate resolver probing is
    performed via direct UDP queries to the specified DNS servers — the system
    settings remain untouched.
    """

    def __init__(self, alternate_resolvers: Optional[List[Tuple[str, int]]] = None):
        if alternate_resolvers is None:
            self._alternate_resolvers = list(_APPROVED_PUBLIC_RESOLVERS)
        else:
            self._alternate_resolvers = list(alternate_resolvers)

    @staticmethod
    def _system_resolve(hostname: str, timeout: float = 5.0) -> Tuple[Optional[List[DnsRecord]], float, Optional[str]]:
        """Resolve *hostname* via the system resolver, with timing."""
        start = time.monotonic()
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            latency = (time.monotonic() - start) * 1000
            records: List[DnsRecord] = []
            seen_a: set = set()
            seen_aaaa: set = set()
            for family, _socktype, _proto, _canonname, sockaddr in infos:
                ip = sockaddr[0]
                if family == socket.AF_INET and ip not in seen_a:
                    seen_a.add(ip)
                    records.append(DnsRecord(rtype="A", value=ip, ttl=-1))
                elif family == socket.AF_INET6 and ip not in seen_aaaa:
                    seen_aaaa.add(ip)
                    records.append(DnsRecord(rtype="AAAA", value=ip, ttl=-1))
            return records, latency, None
        except socket.gaierror as e:
            latency = (time.monotonic() - start) * 1000
            return None, latency, str(e)
        except socket.timeout:
            latency = (time.monotonic() - start) * 1000
            return None, latency, "DNS query timed out"
        except OSError as e:
            latency = (time.monotonic() - start) * 1000
            return None, latency, f"OS error: {e}"

    def _check_cache_state(self) -> str:
        """Best-effort check of DNS cache state (informational only)."""
        # On Windows, ipconfig /displaydns can show cache; on Unix, systemd-resolved.
        # We do NOT modify anything — just report whether a cache command exists.
        import shutil
        for cmd in ("ipconfig", "systemd-resolve", "resolvectl"):
            if shutil.which(cmd):
                return f"available ({cmd})"
        return "unknown"

    def diagnose(self, hostname: str, use_alternates: bool = True) -> DnsDiagnosticsResult:
        """Run full DNS diagnostics for *hostname*.

        Parameters
        ----------
        hostname
            The hostname to resolve.
        use_alternates
            When True, also probe approved public resolvers via direct UDP.
            The system resolver is always checked first and is authoritative.
        """
        from jarvis_backend.core import now_iso
        ts = now_iso()

        result = DnsDiagnosticsResult(hostname=hostname, timestamp=ts)

        # 1. System resolver (authoritative)
        sys_records, sys_latency, sys_err = self._system_resolve(hostname)
        cache_state = self._check_cache_state()
        if sys_records is not None:
            result.system_resolver = DnsDiagnosticResult(
                resolver="system",
                hostname=hostname,
                available=True,
                latency_ms=round(sys_latency, 2),
                records=sys_records,
                cache_state=cache_state,
                error=None,
            )
            result.records = sys_records
            result.all_available = True
        else:
            result.system_resolver = DnsDiagnosticResult(
                resolver="system",
                hostname=hostname,
                available=False,
                latency_ms=round(sys_latency, 2),
                records=[],
                cache_state=cache_state,
                error=sys_err,
            )

        # 2. Alternate resolvers (diagnostic only, never auto-applied)
        if use_alternates:
            for dns_ip, dns_port in self._alternate_resolvers:
                label = f"{dns_ip}:{dns_port}"
                # Query A and AAAA records
                a_records = _DnsQuery.query(dns_ip, dns_port, hostname, _DnsQuery._TYPE_A, timeout=3.0)
                aaaa_records = _DnsQuery.query(dns_ip, dns_port, hostname, _DnsQuery._TYPE_AAAA, timeout=3.0)
                if a_records is None and aaaa_records is None:
                    # Server unreachable
                    result.alternate_resolvers.append(DnsDiagnosticResult(
                        resolver=label, hostname=hostname, available=False,
                        latency_ms=None, records=[],
                        cache_state="n/a (remote resolver)",
                        error="Resolver unreachable (timeout or network error)",
                    ))
                else:
                    recs: List[DnsRecord] = []
                    if a_records:
                        recs.extend(a_records)
                    if aaaa_records:
                        recs.extend(aaaa_records)
                    # Try to get latency: re-query once and measure
                    start = time.monotonic()
                    _DnsQuery.query(dns_ip, dns_port, hostname, _DnsQuery._TYPE_A, timeout=2.0)
                    lat = (time.monotonic() - start) * 1000
                    result.alternate_resolvers.append(DnsDiagnosticResult(
                        resolver=label, hostname=hostname, available=True,
                        latency_ms=round(lat, 2), records=recs,
                        cache_state="n/a (remote resolver)",
                        error=None,
                    ))
                    if recs and not result.records:
                        result.records = recs

        if result.all_available or any(r.available for r in result.alternate_resolvers):
            result.summary = f"DNS resolved for {hostname} (system resolver available)"
        elif result.system_resolver and not result.system_resolver.available:
            result.summary = f"System DNS resolution failed for {hostname}"
            if result.alternate_resolvers:
                avail = [r for r in result.alternate_resolvers if r.available]
                if avail:
                    result.summary += f"; {len(avail)} alternate resolver(s) succeeded"
                else:
                    result.summary += "; all alternate resolvers also failed"
        else:
            result.summary = f"DNS resolution failed for {hostname}"

        return result


# ---------------------------------------------------------------------------
# Proxy Diagnostics
# ---------------------------------------------------------------------------

class ProxyDiagResult:
    """Result of proxy diagnostics for a URL."""
    # Using a plain dict-friendly structure for JSON serialization
    pass


class ProxyDiagnostics:
    """Proxy diagnostics using ``urllib.request.getproxies()``.

    Detects configured proxies and tests reachability.  Does NOT change
    proxy settings.
    """

    @staticmethod
    def get_proxy_settings() -> Dict[str, Any]:
        """Return current proxy configuration as reported by the OS / env."""
        proxies = urllib.request.getproxies()
        return {
            "proxies": proxies,
            "has_proxy": bool(proxies),
            "proxy_count": len(proxies),
            "sources": list(proxies.keys()),
        }

    @staticmethod
    def check_proxy_for_url(url: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Check whether a proxy applies to *url* and whether it's reachable."""
        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        proxies = urllib.request.getproxies()
        applicable = urllib.request.proxy_bypass(parsed.hostname or "")

        # Find the proxy that would be used for this URL
        proxy_url = urllib.request.getproxies_environment().get(scheme) or proxies.get(scheme)

        result: Dict[str, Any] = {
            "url": url,
            "scheme": scheme,
            "proxy_applies": bool(proxy_url),
            "proxy_bypass": applicable,
            "proxy_url": proxy_url,
        }

        if proxy_url and not applicable:
            # Test reachability of the proxy
            proxy_parsed = urlparse(proxy_url)
            proxy_host = proxy_parsed.hostname
            proxy_port = proxy_parsed.port or 0
            if proxy_host:
                start = time.monotonic()
                try:
                    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
                    latency = (time.monotonic() - start) * 1000
                    sock.close()
                    result["proxy_reachable"] = True
                    result["proxy_latency_ms"] = round(latency, 2)
                    result["proxy_error"] = None
                except Exception as e:
                    result["proxy_reachable"] = False
                    result["proxy_latency_ms"] = None
                    result["proxy_error"] = str(e)[:200]
            else:
                result["proxy_reachable"] = False
                result["proxy_latency_ms"] = None
                result["proxy_error"] = "Could not parse proxy host"
        else:
            result["proxy_reachable"] = None
            result["proxy_latency_ms"] = None
            result["proxy_error"] = None if not proxy_url else "Proxy bypass applies"

        return result


# ---------------------------------------------------------------------------
# Transport / TLS / HTTP Diagnostics
# ---------------------------------------------------------------------------

class TransportDiagnostics:
    """TCP, TLS, and HTTP-level diagnostics (non-destructive)."""

    @staticmethod
    def tcp_probe(host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
        """Attempt a raw TCP connection to *host*:*port*."""
        start = time.monotonic()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            latency = (time.monotonic() - start) * 1000
            sock.close()
            return {
                "host": host,
                "port": port,
                "reached": True,
                "latency_ms": round(latency, 2),
                "error": None,
            }
        except socket.timeout:
            return {
                "host": host, "port": port, "reached": False,
                "latency_ms": None,
                "error": "CONNECTION_TIMEOUT",
            }
        except ConnectionRefusedError:
            return {
                "host": host, "port": port, "reached": False,
                "latency_ms": None,
                "error": "CONNECTION_REFUSED",
            }
        except OSError as e:
            return {
                "host": host, "port": port, "reached": False,
                "latency_ms": None,
                "error": str(e)[:200],
            }

    @staticmethod
    def tls_probe(host: str, port: int = 443, timeout: float = 8.0,
                  server_hostname: Optional[str] = None) -> Dict[str, Any]:
        """Attempt a TLS handshake to inspect certificate and protocol."""
        # NOTE: This uses the DEFAULT ssl context (verification ENABLED).
        # We never disable certificate verification.
        ctx = ssl.create_default_context()
        start = time.monotonic()
        result: Dict[str, Any] = {
            "host": host, "port": port,
            "tls_version": None, "cipher": None,
            "cert_valid": None, "cert_subject": None,
            "cert_issuer": None, "cert_not_after": None,
            "reachable": False, "latency_ms": None,
            "error": None,
        }
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=server_hostname or host) as ssock:
                    latency = (time.monotonic() - start) * 1000
                    result["reachable"] = True
                    result["latency_ms"] = round(latency, 2)
                    result["tls_version"] = ssock.version()
                    cipher = ssock.cipher()
                    if cipher:
                        result["cipher"] = cipher[0]
                    cert = ssock.getpeercert()
                    if cert:
                        result["cert_valid"] = True
                        result["cert_subject"] = dict(x[0] for x in cert.get("subject", []))
                        result["cert_issuer"] = dict(x[0] for x in cert.get("issuer", []))
                        result["cert_not_after"] = cert.get("notAfter")
        except ssl.SSLError as e:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["error"] = str(e)[:300]
            if "certificate" in str(e).lower() or "verify" in str(e).lower():
                result["cert_valid"] = False
        except socket.timeout:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["error"] = "TIMEOUT"
        except ConnectionRefusedError:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["error"] = "CONNECTION_REFUSED"
        except OSError as e:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["error"] = str(e)[:200]
        return result

    @staticmethod
    def http_probe(url: str, timeout: float = 15.0) -> Dict[str, Any]:
        """Perform an HTTP GET and classify the response."""
        req = urllib.request.Request(url, headers={
            "User-Agent": "JARVIS-Browser-Diagnostics/3.0 (+https://jarvis.local)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        })
        start = time.monotonic()
        result: Dict[str, Any] = {
            "url": url,
            "reached": False,
            "status_code": None,
            "content_type": None,
            "content_length": 0,
            "latency_ms": None,
            "redirect_count": 0,
            "final_url": url,
            "error_category": None,
            "error": None,
        }
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                latency = (time.monotonic() - start) * 1000
                result["reached"] = True
                result["status_code"] = resp.status
                result["content_type"] = resp.headers.get("Content-Type", "")
                result["content_length"] = int(resp.headers.get("Content-Length", 0) or 0)
                result["latency_ms"] = round(latency, 2)
                result["final_url"] = resp.geturl()
                result["error_category"] = None
        except urllib.error.HTTPError as e:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["reached"] = True
            result["status_code"] = e.code
            result["error_category"] = classify_urllib_exception(e).value
            result["error"] = f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["error_category"] = classify_urllib_exception(e).value
            result["error"] = str(e.reason)[:300]
        except Exception as e:
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
            result["error_category"] = classify_urllib_exception(e).value
            result["error"] = str(e)[:300]
        return result


# ---------------------------------------------------------------------------
# Navigation Diagnoser (diagnostic chain)
# ---------------------------------------------------------------------------

@dataclass
class NavigationErrorContext:
    """Context for a failed navigation."""
    url: str
    error_message: str = ""
    error_category: Optional[str] = None
    user_agent: str = ""
    privacy_mode: str = "standard"
    tab_id: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class RecoveryPlan:
    """A bounded recovery plan — never infinite retry."""
    action: str           # "retry", "clear_cache", "force_ipv4", "skip_proxy", "switch_resolver", "none"
    max_attempts: int     # bounded, never exceeds this
    description: str
    safe: bool            # safe to auto-apply without user consent


@dataclass
class NavigationDiagnosis:
    """Full diagnosis result for a failed navigation."""
    url: str
    hostname: str
    error_category: BrowserErrorCategory
    dns: Optional[DnsDiagnosticsResult] = None
    proxy: Optional[Dict[str, Any]] = None
    tcp: Optional[Dict[str, Any]] = None
    tls: Optional[Dict[str, Any]] = None
    http: Optional[Dict[str, Any]] = None
    diagnosis: str = ""
    recovery_plan: Optional[RecoveryPlan] = None
    recommendations: List[str] = field(default_factory=list)
    timestamp: str = ""


class NavigationDiagnoser:
    """Orchestrates the diagnostic chain for a failed navigation.

    Implements the chain from spec §51.4:
        Navigation failed -> Classify -> DNS check -> system resolver ->
        alternate resolver -> proxy state -> network connectivity ->
        retry policy -> final diagnosis
    """

    def __init__(self, dns: Optional[DnsDiagnostics] = None,
                 proxy: Optional[ProxyDiagnostics] = None,
                 transport: Optional[TransportDiagnostics] = None):
        self._dns = dns or DnsDiagnostics()
        self._proxy = proxy or ProxyDiagnostics()
        self._transport = transport or TransportDiagnostics()

    @staticmethod
    def _extract_hostname(url: str) -> str:
        parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
        return parsed.hostname or ""

    def diagnose(self, context: NavigationErrorContext) -> NavigationDiagnosis:
        """Run the full diagnostic chain for a failed navigation."""
        from jarvis_backend.core import now_iso
        hostname = self._extract_hostname(context.url)
        ts = now_iso()

        # Step 1: Classify error from the exception/message
        if context.error_category:
            try:
                category = BrowserErrorCategory(context.error_category)
            except ValueError:
                category = BrowserErrorCategory.UNKNOWN_NETWORK_ERROR
        elif context.error_message:
            # Try to infer category from the error message
            msg_lower = context.error_message.lower()
            if "gaierror" in msg_lower or "getaddrinfo" in msg_lower or "name or service" in msg_lower or "nodename" in msg_lower or "not known" in msg_lower or "11001" in msg_lower or "11002" in msg_lower:
                category = BrowserErrorCategory.DNS_RESOLUTION_FAILED
            elif "connection refused" in msg_lower:
                category = BrowserErrorCategory.CONNECTION_REFUSED
            elif "timed out" in msg_lower or "timeout" in msg_lower:
                category = BrowserErrorCategory.CONNECTION_TIMEOUT
            elif "ssl" in msg_lower or "tls" in msg_lower:
                category = BrowserErrorCategory.TLS_HANDSHAKE_FAILED
            elif "certificate" in msg_lower or "cert" in msg_lower:
                category = BrowserErrorCategory.CERTIFICATE_INVALID
            elif "proxy" in msg_lower:
                category = BrowserErrorCategory.PROXY_CONNECTION_FAILED
            elif "40" in msg_lower or "404" in msg_lower or "429" in msg_lower:
                category = BrowserErrorCategory.HTTP_4XX
            elif "50" in msg_lower or "500" in msg_lower or "502" in msg_lower or "503" in msg_lower:
                category = BrowserErrorCategory.HTTP_5XX
            else:
                category = BrowserErrorCategory.UNKNOWN_NETWORK_ERROR
        else:
            category = BrowserErrorCategory.UNKNOWN_NETWORK_ERROR

        diagnosis = NavigationDiagnosis(
            url=context.url,
            hostname=hostname,
            error_category=category,
            timestamp=ts,
        )

        # Step 2: DNS resolution check
        if hostname:
            diagnosis.dns = self._dns.diagnose(hostname, use_alternates=True)

        # Step 3: Proxy state check
        diagnosis.proxy = self._proxy.check_proxy_for_url(context.url)

        # Step 4: Network connectivity check (TCP + TLS)
        if hostname:
            port = 443 if urlparse(context.url).scheme in ("", "https") else 80
            # TCP probe
            diagnosis.tcp = self._transport.tcp_probe(hostname, port)

            # TLS probe (only for HTTPS)
            if urlparse(context.url).scheme in ("", "https"):
                diagnosis.tls = self._transport.tls_probe(hostname, port)

            # HTTP probe
            diagnosis.http = self._transport.http_probe(context.url)

        # Step 5: Build final diagnosis
        diagnosis.diagnosis = self._build_diagnosis(diagnosis, category, hostname)

        # Step 6: Recovery plan (bounded)
        diagnosis.recovery_plan = self._build_recovery_plan(diagnosis, category)

        # Step 7: Recommendations
        diagnosis.recommendations = self._build_recommendations(diagnosis)

        return diagnosis

    def _build_diagnosis(self, d: NavigationDiagnosis, category: BrowserErrorCategory, hostname: str) -> str:
        """Build a human-readable diagnosis string."""
        parts: List[str] = []

        parts.append(f"Navigation to {d.url} failed.")

        # DNS analysis
        if d.dns:
            if d.dns.system_resolver and d.dns.system_resolver.available:
                parts.append(f"System DNS resolved {hostname} successfully ({len(d.dns.records)} record(s)).")
            elif d.dns.system_resolver:
                parts.append(f"System DNS resolution FAILED for {hostname}.")
            if d.dns.alternate_resolvers:
                working = [r for r in d.dns.alternate_resolvers if r.available]
                parts.append(f"Alternate resolvers: {len(working)}/{len(d.dns.alternate_resolvers)} reachable.")

        # Proxy analysis
        if d.proxy:
            if d.proxy.get("proxy_applies"):
                parts.append(f"Proxy applies to this URL ({d.proxy.get('proxy_url', 'unknown')}).")
                if d.proxy.get("proxy_reachable") is False:
                    parts.append("Proxy server is NOT reachable.")
            else:
                parts.append("No proxy applies to this URL.")

        # TCP analysis
        if d.tcp:
            if d.tcp.get("reached"):
                parts.append(f"TCP connection to {hostname}:{d.tcp.get('port')} succeeded ({d.tcp.get('latency_ms')}ms).")
            else:
                parts.append(f"TCP connection to {hostname}:{d.tcp.get('port')} failed: {d.tcp.get('error')}.")

        # TLS analysis
        if d.tls:
            if d.tls.get("reachable"):
                parts.append(f"TLS handshake succeeded (version: {d.tls.get('tls_version')}).")
            else:
                parts.append(f"TLS handshake failed: {d.tls.get('error')}.")

        # HTTP analysis
        if d.http:
            if d.http.get("reached"):
                sc = d.http.get("status_code")
                parts.append(f"HTTP response: status {sc}.")
            else:
                parts.append(f"HTTP request failed: {d.http.get('error')}.")

        parts.append(f"Root cause classification: {category.value}")
        return " ".join(parts)

    def _build_recovery_plan(self, d: NavigationDiagnosis, category: BrowserErrorCategory) -> RecoveryPlan:
        """Build a bounded recovery plan based on the diagnosis."""
        if category == BrowserErrorCategory.DNS_RESOLUTION_FAILED:
            # Only suggest alternate resolver, never change system DNS
            return RecoveryPlan(
                action="switch_resolver",
                max_attempts=1,
                description="DNS resolution failed on system resolver. Alternate resolvers were checked during diagnosis. "
                            "Suggest using an alternate DNS provider (do NOT change system DNS automatically).",
                safe=False,  # requires user consent since it implies changing DNS
            )
        if category == BrowserErrorCategory.CONNECTION_REFUSED:
            return RecoveryPlan(
                action="retry",
                max_attempts=2,
                description="Connection was refused. The server may be down or a firewall is blocking the port.",
                safe=True,
            )
        if category == BrowserErrorCategory.CONNECTION_TIMEOUT:
            return RecoveryPlan(
                action="retry",
                max_attempts=2,
                description="Connection timed out. Possible network congestion or firewall.",
                safe=True,
            )
        if category == BrowserErrorCategory.TLS_HANDSHAKE_FAILED:
            return RecoveryPlan(
                action="retry",
                max_attempts=1,
                description="TLS handshake failed. The server may be misconfigured or blocking the client.",
                safe=True,
            )
        if category == BrowserErrorCategory.CERTIFICATE_INVALID:
            return RecoveryPlan(
                action="none",
                max_attempts=0,
                description="TLS certificate is invalid. Do NOT disable TLS verification. "
                            "Check system clock and whether this is expected (e.g., self-signed cert).",
                safe=False,  # never auto-skip cert verification
            )
        if category in (BrowserErrorCategory.HTTP_4XX, BrowserErrorCategory.HTTP_5XX):
            if category == BrowserErrorCategory.HTTP_4XX:
                return RecoveryPlan(
                    action="none",
                    max_attempts=0,
                    description=f"HTTP client error (4xx). The resource is unavailable or access is denied.",
                    safe=True,
                )
            return RecoveryPlan(
                action="retry",
                max_attempts=2,
                description="HTTP server error (5xx). The server is temporarily unavailable.",
                safe=True,
            )
        if category == BrowserErrorCategory.PROXY_CONNECTION_FAILED:
            return RecoveryPlan(
                action="clear_cache",
                max_attempts=1,
                description="Proxy connection failed. Check proxy configuration.",
                safe=False,
            )
        if category == BrowserErrorCategory.BROWSER_CRASH:
            return RecoveryPlan(
                action="retry",
                max_attempts=1,
                description="Browser engine crashed. Creating a new browser session is recommended.",
                safe=True,
            )
        return RecoveryPlan(
            action="retry",
            max_attempts=2,
            description="Unknown network error. Retry with exponential backoff.",
            safe=True,
        )

    def _build_recommendations(self, d: NavigationDiagnosis) -> List[str]:
        """Build non-destructive recommendations."""
        recs: List[str] = []
        cat = d.error_category

        if cat == BrowserErrorCategory.DNS_RESOLUTION_FAILED:
            recs.append("Check that the hostname is correct.")
            if d.dns and d.dns.alternate_resolvers:
                working = [f"{r.resolver} ({r.latency_ms}ms)" for r in d.dns.alternate_resolvers if r.available]
                if working:
                    recs.append(f"Alternate DNS resolvers that worked: {', '.join(working)}. "
                                "Consider configuring these as your system DNS manually.")
            recs.append("Do NOT let the browser auto-change your OS DNS settings.")
            recs.append("Flush DNS cache manually if needed (e.g. 'ipconfig /flushdns' on Windows).")

        if cat == BrowserErrorCategory.CONNECTION_REFUSED:
            recs.append("The server actively refused the connection. Verify the host and port are correct.")
            recs.append("Check if a firewall or the server itself is blocking the connection.")

        if cat == BrowserErrorCategory.CONNECTION_TIMEOUT:
            recs.append("The connection timed out before a response was received.")
            recs.append("Check network connectivity and firewall rules.")

        if cat == BrowserErrorCategory.TLS_HANDSHAKE_FAILED:
            recs.append("TLS negotiation failed. The server may not support the protocol version required.")
            recs.append("Do NOT disable TLS verification to work around this.")

        if cat == BrowserErrorCategory.CERTIFICATE_INVALID:
            recs.append("The TLS certificate could not be validated.")
            recs.append("Do NOT disable certificate verification. Check the system date/time.")
            recs.append("If this is a legitimate internal site, add its CA to the system trust store manually.")

        if cat == BrowserErrorCategory.HTTP_4XX:
            recs.append("The server returned a client error. The URL or access credentials may be incorrect.")

        if cat == BrowserErrorCategory.HTTP_5XX:
            recs.append("The server returned a server error. The site may be temporarily unavailable.")

        if cat == BrowserErrorCategory.REDIRECT_LOOP:
            recs.append("The server returned too many redirects. This may be a server-side configuration issue.")

        return recs


# ---------------------------------------------------------------------------
# Browser Health Status
# ---------------------------------------------------------------------------

@dataclass
class HealthCheck:
    name: str
    passed: bool
    detail: str = ""
    latency_ms: Optional[float] = None


@dataclass
class BrowserHealthStatus:
    """Real browser health checks — never faked."""
    checks: List[HealthCheck] = field(default_factory=list)
    overall: str = "unknown"  # "healthy", "degraded", "unhealthy", "unknown"
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": self.overall,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail, "latency_ms": c.latency_ms}
                for c in self.checks
            ],
            "timestamp": self.timestamp,
        }

    @classmethod
    def run(cls) -> "BrowserHealthStatus":
        """Run all real health checks and report honest status."""
        from jarvis_backend.core import now_iso
        checks: List[HealthCheck] = []

        # 1. Store accessibility
        try:
            from jarvis_backend.core import get_store
            store = get_store("browser_tabs")
            _ = store.load()
            checks.append(HealthCheck(
                name="store_accessibility",
                passed=True,
                detail="Browser stores are accessible",
            ))
        except Exception as e:
            checks.append(HealthCheck(
                name="store_accessibility",
                passed=False,
                detail=f"Store error: {e}",
            ))

        # 2. DNS resolver reachability (system resolver)
        start = time.monotonic()
        try:
            socket.getaddrinfo("example.com", None)
            latency = (time.monotonic() - start) * 1000
            checks.append(HealthCheck(
                name="dns_resolver",
                passed=True,
                detail="System DNS resolver resolved example.com",
                latency_ms=round(latency, 2),
            ))
        except Exception as e:
            checks.append(HealthCheck(
                name="dns_resolver",
                passed=False,
                detail=f"DNS resolution failed: {e}",
            ))

        # 3. TCP connectivity to a known-good endpoint (Google DNS 8.8.8.8)
        start = time.monotonic()
        t = TransportDiagnostics.tcp_probe("8.8.8.8", 53, timeout=5.0)
        latency = (time.monotonic() - start) * 1000
        checks.append(HealthCheck(
            name="network_connectivity",
            passed=t.get("reached", False),
            detail=t.get("error") or f"TCP to 8.8.8.8:53 succeeded",
            latency_ms=t.get("latency_ms") or round(latency, 2),
        ))

        # 4. TLS reachability to a known-good HTTPS endpoint
        start = time.monotonic()
        t = TransportDiagnostics.tls_probe("www.google.com", 443, timeout=8.0)
        latency = (time.monotonic() - start) * 1000
        checks.append(HealthCheck(
            name="tls_reachability",
            passed=t.get("reachable", False),
            detail=t.get("error") or f"TLS to www.google.com:443 succeeded (v{t.get('tls_version', '?')})",
            latency_ms=t.get("latency_ms") or round(latency, 2),
        ))

        # 5. Proxy configuration (informational, not pass/fail)
        proxy_info = ProxyDiagnostics.get_proxy_settings()
        checks.append(HealthCheck(
            name="proxy_config",
            passed=True,
            detail=f"Proxies configured: {proxy_info['proxy_count']} ({', '.join(proxy_info['sources']) or 'none'})",
        ))

        # Determine overall status — must be honest
        failed = [c for c in checks if not c.passed]
        if failed:
            overall = "unhealthy"
            # If only informational checks failed, consider degraded
            if all(c.name == "proxy_config" for c in failed):
                overall = "degraded"
        else:
            overall = "healthy"

        return cls(checks=checks, overall=overall, timestamp=now_iso())


# ---------------------------------------------------------------------------
# Bounded recovery
# ---------------------------------------------------------------------------

# Maximum recovery attempts across all strategies — hard upper bound.
_MAX_RECOVERY_ATTEMPTS = 3
_MAX_RECOVERY_TIMEOUT = 30.0


@dataclass
class RecoveryResult:
    """Result of a bounded recovery attempt."""
    success: bool
    strategy: str
    attempts: int
    max_attempts: int
    final_error: Optional[str] = None
    recovered_category: Optional[str] = None
    details: List[str] = field(default_factory=list)


class RecoveryOrchestrator:
    """Orchestrates bounded recovery actions for navigation failures.

    NEVER performs dangerous auto-repair:
    - Does NOT change OS DNS settings
    - Does NOT disable firewall / AV / TLS verification
    - Does NOT install certificates
    - Does NOT modify system routes
    """

    @staticmethod
    def recover(url: str, strategy: str = "auto",
                max_attempts: int = _MAX_RECOVERY_ATTEMPTS,
                timeout: float = _MAX_RECOVERY_TIMEOUT) -> RecoveryResult:
        """Attempt bounded recovery for a failed navigation to *url*.

        Parameters
        ----------
        url
            The URL that failed to navigate.
        strategy
            "auto" for intelligent strategy selection, or a specific:
            "retry", "clear_cache", "force_ipv4", "skip_proxy", "switch_resolver".
        max_attempts
            Hard cap on attempts.  Capped at ``_MAX_RECOVERY_ATTEMPTS``.
        timeout
            Timeout per attempt.
        """
        # Enforce hard bounds
        max_attempts = min(max_attempts, _MAX_RECOVERY_ATTEMPTS)
        max_attempts = max(max_attempts, 1)
        timeout = min(timeout, _MAX_RECOVERY_TIMEOUT)

        details: List[str] = []
        hostname = NavigationDiagnoser._extract_hostname(url)
        parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
        scheme = parsed.scheme or "https"
        port = parsed.port or (443 if scheme == "https" else 80)

        # If strategy is "auto", pick based on initial diagnosis
        if strategy == "auto":
            # Quick initial probe to pick strategy
            tcp = TransportDiagnostics.tcp_probe(hostname, port, timeout=min(timeout, 8.0))
            dns = DnsDiagnostics().diagnose(hostname, use_alternates=False)

            if not dns.system_resolver or not dns.system_resolver.available:
                strategy = "switch_resolver"
            elif not tcp.get("reached"):
                if tcp.get("error") and "refused" in tcp.get("error", "").lower():
                    strategy = "retry"
                else:
                    strategy = "retry"
            else:
                strategy = "retry"

        details.append(f"Recovery strategy: {strategy} (max {max_attempts} attempts)")

        success = False
        final_error = None
        recovered_cat = None

        for attempt in range(1, max_attempts + 1):
            details.append(f"Attempt {attempt}/{max_attempts}")

            if strategy in ("clear_cache",):
                # Clear in-memory DNS cache hint — Python doesn't cache DNS by default.
                # On Windows, suggest manual flush.
                details.append("Cache clear step: Python has no DNS cache; suggest manual 'ipconfig /flushdns'")
                # Retry the fetch
                result = TransportDiagnostics.http_probe(url, timeout=timeout)
                if result.get("reached"):
                    success = True
                    recovered_cat = result.get("error_category")
                    details.append(f"Recovery succeeded after cache clear (HTTP {result.get('status_code')})")
                    break
                else:
                    final_error = result.get("error")
                    details.append(f"Still failed: {final_error}")

            elif strategy == "force_ipv4":
                # Force IPv4 resolution and TCP connection
                try:
                    infos = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
                    family, socktype, proto, _, sockaddr = infos[0]
                    start = time.monotonic()
                    with socket.create_connection(saddr := (sockaddr[0], sockaddr[1]),
                                                  timeout=timeout) as sock:
                        lat = (time.monotonic() - start) * 1000
                    if scheme == "https":
                        tls = TransportDiagnostics.tls_probe(hostname, port, timeout=timeout)
                        if tls.get("reachable"):
                            success = True
                            recovered_cat = None
                            details.append(f"Force-IPv4 TCP + TLS succeeded (latency: {lat:.0f}ms)")
                            break
                    else:
                        success = True
                        recovered_cat = None
                        details.append(f"Force-IPv4 TCP succeeded (latency: {lat:.0f}ms)")
                        break
                except Exception as e:
                    final_error = str(e)[:200]
                    details.append(f"Force-IPv4 attempt failed: {final_error}")

            elif strategy == "skip_proxy":
                # Try a direct HTTP probe bypassing any proxy
                no_proxy_handler = urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(no_proxy_handler)
                req = urllib.request.Request(url, headers={
                    "User-Agent": "JARVIS-Browser-Diagnostics/3.0 (+https://jarvis.local)",
                })
                start = time.monotonic()
                try:
                    with opener.open(req, timeout=timeout) as resp:
                        _ = resp.read(1024)
                        lat = (time.monotonic() - start) * 1000
                    success = True
                    recovered_cat = None
                    details.append(f"Direct (no-proxy) fetch succeeded (latency: {lat:.0f}ms)")
                    break
                except Exception as e:
                    final_error = str(e)[:200]
                    details.append(f"No-proxy attempt failed: {final_error}")

            elif strategy == "switch_resolver":
                # Use alternate resolver for diagnosis only; do NOT change system DNS.
                # Attempt to connect using IPs resolved via alternate resolver.
                dns_diag = DnsDiagnostics()
                # Try alternate resolvers
                for alt_ip, alt_port in _APPROVED_PUBLIC_RESOLVERS:
                    recs = _DnsQuery.query(alt_ip, alt_port, hostname, _DnsQuery._TYPE_A, timeout=3.0)
                    if recs:
                        # Try connecting to the first resolved IP
                        for rec in recs:
                            if rec.rtype == "A":
                                try:
                                    start = time.monotonic()
                                    with socket.create_connection((rec.value, port), timeout=timeout) as sock:
                                        lat = (time.monotonic() - start) * 1000
                                    if scheme == "https":
                                        ctx = ssl.create_default_context()
                                        with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                                            pass
                                    success = True
                                    recovered_cat = None
                                    details.append(f"Connected via alternate resolver {alt_ip} (latency: {lat:.0f}ms)")
                                    break
                                except Exception:
                                    continue
                        if success:
                            break

            elif strategy in ("retry", "auto"):
                # Simple retry with the HTTP probe
                result = TransportDiagnostics.http_probe(url, timeout=timeout)
                if result.get("reached"):
                    success = True
                    recovered_cat = result.get("error_category")
                    details.append(f"Retry succeeded (HTTP {result.get('status_code')}, latency: {result.get('latency_ms')}ms)")
                    break
                else:
                    final_error = result.get("error")
                    details.append(f"Retry still failed: {final_error}")

            elif strategy == "none":
                details.append("No automatic recovery strategy applicable (unsafe to auto-repair).")
                break

            # Exponential backoff between attempts
            if attempt < max_attempts:
                backoff = min(2 ** attempt, 10)
                details.append(f"Backing off {backoff}s before next attempt")
                time.sleep(backoff)

        return RecoveryResult(
            success=success,
            strategy=strategy,
            attempts=min(attempt if 'attempt' in dir() else max_attempts, max_attempts) if not success else attempt,
            max_attempts=max_attempts,
            final_error=final_error if not success else None,
            recovered_category=recovered_cat,
            details=details,
        )


# ---------------------------------------------------------------------------
# Network event recording (persisted to browser_network_events store)
# ---------------------------------------------------------------------------

def record_network_event(event_type: str, url: str, category: BrowserErrorCategory,
                         detail: str = "", severity: str = "info",
                         extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record a network event to the persisted events store."""
    from jarvis_backend.core import get_store, now_iso
    store = get_store("browser_network_events")
    events = store.load()
    if not isinstance(events, list):
        events = []
    event = {
        "id": f"netev-{uuid_hex()}",
        "timestamp": now_iso(),
        "epoch": int(time.time()),
        "type": event_type,
        "url": url,
        "category": category.value if isinstance(category, BrowserErrorCategory) else str(category),
        "severity": severity,
        "detail": detail,
        "extra": extra or {},
    }
    events.append(event)
    if len(events) > 5000:
        events = events[-5000:]
    store.save()
    return event


def record_navigation_timeline(session_id: str, tab_id: Optional[str], url: str,
                               action: str, detail: str = "",
                               category: Optional[str] = None,
                               extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record a navigation timeline entry."""
    from jarvis_backend.core import get_store, now_iso
    store = get_store("browser_navigation_timeline")
    timeline = store.load()
    if not isinstance(timeline, list):
        timeline = []
    entry = {
        "id": f"navtl-{uuid_hex()}",
        "timestamp": now_iso(),
        "epoch": int(time.time()),
        "session_id": session_id,
        "tab_id": tab_id,
        "url": url,
        "action": action,
        "detail": detail,
        "category": category,
        "extra": extra or {},
    }
    timeline.append(entry)
    if len(timeline) > 5000:
        timeline = timeline[-5000:]
    store.save()
    return entry


def uuid_hex() -> str:
    """Generate a short hex string (uses uuid4 if available)."""
    import uuid
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_diagnoser: Optional[NavigationDiagnoser] = None


def get_diagnoser() -> NavigationDiagnoser:
    """Return the shared NavigationDiagnoser singleton."""
    global _default_diagnoser
    if _default_diagnoser is None:
        _default_diagnoser = NavigationDiagnoser()
    return _default_diagnoser
