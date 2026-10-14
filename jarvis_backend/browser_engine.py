"""Browser Engine Abstraction.

Provides a ``BrowserEngine`` abstraction layer that decouples the JARVIS Browser
controller (session management, page understanding, actions) from the underlying
fetch/render engine.  The current production engine (:class:`HttpBrowserEngine`)
wraps the existing urllib-based fetcher, but the abstraction allows future
engines (Playwright, remote browser worker, etc.) to be plugged in without
changing the controller or frontend.

This module also provides:

* :class:`NavigationPresentation` — classifies how a destination should be
  presented (embedded, top-level, isolated window).
* :class:`NavigationFailureClass` — normalised failure reasons when embedding
  or navigation fails (FRAME_BLOCKED, AUTH_REQUIRED, etc.).
* :func:`classify_navigation_context` — determines the safest presentation for
  a given URL **without** hard-coding specific domains.
* :func:`classify_navigation_failure` — maps an exception + URL into a
  ``NavigationFailureClass``.
"""

from __future__ import annotations

import gzip
import html as _html
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone


# --------------------------------------------------------------------------- #
# Navigation presentation classification (spec §7)
# --------------------------------------------------------------------------- #

class NavigationPresentation(str, Enum):
    """How a URL should be presented to the user."""

    EMBEDDED = "embedded"            # Safe to embed in an iframe/panel
    TOP_LEVEL = "top_level"          # Needs a full browser context/tab
    ISOLATED_WINDOW = "isolated"     # Needs a sandboxed, isolated window


@dataclass
class NavigationContext:
    """Result of classifying a URL for presentation."""
    url: str
    presentation: NavigationPresentation
    reason: str = ""
    confidence: float = 0.0  # 0.0 – 1.0
    signals: Dict[str, Any] = field(default_factory=dict)


# Headers that websites use to deny being framed (X-Frame-Options, CSP frame-ancestors).
# We detect these at runtime by examining response headers, but we also maintain a
# conservative heuristic: sites that are known to set strict framing policies or
# require their own browsing context are classified as top-level based on their
# structural complexity, not on a hard-coded domain list.
_SPATIAL_NAVIGATION_HINTS: List[str] = [
    "application",
    "webapp",
    "web appeal",
]


def _parse_url(url: str) -> Optional[urllib.parse.ParseResult]:
    try:
        return urllib.parse.urlparse(url)
    except Exception:
        return None


