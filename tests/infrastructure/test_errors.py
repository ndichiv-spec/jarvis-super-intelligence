"""Tests for infrastructure.errors — Error types, handler, tracker."""

from __future__ import annotations
import pytest


class TestErrorTypes:
    def test_jarvis_error_base(self):
        from infrastructure.errors import JarvisError
        err = JarvisError(message="Test error", code="test_error", subsystem="core")
        assert str(err) == "[test_error] Test error"
        d = err.to_dict()
        assert d["code"] == "test_error"
        assert d["subsystem"] == "core"

    def test_jarvis_error_defaults(self):
        from infrastructure.errors import JarvisError
        err = JarvisError()
        assert err.code == "internal_error"
        assert err.subsystem == "core"
        assert err.details == {}

    def test_jarvis_error_with_details(self):
        from infrastructure.errors import JarvisError
        err = JarvisError(message="Detail test", details={"key": "val"})
        assert err.details["key"] == "val"

    def test_jarvis_error_with_original(self):
        from infrastructure.errors import JarvisError
        original = ValueError("original")
        err = JarvisError(message="Wrapped", original=original)
        assert err.original is original

    def test_configuration_error(self):
        from infrastructure.errors import ConfigurationError
        err = ConfigurationError("Missing API key", details={"key": "OPENAI_KEY"})
        assert err.code == "configuration_error"
        assert err.subsystem == "config"

    def test_authentication_error(self):
        from infrastructure.errors import AuthenticationError
        err = AuthenticationError("Invalid token")
        assert err.code == "authentication_error"
        assert err.subsystem == "security"

    def test_authorization_error(self):
        from infrastructure.errors import AuthorizationError
        err = AuthorizationError("Not allowed")
        assert err.code == "authorization_error"

    def test_not_found_error(self):
        from infrastructure.errors import NotFoundError
        err = NotFoundError("Document not found")
        assert err.code == "not_found"

    def test_validation_error(self):
        from infrastructure.errors import ValidationError
        err = ValidationError("Invalid input", details={"field": "name"})
        assert err.code == "validation_error"

    def test_ai_provider_error(self):
        from infrastructure.errors import AIProviderError
        err = AIProviderError("OpenAI API error", provider="openai")
        assert err.code == "ai_provider_error"
        assert err.details["provider"] == "openai"

    def test_sandbox_error(self):
        from infrastructure.errors import SandboxError
        err = SandboxError("Execution rejected", action="rm -rf /")
        assert err.code == "sandbox_error"

    def test_rate_limit_error(self):
        from infrastructure.errors import RateLimitError
        err = RateLimitError("Too many requests", retry_after=30)
        assert err.code == "rate_limit_error"
        assert err.details["retry_after"] == 30

    def test_database_error(self):
        from infrastructure.errors import DatabaseError
        err = DatabaseError("Connection lost")
        assert err.code == "database_error"

    def test_integration_error(self):
        from infrastructure.errors import IntegrationError
        err = IntegrationError("GitHub API failure", service="github")
        assert err.code == "integration_error"

    def test_exception_inheritance(self):
        from infrastructure.errors import JarvisError, AuthenticationError
        assert issubclass(AuthenticationError, JarvisError)
        assert issubclass(AuthenticationError, Exception)


class TestErrorTracker:
    def test_tracks_error_event(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        event = ErrorEvent(code="test", message="test error", subsystem="core")
        error_tracker.track(event)
        events = error_tracker.get_events()
        assert len(events) == 1
        assert events[0].code == "test"

    def test_dedup_within_window(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        e1 = ErrorEvent(code="dup", message="first", subsystem="core")
        e2 = ErrorEvent(code="dup", message="second", subsystem="core")
        error_tracker.track(e1)
        error_tracker.track(e2)
        assert len(error_tracker.get_events()) == 1

    def test_different_codes_not_deduped(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        error_tracker.track(ErrorEvent(code="a", subsystem="core"))
        error_tracker.track(ErrorEvent(code="b", subsystem="core"))
        assert len(error_tracker.get_events()) == 2

    def test_track_exception(self, error_tracker):
        try:
            raise ValueError("something broke")
        except ValueError as e:
            error_tracker.track_exception(e, subsystem="test")
        events = error_tracker.get_events()
        assert len(events) == 1
        assert "something broke" in events[0].message

    def test_track_exception_with_jarvis_error(self, error_tracker):
        from infrastructure.errors import ConfigurationError
        err = ConfigurationError("bad config")
        error_tracker.track_exception(err)
        events = error_tracker.get_events()
        assert events[0].code == "configuration_error"
        assert events[0].subsystem == "config"

    def test_filter_by_subsystem(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        error_tracker.track(ErrorEvent(code="a", subsystem="core"))
        error_tracker.track(ErrorEvent(code="b", subsystem="plugins"))
        core_events = error_tracker.get_events(subsystem="core")
        assert len(core_events) == 1
        assert core_events[0].code == "a"

    def test_filter_by_severity(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        error_tracker.track(ErrorEvent(code="a", severity="error"))
        error_tracker.track(ErrorEvent(code="b", severity="warning"))
        errors = error_tracker.get_events(severity="error")
        assert len(errors) == 1

    def test_get_stats(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        error_tracker.track(ErrorEvent(code="e1", subsystem="core", severity="error"))
        error_tracker.track(ErrorEvent(code="e2", subsystem="plugins", severity="warning"))
        stats = error_tracker.get_stats()
        assert stats["total_events"] == 2
        assert stats["by_subsystem"]["core"] == 1
        assert stats["by_severity"]["error"] == 1

    def test_clear(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        error_tracker.track(ErrorEvent(code="test", subsystem="core"))
        error_tracker.clear()
        assert len(error_tracker.get_events()) == 0

    def test_add_exporter(self, error_tracker):
        from infrastructure.errors import ErrorEvent
        exported = []
        error_tracker.add_exporter(lambda event: exported.append(event))
        error_tracker.track(ErrorEvent(code="x", subsystem="core"))
        assert len(exported) == 1
