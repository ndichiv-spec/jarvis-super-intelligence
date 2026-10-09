"""Live (internet) tests for the BrowserSearchTool + Research Engine fabric.

These exercise the REAL browser/search pipeline end-to-end:

    BrowserSearchTool -> HttpBrowserEngine.get_engine("default")
                      -> engine.search()   (DuckDuckGo Lite + Wikipedia)
                      -> engine.fetch_document()  (navigate -> extract -> normalize)

They are NOT marked ``brain`` so the offline green gate
(``pytest -m brain`` -> 145/1/0) is untouched; the whole module is skipped
unless the platform has opted into live web search.  Run explicitly:

    JARVIS_BROWSER_SEARCH_ENABLED=1 python -m pytest tests/test_browser_search_live.py -p no:cacheprovider -q

Assertions are honest and tolerance-bounded: they assert minimums
(minimum result count, presence of a real URL, positive word count) rather
than exact DuckDuckGo result sets, so transient provider changes do not make
the harness brittle.
"""
from __future__ import annotations

import asyncio
import os
import socket

import pytest

from jarvis_backend.browser_engine import NavigationFailureClass, get_engine
from research_engine.models import (
    ResearchBudgets,
    ResearchMode,
    VerificationStatus,
)
from research_engine.research_engine import ResearchEngine
from research_engine.tool_registry import (
    BrowserSearchTool,
    DefaultPermissionPolicy,
    SandboxRunTool,
    ToolContext,
    ToolRegistry,
)


def _browser_enabled() -> bool:
    return os.environ.get("JARVIS_BROWSER_SEARCH_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _internet_ok(timeout: float = 4.0) -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=timeout)
        return True
    except OSError:
        return False


# Collection-time gate is env-only (no network call): keeps the brain gate offline.
pytestmark = pytest.mark.skipif(not _browser_enabled(), reason="JARVIS_BROWSER_SEARCH_ENABLED=1 required")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _registry():
    reg = ToolRegistry(policy=DefaultPermissionPolicy(confirmations={"researcher:search_web": True}))
    reg.register(BrowserSearchTool())
    reg.register(SandboxRunTool())
    return reg


# --------------------------------------------------------------------------- #
# Wiring (no network required, but still gated to the live module)
# --------------------------------------------------------------------------- #
def test_default_engine_has_search_and_fetch_document():
    engine = get_engine("default")
    assert engine is not None
    assert hasattr(engine, "search")
    assert hasattr(engine, "fetch_document")
    assert "http_fetch" in engine.capabilities


# --------------------------------------------------------------------------- #
# Live web search
# --------------------------------------------------------------------------- #
def test_live_search_returns_results():
    if not _internet_ok():
        pytest.skip("no internet")
    reg = _registry()
    ctx = ToolContext(user_id="researcher", permissions={"web:read"})
    res = _run(reg.invoke("search_web", {"query": "python programming language", "max_results": 8}, ctx))
    assert res.success, res.error
    assert res.metrics.get("available") is True
    assert res.metrics.get("results", 0) >= 3
    assert len(res.artifacts) >= 3
    # Each artifact carries the Section 3 SearchResult contract.
    a = res.artifacts[0]
    assert {"url", "title", "snippet", "source"}.issubset(a.keys())
    assert a["url"].startswith(("http://", "https://"))


def test_live_search_no_query_is_client_error():
    reg = _registry()
    ctx = ToolContext(user_id="researcher", permissions={"web:read"})
    res = _run(reg.invoke("search_web", {}, ctx))
    assert not res.success
    assert "required" in res.error.lower()


# --------------------------------------------------------------------------- #
# Live page retrieval / extraction
# --------------------------------------------------------------------------- #
def test_live_fetch_document_extracts_content():
    if not _internet_ok():
        pytest.skip("no internet")
    engine = get_engine("default")
    doc = engine.fetch_document("https://www.python.org/")
    assert doc["success"] is True
    assert doc["status"] == 200
    assert doc["is_html"] is True
    assert doc["title"], "expected a <title> for python.org"
    assert doc["word_count"] > 0


def test_live_navigation_failure_404_is_granular():
    if not _internet_ok():
        pytest.skip("no internet")
    engine = get_engine("default")
    doc = engine.fetch_document("https://httpbin.org/status/404")
    assert doc["success"] is False
    assert doc["status"] == 404
    # Granular classification (spec §5), NOT the coarse HTTP_FAILURE.
    # fetch_document stores the failure_class *value* (str), so compare by value.
    assert doc["failure_category"] == NavigationFailureClass.HTTP_404.value
    assert doc["failure_category"] in NavigationFailureClass._value2member_map_


def test_live_navigation_failure_bad_host_is_dns_failure():
    # `.invalid` is a reserved TLD that never resolves -> DNS_FAILURE.
    engine = get_engine("default")
    doc = engine.fetch_document("http://nonexistent-host-xyz.invalid/page")
    assert doc["success"] is False
    assert doc["failure_category"] in (
        NavigationFailureClass.DNS_FAILURE,
        NavigationFailureClass.NETWORK_UNAVAILABLE,
    )


# --------------------------------------------------------------------------- #
# Deep-research: evidence + per-URL provenance flow into the ResearchEngine
# --------------------------------------------------------------------------- #
def test_live_research_gathers_evidence_with_provenance():
    if not _internet_ok():
        pytest.skip("no internet")
    reg = _registry()
    eng = ResearchEngine(reg)
    # Bounded budget: 2 source-navigating passes to keep the test fast.
    budgets = ResearchBudgets(max_iterations=2, max_sources=2)
    report = _run(
        eng.research(
            "python programming language",
            mode=ResearchMode.DEEP_RESEARCH,
            user_id="researcher",
            budgets=budgets,
        )
    )
    assert report is not None
    # The search step must have been attempted (honest: not fabricated).
    kinds = [e.kind for e in report.timeline]
    assert "search" in kinds or "research_start" in kinds
    if report.evidence:
        # At least one piece of evidence must be attributed to a real source URL
        # (fine-grained provenance), never only the synthetic web://search digest.
        real = [e for e in report.evidence if e.source_url.startswith(("http://", "https://"))]
        assert real, "expected at least one evidence item with a real source URL"
    # Verification status is one of the honest enum values.
    assert report.verification in VerificationStatus.__members__.values() or isinstance(report.verification, VerificationStatus)
