"""Tests for the maintained infrastructure configuration settings."""

from infrastructure.config.loader import ConfigLoader
from infrastructure.config.settings import settings_from_loader


def _settings():
    return settings_from_loader(ConfigLoader(environment="test"))


def test_settings_loaded():
    settings = _settings()
    assert settings.app_name
    assert settings.app_version


def test_app_name_uses_jarvis_identity():
    assert "JARVIS" in _settings().app_name


def test_database_url_is_configured():
    settings = _settings()
    assert isinstance(settings.database.url, str)
    assert settings.database.url


def test_api_prefix_is_configured():
    assert _settings().server.api_prefix.startswith("/")


def test_rate_limit_is_configured():
    assert _settings().security.rate_limit_per_minute > 0


def test_cors_origins_are_configured():
    assert isinstance(_settings().server.cors_origins, list)


def test_log_level_is_configured():
    assert _settings().logging.level.lower() in {
        "debug", "info", "warning", "error", "critical",
    }


def test_log_format_is_configured():
    assert _settings().logging.format in {"json", "text"}
