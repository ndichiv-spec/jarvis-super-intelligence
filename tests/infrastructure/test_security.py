"""Tests for infrastructure.security — JWTAuthenticator, RateLimiter, ApiKeyManager."""

from __future__ import annotations
import time
import pytest


class TestJWTAuthenticator:
    def test_create_token(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1", roles=["admin"])
        assert token is not None
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

    def test_verify_token_valid(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1")
        payload = jwt_authenticator.verify(token)
        assert payload is not None
        assert payload.sub == "user1"

    def test_verify_token_invalid(self, jwt_authenticator):
        assert jwt_authenticator.verify("invalid.token.here") is None

    def test_verify_token_expired(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1", ttl=-1)
        assert jwt_authenticator.verify(token) is None

    def test_refresh_token(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1", roles=["admin"])
        new_token = jwt_authenticator.refresh_token(token)
        assert new_token is not None
        payload = jwt_authenticator.verify(new_token)
        assert payload.sub == "user1"

    def test_refresh_expired_token_fails(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1", ttl=-1)
        assert jwt_authenticator.refresh_token(token) is None

    def test_has_permission_admin(self, jwt_authenticator):
        token = jwt_authenticator.create_token("admin", roles=["admin"])
        assert jwt_authenticator.has_permission(token, "write") is True

    def test_has_permission_user(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1", roles=["user"], scopes=["read"])
        assert jwt_authenticator.has_permission(token, "read") is True
        assert jwt_authenticator.has_permission(token, "write") is False

    def test_has_permission_invalid_token(self, jwt_authenticator):
        assert jwt_authenticator.has_permission("bad.token", "read") is False

    def test_token_contains_roles_and_scopes(self, jwt_authenticator):
        token = jwt_authenticator.create_token("user1", roles=["user"], scopes=["read", "write"])
        payload = jwt_authenticator.verify(token)
        assert "admin" not in payload.roles
        assert "read" in payload.scopes


class TestRateLimiter:
    def test_allow_first_request(self, rate_limiter):
        result = rate_limiter.check("client1")
        assert result.allowed is True

    def test_block_after_limit(self, rate_limiter):
        rate_limiter.default_limit = 3
        for _ in range(3):
            r = rate_limiter.check("client1")
            assert r.allowed is True
        r = rate_limiter.check("client1")
        assert r.allowed is False

    def test_different_clients_independent(self, rate_limiter):
        rate_limiter.default_limit = 2
        assert rate_limiter.check("client_a").allowed is True
        assert rate_limiter.check("client_a").allowed is True
        assert rate_limiter.check("client_a").allowed is False
        assert rate_limiter.check("client_b").allowed is True

    def test_reset_client(self, rate_limiter):
        rate_limiter.default_limit = 1
        rate_limiter.check("client1")
        rate_limiter.reset("client1")
        assert rate_limiter.check("client1").allowed is True

    def test_remaining_count(self, rate_limiter):
        rate_limiter.default_limit = 5
        rate_limiter.check("client1")
        rate_limiter.check("client1")
        result = rate_limiter.check("client1")
        assert result.remaining == 2

    def test_bucket_limiter(self, rate_limiter):
        assert rate_limiter.check_bucket("burst", tokens=1, capacity=2, refill_rate=10) is True
        assert rate_limiter.check_bucket("burst", tokens=1, capacity=2, refill_rate=10) is True
        assert rate_limiter.check_bucket("burst", tokens=1, capacity=2, refill_rate=10) is False

    def test_rate_limit_result_headers(self, rate_limiter):
        result = rate_limiter.check("client1")
        headers = result.to_headers()
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers


class TestApiKeyManager:
    def test_generate_key(self, api_key_manager):
        key_id, raw_key = api_key_manager.generate("test-key")
        assert key_id is not None
        assert raw_key.startswith("jv_")

    def test_validate_key_valid(self, api_key_manager):
        key_id, raw_key = api_key_manager.generate("test-key")
        result = api_key_manager.validate(raw_key)
        assert result is not None
        assert result.name == "test-key"

    def test_validate_key_invalid(self, api_key_manager):
        assert api_key_manager.validate("jv_invalidkey123") is None

    def test_validate_revoked_key(self, api_key_manager):
        key_id, raw_key = api_key_manager.generate("test-key")
        api_key_manager.revoke(key_id)
        assert api_key_manager.validate(raw_key) is None

    def test_revoke_nonexistent_key(self, api_key_manager):
        assert api_key_manager.revoke("nonexistent") is False

    def test_get_key_by_id(self, api_key_manager):
        key_id, raw_key = api_key_manager.generate("my-key")
        api_key = api_key_manager.get(key_id)
        assert api_key is not None
        assert api_key.name == "my-key"

    def test_list_keys(self, api_key_manager):
        api_key_manager.generate("key1")
        api_key_manager.generate("key2")
        keys = api_key_manager.list_keys()
        assert len(keys) == 2

    def test_delete_key(self, api_key_manager):
        key_id, raw_key = api_key_manager.generate("to-delete")
        assert api_key_manager.delete(key_id) is True
        assert api_key_manager.get(key_id) is None
