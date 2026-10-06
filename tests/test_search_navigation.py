"""Tests for the Federated Search and Navigation Context endpoints (spec §26–31, §7–8, §63)."""

import json
import os
import sys
import time
import urllib.parse

import pytest

from jarvis_backend.routers.search import router as search_router, SearchDomain


# --------------------------------------------------------------------------- #
# Navigation Context classification (spec §7)
# --------------------------------------------------------------------------- #
class TestNavigationContext:
    def test_classify_embedded_url_no_headers(self, test_client, auth_headers):
        """URL with no framing restrictions should be classified as embedded."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "https://example.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://example.com"
        assert data["presentation"] == "embedded"
        assert data["confidence"] >= 0.0

    def test_classify_frame_blocked_deny(self, test_client, auth_headers):
        """X-Frame-Options: DENY should classify as top_level."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "https://example.com", "headers": {"X-Frame-Options": "DENY"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["presentation"] == "top_level"
        assert "DENY" in data["reason"]

    def test_classify_frame_blocked_sameorigin(self, test_client, auth_headers):
        """X-Frame-Options: SAMEORIGIN should classify as top_level for cross-origin."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "https://example.com", "headers": {"X-Frame-Options": "SAMEORIGIN"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["presentation"] == "top_level"

    def test_classify_csp_frame_ancestors_none(self, test_client, auth_headers):
        """CSP frame-ancestors 'none' should classify as top_level."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "https://example.com",
                  "headers": {"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["presentation"] == "top_level"
        assert "frame-ancestors" in data["reason"].lower() or "none" in data["reason"].lower()

    def test_classify_unsupported_protocol(self, test_client, auth_headers):
        """Non-HTTP protocols should classify as top_level."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "ftp://example.com/file"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["presentation"] == "top_level"
        assert "ftp" in data["reason"].lower()

    def test_classify_blocked_domain(self, test_client, auth_headers):
        """Blocked domains (localhost, etc.) should return 403."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "http://localhost:3000/test"},
            headers=auth_headers,
        )
        assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Navigation failure classification (spec §8)