def classify_navigation_context(url: str, headers: Optional[Dict[str, str]] = None) -> NavigationContext:
    """Determine the safest presentation for a URL.

    Uses HTTP response headers (``X-Frame-Options``, ``Content-Security-Policy``
    ``frame-ancestors``) when available, and structural heuristics otherwise.
    Does NOT hard-code specific domains.

    Classification logic:
      1. If the server explicitly denies framing (X-Frame-Options: DENY/SAMEORIGIN
         with a different origin, or CSP frame-ancestors that excludes the
         embedding origin), classify as TOP_LEVEL.
      2. If the URL requires authentication (HTTP 401 WWW-Authenticate, or
         OAuth/SSO redirects), classify as TOP_LEVEL.
      3. If the content type is not embeddable (PDF, binary, etc.), classify
         as TOP_LEVEL or ISOLATED_WINDOW depending on type.
      4. Otherwise, EMBEDDED is safe.
    """
    parsed = _parse_url(url)
    if not parsed or not parsed.scheme:
        return NavigationContext(
            url=url,
            presentation=NavigationPresentation.TOP_LEVEL,
            reason="Invalid or non-http(s) URL — requires external context",
            confidence=0.95,
            signals={"invalid_url": True},
        )

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return NavigationContext(
            url=url,
            presentation=NavigationPresentation.TOP_LEVEL,
            reason=f"Unsupported protocol: {scheme}. Not an HTTP(S) website.",
            confidence=0.9,
            signals={"unsupported_protocol": True, "scheme": scheme},
        )

    hostname = (parsed.hostname or "").lower()
    signals: Dict[str, Any] = {"hostname": hostname, "scheme": scheme}

    # Check for authentication requirements (spec §7: AUTH_REQUIRED)
    auth_indicators = []
    if headers:
        # Check X-Frame-Options header
        xfo = headers.get("X-Frame-Options", "").strip().upper()
        if xfo == "DENY":
            return NavigationContext(
                url=url,
                presentation=NavigationPresentation.TOP_LEVEL,
                reason="Server denies all framing (X-Frame-Options: DENY)",
                confidence=0.95,
                signals={**signals, "x_frame_options": xfo},
            )
        if xfo == "SAMEORIGIN":
            # If the embedding origin differs from the target, top-level is needed.
            # We conservatively treat SAMEORIGIN as requiring top-level context
            # since JARVIS is a cross-origin embedder.
            return NavigationContext(
                url=url,
                presentation=NavigationPresentation.TOP_LEVEL,
                reason="Server allows same-origin framing only (X-Frame-Options: SAMEORIGIN); JARVIS is cross-origin",
                confidence=0.9,
                signals={**signals, "x_frame_options": xfo},
            )

        # Check CSP frame-ancestors
        csp = headers.get("Content-Security-Policy", "") or headers.get("Frame-Options-Equivalent-CSP", "")
        if "frame-ancestors" in csp.lower():
            # Parse frame-ancestors directive
            parts = csp.split("frame-ancestors")
            if len(parts) > 1:
                ancestors = parts[1].split(";")[0].strip()
                if "none" in ancestors:
                    return NavigationContext(
                        url=url,
                        presentation=NavigationPresentation.TOP_LEVEL,
                        reason="Content-Security-Policy denies all framing (frame-ancestors 'none')",
                        confidence=0.95,
                        signals={**signals, "csp_frame_ancestors": ancestors},
                    )
                if "'self'" in ancestors and hostname and "'self'" in ancestors:
                    # Cross-origin embedding — top-level required
                    return NavigationContext(
                        url=url,
                        presentation=NavigationPresentation.TOP_LEVEL,
                        reason=f"CSP frame-ancestors restricts to self; cross-origin embedding not allowed",
                        confidence=0.9,
                        signals={**signals, "csp_frame_ancestors": ancestors},
                    )

    # Check for authentication requirements (spec §7: AUTH_REQUIRED)
    content_type = (headers or {}).get("Content-Type", "")
    if headers and headers.get("status") in (401, 403):
        auth_indicators.append("HTTP 401/403 response")

    # PDF / binary content: open in top-level context for proper rendering
    if content_type:
        if "application/pdf" in content_type:
            return NavigationContext(
                url=url,
                presentation=NavigationPresentation.TOP_LEVEL,
                reason="PDF content should be rendered in a top-level browser context",
                confidence=0.85,
                signals={**signals, "content_type": content_type},
            )
        if not any(ct in content_type for ct in ("text/html", "text/plain", "application/xhtml")):
            if "json" not in content_type and "xml" not in content_type:
                return NavigationContext(
                    url=url,
                    presentation=NavigationPresentation.ISOLATED_WINDOW,
                    reason=f"Non-HTML content type ({content_type}) — use isolated window",
                    confidence=0.8,
                    signals={**signals, "content_type": content_type},
                )

    # If we have no headers to inspect, use the URL structure heuristic.
    # This handles the case where the classification is being done before
    # any HTTP request is made (e.g., the user types a URL).
    if not headers:
        return NavigationContext(
            url=url,
            presentation=NavigationPresentation.EMBEDDED,
            reason="No framing restrictions detected from headers — safe to embed",
            confidence=0.7,
            signals={**signals, "no_headers_inspected": True},
        )

    return NavigationContext(
        url=url,
        presentation=NavigationPresentation.EMBEDDED,
        reason="No framing restrictions detected — safe to embed",
        confidence=0.85,
        signals={**signals, "auth_indicators": auth_indicators},
    )


# --------------------------------------------------------------------------- #
# Navigation failure classification (spec §7, §8)
# --------------------------------------------------------------------------- #

