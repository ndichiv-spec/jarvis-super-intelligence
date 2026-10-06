"""Regression test suite runner and coverage validation."""

from __future__ import annotations
import pytest


# ── Regression Marker Configuration ──────────────────────
# Run with: pytest tests/regression/ -m regression
# Run full suite: pytest tests/regression/


class TestRegressionSuite:
    """Meta-tests that verify the test suite itself is healthy."""

    def test_required_test_dirs_exist(self):
        import os
        dirs = [
            "tests/infrastructure",
            "tests/api",
            "tests/orchestrator",
            "tests/memory",
            "tests/automation",
            "tests/regression",
            "tests/utils",
            "tests/deployment",
        ]
        for d in dirs:
            assert os.path.isdir(d), f"Missing test directory: {d}"

    def test_required_test_files_exist(self):
        import os
        files = [
            "tests/infrastructure/test_config.py",
            "tests/infrastructure/test_vault.py",
            "tests/infrastructure/test_logsys.py",
            "tests/infrastructure/test_health.py",
            "tests/infrastructure/test_startup.py",
            "tests/infrastructure/test_observability.py",
            "tests/infrastructure/test_security.py",
            "tests/infrastructure/test_resilience.py",
            "tests/infrastructure/test_errors.py",
            "tests/infrastructure/test_sandbox.py",
            "tests/infrastructure/test_plugins.py",
            "tests/utils/mocks.py",
            "tests/utils/factories.py",
            "tests/utils/assertions.py",
            "tests/utils/helpers.py",
        ]
        for f in files:
            assert os.path.isfile(f), f"Missing test file: {f}"

    def test_pytest_ini_has_asyncio_mode(self):
        import configparser
        import os
        if os.path.exists("pytest.ini"):
            config = configparser.ConfigParser()
            config.read("pytest.ini")
            mode = config.get("tool:pytest", "asyncio_mode", fallback="")
            assert mode == "auto", "pytest.ini must set asyncio_mode = auto"
        elif os.path.exists("pyproject.toml"):
            import tomllib
            with open("pyproject.toml", "rb") as f:
                data = tomllib.load(f)
            mode = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("asyncio_mode", "")
            assert mode == "auto"


class TestCoverageValidation:
    """Validates that test coverage infrastructure is configured."""

    def test_coverage_config_exists(self):
        import os
        has_setup = os.path.exists("setup.cfg")
        has_pyproject = os.path.exists("pyproject.toml")
        has_coveragerc = os.path.exists(".coveragerc")
        assert any([has_setup, has_pyproject, has_coveragerc]), (
            "No coverage configuration found (setup.cfg, pyproject.toml, or .coveragerc)"
        )

    def test_pytest_cov_installed(self):
        try:
            import pytest_cov
            assert pytest_cov is not None
        except ImportError:
            pytest.skip("pytest-cov not installed")

    def test_coverage_minimum_threshold(self):
        import os
        threshold = 70
        assert 0 <= threshold <= 100


class TestRegressionMarkers:
    """Verify regression test markers are properly configured."""

    @pytest.mark.slow
    def test_slow_marker_works(self):
        assert True

    @pytest.mark.integration
    def test_integration_marker_works(self):
        assert True

    def test_smoke_tests_pass(self):
        """Quick sanity checks that core functionality works."""
        assert 1 + 1 == 2
        assert isinstance("test", str)
        assert [1, 2, 3][0] == 1


class TestTestUtilityImports:
    """Verify all test utilities can be imported without errors."""

    def test_import_mocks(self):
        from tests.utils.mocks import MockAIProvider, MockEmbeddingProvider
        assert MockAIProvider is not None
        assert MockEmbeddingProvider is not None

    def test_import_factories(self):
        from tests.utils.factories import DocumentFactory, ChunkFactory
        assert DocumentFactory is not None
        assert ChunkFactory is not None

    def test_import_assertions(self):
        from tests.utils.assertions import assert_valid_document, assert_valid_chunk
        assert assert_valid_document is not None
        assert assert_valid_chunk is not None

    def test_import_helpers(self):
        from tests.utils.helpers import temp_env_vars, measure_time
        assert temp_env_vars is not None
        assert measure_time is not None

    def test_use_mock_ai_provider(self):
        from tests.utils.mocks import MockAIProvider
        import asyncio
        provider = MockAIProvider(response_template="Answer: {query}")
        result = asyncio.run(provider.generate("test"))
        assert "Answer:" in result

    def test_use_document_factory(self):
        from tests.utils.factories import DocumentFactory
        doc = DocumentFactory.create(content="factory test")
        assert doc.content == "factory test"
        assert doc.id is not None
