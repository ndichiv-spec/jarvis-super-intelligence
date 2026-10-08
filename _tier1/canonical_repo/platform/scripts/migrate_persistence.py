#!/usr/bin/env python3
"""Migration script for the JARVIS SQL persistence layer (Phase 2.1).

Creates the ``jarvis_kv`` collection table — the single "001" migration that
backs every logical store (``users``, ``sessions``, ``refresh_tokens``,
``chat_sessions``, ``audit_logs``, ``memory``, ``knowledge``, ...) — and
optionally seeds the default roles/permissions.  Idempotent: safe to run
repeatedly against the same database.

Backend selection
-----------------
* Default:  SQLite file at ``jarvis_data/jarvis.db``
* Override: ``DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db``
            ``JARVIS_DB_PATH=/path/to/custom.db``
            ``JARVIS_TEST_MODE=1`` (in-memory SQLite)

Usage
-----
    python scripts/migrate_persistence.py            # create/ensure schema
    python scripts/migrate_persistence.py --seed     # create + seed defaults
    python scripts/migrate_persistence.py --check    # verify schema (exit 1 if missing)
    python scripts/migrate_persistence.py --reset    # truncate jarvis_kv (dev/test)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the project importable when run directly as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_backend import db  # noqa: E402
from jarvis_backend.core import start_backend  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

MIGRATION_VERSION = "001_initial_kv_store"


def create_schema() -> None:
    url = db.create_db_and_tables()
    print(f"[migrate] ensured schema v{MIGRATION_VERSION}")
    print(f"[migrate] backend  : {make_url(url).render_as_string(hide_password=True)}")


def seed_defaults() -> None:
    db.create_db_and_tables()
    start_backend()  # seeds roles/permissions if empty
    print("[migrate] seeded default roles & permissions")


def check_schema() -> int:
    from sqlalchemy import inspect

    db.ensure_schema()
    tables = inspect(db.get_engine()).get_table_names()
    if "jarvis_kv" in tables:
        print(f"[check] OK  — jarvis_kv present "
              f"({len(tables)} table(s): {', '.join(sorted(tables))})")
        return 0
    print(f"[check] FAIL— jarvis_kv missing (tables: {tables})")
    return 1


def reset_data() -> None:
    db.ensure_schema()
    db.reset_database()
    print("[migrate] truncated jarvis_kv (all collections cleared)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="JARVIS persistence migration (Phase 2.1)")
    parser.add_argument("--seed", action="store_true",
                        help="also seed default roles/permissions (idempotent)")
    parser.add_argument("--check", action="store_true",
                        help="verify the schema exists; exit non-zero if missing")
    parser.add_argument("--reset", action="store_true",
                        help="truncate jarvis_kv (dev/test only)")
    args = parser.parse_args()

    if args.check:
        sys.exit(check_schema())

    create_schema()
    if args.seed:
        seed_defaults()
    if args.reset:
        reset_data()


if __name__ == "__main__":
    main()
