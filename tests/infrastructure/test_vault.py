"""Tests for infrastructure.vault — SecretsManager."""

from __future__ import annotations
import os
import pytest
from tests.utils.helpers import temp_env_vars
from infrastructure.vault.manager import SecretNotFoundError, EnvBackend, DotenvBackend


class TestSecretsManager:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.manager = None

    def _make_manager(self, backends=None):
        from infrastructure.vault import SecretsManager
        return SecretsManager(backends=backends or [EnvBackend(prefix="TEST_")])

    def test_get_env_secret(self):
        manager = self._make_manager()
        with temp_env_vars({"TEST_MY_SECRET": "env_value"}):
            assert manager.get("MY_SECRET") == "env_value"

    def test_get_missing_raises(self):
        manager = self._make_manager()
        with pytest.raises(SecretNotFoundError):
            manager.get("NONEXISTENT_SECRET_XYZ")

    def test_get_or_none_missing(self):
        manager = self._make_manager()
        assert manager.get_or_none("NONEXISTENT") is None

    def test_get_or_none_present(self):
        manager = self._make_manager()
        with temp_env_vars({"TEST_FOUND_SECRET": "yes"}):
            assert manager.get_or_none("FOUND_SECRET") == "yes"

    def test_get_with_default(self):
        manager = self._make_manager()
        val = manager.get("MISSING_KEY", default="fallback")
        assert val == "fallback"

    def test_get_from_env_backend(self):
        manager = self._make_manager()
        with temp_env_vars({"TEST_DATABASE_URL": "postgresql://localhost/mydb"}):
            val = manager.get("DATABASE_URL")
            assert val == "postgresql://localhost/mydb"

    def test_mask_short_value(self):
        manager = self._make_manager()
        assert manager.mask("ab") == "****"

    def test_mask_long_value(self):
        manager = self._make_manager()
        assert manager.mask("supersecretkey123") == "supe****"

    def test_get_masked(self):
        manager = self._make_manager()
        with temp_env_vars({"TEST_API_KEY": "sk-1234567890abcdef"}):
            masked = manager.get_masked("API_KEY")
            assert "sk-1" in masked
            assert "abcdef" not in masked

    def test_add_custom_backend(self):
        from infrastructure.vault.manager import SecretBackend
        class TestBackend(SecretBackend):
            def name(self): return "test"
            def get(self, key): return "test_val" if key == "custom" else None
            def list_keys(self): return ["custom"]
            def health(self): return True
        manager = self._make_manager(backends=[TestBackend()])
        assert manager.get("custom") == "test_val"

    def test_backend_priority(self):
        from infrastructure.vault.manager import SecretBackend
        class LowBackend(SecretBackend):
            def name(self): return "low"
            def get(self, key): return "low_value"
            def list_keys(self): return []
            def health(self): return True
        manager = self._make_manager(backends=[EnvBackend(prefix="TEST_"), LowBackend()])
        with temp_env_vars({"TEST_CONFLICT_KEY": "high_value"}):
            assert manager.get("CONFLICT_KEY") == "high_value"


class TestEnvBackend:
    def test_uses_prefix(self):
        with temp_env_vars({"TEST_SPECIAL_KEY": "special_value"}):
            backend = EnvBackend(prefix="TEST_")
            assert backend.get("SPECIAL_KEY") == "special_value"

    def test_list_keys(self):
        with temp_env_vars({"TEST_KEY_A": "a", "TEST_KEY_B": "b"}):
            backend = EnvBackend(prefix="TEST_")
            keys = backend.list_keys()
            assert "KEY_A" in keys
            assert "KEY_B" in keys
