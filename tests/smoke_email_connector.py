"""Isolated live smoke test of the email-connector HTTP API (the contract the
Connections page depends on). Runs IN-PROCESS against the real FastAPI app,
using:
  * an in-memory SQLite DB (JARVIS_TEST_MODE=1)  -> never touches jarvis.db
  * temp connector config/audit dirs             -> never touches jarvis_data/
  * loopback FakeIMAPServer/FakeSMTPServer       -> real imaps/smtplib code path

Validates POST /email/test (Test button), the save/list/get/patch/delete
lifecycle, an actual email action (audit source), the audit activity feed,
and the unauth guard.
"""
from __future__ import annotations
import os, sys, tempfile, uuid

# --- isolation FIRST: in-memory DB, set before any jarvis import ---
os.environ["JARVIS_TEST_MODE"] = "1"
os.environ.pop("JARVIS_SECRET_KEY", None)  # ephemeral key is fine in-process

ROOT = r"F:\AI"
PKG = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, ROOT)
sys.path.insert(0, PKG)

import shutil  # noqa: E402
from pathlib import Path  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jarvis_backend.main import app  # noqa: E402
from jarvis_backend.core import hash_password, now_iso, create_token, get_store  # noqa: E402

# redirect connector config + audit files to a temp dir (mirrors tests iso_dirs)
import jarvis_backend.connectors.registry as registry  # noqa: E402
_tmp = Path(tempfile.mkdtemp(prefix="jarvis_smoke_"))
registry.CONNECTORS_DIR = _tmp / "connectors"
registry.AUDIT_DIR = _tmp / "audit"
registry.AUDIT_FILE = _tmp / "audit" / "connectors.jsonl"
registry.CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
registry.AUDIT_DIR.mkdir(parents=True, exist_ok=True)

from tests.fakes.mail_servers import FakeIMAPServer, FakeSMTPServer  # noqa: E402


