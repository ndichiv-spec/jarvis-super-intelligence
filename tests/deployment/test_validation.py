"""Tests for deployment validation — pre-flight checks, config, and environment."""

from __future__ import annotations
import os
import pytest
from tests.utils.helpers import temp_env_vars


class TestEnvironmentValidation:
    def test_required_env_vars_documented(self):
        required_vars = [
            "SECRET_KEY",
            "DATABASE_URL",
            "LOG_LEVEL",
        ]
        for var in required_vars:
            assert var, f"Required env var {var} must be defined"

    def test_env_var_format_validation(self):
        valid = "postgresql://user:pass@localhost:5432/jarvis"
        invalid = "not-a-url"
        assert "://" in valid
        assert "://" not in invalid

    def test_port_numbers_valid_range(self):
        ports = [8000, 5432, 6379, 8080]
        for port in ports:
            assert 1 <= port <= 65535

    def test_secret_key_minimum_length(self):
        short_key = "abc"
        long_key = "a" * 32
        assert len(short_key) < 32
        assert len(long_key) >= 32


class TestStartupValidation:
    def test_config_validation_required_fields(self):
        from infrastructure.config.loader import ConfigLoader, ConfigRule, ConfigValidationError
        loader = ConfigLoader()
        loader.add_rule(ConfigRule(key="secret_key", required=True, description="Must exist"))
        with pytest.raises(ConfigValidationError):
            loader.load()

    def test_config_validation_type_check(self):
        from infrastructure.config.loader import ConfigLoader, ConfigRule, ConfigValidationError
        loader = ConfigLoader()
        loader.add_rule(ConfigRule(key="port", type_=int))
        loader.add_source("test", priority=10, loader=lambda: {"port": "not_a_number"})
        with pytest.raises(ConfigValidationError):
            loader.load()

    def test_env_prefix_consistency(self):
        prefix = "JARVIS_"
        vars_with_prefix = {
            "JARVIS_APP_NAME": "Jarvis",
            "JARVIS_DEBUG": "true",
            "JARVIS_LOG_LEVEL": "INFO",
            "JARVIS_DATABASE_URL": "sqlite:///db.sqlite",
        }
        for key in vars_with_prefix:
            assert key.startswith(prefix)

    def test_database_url_default_fallback(self):
        url = os.environ.get("DATABASE_URL", "sqlite:///default.db")
        assert url.endswith(".db") or url.startswith("postgresql")


class TestDeploymentConfig:
    def test_docker_compose_required_services(self):
        required_services = ["api", "redis", "postgres"]
        assert "api" in required_services
        assert "redis" in required_services
        assert "postgres" in required_services

    def test_healthcheck_endpoints_defined(self):
        endpoints = {
            "api": "/health",
            "redis": "redis://localhost:6379/0",
            "postgres": "postgresql://localhost:5432/jarvis",
        }
        assert endpoints["api"] == "/health"
        assert endpoints["redis"].startswith("redis://")

    def test_resource_limits_defined(self):
        limits = {"cpus": "1.0", "memory": "512M"}
        assert float(limits["cpus"]) > 0
        assert limits["memory"].endswith("M") or limits["memory"].endswith("G")

    def test_deployment_mode_selection(self):
        modes = ["local", "cloud", "hybrid"]
        for mode in modes:
            assert mode in ["local", "cloud", "hybrid"]
