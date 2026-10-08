"""Tests for administrative password reset mechanism."""

import os
import pytest
from jarvis_backend.core import get_store, hash_password, verify_password
from jarvis_backend.admin_reset import reset_admin_password, AdminResetError


@pytest.fixture
def seed_admin_user(client):
    """Seed a test admin user into the isolated test store."""
    store = get_store("users")
    users = store.load()
    admin_id = "test-admin-id"
    users[admin_id] = {
        "id": admin_id,
        "email": "admin@jarvis.local",
        "role": "admin",
        "roles": ["admin"],
        "password_hash": hash_password("OldPassword123"),
        "owner": True,
    }
    store.save()
    return admin_id


def test_reset_admin_password_explicit(seed_admin_user):
    """Test explicit admin password reset with provided password."""
    admin_id = seed_admin_user
    users = get_store("users").load()
    original_hash = users[admin_id]["password_hash"]

    new_pw = "NewAdminPassword!2026"
    res = reset_admin_password(identifier=admin_id, new_password=new_pw)

    assert res["success"] is True
    assert res["user_id"] == admin_id
    assert "password" not in res
    assert "NewAdminPassword" not in str(res)

    # Verify updated hash in store
    updated_users = get_store("users").load()
    updated_hash = updated_users[admin_id]["password_hash"]
    assert updated_hash != original_hash
    assert verify_password(new_pw, updated_hash) is True
    assert verify_password("wrong-password", updated_hash) is False


def test_reset_admin_password_from_env(seed_admin_user, monkeypatch):
    """Test admin password reset using JARVIS_ADMIN_PASSWORD environment variable."""
    env_pw = "EnvAdminSecret98765#"
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", env_pw)

    res = reset_admin_password(identifier="admin@jarvis.local")
    assert res["success"] is True

    updated_users = get_store("users").load()
    updated_user = next(u for u in updated_users.values() if u.get("email") == "admin@jarvis.local")
    assert verify_password(env_pw, updated_user["password_hash"]) is True


def test_reset_admin_password_short_password(seed_admin_user):
    """Test rejection of passwords shorter than 8 characters."""
    with pytest.raises(AdminResetError, match="at least 8 characters"):
        reset_admin_password(new_password="short")


def test_reset_admin_password_nonexistent_user(seed_admin_user):
    """Test rejection when targeting a non-existent user."""
    with pytest.raises(AdminResetError, match="not found"):
        reset_admin_password(identifier="nonexistent@nowhere.local", new_password="ValidPassword123")


def test_reset_admin_password_non_admin_user(seed_admin_user):
    """Test rejection when targeting a non-admin user when require_admin_role is True."""
    store = get_store("users")
    users = store.load()
    test_user_id = "test-regular-user"
    users[test_user_id] = {
        "id": test_user_id,
        "email": "regular@jarvis.local",
        "role": "user",
        "roles": ["user"],
        "password_hash": hash_password("OldPassword123"),
    }
    store.save()

    with pytest.raises(AdminResetError, match="does not have admin privileges"):
        reset_admin_password(identifier="regular@jarvis.local", new_password="ValidPassword123")
