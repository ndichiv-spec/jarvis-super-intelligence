import sys
from pathlib import Path

fn = Path("tests/test_security_regression.py")
c = fn.read_text(encoding="utf-8")

repls = []

# R1: extend core imports for API-key helpers (keep originals, add api_key_prefix + generate_api_key)
repls.append((
'''from jarvis_backend.core import (  # noqa: E402
    admin_email, create_token, decode_token, create_refresh_token,
    refresh_access_token, now, now_iso, iso_expire_at, is_api_key_expired,
    _iso_to_epoch, is_production, get_store, hash_password,
)''',
'''from jarvis_backend.core import (  # noqa: E402
    admin_email, api_key_prefix, create_token, decode_token, create_refresh_token,
    generate_api_key, now, now_iso, iso_expire_at, is_api_key_expired,
    _iso_to_epoch, is_production, get_store, hash_password, refresh_access_token,
)''',
))

# R2: add _make_admin_user helper + admin_headers fixture after _oauth_clients
repls.append((
'''@pytest.fixture(autouse=True)
def _oauth_clients(monkeypatch):
    """Seed JARVIS_OAUTH_CLIENTS for the OAuth-scoped tests (isolated per test)."""
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps(GMAIL_CLIENTS))''',
'''@pytest.fixture(autouse=True)
def _oauth_clients(monkeypatch):
    """Seed JARVIS_OAUTH_CLIENTS for the OAuth-scoped tests (isolated per test)."""
    monkeypatch.setenv("JARVIS_OAUTH_CLIENTS", json.dumps(GMAIL_CLIENTS))


def _make_admin_user():
    """Create an admin user in the store; return (user_id, Authorization headers)."""
    uid = str(uuid.uuid4())
    users = get_store("users").load()
    users[uid] = {
        "id": uid, "email": f"admin-{uid[:8]}@t.test", "username": "admin_" + uid[:8],
        "password_hash": hash_password("Admin#Jarvis1"),
        "full_name": "Admin", "avatar_url": None, "status": "active",
        "tenant_id": None, "roles": ["admin"], "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    return uid, {"Authorization": f"Bearer {create_token({'sub': uid, 'sid': None})}"}


@pytest.fixture
def admin_headers():
    _, headers = _make_admin_user()
    return headers''',
))

# R3
repls.append((
'''    def test_create_api_key_endpoint_sets_future_expiry(self, client, auth_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "reg-key", "expires_in_days": 30},
                        headers=auth_headers)
        assert r.status_code == 200
        exp = r.json()["api_key"]["expires_at"]
        assert exp is not None
        assert _iso_to_epoch(exp) > time.time()''',
'''    def test_create_api_key_endpoint_sets_future_expiry(self, client, admin_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "reg-key", "expires_in_days": 30, "scopes": ["admin"]},
                        headers=admin_headers)
        assert r.status_code == 200
        exp = r.json()["api_key"]["expires_at"]
        assert exp is not None
        assert _iso_to_epoch(exp) > time.time()''',
))

# R4
repls.append((
'''    def test_api_key_list_never_returns_raw_key(self, client, auth_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "nd", "expires_in_days": 30},
                          headers=auth_headers).json()["raw_key"]
        body = client.get("/api/v1/auth/api-keys", headers=auth_headers).json()
        blob = json.dumps(body)
        assert raw not in blob
        assert "key" not in body["api_keys"][0]
        # raw_key must NOT appear again on the list endpoint.
        assert "raw_key" not in blob''',
'''    def test_api_key_list_never_returns_raw_key(self, client, admin_headers):
        raw = client.post("/api/v1/auth/api-keys",
                          json={"name": "nd", "expires_in_days": 30, "scopes": ["admin"]},
                          headers=admin_headers).json()["key"]
        body = client.get("/api/v1/auth/api-keys", headers=admin_headers).json()
        blob = json.dumps(body)
        assert raw not in blob
        assert "key" not in body["api_keys"][0]
        assert "hash" not in body["api_keys"][0]
        # raw_key must NOT appear again on the list endpoint.
        assert "raw_key" not in blob''',
))

# R5
repls.append((
'''    def test_api_key_create_returns_raw_key_once(self, client, auth_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "once"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["raw_key"].startswith("jarvis_")
        # but the persisted api_key object omits the plaintext key field
        assert "key" not in r.json()["api_key"]''',
'''    def test_api_key_create_returns_raw_key_once(self, client, admin_headers):
        r = client.post("/api/v1/auth/api-keys",
                        json={"name": "once", "scopes": ["admin"]}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["key"].startswith("jarvis_")
        assert r.json()["key_id"]
        assert r.json()["prefix"].startswith("jarvis_")
        # but the persisted api_key object omits the plaintext key/hash fields
        assert "key" not in r.json()["api_key"]
        assert "hash" not in r.json()["api_key"]''',
))

