"""Tests for infrastructure.config — ConfigLoader and sub-settings."""

from __future__ import annotations
import pytest
from tests.utils.helpers import temp_env_vars
from infrastructure.config.loader import ConfigLoader, ConfigRule, ConfigValidationError


class TestConfigLoader:
    def test_creates_with_defaults(self, config_loader):
        assert config_loader is not None

    def test_add_source_and_load(self, config_loader):
        config_loader.add_source("test", priority=10, loader=lambda: {"key": "val"})
        config = config_loader.load()
        assert config["key"] == "val"

    def test_source_lower_priority_overrides(self, config_loader):
        config_loader.add_source("high", priority=10, loader=lambda: {"key": "high_val"})
        config_loader.add_source("low", priority=20, loader=lambda: {"key": "low_val"})
        config = config_loader.load()
        assert config["key"] == "low_val"

    def test_rule_required_missing_raises(self, config_loader):
        config_loader.add_rule(ConfigRule(key="required_key", required=True, description="Must exist"))
        with pytest.raises(ConfigValidationError, match="required_key"):
            config_loader.load()

    def test_rule_required_present_passes(self, config_loader):
        config_loader.add_rule(ConfigRule(key="my_key", required=True))
        config_loader.add_source("test", priority=10, loader=lambda: {"my_key": "present"})
        config = config_loader.load()
        assert config["my_key"] == "present"

    def test_rule_default_value(self, config_loader):
        config_loader.add_rule(ConfigRule(key="opt_key", default="default_val"))
        config = config_loader.load()
        assert config["opt_key"] == "default_val"

    def test_rule_type_coercion(self, config_loader):
        config_loader.add_rule(ConfigRule(key="port", type_=int, default=8080))
        config = config_loader.load()
        assert config["port"] == 8080
        assert isinstance(config["port"], int)

    def test_rule_choices_valid(self, config_loader):
        config_loader.add_rule(ConfigRule(key="mode", choices=["dev", "prod"], default="dev"))
        config = config_loader.load()
        assert config["mode"] == "dev"

    def test_rule_choices_invalid(self, config_loader):
        config_loader.add_rule(ConfigRule(key="mode", choices=["dev", "prod"]))
        config_loader.add_source("test", priority=10, loader=lambda: {"mode": "invalid"})
        with pytest.raises(ConfigValidationError, match="mode"):
            config_loader.load()

    def test_rule_range_validation(self, config_loader):
        config_loader.add_rule(ConfigRule(key="threads", type_=int, min_value=1, max_value=100, default=4))
        config = config_loader.load()
        assert config["threads"] == 4

    def test_sensitive_marked(self, config_loader):
        config_loader.add_rule(ConfigRule(key="password", sensitive=True, required=True))
        config_loader.add_source("test", priority=10, loader=lambda: {"password": "secret123"})
        config_loader.load()
        assert config_loader.is_sensitive("password") is True

    def test_get_returns_value(self, config_loader):
        config_loader.add_source("test", priority=10, loader=lambda: {"key": "value"})
        config_loader.load()
        assert config_loader.get("key") == "value"

    def test_get_missing_returns_default(self, config_loader):
        config_loader.load()
        assert config_loader.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_returns_none(self, config_loader):
        config_loader.load()
        assert config_loader.get("nonexistent") is None

    def test_load_empty(self, config_loader):
        config = config_loader.load()
        assert config == {}

    def test_expose_redacts_sensitive(self, config_loader):
        config_loader.add_rule(ConfigRule(key="password", sensitive=True))
        config_loader.add_source("test", priority=10, loader=lambda: {"password": "secret"})
        config_loader.load()
        exposed = config_loader.expose()
        assert exposed["password"] == "***REDACTED***"


class TestDatabaseSettings:
    def test_defaults(self):
        from infrastructure.config.settings import DatabaseSettings
        s = DatabaseSettings()
        assert s.url == "sqlite+aiosqlite:///./jarvis.db"
        assert s.port == 5432

    def test_custom_values(self):
        from infrastructure.config.settings import DatabaseSettings
        s = DatabaseSettings(url="postgresql://localhost/mydb", pool_size=10)
        assert s.url == "postgresql://localhost/mydb"
        assert s.pool_size == 10


class TestServerSettings:
    def test_defaults(self):
        from infrastructure.config.settings import ServerSettings
        s = ServerSettings()
        assert s.port == 8000
        assert s.debug is False