class NavigationFailureClass(str, Enum):
    """Normalised reasons why a navigation or embedding failed."""

    # Coarse categories (retained for backwards compatibility with existing callers
    # such as the /browser/classify endpoint, which compares == against these).
    FRAME_BLOCKED = "FRAME_BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNSUPPORTED_EMBED = "UNSUPPORTED_EMBED"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    DNS_FAILURE = "DNS_FAILURE"
    TLS_FAILURE = "TLS_FAILURE"
    HTTP_FAILURE = "HTTP_FAILURE"
    BROWSER_ENGINE_FAILURE = "BROWSER_ENGINE_FAILURE"
    REDIRECT_LOOP = "REDIRECT_LOOP"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    PROXY_FAILURE = "PROXY_FAILURE"

    # Granular transport / HTTP codes (spec §51 taxonomy).  Returned by
    # HttpBrowserEngine.fetch_document for precise, actionable failures, so the
    # Research Fabric can distinguish e.g. HTTP_404 from HTTP_429 from HTTP_5XX.
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    TIMEOUT = "TIMEOUT"
    HTTP_401 = "HTTP_401"
    HTTP_403 = "HTTP_403"
    HTTP_404 = "HTTP_404"
    HTTP_429 = "HTTP_429"
    HTTP_5XX = "HTTP_5XX"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    BROWSER_WORKER_UNAVAILABLE = "BROWSER_WORKER_UNAVAILABLE"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    PARSER_FAILED = "PARSER_FAILED"
    SERVICE_WORKER_ERROR = "SERVICE_WORKER_ERROR"
    BROWSER_CRASH = "BROWSER_CRASH"

    @classmethod
    def from_http_status(cls, status_code: int) -> "NavigationFailureClass":
        """Map a concrete HTTP status code to a granular failure class.

        Unlike :meth:`from_browser_error_category` (which only sees the coarse
        ``BrowserErrorCategory``), this preserves the actual status so callers can
        distinguish HTTP_404 from HTTP_429 from HTTP_5XX.
        """
        try:
            code = int(status_code)
        except (TypeError, ValueError):
            return cls.HTTP_FAILURE
        if code == 401:
            return cls.HTTP_401
        if code == 403:
            return cls.HTTP_403
        if code == 404:
            return cls.HTTP_404
        if code == 429:
            return cls.HTTP_429
        if 500 <= code < 600:
            return cls.HTTP_5XX
        if 300 <= code < 400:
            return cls.REDIRECT_LOOP
        if 400 <= code < 500:
            return cls.HTTP_FAILURE
        return cls.HTTP_FAILURE

    @classmethod
    def from_browser_error_category(cls, category_str: str) -> "NavigationFailureClass":
        """Map a BrowserErrorCategory value to a NavigationFailureClass.

        The original coarse mapping is preserved verbatim (the router's
        ``/browser/classify`` endpoint compares ``==`` against these coarse
        values).  Granular codes are reached via :meth:`from_http_status` and
        ``HttpBrowserEngine.fetch_document``.
        """
        mapping = {
            "DNS_RESOLUTION_FAILED": cls.DNS_FAILURE,
            "DNS_TIMEOUT": cls.DNS_FAILURE,
            "DNS_SERVER_UNAVAILABLE": cls.DNS_FAILURE,
            "CONNECTION_TIMEOUT": cls.NETWORK_FAILURE,
            "CONNECTION_REFUSED": cls.NETWORK_FAILURE,
            "TLS_HANDSHAKE_FAILED": cls.TLS_FAILURE,
            "CERTIFICATE_INVALID": cls.TLS_FAILURE,
            "HTTP_4XX": cls.HTTP_FAILURE,
            "HTTP_5XX": cls.HTTP_FAILURE,
            "AUTH_REQUIRED": cls.AUTH_REQUIRED,
            "REDIRECT_LOOP": cls.REDIRECT_LOOP,
            "BROWSER_ENGINE_ERROR": cls.BROWSER_ENGINE_FAILURE,
            "CONTENT_BLOCKED": cls.CONTENT_BLOCKED,
            "PROXY_CONNECTION_FAILED": cls.PROXY_FAILURE,
            "PROXY_RESOLUTION_FAILED": cls.PROXY_FAILURE,
            "UNKNOWN_NETWORK_ERROR": cls.NETWORK_FAILURE,
        }
        return mapping.get(category_str, cls.BROWSER_ENGINE_FAILURE)


