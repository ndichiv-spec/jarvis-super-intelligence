"""JARVIS dev/test launcher — boots the real FastAPI app on 127.0.0.1:8000.

Run from anywhere:
    python3 F:/AI/start_jarvis.py

Environment (defaults safe for local verification, never prod):
    JARVIS_TEST_MODE=1     -> in-memory-friendly schema, test admin password branch
    JARVIS_ENV=dev         -> dev identity defaults (admin@jarvis.local)

It seeds the canonical admin (idempotent via start_backend()), mints a real
admin JWT signed with the process signing key, writes it to F:/AI/_token.txt
(NEVER printed), then starts uvicorn. The bearer token in that file is what
F:/AI/verify_system_contract.py uses to exercise the auth-gated /system/* routes.

NOTE: core.py is READ-ONLY for this task. Uptime + real memory in /system/status
are owned by system.py module-level helpers, NOT by any startup hook here.
"""

from __future__ import annotations

import os
import stat
import sys

# --- environment (set BEFORE importing jarvis_backend) --------------------- #
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_ENV", "dev")

REPO_ROOT = r"F:\AI\Jarvis-super-intelligence-"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))  # F:/AI

# Make `jarvis_backend` importable regardless of cwd, and chdir to the repo
# root so relative data paths (jarvis_data/) land inside the repo. The chdir
# is guarded so that *importing* this module (e.g. from tests or CI) does not
# raise when the git-ignored operational checkout (REPO_ROOT) is absent; the
# operational boot path is unchanged when that tree is present.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if os.path.isdir(REPO_ROOT):
    os.chdir(REPO_ROOT)


def _write_token_file(path: str, token: str) -> None:
    """Persist an admin bearer token to *path* with mode 0600 (owner-only).

    The token is written via ``os.open`` with mode ``0o600`` and re-chmoded so
    it is not world-readable regardless of umask. The token *value* is never
    logged by this helper or by its callers. ``_token.txt`` is covered by
    ``.gitignore`` (``/_*.txt``) and must never be committed.
    """
    # O_WRONLY|O_CREAT|O_TRUNC, mode 0600.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    # Belt-and-suspenders: enforce 0600 even if the open mode was ignored
    # (permissive umask or Windows, which lacks POSIX mode bits). Best-effort.
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass


def _seed_and_mint_token() -> str:
    """Set up schema + admin (idempotent) and return a real admin bearer token."""
    from jarvis_backend.core import (  # noqa: PLC0415
        start_backend, get_store, create_token, is_admin, hash_password, now_iso,
    )

    # start_backend() == create_db_and_tables() + role/admin seed (idempotent).
    # Calling it here means the admin exists *before* uvicorn's startup event,
    # so the live curl flow has a user to authenticate against. The startup
    # event calls it again — harmless (skips when admin already present).
    try:
        start_backend()
    except Exception as exc:  # noqa: BLE001 — never block launch on seeding
        print(f"[start_jarvis] start_backend() warning: {exc}")

    admin_id = "00000000-0000-0000-0000-000000000001"
    users = get_store("users").load()
    record = users.get(admin_id)
    if not record:
        # Fallback: seed directly if start_backend's guard didn't run.
        users[admin_id] = {
            "id": admin_id,
            "email": "admin@jarvis.local",
            "username": "owner",
            "password_hash": hash_password("test-password-for-testing"),
            "is_admin": True,
            "roles": ["admin"],
            "status": "active",
            "email_verified": True,
            "created_at": now_iso(),
        }
        get_store("users").save()

    if not is_admin(record if record else users.get(admin_id)):
        raise SystemExit("[start_jarvis] FATAL: seeded admin is not admin-capable; abort.")

    token = create_token({"sub": admin_id})
    token_path = os.path.join(PROJECT_DIR, "_token.txt")
    _write_token_file(token_path, token)
    print(f"[start_jarvis] admin JWT written to {token_path} (len={len(token)}, NOT echoed).")
    print(f"[start_jarvis] admin seeded uid={admin_id} email=admin@jarvis.local is_admin=True")
    return token


def main() -> None:
    # Importing jarvis_backend.main builds the app eagerly (setup_routers,
    # integrations: Identity / MCP / A2A). This is the SINGLE FastAPI app.
    from jarvis_backend.main import app  # noqa: PLC0415

    _seed_and_mint_token()

    import uvicorn  # noqa: PLC0415

    print("[start_jarvis] starting uvicorn 127.0.0.1:8000 (log_level=warning)...")
    print("[start_jarvis] endpoints: /api/v1/system/{status,identity,capabilities,dashboard,diagnose,processes,files,provider-settings,models,services}")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