# R6
repls.append((
'''    def test_api_key_creation_is_audited(self, client, auth_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "audited-key"}, headers=auth_headers)
        logs = get_store("audit_logs").load()
        assert any(l["action"] == "create_api_key" and l.get("detail") == "audited-key"
                   for l in logs)''',
'''    def test_api_key_creation_is_audited(self, client, admin_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "audited-key", "scopes": ["admin"]}, headers=admin_headers)
        logs = get_store("audit_logs").load()
        assert any(l["action"] == "create_api_key" and l.get("detail") == "audited-key"
                   for l in logs)''',
))

# R7
repls.append((
'''    def test_audit_entry_shape(self, client, auth_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "shape"}, headers=auth_headers)
        logs = get_store("audit_logs").load()
        entry = [l for l in logs if l.get("action") == "create_api_key"][-1]
        for field in ("id", "actor_id", "action", "resource_type", "timestamp"):
            assert field in entry
        assert entry["resource_type"] == "auth"''',
'''    def test_audit_entry_shape(self, client, admin_headers):
        client.post("/api/v1/auth/api-keys",
                    json={"name": "shape", "scopes": ["admin"]}, headers=admin_headers)
        logs = get_store("audit_logs").load()
        entry = [l for l in logs if l.get("action") == "create_api_key"][-1]
        for field in ("id", "actor_id", "action", "resource_type", "timestamp"):
            assert field in entry
        assert entry["resource_type"] == "auth"
        # The audit entry must never reference a secret value or field alias.
        assert "key" not in entry
        assert "hash" not in entry''',
))