def classify_navigation_failure(
    url: str,
    error: Optional[BaseException] = None,
    status_code: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
) -> NavigationFailureClass:
    """Classify the reason why a navigation or embedding failed.

    Examines the HTTP status code, response headers, and the exception chain
    to produce a normalised ``NavigationFailureClass``.
    """
    # Check for HTTP auth challenge
    if status_code == 401 and headers:
        www_auth = headers.get("WWW-Authenticate", "")
        if www_auth:
            return NavigationFailureClass.AUTH_REQUIRED

    if status_code == 403:
        # Check if this is a framing restriction
        csp = (headers or {}).get("Content-Security-Policy", "")
        xfo = (headers or {}).get("X-Frame-Options", "").upper()
        if "frame-ancestors" in csp.lower() or xfo:
            return NavigationFailureClass.FRAME_BLOCKED
        return NavigationFailureClass.AUTH_REQUIRED

    if status_code is not None:
        if status_code in (301, 302, 307, 308):
            return NavigationFailureClass.NETWORK_FAILURE  # redirect chain issue
        if 400 <= status_code < 500:
            return NavigationFailureClass.HTTP_FAILURE
        if status_code >= 500:
            return NavigationFailureClass.HTTP_FAILURE

    # Examine the exception chain
    if error:
        # Map to BrowserErrorCategory first, then to NavigationFailureClass
        try:
            from .network_diagnostics import classify_urllib_exception
            category = classify_urllib_exception(error)
            return NavigationFailureClass.from_browser_error_category(category.value)
        except Exception:
            pass

        # Direct exception type checks
        if isinstance(error, urllib.error.HTTPError):
            if error.code == 401:
                return NavigationFailureClass.AUTH_REQUIRED
            if error.code == 403:
                return NavigationFailureClass.FRAME_BLOCKED
            return NavigationFailureClass.HTTP_FAILURE
        if isinstance(error, ssl.SSLError):
            if "certificate" in str(error).lower():
                return NavigationFailureClass.TLS_FAILURE
            return NavigationFailureClass.TLS_FAILURE
        if isinstance(error, (ConnectionRefusedError, ConnectionError)):
            return NavigationFailureClass.NETWORK_FAILURE
        if isinstance(error, socket.timeout):
            return NavigationFailureClass.NETWORK_FAILURE
        if isinstance(error, socket.gaierror):
            return NavigationFailureClass.DNS_FAILURE

    return NavigationFailureClass.BROWSER_ENGINE_FAILURE


# --------------------------------------------------------------------------- #
# Browser Engine abstraction (spec §4)
# --------------------------------------------------------------------------- #

