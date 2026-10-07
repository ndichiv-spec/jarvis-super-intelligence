"""Deterministic tests for browser navigation failure classification (spec §5/§7/§8).

These lock the navigation-failure contract that the Research Fabric relies on:

* ``classify_navigation_failure`` and ``from_browser_error_category`` stay
  **coarse** (backwards-compatible with the ``/browser/classify`` endpoint —
  the invariant the platform depends on).
* ``NavigationFailureClass.from_http_status`` exposes the new **granular**
  taxonomy (HTTP_404, HTTP_429, HTTP_5XX, ...) that
  ``HttpBrowserEngine.fetch_document`` returns for actionable failures.

These files are NOT marked ``brain`` so they are deselected by
``pytest -m brain``; the green gate therefore stays exactly 145/1/0.  Run them
explicitly:

    python -m pytest tests/test_search_navigation.py -p no:cacheprovider -q
    python -m pytest tests/test_browser_search_live.py -p no:cacheprovider -q
"""
from __future__ import annotations

import pytest

from jarvis_backend.browser_engine import (
    NavigationFailureClass,
    classify_navigation_failure,
)

# Coarse categories that pre-date the granular taxonomy (spec §7).
COARSE = {
    "FRAME_BLOCKED", "AUTH_REQUIRED", "UNSUPPORTED_EMBED", "NETWORK_FAILURE",
    "DNS_FAILURE", "TLS_FAILURE", "HTTP_FAILURE", "BROWSER_ENGINE_FAILURE",
    "REDIRECT_LOOP", "CONTENT_BLOCKED", "PROXY_FAILURE",
}
# New granular codes (spec §5).
GRANULAR = {
    "CONNECTION_REFUSED", "TIMEOUT", "HTTP_401", "HTTP_403", "HTTP_404",
    "HTTP_429", "HTTP_5XX", "NETWORK_UNAVAILABLE", "BROWSER_WORKER_UNAVAILABLE",
    "DOWNLOAD_FAILED", "PARSER_FAILED", "SERVICE_WORKER_ERROR", "BROWSER_CRASH",
}


def test_navigation_failure_class_is_superset():
    present = {c.value for c in NavigationFailureClass}
    # Coarse must remain intact (regression guard for /browser/classify consumers).
    assert COARSE.issubset(present)
    # Granular must exist (spec §5 taxonomy).
    assert GRANULAR.issubset(present)
    # No value may be both coarse and granular.
    assert not (COARSE & GRANULAR)


def test_from_http_status_granular():
    f = NavigationFailureClass.from_http_status
    assert f(401) is NavigationFailureClass.HTTP_401
    assert f(403) is NavigationFailureClass.HTTP_403
    assert f(404) is NavigationFailureClass.HTTP_404
    assert f(429) is NavigationFailureClass.HTTP_429
    assert f(500) is NavigationFailureClass.HTTP_5XX
    assert f(503) is NavigationFailureClass.HTTP_5XX
    assert f(502) is NavigationFailureClass.HTTP_5XX
    assert f(301) is NavigationFailureClass.REDIRECT_LOOP
    assert f(302) is NavigationFailureClass.REDIRECT_LOOP
    # Remaining 4xx (not 401/403/404/429) and 2xx default to HTTP_FAILURE.
    assert f(400) is NavigationFailureClass.HTTP_FAILURE
    assert f(418) is NavigationFailureClass.HTTP_FAILURE
    assert f(200) is NavigationFailureClass.HTTP_FAILURE
    # Non-integer / None -> safe default, never raises.
    assert f("not-a-code") is NavigationFailureClass.HTTP_FAILURE


def test_classify_navigation_failure_stays_coarse():
    # The coarse classifier must NOT emit a granular code like HTTP_404.
    assert classify_navigation_failure("https://x.example", status_code=404) is NavigationFailureClass.HTTP_FAILURE
    assert classify_navigation_failure("https://x.example", status_code=400) is NavigationFailureClass.HTTP_FAILURE
    assert classify_navigation_failure("https://x.example", status_code=500) is NavigationFailureClass.HTTP_FAILURE
    # 401 + WWW-Authenticate challenge -> AUTH_REQUIRED (coarse).
    assert classify_navigation_failure(
        "https://x.example", status_code=401,
        headers={"WWW-Authenticate": "Basic realm=private"},
    ) is NavigationFailureClass.AUTH_REQUIRED
    # 403 + framing header -> FRAME_BLOCKED; 403 without -> AUTH_REQUIRED (coarse).
    assert classify_navigation_failure(
        "https://x.example", status_code=403,
        headers={"X-Frame-Options": "DENY"},
    ) is NavigationFailureClass.FRAME_BLOCKED
    assert classify_navigation_failure("https://x.example", status_code=403) is NavigationFailureClass.AUTH_REQUIRED
    # Redirect codes are coarse NETWORK_FAILURE here (not REDIRECT_LOOP).
    assert classify_navigation_failure("https://x.example", status_code=301) is NavigationFailureClass.NETWORK_FAILURE


def test_from_browser_error_category_coarse_unchanged():
    f = NavigationFailureClass.from_browser_error_category
    # Original coarse mapping preserved verbatim.
    assert f("CONNECTION_TIMEOUT") is NavigationFailureClass.NETWORK_FAILURE
    assert f("CONNECTION_REFUSED") is NavigationFailureClass.NETWORK_FAILURE
    assert f("UNKNOWN_NETWORK_ERROR") is NavigationFailureClass.NETWORK_FAILURE
    assert f("HTTP_5XX") is NavigationFailureClass.HTTP_FAILURE
    assert f("HTTP_4XX") is NavigationFailureClass.HTTP_FAILURE
    assert f("TLS_HANDSHAKE_FAILED") is NavigationFailureClass.TLS_FAILURE
    assert f("CERTIFICATE_INVALID") is NavigationFailureClass.TLS_FAILURE
    assert f("DNS_RESOLUTION_FAILED") is NavigationFailureClass.DNS_FAILURE
    assert f("AUTH_REQUIRED") is NavigationFailureClass.AUTH_REQUIRED
    assert f("REDIRECT_LOOP") is NavigationFailureClass.REDIRECT_LOOP
    assert f("BROWSER_ENGINE_ERROR") is NavigationFailureClass.BROWSER_ENGINE_FAILURE
    assert f("CONTENT_BLOCKED") is NavigationFailureClass.CONTENT_BLOCKED
    assert f("PROXY_CONNECTION_FAILED") is NavigationFailureClass.PROXY_FAILURE
    # Unknown category -> coarse default (NOT a granular code).
    assert f("NOPE_NOT_A_CATEGORY") is NavigationFailureClass.BROWSER_ENGINE_FAILURE
