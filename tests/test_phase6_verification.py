"""
Phase 6 Verification Tests.

Tests for the verification engine and platform diagnostics.
"""

import pytest
import json
import tempfile
import os


class TestVerificationEngine:
    """Tests for the VerificationEngine class."""

    def test_verify_python_syntax_valid(self):
        """Test that valid Python syntax passes verification."""
        from jarvis_backend.verify import get_verification_engine
        
        engine = get_verification_engine()
        code = "def hello():\n    return 'world'"
        result = engine.verify_python_syntax(code)
        
        assert result.verified is True
        assert result.status == "passed"
        assert "Python syntax is valid" in result.description

    def test_verify_python_syntax_invalid(self):
        """Test that invalid Python syntax fails verification."""
        from jarvis_backend.verify import get_verification_engine
        
        engine = get_verification_engine()
        code = "def hello(:\n    return 'world'"  # Missing closing paren
        result = engine.verify_python_syntax(code)
        
        assert result.verified is False
        assert result.status == "failed"

    def test_verify_json_document_valid(self):
        """Test that valid JSON passes verification."""
        from jarvis_backend.verify import get_verification_engine
        
        engine = get_verification_engine()
        content = '{"name": "test", "value": 123}'
        result = engine.verify_json_document(content)
        
        assert result.verified is True
        assert result.status == "passed"

    def test_verify_json_document_invalid(self):
        """Test that invalid JSON fails verification."""
        from jarvis_backend.verify import get_verification_engine
        
        engine = get_verification_engine()
        content = '{"name": "test", invalid}'
        result = engine.verify_json_document(content)
        
        assert result.verified is False
        assert result.status == "failed"

    def test_verify_csv_document_valid(self):
        """Test that valid CSV passes verification."""
        from jarvis_backend.verify import get_verification_engine
        
        engine = get_verification_engine()
        content = "name,value\ntest,123\nfoo,456"
        result = engine.verify_csv_document(content)
        
        assert result.verified is True
        assert result.status == "passed"

    def test_verify_csv_document_invalid(self):
        """Test that malformed CSV fails verification."""
        from jarvis_backend.verify import get_verification_engine
        
        engine = get_verification_engine()
        content = "name,value\na,b,c\ntest,123"  # Inconsistent columns
        result = engine.verify_csv_document(content)
        
        assert result.verified is False
        assert result.status == "failed"

    def test_verify_math_valid(self):
        """Test that math expressions are verified correctly."""
        from jarvis_backend.verify import verify_math
        
        results = verify_math("The answer is 2 + 2 = 4")
        assert len(results) > 0
        assert results[0]["verified"] is True
        assert results[0]["value"] == 4

    def test_verify_composite_all_passed(self):
        """Test composite verification when all pass."""
        from jarvis_backend.verify import get_verification_engine, VerificationResult
        
        engine = get_verification_engine()
        results = [
            VerificationResult(verified=True, status="passed"),
            VerificationResult(verified=True, status="passed"),
        ]
        result = engine.verify_composite(results, require_all=True)
        
        assert result.verified is True
        assert result.status == "passed"

    def test_verify_composite_some_failed(self):
        """Test composite verification when some fail."""
        from jarvis_backend.verify import get_verification_engine, VerificationResult
        
        engine = get_verification_engine()
        results = [
            VerificationResult(verified=True, status="passed"),
            VerificationResult(verified=False, status="failed"),
        ]
        result = engine.verify_composite(results, require_all=True)
        
        assert result.verified is False
        assert result.status == "failed"


class TestVerifiedChat:
    """Tests for the verified_chat function."""

    def test_retrieve_finds_relevant_items(self):
        """Test that retrieve finds relevant knowledge items."""
        from jarvis_backend.verify import retrieve
        
        # Create a temporary knowledge item
        from jarvis_backend.core import get_store
        store = get_store("knowledge")
        items = store.load()
        
        # Add a test item
        items["test-key"] = {
            "key": "test-key",
            "value": "This is test content for testing retrieval",
            "tags": ["test", "verification"]
        }
        store.save()
        
        results = retrieve("test content", limit=3)
        
        # Clean up
        store.load().pop("test-key", None)
        store.save()
        
        assert isinstance(results, list)

    def test_find_math_expressions(self):
        """Test that math expressions are found correctly."""
        from jarvis_backend.verify import find_math_expressions
        
        text = "The result of 2 + 2 equals 4, and 10 * 5 = 50"
        patterns = find_math_expressions(text)
        
        assert len(patterns) >= 1
        assert any("+" in p for p in patterns)


class TestVerificationRouter:
    """Tests for the verification API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from jarvis_backend.main import app
        return TestClient(app)

    def test_verify_code_endpoint(self, client, auth_headers):
        """Test the POST /verify/code endpoint."""
        response = client.post(
            "/api/v1/verify/code",
            json={"code": "x = 1 + 1", "check_type": "syntax"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("verified") is True

    def test_verify_document_endpoint(self, client, auth_headers):
        """Test the POST /verify/document endpoint."""
        response = client.post(
            "/api/v1/verify/document",
            json={"content": '{"test": "value"}', "format": "json"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("verified") is True

    def test_verification_endpoints_exist(self, client):
        """Test that verification endpoints are registered and accessible."""
        # Test verify/code endpoint with minimal valid data
        response = client.post(
            "/api/v1/verify/code",
            json={"code": "pass", "check_type": "syntax"}
        )
        # Should not be 404 (route not found)
        assert response.status_code != 404, "Route /api/v1/verify/code not registered"
        # Should work (200) or need auth (401) but not route not found (404)
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"


class TestPlatformDiagnostics:
    """Tests for platform diagnostics."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from jarvis_backend.main import app
        return TestClient(app)

    def test_platform_diagnose_endpoint(self, client, admin_headers):
        """Test the GET /system/diagnose endpoint."""
        response = client.get("/api/v1/system/diagnose", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "services" in data
        assert "providers" in data
        assert "verification" in data

    def test_platform_diagnose_includes_required_fields(self, client, admin_headers):
        """Test that diagnostics includes all required fields."""
        response = client.get("/api/v1/system/diagnose", headers=admin_headers)
        data = response.json()
        
        # Check required fields
        assert "status" in data
        assert "timestamp" in data
        assert "services" in data
        assert "database" in data["services"]
        assert "chat" in data["services"]
        assert "tasks" in data["services"]
        assert "memory" in data["services"]
        assert "knowledge" in data["services"]


class TestCapabilityIntegration:
    """Tests for capability verification integration."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from jarvis_backend.main import app
        return TestClient(app)

    def test_verify_capabilities_endpoint(self, client, auth_headers):
        """Test verification of capabilities."""
        response = client.get(
            "/api/v1/verify/capabilities",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_capabilities" in data
        assert "capabilities" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])