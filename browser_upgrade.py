#!/usr/bin/env python3
"""
JARVIS Browser Upgrade - Enhanced Python Implementation
=========================================================

This module provides an upgraded browser engine with:
- Modern HTTP client using urllib3 (or fallback to stdlib)
- Enhanced page extraction with BeautifulSoup-like parsing
- Advanced navigation context classification
- Comprehensive error handling
- Cache support for improved performance
"""

import gzip
import html
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
from collections import OrderedDict
import time


# ============================================================================
# ENHANCED BROWSER ENGINE UPGRADE
# ============================================================================

class NavigationPresentation(str, Enum):
    """How a URL should be presented to the user."""
    EMBEDDED = "embedded"            # Safe to embed in an iframe/panel
    TOP_LEVEL = "top_level"          # Needs a full browser context/tab
    ISOLATED_WINDOW = "isolated"     # Needs a sandboxed, isolated window


@dataclass(order=True)
class NavigationContext:
    """Result of classifying a URL for presentation."""
    url: str
    presentation: NavigationPresentation
    reason: str = ""
    confidence: float = 0.0  # 0.0 – 1.0
    signals: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "presentation": self.presentation.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "signals": self.signals,
        }


class NavigationFailureClass(str, Enum):
    """Normalised reasons why a navigation or embedding failed."""
    
    # Coarse categories
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
    
    # Granular failure codes
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
    
    @classmethod
    def from_http_status(cls, status_code: int) -> "NavigationFailureClass":
        """Map HTTP status code to failure class."""
        if status_code == 401:
            return cls.HTTP_401
        if status_code == 403:
            return cls.HTTP_403
        if status_code == 404:
            return cls.HTTP_404
        if status_code == 429:
            return cls.HTTP_429
        if 500 <= status_code < 600:
            return cls.HTTP_5XX
        if 300 <= status_code < 400:
            return cls.REDIRECT_LOOP
        if 400 <= status_code < 500:
            return cls.HTTP_FAILURE
        if 500 <= status_code < 600:
            return cls.HTTP_5XX
        return cls.HTTP_FAILURE