class BrowserEngine(ABC):
    """Abstract base class for browser engines.

    Implementations provide HTTP fetch capabilities.  Future engines
    (Playwright, remote browser worker) will subclass this and implement
    the same interface.
    """

    name: str = "abstract"

    @abstractmethod
    def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch a URL and return structured page data.

        Returns a dict with keys: url, status, content_type, content_length,
        html, is_html, headers, error (optional).
        """
        ...

    @abstractmethod
    def fetch_with_context(self, url: str, options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], NavigationContext]:
        """Fetch a URL and classify the navigation context for it.

        Returns (page_data, NavigationContext).
        """
        ...

    @property
    def capabilities(self) -> List[str]:
        """Engine capabilities: chat, responses, streaming, etc."""
        return ["http_fetch", "page_extraction"]


class HttpBrowserEngine(BrowserEngine):
    """Default browser engine using urllib (HTTP/HTTPS only, no JS execution).

    This wraps the same logic as the existing ``_fetch_url_sync`` in
    ``router.browser``.  It is a stateless, stdlib-only fetcher suitable as the
    baseline implementation.
    """

    name = "http_browser_engine"

    DEFAULT_HEADERS = {
        "User-Agent": "JARVIS-Browser/3.0 (AI Research Environment; +https://jarvis.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, timeout: float = 15.0, max_bytes: int = 5 * 1024 * 1024):
        self.timeout = timeout
        self.max_bytes = max_bytes

    def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        opts = options or {}
        timeout = opts.get("timeout", self.timeout)
        headers = {**self.DEFAULT_HEADERS, **(opts.get("headers") or {})}

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read()
                if len(data) > self.max_bytes:
                    data = data[:self.max_bytes]
                # Transparently decompress gzip returned raw (some sites, e.g.
                # python.org, gzip regardless of Accept-Encoding header).
                if data[:2] == b"\x1f\x8b":
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                charset = "utf-8"
                for part in content_type.split(";"):
                    part = part.strip()
                    if part.startswith("charset="):
                        charset = part.split("=", 1)[1]
                try:
                    html_content = data.decode(charset or "utf-8")
                except (UnicodeDecodeError, LookupError):
                    html_content = data.decode("utf-8", errors="replace")

                return {
                    "url": resp.geturl(),
                    "status": resp.status,
                    "content_type": content_type,
                    "content_length": len(data),
                    "html": html_content if self._is_html_content(content_type) else "",
                    "is_html": self._is_html_content(content_type),
                    "headers": dict(resp.headers),
                }
        except urllib.error.HTTPError as e:
            return {
                "url": url,
                "status": e.code,
                "content_type": e.headers.get("Content-Type", "") if e.headers else "",
                "content_length": len(e.read() or b"") if hasattr(e, 'read') else 0,
                "html": "",
                "is_html": False,
                "headers": dict(e.headers) if e.headers else {},
                "error": str(e),
            }
        except Exception as e:
            return {
                "url": url,
                "status": None,
                "content_type": "",
                "content_length": 0,
                "html": "",
                "is_html": False,
                "headers": {},
                "error": str(e),
            }

    def fetch_with_context(self, url: str, options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], NavigationContext]:
        page = self.fetch(url, options)
        headers = {k: v for k, v in page.get("headers", {}).items() if isinstance(v, str)}
        if page.get("status"):
            headers["status"] = str(page["status"])
        context = classify_navigation_context(url, headers)
        return page, context

    @staticmethod
    def _is_html_content(content_type: str) -> bool:
        return "text/html" in content_type or "text/plain" in content_type

    # ------------------------------------------------------------------ #
    # Web search (spec §3) + document retrieval/extraction (spec §4)
    # ------------------------------------------------------------------ #

    def search(self, query: str, max_results: int = 10, timeout: float = 15.0) -> List[Dict[str, Any]]:
        """Search the live web via DuckDuckGo Lite with a Wikipedia API fallback.

        Returns normalised result dicts::

            {title, url, snippet, source, domain, rank, provider, metadata}

        Never fabricates results: if both backends fail, raises the underlying
        exception so the caller can classify it.
        """
        max_results = max(1, min(int(max_results), 20))
        results: List[Dict[str, Any]] = []
        successful_backends = 0
        backend_errors: list[Exception] = []

        try:
            results.extend(self._ddg_lite_search(query, max_results, timeout))
            successful_backends += 1
        except Exception as error:
            # DDG may be blocked/interstitial; try the Wikipedia API fallback
            # only if DDG returned nothing or raised.
            backend_errors.append(error)
            results = []

        if len(results) < max_results:
            try:
                results.extend(
                    self._wikipedia_search(query, max_results - len(results), timeout)
                )
                successful_backends += 1
            except Exception as error:
                backend_errors.append(error)

        if successful_backends == 0:
            raise RuntimeError("All configured web-search providers failed") from backend_errors[-1]

        # Normalise ordering + provenance metadata.
        for i, r in enumerate(results):
            r.setdefault("rank", i + 1)
            r.setdefault("provider", "duckduckgo")
            r.setdefault("source", "web")
            r.setdefault("metadata", {})
            r.setdefault("domain", self._domain_of(r.get("url", "")))
        return results[:max_results]

    def _ddg_lite_search(self, query: str, max_results: int, timeout: float) -> List[Dict[str, Any]]:
        """DuckDuckGo Lite parses as single-quoted ``class='result-link'``."""
        url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
        headers = {**self.DEFAULT_HEADERS, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
        html = raw.decode("utf-8", "replace")

        # A successful DDG Lite SERP contains result anchors; an empty/ bot
        # interstitial would yield none — treat that as "no results" rather
        # than returning fabricated data.
        out: List[Dict[str, Any]] = []
        for i, m in enumerate(re.finditer(
                r"<a\s[^>]*\bclass\s*=\s*['\"]"
                r"(?:[^'\"]*\s)?result-link(?:[^'\"]*)['\"][^>]*>(.*?)</a>",
                html, re.I | re.DOTALL)):
            if i >= max_results:
                break
            tag = m.group(0)
            href_m = (re.search(r'\bhref\s*=\s*"([^"]+)"', tag)
                      or re.search(r"\bhref\s*=\s*'([^']+)'", tag))
            if not href_m:
                continue
            href = href_m.group(1)
            uddg = re.search(r"uddg=([^&]+)", href)
            real = urllib.parse.unquote(uddg.group(1)) if uddg else href
            title = _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip())[:120]
            if not real or not real.startswith("http"):
                continue
            out.append({
                "title": title, "url": real[:300], "snippet": "", "source": "web",
                "domain": self._domain_of(real), "rank": i + 1,
                "provider": "duckduckgo",
                "metadata": {"engine": "ddg_lite"},
            })
        snippets = re.findall(
            r"<td[^>]*\bclass\s*=\s*['\"][^'\"]*result-snippet[^'\"]*['\"][^>]*>(.*?)</td>",
            html, re.I | re.DOTALL,
        )
        for i, s in enumerate(snippets[:len(out)]):
            out[i]["snippet"] = re.sub(r"\s+", " ", _html.unescape(
                re.sub(r"<[^>]+>", "", s)).strip())[:300]
        return out

    def _wikipedia_search(self, query: str, max_results: int, timeout: float) -> List[Dict[str, Any]]:
        """Wikipedia REST API: search + build canonical curid URLs."""
        params = {
            "action": "query", "list": "search", "format": "json",
            "srlimit": str(min(max_results, 10)), "srsearch": query,
        }
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        headers = {**self.DEFAULT_HEADERS, "Accept": "application/json"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", "replace"))
        out: List[Dict[str, Any]] = []
        for i, r in enumerate(data.get("query", {}).get("search", [])[:max_results]):
            pid = r.get("pageid")
            out.append({
                "title": _html.unescape(str(r.get("title", "")))[:120],
                "url": (f"https://en.wikipedia.org/?curid={pid}" if pid else ""),
                "snippet": re.sub(r"\s+", " ", _html.unescape(
                    re.sub(r"<[^>]+>", "", str(r.get("snippet", "")))).strip())[:300],
                "source": "web", "domain": "wikipedia.org", "rank": i + 1,
                "provider": "wikipedia",
                "metadata": {"engine": "wikipedia", "pageid": pid},
            })
        return out

    def fetch_document(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Navigate → wait → extract → normalize (spec §4).

        Wraps :meth:`fetch` with content extraction and granular failure
        classification.  Returns a structured document dict::

            {url, final_url, status, content_type, is_html, content_length,
             title, description, text, word_count, structure, navigation_context,
             success, failure, failure_category, headers}
        """
        page = self.fetch(url, options)
        status = page.get("status")
        is_html = bool(page.get("is_html", False))
        body = page.get("html", "") or ""
        headers = {k: v for k, v in page.get("headers", {}).items() if isinstance(v, str)}
        if status:
            headers["status"] = str(status)

        doc: Dict[str, Any] = {
            "url": url,
            "final_url": page.get("url", url),
            "status": status,
            "content_type": page.get("content_type", ""),
            "is_html": is_html,
            "content_length": page.get("content_length", 0),
            "title": "", "description": "", "text": "", "word_count": 0,
            "structure": {}, "navigation_context": None,
            "success": False, "failure": None, "failure_category": None,
            "headers": headers,
        }

        if status is not None and 200 <= status < 400:
            if is_html and body:
                text = self._extract_text(body)
                # Content blocking / soft-block signals
                if text.lower().find("captcha") != -1 or "blocked" in (
                    headers.get("X-Frame-Options", "") or "").lower():
                    doc["failure_category"] = NavigationFailureClass.CONTENT_BLOCKED.value
                    doc["failure"] = "CONTENT_BLOCKED: content blocked by remote"
                    doc["navigation_context"] = self._nav_context(url, headers)
                    return doc
                doc["title"] = self._extract_title(body)
                doc["description"] = self._extract_description(body)
                doc["text"] = text[:20000]
                doc["word_count"] = len(text.split())
                doc["structure"] = self._structure_summary(body, text)
                if not text:
                    doc["failure_category"] = NavigationFailureClass.PARSER_FAILED.value
                    doc["failure"] = "PARSER_FAILED: HTML fetched but no text extracted"
                    doc["success"] = False
                else:
                    doc["success"] = True
            elif body:
                doc["text"] = body[:5000]
                doc["word_count"] = len(body.split())
                doc["success"] = True
            else:
                doc["failure_category"] = NavigationFailureClass.DOWNLOAD_FAILED.value
                doc["failure"] = "DOWNLOAD_FAILED: server returned empty body"
                doc["success"] = False
        else:
            transport_err = page.get("error", "")
            if status is not None and status != 200:
                doc["failure_category"] = self._http_failure_class(status, headers).value
                doc["failure"] = f"HTTP {status}: {transport_err[:160]}"
            else:
                cat = self._classify_transport_error(transport_err)
                doc["failure_category"] = cat.value
                doc["failure"] = f"{cat.value}: {transport_err[:160]}"
            doc["success"] = False

        doc["navigation_context"] = self._nav_context(url, headers)
        return doc

    # ---- extraction / classification helpers (spec §4, §5) ---- #

    @staticmethod
    def _domain_of(url: str) -> str:
        try:
            return (urllib.parse.urlparse(url).netloc or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _extract_text(html: str) -> str:
        if not html:
            return ""
        # Drop script/style blocks, then strip tags.
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.I)
        t = re.sub(r"<[^>]+>", " ", t)
        t = _html.unescape(t)
        return re.sub(r"\s+", " ", t).strip()

    @staticmethod
    def _extract_title(html: str) -> str:
        if not html:
            return ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.I)
        if not m:
            return ""
        return _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip())[:200]

    @staticmethod
    def _extract_description(html: str) -> str:
        if not html:
            return ""
        m = re.search(
            r'''<meta[^>]+name\s*=\s*['"](?:description|og:description)["']\s+content\s*=\s*['"]([^'"]*)['"]''',
            html, re.I,
        )
        if m:
            return _html.unescape(m.group(1))[:300]
        return ""

    @staticmethod
    def _structure_summary(html: str, text: str) -> Dict[str, Any]:
        return {
            "headings": len(re.findall(r"<h[1-6][^>]*>", html, re.I)),
            "paragraphs": len(re.findall(r"<p[^>]*>", html, re.I)),
            "links": len(re.findall(r"<a[^>]+href", html, re.I)),
            "word_count": len(text.split()),
        }

    @staticmethod
    def _http_failure_class(code: int, headers: Dict[str, str]) -> NavigationFailureClass:
        """Granular HTTP failure class, preserving the 401/403 auth nuance."""
        if code == 401 and headers.get("WWW-Authenticate", ""):
            return NavigationFailureClass.AUTH_REQUIRED
        if code == 403:
            csp = (headers.get("Content-Security-Policy", "") or "")
            xfo = (headers.get("X-Frame-Options", "") or "").upper()
            if "frame-ancestors" in csp.lower() or xfo:
                return NavigationFailureClass.FRAME_BLOCKED
            return NavigationFailureClass.HTTP_403
        return NavigationFailureClass.from_http_status(code)

    @staticmethod
    def _classify_transport_error(error_str: str) -> NavigationFailureClass:
        """Classify a urllib transport failure string into a granular code.

        Works from the string form of the exception raised by ``fetch`` (the
        engine stores ``str(exc)`` in ``page["error"]``); precise enough to
        map DNS / TLS / refused / timeout to actionable codes.
        """
        msg = (str(error_str) or "").lower()
        if not msg:
            return NavigationFailureClass.NETWORK_FAILURE
        if any(k in msg for k in ("certificate", "ssl", "tls", "handshake", "eof in violation")):
            return NavigationFailureClass.TLS_FAILURE
        if any(k in msg for k in ("nodename", "getaddrinfo", "name or service", "nxdomain",
                                  "noname", "no address", "11001", "11002", "temporary failure in name resolution",
                                  "[errno -2]", "nodename nor servname")):
            return NavigationFailureClass.DNS_FAILURE
        if "refused" in msg or "connection refused" in msg:
            return NavigationFailureClass.CONNECTION_REFUSED
        if "timed out" in msg or "timeout" in msg or "the read operation has timed out" in msg:
            return NavigationFailureClass.TIMEOUT
        if "proxy" in msg:
            return NavigationFailureClass.PROXY_FAILURE
        return NavigationFailureClass.NETWORK_UNAVAILABLE

    @staticmethod
    def _nav_context(url: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        try:
            ctx = classify_navigation_context(url, headers)
            return {
                "url": ctx.url,
                "presentation": ctx.presentation.value,
                "reason": ctx.reason,
                "confidence": ctx.confidence,
                "signals": dict(ctx.signals),
            }
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Browser profile model (spec §12)
# --------------------------------------------------------------------------- #

class BrowserProfile:
    """Browser profile controlling storage and permissions.

    Profiles are lightweight configurations — not full browser data directories.
    """

    DEFAULTS: Dict[str, Dict[str, Any]] = {
        "research": {
            "history_policy": "record_all",
            "download_policy": "prompt",
            "agent_permissions": ["navigate", "extract", "screenshot", "evidence", "search"],
            "cookie_isolation": True,
            "model_context": "research",
        },
        "engineering": {
            "history_policy": "record_domains_only",
            "download_policy": "auto_save_documents",
            "agent_permissions": ["navigate", "extract", "screenshot", "evidence", "search", "download", "inspect"],
            "cookie_isolation": True,
            "model_context": "engineering",
        },
        "personal": {
            "history_policy": "record_all",
            "download_policy": "prompt",
            "agent_permissions": ["navigate", "extract", "search", "evidence"],
            "cookie_isolation": False,
            "model_context": "personal",
        },
        "automation": {
            "history_policy": "none",
            "download_policy": "prompt",
            "agent_permissions": ["navigate", "extract", "evidence", "search"],
            "cookie_isolation": True,
            "model_context": "automation",
        },
        "private": {
            "history_policy": "none",
            "download_policy": "prompt",
            "agent_permissions": ["navigate", "extract"],
            "cookie_isolation": True,
            "model_context": "minimal",
        },
    }

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        base = self.DEFAULTS.get(name, self.DEFAULTS["personal"])
        self.config: Dict[str, Any] = {**base, **(config or {})}

    @property
    def history_policy(self) -> str:
        return self.config.get("history_policy", "record_all")

    @property
    def download_policy(self) -> str:
        return self.config.get("download_policy", "prompt")

    @property
    def agent_permissions(self) -> List[str]:
        return self.config.get("agent_permissions", [])

    @property
    def cookie_isolation(self) -> bool:
        return bool(self.config.get("cookie_isolation", True))

    @property
    def model_context(self) -> str:
        return self.config.get("model_context", "general")

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "config": self.config}


