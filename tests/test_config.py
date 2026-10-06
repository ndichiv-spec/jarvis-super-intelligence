"""
Tests for Core Config and Logging
==================================
"""

import pytest
from unittest.mock import Mock, patch


class TestConfig:
    """Test configuration module."""

    def test_settings_loaded(self):
        """Test settings are loaded."""
        from core.config import settings

        assert settings is not None
        assert settings.APP_NAME is not None
        assert settings.APP_VERSION is not None

    def test_app_name(self):
        """Test app name is set."""
        from core.config import settings

        assert "JARVIS" in settings.APP_NAME or settings.APP_NAME

    def test_database_url(self):
        """Test database URL is configured."""
        from core.config import settings

        assert settings.DATABASE_URL is not None
        assert isinstance(settings.DATABASE_URL, str)

    def test_api_prefix(self):
        """Test API prefix is configured."""
        from core.config import settings

        assert settings.API_PREFIX is not None
        assert settings.API_PREFIX.startswith("/")

    def test_rate_limit_config(self):
        """Test rate limiting is configured."""
        from core.config import settings

        assert hasattr(settings, "RATE_LIMIT_REQUESTS")
        assert hasattr(settings, "RATE_LIMIT_PERIOD")
        assert settings.RATE_LIMIT_REQUESTS > 0

    def test_cors_config(self):
        """Test CORS is configured."""
        from core.config import settings

        assert settings.CORS_ORIGINS is not None
        assert isinstance(settings.CORS_ORIGINS, (list, str))


class TestLogging:
    """Test logging module."""

    def test_setup_logging(self):
        """Test logging setup function."""
        from core.logging import setup_logging

        # Should not raise
        setup_logging(
            log_level="DEBUG",
            log_format="console",
            log_file=None,
            service_name="test",
        )

    def test_log_level_config(self):
        """Test log level from settings."""
        from core.config import settings

        assert settings.LOG_LEVEL.lower() in ["debug", "info", "warning", "error"]

    @patch("core.logging.logging")
    def test_log_format_config(self, mock_logging):
        """Test log format configuration."""
        from core.config import settings

        assert settings.LOG_FORMAT in ["json", "console", "standard"]


class TestErrorTracker:
    """Test error tracking module."""

    def test_error_tracker_import(self):
        """Test error tracker can be imported."""
        from core.error_tracker import get_error_tracker

        tracker = get_error_tracker()
        assert tracker is not None

    def test_error_tracker_setup(self):
        """Test error tracker setup."""
        from core.error_tracker import ErrorTracker

        tracker = ErrorTracker()
        tracker.setup()
        assert tracker.is_initialized() == True

    def test_error_tracker_sentry_status(self):
        """Test error tracker sentry status."""
        from core.error_tracker import get_error_tracker

        tracker = get_error_tracker()
        # Should return boolean for sentry status
        assert isinstance(tracker.is_sentry_enabled(), bool)


class TestDatabase:
    """Test database module."""

    def test_database_import(self):
        """Test database module can be imported."""
        from core.database import get_engine, get_session_factory

        engine = get_engine()
        assert engine is not None

        factory = get_session_factory()
        assert factory is not None