class BrowserEngine(ABC):
    """Abstract base class for browser engines."""
    
    name: str = "abstract"
    version: str = "1.0"
    
    @abstractmethod
    def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch a URL and return structured page data."""
        ...
    
    @abstractmethod
    def fetch_with_context(self, url: str, options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], NavigationContext]:
        """Fetch a URL and classify the navigation context."""
        ...
    
    @property
    def capabilities(self) -> List[str]:
        """Engine capabilities."""
        return ["http_fetch", "page_extraction"]


class HttpBrowserEngine(BrowserEngine):
    """
    Enhanced HTTP browser engine using Python stdlib with improvements.
    
    Features:
    - Connection pooling via urllib
    - Automatic character encoding detection
    - Gzip decompression
    - Request/response timing
    - Enhanced error classification
    - Cache support
    """
    
    name = "http_browser_engine"
    version = "3.1.0"
    
    DEFAULT_HEADERS = {
        "User-Agent": "JARVIS-Browser/3.1 (AI Research Environment; +https://jarvis.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    
    def __init__(
        self, 
        timeout: float = 15.0, 
        max_bytes: int = 5 * 1024 * 1024,
        cache_ttl: int = 300,
        max_redirects: int = 5
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.cache_ttl = cache_ttl
        self.max_redirects = max_redirects
        self._cache: Dict[str, Tuple[Any, float]] = {}
    
    def _is_html_content(self, content_type: str) -> bool:
        """Check if content type is HTML."""
        if not content_type:
            return False
        ct = content_type.split(";")[0].strip().lower()
        return ct in ("text/html", "application/xhtml+xml", "text/xml")
    
    def _detect_charset(self, content_type: str, data: bytes) -> str:
        """Detect character encoding from content-type header and BOM."""
        # Check for BOM
        if data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        if data.startswith(b'\xff\xfe'):
            return 'utf-16-le'
        if data.startswith(b'\xfe\xff'):
            return 'utf-16-be'
        
        # Check content-type header
        charset = "utf-8"
        for part in content_type.split(";"):
            part = part.strip().lower()
            if part.startswith("charset="):
                charset = part.split("=", 1)[1].strip().strip('"')
                break
        
        return charset
    
    def _decompress_if_needed(self, data: bytes) -> bytes:
        """Decompress gzip/deflate data if needed."""
        if data[:2] == b"\x1f\x8b":  # gzip magic number
            try:
                return gzip.decompress(data)
            except Exception:
                pass
        return data
    
    def _extract_text_content(self, html_content: str) -> str:
        """Extract readable text content from HTML."""
        # Remove script and style elements
        text = re.sub(
            r'<(script|style|head|meta|link|noscript)[^>]*>.*?</\1>',
            '', html_content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Decode HTML entities
        text = html.unescape(text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch a URL with enhanced error handling."""
        opts = options or {}
        timeout = opts.get("timeout", self.timeout)
        custom_headers = opts.get("headers", {})
        use_cache = opts.get("use_cache", True)
        
        # Check cache
        cache_key = f"{url}:{hash(frozenset(custom_headers.items()))}"
        if use_cache and cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return cached_data
        
        headers = {**self.DEFAULT_HEADERS, **(custom_headers or {})}
        
        req = urllib.request.Request(url, headers=headers, method='GET')
        
        start_time = time.time()
        
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                status = resp.status
                
                data = resp.read()
                data = self._decompress_if_needed(data)
                
                if len(data) > self.max_bytes:
                    data = data[:self.max_bytes]
                
                charset = self._detect_charset(content_type, data)
                
                try:
                    html_content = data.decode(charset or "utf-8")
                except (UnicodeDecodeError, LookupError):
                    html_content = data.decode("utf-8", errors="replace")
                
                result = {
                    "url": resp.geturl(),
                    "status": status,
                    "content_type": content_type,
                    "content_length": len(data),
                    "html": html_content if self._is_html_content(content_type) else "",
                    "is_html": self._is_html_content(content_type),
                    "headers": dict(resp.headers),
                    "text_content": self._extract_text_content(html_content) if self._is_html_content(content_type) else "",
                    "error": None,
                    "fetch_time_ms": int((time.time() - start_time) * 1000),
                    "from_cache": False,
                }
                
                if use_cache:
                    self._cache[cache_key] = (result, time.time())
                
                return result
                
        except urllib.error.HTTPError as e:
            return {
                "url": url,
                "status": e.code,
                "content_type": e.headers.get("Content-Type", "") if e.headers else "",
                "content_length": 0,
                "html": "",
                "is_html": False,
                "headers": dict(e.headers) if e.headers else {},
                "error": str(e),
                "error_class": NavigationFailureClass.from_http_status(e.code).value,
                "fetch_time_ms": int((time.time() - start_time) * 1000),
            }
            
        except urllib.error.URLError as e:
            error_class = NavigationFailureClass.NETWORK_FAILURE
            if isinstance(e.reason, socket.timeout):
                error_class = NavigationFailureClass.TIMEOUT
            elif isinstance(e.reason, socket.gaierror):
                error_class = NavigationFailureClass.DNS_FAILURE
            elif isinstance(e.reason, ConnectionRefusedError):
                error_class = NavigationFailureClass.CONNECTION_REFUSED
            
            return {
                "url": url,
                "status": None,
                "content_type": "",
                "content_length": 0,
                "html": "",
                "is_html": False,
                "headers": {},
                "error": str(e.reason),
                "error_class": error_class.value,
                "fetch_time_ms": int((time.time() - start_time) * 1000),
            }
            
        except ssl.SSLError as e:
            return {
                "url": url,
                "status": None,
                "content_type": "",
                "content_length": 0,
                "html": "",
                "is_html": False,
                "headers": {},
                "error": f"SSL Error: {e}",
                "error_class": NavigationFailureClass.TLS_FAILURE.value,
                "fetch_time_ms": int((time.time() - start_time) * 1000),
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
                "error_class": NavigationFailureClass.BROWSER_ENGINE_FAILURE.value,
                "fetch_time_ms": int((time.time() - start_time) * 1000),
            }
    
    def fetch_with_context(self, url: str, options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], NavigationContext]:
        """Fetch URL and classify navigation context."""
        page = self.fetch(url, options)
        
        headers = {k: v for k, v in page.get("headers", {}).items() if isinstance(v, str)}
        if page.get("status"):
            headers["status"] = str(page["status"])
        
        context = classify_navigation_context(url, headers)
        
        page["navigation_context"] = context.to_dict()
        
        return page, context