# --------------------------------------------------------------------------- #
# Navigation failure record (spec §7)
# --------------------------------------------------------------------------- #

@dataclass
class NavigationFailureRecord:
    """Record of a navigation failure for observability (spec §57)."""
    url: str
    failure_class: NavigationFailureClass
    error_category: str  # BrowserErrorCategory value
    detail: str
    timestamp: str = ""
    session_id: Optional[str] = None
    tab_id: Optional[str] = None
    user_id: Optional[str] = None
    recovered: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "failure_class": self.failure_class.value,
            "error_category": self.error_category,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "tab_id": self.tab_id,
            "user_id": self.user_id,
            "recovered": self.recovered,
        }


# --------------------------------------------------------------------------- #
# Engine registry — allows future engine plugins
# --------------------------------------------------------------------------- #

_engines: Dict[str, BrowserEngine] = {}


def register_engine(name: str, engine: BrowserEngine) -> None:
    """Register a browser engine implementation."""
    _engines[name] = engine


def get_engine(name: str = "default") -> BrowserEngine:
    """Get a registered browser engine by name.

    Falls back to ``HttpBrowserEngine`` for the ``default`` engine.
    """
    if name == "default" and not _engines:
        engine = HttpBrowserEngine()
        _engines["default"] = engine
        return engine
    engine = _engines.get(name)
    if engine is None:
        engine = _engines.get("default")
    if engine is None:
        engine = HttpBrowserEngine()
        _engines["default"] = engine
    return engine


# Initialise the default engine
get_engine("default")