# --------------------------------------------------------------------------- #
class TestNavigationFailureClassification:
    def test_classify_frame_blocked_403(self, test_client, auth_headers):
        """HTTP 403 with X-Frame-Options should classify as FRAME_BLOCKED."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://example.com", "status_code": 403,
                  "headers": {"X-Frame-Options": "DENY"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "FRAME_BLOCKED"

    def test_classify_auth_required_401(self, test_client, auth_headers):
        """HTTP 401 with WWW-Authenticate should classify as AUTH_REQUIRED."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://example.com", "status_code": 401,
                  "headers": {"WWW-Authenticate": "Bearer"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "AUTH_REQUIRED"

    def test_classify_dns_error_category(self, test_client, auth_headers):
        """DNS error category should classify as DNS_FAILURE."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://nonexistent.invalid.domain.xyz",
                  "error_category": "DNS_RESOLUTION_FAILED"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "DNS_FAILURE"

    def test_classify_http_failure(self, test_client, auth_headers):
        """HTTP 4xx error codes should classify as HTTP_FAILURE."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://example.com", "status_code": 404},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "HTTP_FAILURE"

    def test_classify_http_500(self, test_client, auth_headers):
        """HTTP 500 should classify as HTTP_FAILURE."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://example.com", "status_code": 500},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "HTTP_FAILURE"

    def test_classify_tls_failure(self, test_client, auth_headers):
        """SSL error category should classify as TLS_FAILURE."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://expired.badssl.com",
                  "error_category": "TLS_HANDSHAKE_FAILED"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "TLS_FAILURE"

    def test_classify_recovery_recommendations(self, test_client, auth_headers):
        """Each failure class should have recovery recommendations."""
        resp = test_client.post(
            "/api/v1/browser/navigate/classify-failure",
            json={"url": "https://example.com", "error_category": "AUTH_REQUIRED"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_class"] == "AUTH_REQUIRED"
        assert len(data["recovery_recommendations"]) > 0


# --------------------------------------------------------------------------- #
# Open-in-browser-context (spec §8)
# --------------------------------------------------------------------------- #
class TestOpenInBrowserContext:
    def test_open_context_embeddable_url(self, test_client, auth_headers):
        """Embeddable URL should not trigger context switch."""
        resp = test_client.post(
            "/api/v1/browser/open-context",
            json={"url": "https://example.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target"] == "embedded"
        assert "embed" in data["reason"].lower() or "safe" in data["reason"].lower()

    def test_open_context_non_embeddable_url(self, test_client, auth_headers):
        """Non-embeddable URL should return top_level target."""
        resp = test_client.post(
            "/api/v1/browser/open-context",
            json={"url": "https://example.com", "headers": {"X-Frame-Options": "DENY"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target"] == "top_level"
        assert data["url"] == "https://example.com"

    def test_open_context_with_query_preservation(self, test_client, auth_headers):
        """Query should be preserved in the target URL."""
        resp = test_client.post(
            "/api/v1/browser/open-context",
            json={"url": "https://example.com", "headers": {"X-Frame-Options": "DENY"},
                  "query": "search terms"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "jarvis_query=search" in data["url"]

    def test_open_context_blocked_domain(self, test_client, auth_headers):
        """Blocked domains should return 403."""
        resp = test_client.post(
            "/api/v1/browser/open-context",
            json={"url": "http://127.0.0.1:8000/test"},
            headers=auth_headers,
        )
        assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Browser profiles (spec §12)
# --------------------------------------------------------------------------- #
class TestBrowserProfiles:
    def test_list_profiles(self, test_client, auth_headers):
        resp = test_client.get("/api/v1/browser/profiles", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert len(data["profiles"]) >= 4

    def test_get_profile(self, test_client, auth_headers):
        resp = test_client.get("/api/v1/browser/profiles/research", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "research"
        assert "history_policy" in data["config"]
        assert "agent_permissions" in data["config"]

    def test_get_profile_not_found(self, test_client, auth_headers):
        resp = test_client.get("/api/v1/browser/profiles/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    def test_profile_permissions(self, test_client, auth_headers):
        """Each profile should have agent_permissions."""
        for profile_name in ["research", "engineering", "personal", "automation", "private"]:
            resp = test_client.get(f"/api/v1/browser/profiles/{profile_name}", headers=auth_headers)
            assert resp.status_code == 200
            config = resp.json()["config"]
            assert "agent_permissions" in config
            assert isinstance(config["agent_permissions"], list)


# --------------------------------------------------------------------------- #
# Browser engine abstraction (spec §4)
# --------------------------------------------------------------------------- #
class TestBrowserEngine:
    def test_get_engine_info(self, test_client, auth_headers):
        resp = test_client.get("/api/v1/browser/engine", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "http_browser_engine"
        assert "http_fetch" in data["capabilities"]
        assert "page_extraction" in data["capabilities"]


# --------------------------------------------------------------------------- #
# Page understand (AI context layer, spec §5)
# --------------------------------------------------------------------------- #
class TestPageUnderstand:
    def test_understand_page_blocked_domain(self, test_client, auth_headers):
        """Blocked domains should return 403."""
        resp = test_client.post(
            "/api/v1/browser/page/understand",
            json={"url": "http://127.0.0.1:8000/test"},
            headers=auth_headers,
        )
        assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Federated Search (spec §26–31, §63)
# --------------------------------------------------------------------------- #
class TestFederatedSearch:
    def test_search_domains_list(self, test_client, auth_headers):
        resp = test_client.get("/api/v1/search/domains", headers=auth_headers)
        assert resp.status_code == 200
        domains = resp.json()
        assert isinstance(domains, list)
        assert "knowledge" in domains
        assert "browser" in domains
        assert "chat" in domains

    def test_search_status(self, test_client, auth_headers):
        resp = test_client.get("/api/v1/search/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "domains" in data
        assert "healthy" in data

    def test_search_empty_query(self, test_client, auth_headers):
        """Empty query should return 0 results."""
        resp = test_client.get("/api/v1/search?q=", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 0
        assert data["results"] == []

    def test_search_post(self, test_client, auth_headers):
        """POST search should work with structured body."""
        resp = test_client.post(
            "/api/v1/search/",
            json={"query": "test", "limit": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert isinstance(data["results"], list)
        assert isinstance(data["total_results"], int)

    def test_search_specific_domain(self, test_client, auth_headers):
        """Search within a specific domain."""
        resp = test_client.get(
            "/api/v1/search?q=test&domain=browser&limit=5",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["results"], list)

    def test_search_result_schema(self, test_client, auth_headers):
        """All search results should have the normalised schema fields."""
        from jarvis_backend.core import get_store
        store = get_store("knowledge")
        data_store = store.load()
        if not isinstance(data_store, dict):
            data_store = {}
        test_key = f"test_search_{int(time.time())}"
        data_store[test_key] = {
            "key": test_key,
            "title": "Test Search Entry",
            "value": "This is a test entry for searching",
            "content": "Test content for federated search",
            "user_id": "system",
            "tags": ["test", "search"],
            "created_at": "2024-01-01T00:00:00Z",
        }
        store.save()

        resp = test_client.get("/api/v1/search?q=test+search&domain=knowledge&limit=5",
                               headers=auth_headers)
        assert resp.status_code == 200
        result_data = resp.json()
        assert result_data["total_results"] > 0
        for r in result_data["results"]:
            assert "id" in r
            assert "source" in r
            assert "title" in r
            assert "score" in r

        # Cleanup
        if test_key in data_store:
            del data_store[test_key]
            store.save()

    def test_search_no_fabrication(self, test_client, auth_headers):
        """Search should never return fabricated results."""
        unique = f"xyzzy_nothing_here_{int(time.time())}"
        resp = test_client.get(
            f"/api/v1/search?q={urllib.parse.quote(unique)}&include_web=false",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 0
        assert data["results"] == []

    def test_search_suggestions(self, test_client, auth_headers):
        """Search suggestions should return autocomplete results."""
        from jarvis_backend.core import get_store
        store = get_store("browser_bookmarks")
        data = store.load()
        if not isinstance(data, dict):
            data = {}
        test_id = f"bk_{int(time.time())}"
        data[test_id] = {
            "id": test_id,
            "url": "https://example.com/test",
            "title": "Example Test Page",
            "domain": "example.com",
            "user_id": "system",
            "tags": [],
            "notes": "",
            "created_at": "2024-01-01T00:00:00Z",
        }
        store.save()

        resp = test_client.get(f"/api/v1/search/suggest?q=example",
                               headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert "Example Test Page" in data["suggestions"]

        # Cleanup
        if test_id in data:
            del data[test_id]
            store.save()


# --------------------------------------------------------------------------- #
# Cross-system object inspection (spec §17)
# --------------------------------------------------------------------------- #
class TestCrossSystemInspection:
    def test_inspect_known_object(self, test_client, auth_headers):
        """Inspect a known object should return its full data."""
        from jarvis_backend.core import get_store
        store = get_store("knowledge")
        data = store.load()
        if not isinstance(data, dict):
            data = {}
        test_key = f"inspect_test_{int(time.time())}"
        data[test_key] = {
            "key": test_key,
            "title": "Inspect Test",
            "value": "Inspectable content",
            "user_id": "system",
            "created_at": "2024-01-01T00:00:00Z",
        }
        store.save()

        resp = test_client.get(f"/api/v1/search/inspect/knowledge/{test_key}",
                               headers=auth_headers)
        assert resp.status_code == 200
        result = resp.json()
        assert result["source"] == "knowledge"
        assert result["id"] == test_key
        assert "object" in result
        assert result["object"]["title"] == "Inspect Test"

        # Cleanup
        if test_key in data:
            del data[test_key]
            store.save()

    def test_inspect_unknown_source(self, test_client, auth_headers):
        """Unknown source should return 400."""
        resp = test_client.get("/api/v1/search/inspect/unknown_source/some_id",
                               headers=auth_headers)
        assert resp.status_code == 400

    def test_inspect_not_found(self, test_client, auth_headers):
        """Non-existent ID should return 404."""
        resp = test_client.get("/api/v1/search/inspect/knowledge/nonexistent_id_12345",
                               headers=auth_headers)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Search → platform handoffs (spec §35–37)
# --------------------------------------------------------------------------- #
class TestSearchHandoffs:
    def test_to_browser_handoff_no_results(self, test_client, auth_headers):
        """Search → Browser handoff with no results should not navigate."""
        unique = f"xyzzy_no_result_{int(time.time())}"
        resp = test_client.post(
            "/api/v1/search/to/browser",
            json={"query": unique, "include_web": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["navigated"] is False

    def test_to_research_handoff(self, test_client, auth_headers):
        """Search → Research handoff should create a research session."""
        resp = test_client.post(
            "/api/v1/search/to/research",
            json={"query": "machine learning test"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "research_session_id" in data
        assert data["query"] == "machine learning test"

    def test_to_knowledge_handoff(self, test_client, auth_headers):
        """Search → Knowledge handoff should promote a result."""
        from jarvis_backend.core import get_store
        store = get_store("knowledge")
        data = store.load()
        if not isinstance(data, dict):
            data = {}
        test_key = f"handoff_test_{int(time.time())}"
        data[test_key] = {
            "key": test_key,
            "title": "Handoff Test Entry",
            "value": "This entry should be promotable to knowledge",
            "user_id": "system",
            "created_at": "2024-01-01T00:00:00Z",
        }
        store.save()

        resp = test_client.post(
            "/api/v1/search/to/knowledge",
            json={"query": "Handoff Test", "result_id": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "promoted" in result

        # Cleanup
        if test_key in data:
            del data[test_key]
            store.save()


# --------------------------------------------------------------------------- #
# BrowserEngine abstraction unit tests (spec §4)
# --------------------------------------------------------------------------- #
class TestBrowserEngineAbstraction:
    def test_browser_engine_imports(self):
        """All browser engine classes should be importable."""
        from jarvis_backend.browser_engine import (
            BrowserEngine,
            HttpBrowserEngine,
            NavigationPresentation,
            NavigationContext,
            NavigationFailureClass,
            BrowserProfile,
            classify_navigation_context,
            classify_navigation_failure,
            get_engine,
            register_engine,
        )

    def test_http_engine_fetch(self):
        """HttpBrowserEngine should be retrievable via registry."""
        from jarvis_backend.browser_engine import get_engine
        engine = get_engine("default")
        assert engine.name == "http_browser_engine"
        assert "http_fetch" in engine.capabilities

    def test_navigation_presentation_values(self):
        """NavigationPresentation should have the correct enum values."""
        from jarvis_backend.browser_engine import NavigationPresentation
        assert NavigationPresentation.EMBEDDED.value == "embedded"
        assert NavigationPresentation.TOP_LEVEL.value == "top_level"
        assert NavigationPresentation.ISOLATED_WINDOW.value == "isolated"

    def test_navigation_failure_classification_values(self):
        """NavigationFailureClass should have all spec §7 values."""
        from jarvis_backend.browser_engine import NavigationFailureClass
        expected = {
            "FRAME_BLOCKED", "AUTH_REQUIRED", "UNSUPPORTED_EMBED",
            "NETWORK_FAILURE", "DNS_FAILURE", "TLS_FAILURE",
            "HTTP_FAILURE", "BROWSER_ENGINE_FAILURE",
        }
        actual = {c.value for c in NavigationFailureClass}
        assert expected.issubset(actual)

    def test_browser_profile_defaults(self):
        """BrowserProfile should have all expected default profiles."""
        from jarvis_backend.browser_engine import BrowserProfile
        expected_profiles = {"research", "engineering", "personal", "automation", "private"}
        actual = set(BrowserProfile.DEFAULTS.keys())
        assert expected_profiles.issubset(actual)

    def test_profile_permissions(self):
        """Each profile should have agent_permissions."""
        from jarvis_backend.browser_engine import BrowserProfile
        for name in BrowserProfile.DEFAULTS:
            profile = BrowserProfile(name)
            assert isinstance(profile.agent_permissions, list)
            assert len(profile.agent_permissions) > 0

    def test_register_engine(self):
        """Custom engines should be registerable."""
        from jarvis_backend.browser_engine import BrowserEngine, register_engine, get_engine
        from typing import Any, Dict, Optional

        class TestEngine(BrowserEngine):
            name = "test_engine"
            def fetch(self, url, options=None):
                return {"html": "<html>test</html>", "status": 200, "is_html": True}
            def fetch_with_context(self, url, options=None):
                from jarvis_backend.browser_engine import classify_navigation_context
                page = self.fetch(url, options)
                ctx = classify_navigation_context(url)
                return page, ctx

        test_engine = TestEngine()
        register_engine("test", test_engine)
        retrieved = get_engine("test")
        assert retrieved.name == "test_engine"

    def test_classify_navigation_context_for_pdf(self):
        """PDF content type should classify as top_level."""
        from jarvis_backend.browser_engine import classify_navigation_context
        ctx = classify_navigation_context("https://example.com/doc.pdf",
                                          {"Content-Type": "application/pdf"})
        assert ctx.presentation.value == "top_level"

    def test_classify_navigation_failure_from_error(self):
        """classify_navigation_failure should map exceptions correctly."""
        import socket
        from jarvis_backend.browser_engine import classify_navigation_failure, NavigationFailureClass
        result = classify_navigation_failure("https://test.com",
                                             error=socket.gaierror(11001, "DNS error"))
        assert result == NavigationFailureClass.DNS_FAILURE

    def test_classify_navigation_failure_auth(self):
        """HTTP 401 should classify as AUTH_REQUIRED."""
        from jarvis_backend.browser_engine import classify_navigation_failure, NavigationFailureClass
        result = classify_navigation_failure("https://test.com", status_code=401,
                                             headers={"WWW-Authenticate": "Bearer"})
        assert result == NavigationFailureClass.AUTH_REQUIRED


# --------------------------------------------------------------------------- #
# Browser → Knowledge integration (spec §11)
# --------------------------------------------------------------------------- #
class TestBrowserKnowledgeIntegration:
    def test_extract_to_knowledge_with_content(self, test_client, auth_headers):
        """Extract page content provided directly to a knowledge entry."""
        resp = test_client.post(
            "/api/v1/browser/page/extract-to-knowledge",
            json={
                "url": "https://example.com/article",
                "content": "<html><head><title>Test Article</title></head><body><p>Hello world test content</p></body></html>",
                "title": "Test Article",
                "tags": ["test"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "knowledge_key" in data
        assert data["title"] == "Test Article"
        assert data["word_count"] > 0
        assert data["page_classification"] != ""

    def test_extract_to_knowledge_missing_content_fetches(self, test_client, auth_headers):
        """When content is not provided, the engine fetches the URL."""
        resp = test_client.post(
            "/api/v1/browser/page/extract-to-knowledge",
            json={"url": "https://www.example.com"},
            headers=auth_headers,
        )
        # example.com is a real domain, engine should fetch it
        assert resp.status_code == 200
        data = resp.json()
        assert "knowledge_key" in data

    def test_extract_to_knowledge_blocked_domain(self, test_client, auth_headers):
        """Blocked domains should return 403."""
        resp = test_client.post(
            "/api/v1/browser/page/extract-to-knowledge",
            json={"url": "http://127.0.0.1:8000/test", "content": "<html></html>"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_extract_to_knowledge_stores_entry(self, test_client, auth_headers):
        """The knowledge entry should be retrievable after extraction."""
        from jarvis_backend.core import get_store
        store = get_store("knowledge")
        data = store.load()
        if not isinstance(data, dict):
            data = {}

        resp = test_client.post(
            "/api/v1/browser/page/extract-to-knowledge",
            json={
                "url": "https://example.com/test",
                "content": "<html><head><title>Unique Test</title></head><body>unique marker content</body></html>",
                "title": "Unique Test",
                "tags": ["uniquetest"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        key = resp.json()["knowledge_key"]
        assert key in data
        assert data[key]["url"] == "https://example.com/test"
        assert "unique marker" in data[key]["value"]
        assert data[key]["source"] == "browser_extractor"


# --------------------------------------------------------------------------- #
# Session context endpoint (spec §6, §17)
# --------------------------------------------------------------------------- #
class TestSessionContext:
    def test_get_session_context(self, test_client, auth_headers):
        """Create a session, then retrieve its context snapshot."""
        # Create a session first
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "context_test_session", "profile": "research"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        session_id = resp.json()["session"]["id"]

        # Get context
        resp = test_client.get(
            f"/api/v1/browser/sessions/{session_id}/context",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert data["profile"] == "research"
        assert "permissions" in data
        assert data["tab_count"] == 0

    def test_get_session_context_not_found(self, test_client, auth_headers):
        """Non-existent session should return 404."""
        resp = test_client.get(
            "/api/v1/browser/sessions/nonexistent_session_123/context",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_get_session_context_permissions_field(self, test_client, auth_headers):
        """Context should include the profile's agent_permissions list."""
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "perm_test", "profile": "private"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        session_id = resp.json()["session"]["id"]

        resp = test_client.get(
            f"/api/v1/browser/sessions/{session_id}/context",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["permissions"], list)
        # private profile has limited permissions (navigate, extract)
        assert "navigate" in data["permissions"]
        assert "extract" in data["permissions"]


# --------------------------------------------------------------------------- #
# Session profile support (spec §12)
# --------------------------------------------------------------------------- #
class TestSessionProfileSupport:
    def test_create_session_with_profile(self, test_client, auth_headers):
        """Creating a session should accept and store a profile."""
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "profile_test", "profile": "engineering"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        session = resp.json()["session"]
        assert session["profile"] == "engineering"

    def test_create_session_default_profile(self, test_client, auth_headers):
        """Creating a session without profile should default to 'personal'."""
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "default_profile_test"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        session = resp.json()["session"]
        assert session["profile"] == "personal"

    def test_create_session_invalid_profile(self, test_client, auth_headers):
        """Invalid profile name should return 400."""
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "bad_profile_test", "profile": "nonexistent_profile"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_update_session_profile(self, test_client, auth_headers):
        """Updating a session should allow changing the profile."""
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "update_profile_test", "profile": "personal"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        session_id = resp.json()["session"]["id"]

        resp = test_client.put(
            f"/api/v1/browser/sessions/{session_id}",
            json={"profile": "research"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        updated = resp.json()["session"]
        assert updated["profile"] == "research"

    def test_get_session_permissions(self, test_client, auth_headers):
        """GET /sessions/{id}/permissions should return profile permissions."""
        resp = test_client.post(
            "/api/v1/browser/sessions",
            json={"name": "perm_endpoint_test", "profile": "research"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        session_id = resp.json()["session"]["id"]

        resp = test_client.get(
            f"/api/v1/browser/sessions/{session_id}/permissions",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert data["profile"] == "research"
        assert "permissions" in data
        assert "history_policy" in data
        assert "cookie_isolation" in data


# --------------------------------------------------------------------------- #
# Semantic search reranking (spec §28, §43, §57)
# --------------------------------------------------------------------------- #
class TestSemanticSearch:
    def test_semantic_param_accepted(self, test_client, auth_headers):
        """semantic=True should return a valid response with ranking info."""
        resp = test_client.get(
            "/api/v1/search?q=test&semantic=true&include_web=false",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "semantic" in data
        assert "semantic_backend" in data

    def test_semantic_rerank_preserves_results(self, test_client, auth_headers):
        """Semantic rerank should return a subset/superset of text results (no fabrication)."""
        from jarvis_backend.core import get_store
        store = get_store("knowledge")
        data = store.load()
        if not isinstance(data, dict):
            data = {}
        test_key = f"sem_test_{int(time.time())}"
        data[test_key] = {
            "key": test_key,
            "title": "Neural Network Pruning Guide",
            "value": "Pruning reduces model size by removing redundant weights in deep networks.",
            "user_id": "system",
            "created_at": "2024-01-01T00:00:00Z",
        }
        store.save()

        try:
            resp = test_client.get(
                "/api/v1/search?q=neural+network+pruning&domain=knowledge&semantic=true&include_web=false",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            result = resp.json()
            assert result["total_results"] >= 1
            assert result["semantic"] is True
            found = any(r["id"] == test_key for r in result["results"])
            assert found
        finally:
            if test_key in data:
                del data[test_key]
                store.save()

    def test_semantic_ranker_offline(self):
        """SemanticRanker should work offline via the fingerprint fallback."""
        from jarvis_backend.semantic_index import SemanticRanker
        ranker = SemanticRanker()
        assert ranker.available()
        sims = ranker.similarity("quantum computing", ["quantum computing", "cat photos"])
        assert len(sims) == 2
        # The exact-match candidate should score higher.
        assert sims[0] >= sims[1]


# --------------------------------------------------------------------------- #
# Learning domain search (spec §41)
# --------------------------------------------------------------------------- #
class TestLearningSearch:
    def test_learning_in_domains_list(self, test_client, auth_headers):
        """Learning should appear in the domains list."""
        resp = test_client.get("/api/v1/search/domains", headers=auth_headers)
        assert resp.status_code == 200
        assert "learning" in resp.json()

    def test_learning_domain_searchable(self, test_client, auth_headers):
        """Searching the learning domain should not error."""
        resp = test_client.get(
            "/api/v1/search?q=model&domain=learning&include_web=false",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "learning" in data["domains_searched"]

    def test_learning_bridge_exposes_arenas(self):
        """get_learning_arenas should expose the full arena set."""
        from jarvis_backend.learning_bridge import get_learning_arenas, reset_learning_arenas
        reset_learning_arenas()
        arenas = get_learning_arenas()
        for key in ("feedback", "failures", "evaluations", "model_revisions",
                    "datasets", "experiences", "training_runs"):
            assert key in arenas


# --------------------------------------------------------------------------- #
# Search history (spec §44)
# --------------------------------------------------------------------------- #
class TestSearchHistory:
    def test_search_records_history(self, test_client, auth_headers):
        """A search should be recorded in the search_history store."""
        from jarvis_backend.core import get_store
        hist_store = get_store("search_history")
        hist_store.load()
        resp = test_client.get(
            "/api/v1/search?q=history_marker_test&include_web=false",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        history = hist_store.load()
        if isinstance(history, list):
            matches = [h for h in history if h.get("query") == "history_marker_test"]
            assert len(matches) >= 1
        hist_store.save()

    def test_history_endpoint(self, test_client, auth_headers):
        """GET /history should return the caller's history."""
        resp = test_client.get("/api/v1/search/history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], list)


# --------------------------------------------------------------------------- #
# Search explain / structured query (spec §38, §40, §43)
# --------------------------------------------------------------------------- #
class TestSearchExplain:
    def test_explain_endpoint(self, test_client, auth_headers):
        """POST /explain should return parsed query + ranking info."""
        resp = test_client.post(
            "/api/v1/search/explain",
            json={"query": "type:lesson neural networks"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "type:lesson neural networks"
        assert "parsed" in data
        assert data["parsed"]["modifiers"].get("type") == "lesson"
        assert data["parsed"]["free_text"] == "neural networks"
        assert "ranking" in data

    def test_structured_query_parsed(self, test_client, auth_headers):
        """Structured modifiers should be parsed out of the free text."""
        resp = test_client.post(
            "/api/v1/search/explain",
            json={"query": "domain:browser after:2024-01-01 example"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        parsed = resp.json()["parsed"]
        assert parsed["modifiers"].get("domain") == "browser"
        assert parsed["modifiers"].get("after") == "2024-01-01"
        assert parsed["free_text"] == "example"

    def test_explain_with_semantic(self, test_client, auth_headers):
        """Explain should honour the semantic flag."""
        resp = test_client.post(
            "/api/v1/search/explain",
            json={"query": "quantum", "semantic": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        ranking = resp.json()["ranking"]
        assert ranking["method"] in ("neural", "fingerprint", "text")


# --------------------------------------------------------------------------- #
# WhatsApp Web compatibility (spec §61)
# --------------------------------------------------------------------------- #
class TestWhatsAppClassification:
    def test_whatsapp_strict_csp_classifies_top_level(self):
        """WhatsApp sets CSP frame-ancestors 'none' — must require top-level context."""
        from jarvis_backend.browser_engine import (
            classify_navigation_context, NavigationPresentation,
        )
        ctx = classify_navigation_context(
            "https://web.whatsapp.com/",
            {"Content-Security-Policy": "frame-ancestors 'none'"},
        )
        assert ctx.presentation == NavigationPresentation.TOP_LEVEL
        assert "frame" in ctx.reason.lower() or "csp" in ctx.reason.lower()

    def test_whatsapp_x_frame_deny_classifies_top_level(self, test_client, auth_headers):
        """X-Frame-Options: DENY should classify WhatsApp as top-level."""
        resp = test_client.post(
            "/api/v1/browser/navigate/context",
            json={"url": "https://web.whatsapp.com/",
                  "headers": {"X-Frame-Options": "DENY"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["presentation"] == "top_level"

    def test_whatsapp_open_context_top_level(self, test_client, auth_headers):
        """Open-context for WhatsApp should target top_level."""
        resp = test_client.post(
            "/api/v1/browser/open-context",
            json={"url": "https://web.whatsapp.com/",
                  "headers": {"Content-Security-Policy": "frame-ancestors 'none'"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["target"] == "top_level"

    def test_network_diagnostics_dns_result_shape(self):
        """DnsDiagnosticsResult exposes the real attributes (not broken stubs)."""
        from jarvis_backend.network_diagnostics import DnsDiagnosticsResult
        result = DnsDiagnosticsResult(hostname="example.com")
        assert hasattr(result, "all_available")
        assert hasattr(result, "records")
        assert hasattr(result, "system_resolver")
        assert hasattr(result, "alternate_resolvers")

    def test_network_diagnostics_tcp_result_shape(self):
        """TransportDiagnostics.tcp_probe returns a dict with 'reached'."""
        from jarvis_backend.network_diagnostics import TransportDiagnostics
        result = TransportDiagnostics.tcp_probe("127.0.0.1", 1)
        assert isinstance(result, dict)
        assert "reached" in result
        assert "error" in result

    def test_whatsapp_check_script_parses(self):
        """The _whatsapp_check.py scratch script must be syntactically valid."""
        import ast
        src = open("../../../_whatsapp_check.py", encoding="utf-8").read() if False else None
        # The script lives above the repo root at F:\AI/_whatsapp_check.py.
        import os
        candidates = ["_whatsapp_check.py", "../../_whatsapp_check.py",
                      "../../../_whatsapp_check.py"]
        found = None
        for c in candidates:
            if os.path.exists(c):
                found = c
                break
        if found is None:
            # Locate via known workspace root.
            for c in ["F:/AI/_whatsapp_check.py"]:
                if os.path.exists(c):
                    found = c
                    break
        assert found is not None, "_whatsapp_check.py not found"
        ast.parse(open(found, encoding="utf-8").read())