# R8: append TestApiKeyAtRestSecurity before the OAuth section (ASCII anchor).
anchor = '        assert r.json()["max_users"] == 5\n'
new_class_lines = [
    '        assert r.json()["max_users"] == 5\n',
    '\n',
    '\n',
    '# --------------------------------------------------------------------------- #\n',
    '# Sections 5-10 / 12-20: API-key at-rest security\n',
    '# --------------------------------------------------------------------------- #\n',
    'class TestApiKeyAtRestSecurity:\n',
    '    """Raw jarvis_ API keys must never persist, be logged, or be recoverable."""\n',
    '\n',
    '    def test_create_key_requires_admin(self, client, auth_headers):\n',
    '        # A regular (non-admin) user cannot mint service credentials.\n',
    '        r = client.post("/api/v1/auth/api-keys",\n',
    '                        json={"name": "nope", "scopes": ["admin"]}, headers=auth_headers)\n',
    '        assert r.status_code == 403\n',
    '\n',
    '    def test_create_returns_raw_key_once(self, client, admin_headers):\n',
    '        r = client.post("/api/v1/auth/api-keys",\n',
    '                        json={"name": "once", "scopes": ["admin"]}, headers=admin_headers)\n',
    '        assert r.status_code == 200\n',
    '        body = r.json()\n',
    '        assert body["key"].startswith("jarvis_")\n',
    '        assert body["key_id"]\n',
    '        assert body["prefix"].startswith("jarvis_")\n',
    '        assert body["warning"]\n',
    '\n',
    '    def test_raw_key_not_persisted(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "p", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        for rec in get_store("api_keys").load().values():\n',
    '            blob = json.dumps(rec)\n',
    '            assert raw not in blob\n',
    '            assert "key" not in rec\n',
    '            assert "raw_key" not in rec\n',
    '            assert "secret" not in rec\n',
    '            assert "token" not in rec\n',
    '            assert rec.get("hash", "").startswith("pbkdf2_sha256$")\n',
    '            assert rec.get("prefix", "").startswith("jarvis_")\n',
    '            import hashlib as _hl\n',
    '            assert rec["hash"] != _hl.sha256(raw.encode()).hexdigest()\n',
    '\n',
    '    def test_list_never_returns_raw_key(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "nd", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        body = client.get("/api/v1/auth/api-keys", headers=admin_headers).json()\n',
    '        blob = json.dumps(body)\n',
    '        assert raw not in blob\n',
    '        for rec in body["api_keys"]:\n',
    '            assert "key" not in rec\n',
    '            assert "hash" not in rec\n',
    '\n',
    '    def test_authentication_succeeds(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "k", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        r = client.get("/api/v1/auth/me",\n',
    '                       headers={"Authorization": f"Bearer {raw}"})\n',
    '        assert r.status_code == 200\n',
    '        assert r.json()["email"].startswith("admin-")\n',
    '\n',
    '    def test_wrong_key_fails(self, client, admin_headers):\n',
    '        client.post("/api/v1/auth/api-keys",\n',
    '                    json={"name": "k", "scopes": ["admin"]}, headers=admin_headers)\n',
    '        r = client.get("/api/v1/auth/me",\n',
    '                       headers={"Authorization": "Bearer jarvis_notarealkey"})\n',
    '        assert r.status_code == 401\n',
    '\n',
    '    def test_expired_key_fails(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "exp", "scopes": ["admin"], "expires_in_days": 1},\n',
    '                          headers=admin_headers).json()["key"]\n',
    '        keys = get_store("api_keys").load()\n',
    '        kid = next(k for k, v in keys.items() if v.get("prefix") == api_key_prefix(raw))\n',
    '        keys[kid]["expires_at"] = (datetime.now(timezone.utc)\n',
    '                                   - timedelta(days=1)).isoformat().replace("+00:00", "Z")\n',
    '        get_store("api_keys").save()\n',
    '        r = client.get("/api/v1/auth/me",\n',
    '                       headers={"Authorization": f"Bearer {raw}"})\n',
    '        assert r.status_code == 401\n',
    '\n',
    '    def test_revoked_key_fails(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "rev", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        keys = get_store("api_keys").load()\n',
    '        kid = next(k for k, v in keys.items() if v.get("prefix") == api_key_prefix(raw))\n',
    '        client.delete(f"/api/v1/auth/api-keys/{kid}", headers=admin_headers)\n',
    '        r = client.get("/api/v1/auth/me",\n',
    '                       headers={"Authorization": f"Bearer {raw}"})\n',
    '        assert r.status_code == 401\n',
    '\n',
    '    def test_scope_denial(self, client, admin_headers):\n',
    '        # A read-scoped key cannot perform admin actions (e.g. create a key).\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "read", "scopes": ["read"]}, headers=admin_headers).json()["key"]\n',
    '        r = client.post("/api/v1/auth/api-keys",\n',
    '                        json={"name": "child", "scopes": ["admin"]},\n',
    '                        headers={"Authorization": f"Bearer {raw}"})\n',
    '        assert r.status_code == 403\n',
    '\n',
    '    def test_rotation(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "orig", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        keys = get_store("api_keys").load()\n',
    '        kid = next(k for k, v in keys.items() if v.get("prefix") == api_key_prefix(raw))\n',
    '        rot = client.post(f"/api/v1/auth/api-keys/{kid}/rotate",\n',
    '                          headers=admin_headers).json()\n',
    '        new_raw = rot["key"]\n',
    '        assert new_raw.startswith("jarvis_")\n',
    '        assert rot["key_id"] != kid\n',
    '        # old key revoked -> cannot authenticate\n',
    '        keys = get_store("api_keys").load()\n',
    '        assert keys[kid]["status"] == "revoked"\n',
    '        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})\n',
    '        assert r.status_code == 401\n',
    '        # new key works\n',
    '        r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_raw}"})\n',
    '        assert r2.status_code == 200\n',
    '\n',
    '    def test_migration_from_plaintext(self, client, admin_headers):\n',
    '        # Simulate a legacy pre-hashing record (plaintext key field, no hash).\n',
    '        uid, _ = _make_admin_user()\n',
    '        raw = generate_api_key()[0]\n',
    '        keys = get_store("api_keys").load()\n',
    '        kid = str(uuid.uuid4())\n',
    '        keys[kid] = {\n',
    '            "id": kid, "key_id": kid, "user_id": uid, "owner": uid,\n',
    '            "name": "legacy", "scopes": ["admin"],\n',
    '            "key": raw, "created_at": now_iso(), "status": "active",\n',
    '        }\n',
    '        get_store("api_keys").save()\n',
    '        # Authenticating with the raw key migrates it in place.\n',
    '        r = client.get("/api/v1/auth/me",\n',
    '                       headers={"Authorization": f"Bearer {raw}"})\n',
    '        assert r.status_code == 200\n',
    '        rec = get_store("api_keys").load()[kid]\n',
    '        assert "key" not in rec\n',
    '        assert rec.get("hash", "").startswith("pbkdf2_sha256$")\n',
    '        assert rec.get("prefix") == api_key_prefix(raw)\n',
    '        assert raw not in json.dumps(get_store("audit_logs").load())\n',
    '\n',
    '    def test_no_secret_in_audit_logs(self, client, admin_headers):\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "s", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        for entry in get_store("audit_logs").load():\n',
    '            assert raw not in json.dumps(entry)\n',
    '\n',
    '    def test_security_regression_raw_key_absent(self, client, admin_headers):\n',
    '        # Mandatory regression (section 20): raw key absent from persisted record,\n',
    '        # logs, and is only ever correlated by key_id/prefix.\n',
    '        raw = client.post("/api/v1/auth/api-keys",\n',
    '                          json={"name": "reg", "scopes": ["admin"]}, headers=admin_headers).json()["key"]\n',
    '        rec = next(r for r in get_store("api_keys").load().values() if r.get("name") == "reg")\n',
    '        assert raw not in json.dumps(rec)\n',
    '        assert rec["prefix"] == api_key_prefix(raw)\n',
    '        assert raw not in json.dumps(get_store("audit_logs").load())\n',
]
new_class = "".join(new_class_lines)
repls.append((anchor, new_class))

# apply
for i, (old, new) in enumerate(repls, 1):
    n = c.count(old)
    if n != 1:
        print(f"R{i}: MATCH COUNT={n} (expected 1)")
        print("OLD repr:", repr(old[:120]))
        sys.exit(1)
    c = c.replace(old, new)
    print(f"R{i}: applied")

fn.write_text(c, encoding="utf-8")
print("test file patched OK")