def main():
    users = get_store("users").load()
    uid = str(uuid.uuid4())
    users[uid] = {
        "id": uid, "email": f"admin-{uid[:8]}@jarvis.local", "username": f"admin_{uid[:6]}",
        "password_hash": hash_password("Sm0ke!Test1"), "full_name": "Smoke Admin",
        "status": "active", "tenant_id": None, "roles": ["admin"],
        "last_login_at": None, "created_at": now_iso(),
    }
    get_store("users").save()
    token = create_token({"sub": uid, "sid": None})
    H = {"Authorization": f"Bearer {token}"}

    imap = FakeIMAPServer().start()
    smtp = FakeSMTPServer().start()

    cfg = {
        "provider": "Fake",
        "imap_host": "127.0.0.1", "imap_port": imap.port, "imap_ssl": False,
        "imap_user": "dev@fake.dev", "password": "app-password-123",
        "smtp_host": "127.0.0.1", "smtp_port": smtp.port, "smtp_starttls": False,
        "send_from": "dev@fake.dev",
        "capabilities": ["read", "summarize", "draft", "send"], "enabled": True,
    }
    test_body = {k: cfg[k] for k in ("provider", "imap_host", "imap_port", "imap_ssl",
                                     "imap_user", "password", "smtp_host", "smtp_port",
                                     "smtp_starttls", "send_from")}

    client = TestClient(app)
    results = []

    def check(name, fn):
        try:
            fn(); results.append((name, "PASS", ""))
        except AssertionError as e:
            results.append((name, "FAIL", str(e) or "assertion"))
        except Exception as e:  # noqa
            results.append((name, "ERR ", f"{type(e).__name__}: {e}"))

    def t_test():
        r = client.post("/api/v1/connectors/email/test", json=test_body, headers=H)
        assert r.status_code == 200, f"status {r.status_code}: {r.text}"
        j = r.json()
        assert j.get("ok") is True, f"test ok={j.get('ok')}"
        assert j.get("imap", {}).get("ok") is True, f"imap {j.get('imap')}"
        assert j.get("smtp", {}).get("ok") is True, f"smtp {j.get('smtp')}"
        assert j.get("at"), "missing timestamp"
        print("  POST /email/test -> ok, imap.ok, smtp.ok, at present")

    def t_create():
        r = client.post("/api/v1/connectors/email", json=cfg, headers=H)
        assert r.status_code == 200, f"status {r.status_code}: {r.text}"
        c = r.json()["config"]
        assert c["password"] == "\u2022" * 6, f"password not masked: {c['password']!r}"
        assert c.get("password_set") is True
        print("  POST /email (Save) -> password masked, password_set=True")

    def t_list():
        r = client.get("/api/v1/connectors", headers=H)
        assert r.status_code == 200
        j = r.json()
        assert j["count"] == 1, f"count={j['count']}"
        item = j["connectors"][0]
        pub = item["config"]
        assert pub["password"] == "\u2022" * 6
        assert pub.get("password_set") is True
        assert item.get("configured") is True      # listing exposes `configured`
        assert "enabled" in pub and "capabilities" in pub
        print("  GET /connectors -> count=1, configured=True, password masked")

    def t_get():
        r = client.get("/api/v1/connectors/email", headers=H)
        assert r.status_code == 200, f"status {r.status_code}: {r.text}"
        body = r.json()
        c = body["config"]
        assert body.get("kind") == "email"
        assert c.get("enabled") is True
        assert c.get("password_set") is True       # secret never echoed
        print("  GET /email -> kind=email, enabled=True, password_set=True (no plaintext)")

    def t_run_action():
        # Action execution is the audit source (dispatch policy path).
        r = client.post("/api/v1/connectors/email/actions",
                        json={"action": "email.folders", "params": {}}, headers=H)
        assert r.status_code == 200, f"status {r.status_code}: {r.text}"
        j = r.json()
        assert j.get("ok") is True, f"action ok={j.get('ok')}: {j}"
        names = [f.get("name") for f in j.get("folders", [])]
        assert "INBOX" in names, f"INBOX missing from {names}"
        print("  POST /email/actions (email.folders) -> ok=True, folders include INBOX")

    def t_activity():
        r = client.get("/api/v1/connectors/activity", headers=H)
        assert r.status_code == 200
        j = r.json()
        entries = j["entries"]
        assert len(entries) >= 1, f"no audit entries; got {j}"
        for e in entries:                       # shape guard
            for key in ("ts", "actor", "kind", "action", "ok"):
                assert key in e, f"audit entry missing {key}: {e}"
        actions = [x.get("action") for x in entries]
        assert "email.folders" in actions, f"email.folders not audited; actions={actions}"
        print("  GET /activity ->", len(entries), "entries; actions:", actions)

    def t_patch_keep_secret():
        r = client.patch("/api/v1/connectors/email",
                         json={"password": "\u2022" * 6, "enabled": False, "capabilities": ["read"]},
                         headers=H)
        assert r.status_code == 200, f"status {r.status_code}: {r.text}"
        after = client.get("/api/v1/connectors/email", headers=H).json()["config"]
        assert after["enabled"] is False
        assert after["password_set"] is True       # masked patch keeps the secret
        assert after["capabilities"] == ["read"]
        print("  PATCH /email (masked pw + disable) -> secret kept, enabled=False, caps=['read']")

    def t_action_unauth():
        r = client.post("/api/v1/agents/coder/act",
                        json={"action": "email", "params": {"email_action": "email.folders"}})
        assert r.status_code == 401, f"expected 401 unauth, got {r.status_code}"
        print("  POST /agents/coder/act (no token) -> 401 guarded")

    def t_delete():
        r = client.delete("/api/v1/connectors/email", headers=H)
        assert r.status_code == 200, f"status {r.status_code}: {r.text}"
        assert client.get("/api/v1/connectors", headers=H).json()["count"] == 0
        print("  DELETE /email -> removed, count=0")

    for name, fn in [
        ("POST /email/test (Test button)", t_test),
        ("POST /email (Save/create)", t_create),
        ("GET /connectors (load/listing)", t_list),
        ("GET /email (single config)", t_get),
        ("POST /email/actions (email.folders)", t_run_action),
        ("GET /connectors/activity (audit)", t_activity),
        ("PATCH /email (keep-secret + disable)", t_patch_keep_secret),
        ("POST /agents/coder/act (unauth guard)", t_action_unauth),
        ("DELETE /email (remove)", t_delete),
    ]:
        check(name, fn)

    imap.stop(); smtp.stop()

    print("\n=== SMOKE RESULTS ===")
    for name, status, msg in results:
        print(f"  [{status}] {name}" + (f" -- {msg}" if msg else ""))
    ok = all(s == "PASS" for _, s, _ in results)
    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)
    sys.exit(code)