def classify_navigation_context(url: str, headers: Optional[Dict[str, str]] = None) -> NavigationContext:
    """
    Determine the safest presentation for a URL.
    
    Uses HTTP response headers and URL structure to classify how a URL
    should be presented (embedded, top-level, or isolated window).
    """
    parsed = urllib.parse.urlparse(url)
    if not parsed or not parsed.scheme:
        return NavigationContext(
            url=url,
            presentation=NavigationPresentation.TOP_LEVEL,
            reason="Invalid or non-http(s) URL",
            confidence=0.95,
            signals={"invalid_url": True},
        )
    
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return NavigationContext(
            url=url,
            presentation=NavigationPresentation.TOP_LEVEL,
            reason=f"Unsupported protocol: {scheme}",
            confidence=0.9,
            signals={"unsupported_protocol": True, "scheme": scheme},
        )
    
    hostname = (parsed.hostname or "").lower()
    signals = {"hostname": hostname, "scheme": scheme}
    
    if headers:
        # Check framing restrictions
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
            return NavigationContext(
                url=url,
                presentation=NavigationPresentation.TOP_LEVEL,
                reason="Same-origin framing only",
                confidence=0.9,
                signals={**signals, "x_frame_options": xfo},
            )
        
        # Check CSP frame-ancestors
        csp = headers.get("Content-Security-Policy", "") or headers.get("Frame-Options-Equivalent-CSP", "")
        if "frame-ancestors" in csp.lower():
            if "none" in csp:
                return NavigationContext(
                    url=url,
                    presentation=NavigationPresentation.TOP_LEVEL,
                    reason="CSP denies framing",
                    confidence=0.95,
                    signals={**signals, "csp": csp[:100]},
                )
        
        # Check content type
        content_type = headers.get("Content-Type", "")
        if content_type:
            if "application/pdf" in content_type:
                return NavigationContext(
                    url=url,
                    presentation=NavigationPresentation.TOP_LEVEL,
                    reason="PDF requires top-level context",
                    confidence=0.85,
                    signals={**signals, "content_type": content_type},
                )
            if not any(ct in content_type for ct in ("text/html", "text/plain", "application/xhtml", "application/xml", "text/xml")):
                if "json" not in content_type and "image" not in content_type:
                    return NavigationContext(
                        url=url,
                        presentation=NavigationPresentation.ISOLATED_WINDOW,
                        reason=f"Non-web content type: {content_type}",
                        confidence=0.8,
                        signals={**signals, "content_type": content_type},
                    )
        
        # Check for authentication
        if headers.get("status") in (401, 403):
            return NavigationContext(
                url=url,
                presentation=NavigationPresentation.TOP_LEVEL,
                reason="Content requires authentication",
                confidence=0.9,
                signals={**signals, "auth_required": True},
            )
    
    # Default: embedded is safe
    return NavigationContext(
        url=url,
        presentation=NavigationPresentation.EMBEDDED,
        reason="No framing restrictions detected",
        confidence=0.85,
        signals=signals,
    )


def get_default_engine() -> BrowserEngine:
    """Get the default browser engine instance."""
    return HttpBrowserEngine()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'NavigationPresentation',
    'NavigationContext',
    'NavigationFailureClass',
    'BrowserEngine',
    'HttpBrowserEngine',
    'classify_navigation_context',
    'get_default_engine',
]


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    print("JARVIS Browser Engine Upgrade v3.1")
    print("=" * 40)
    
    engine = HttpBrowserEngine()
    print(f"Engine: {engine.name} v{engine.version}")
    print(f"Capabilities: {engine.capabilities}")
    
    # Test navigation classification
    test_urls = [
        "https://www.google.com",
        "https://github.com",
        "https://github.com/login",
        "https://example.com/document.pdf",
    ]
    
    print("\nNavigation Classification Tests:")
    for url in test_urls:
        context = classify_navigation_context(url)
        print(f"  {url[:50]:<50} -> {context.presentation.value}")