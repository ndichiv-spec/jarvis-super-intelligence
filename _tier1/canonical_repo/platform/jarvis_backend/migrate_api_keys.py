"""One-shot migration of the raw jarvis_backend.core API-key storage.

Run with:  python -m jarvis_backend.migrate_api_keys   (or: python -m jarvis_backend.migrate_api_keys --dry-run)
"""
import argparse
import os
import sys
from pathlib import Path

# Ensure a secret key exists so core imports cleanly in CI/dev.
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_SECRET_KEY", "migration-secret-key-0123456789abcdef")

# Make the package importable when run as a module from the repo root.
ROOT = Path(__file__).resolve().parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from jarvis_backend.core import (  # noqa: E402
    API_KEY_PREFIX, api_key_prefix, hash_api_key, is_api_key_expired, now_iso,
    get_store,
)


def _audit(owner, prefix, detail="migrated"):
    logs = get_store("audit_logs").load()
    logs.append({
        "id": __import__("uuid").uuid4().__str__(),
        "actor_id": owner,
        "action": "api_key_migrated",
        "resource_type": "auth",
        "timestamp": now_iso(),
        "detail": detail,
    })
    get_store("audit_logs").save()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy plaintext API keys to hashed storage")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write changes")
    args = parser.parse_args()

    keys = get_store("api_keys").load()
    inspected = len(keys)
    migrated = 0
    already_hashed = 0
    skipped = 0
    errors = 0

    for key_id, record in list(keys.items()):
        try:
            has_plaintext = "key" in record and record.get("key")
            has_hash = bool(record.get("hash"))
            if has_plaintext:
                # Migrate: hash the plaintext, set prefix/status, drop the secret.
                raw = record["key"]
                record["hash"] = hash_api_key(raw)
                record["prefix"] = api_key_prefix(raw) if raw.startswith(API_KEY_PREFIX) else record.get("prefix", "")
                record["status"] = "revoked" if record.get("status") == "revoked" else "active"
                record.setdefault("owner", record.get("user_id"))
                record.pop("key", None)
                if not args.dry_run:
                    get_store("api_keys").save()
                    _audit(record.get("owner"), record.get("prefix", key_id))
                migrated += 1
            elif has_hash:
                already_hashed += 1
            else:
                # No plaintext and no hash -> irrecoverable; cannot migrate.
                skipped += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"ERROR  key={key_id}  {type(e).__name__}: {e}", file=sys.stderr)

    if not args.dry_run:
        get_store("api_keys").save()

    print("API-key migration complete")
    print(f"  records inspected   : {inspected}")
    print(f"  records migrated    : {migrated}")
    print(f"  records already hashed: {already_hashed}")
    print(f"  records skipped     : {skipped}")
    print(f"  errors              : {errors}")
    print("NOTE: raw secrets are never printed.")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
