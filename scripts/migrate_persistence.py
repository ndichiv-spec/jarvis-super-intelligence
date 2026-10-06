#!/usr/bin/env python3
"""Explicit, ordered migrations for the JARVIS SQL persistence layer."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_backend.secret_config import load_file_secrets  # noqa: E402

load_file_secrets()

from jarvis_backend import db  # noqa: E402
from jarvis_backend.core import start_backend  # noqa: E402
from jarvis_backend.schema_migrations import MIGRATIONS, MIGRATION_BY_REVISION  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

MIGRATION_VERSION = db.LATEST_SCHEMA_REVISION


def upgrade_schema() -> None:
    engine = db.get_engine()
    tables = set(inspect(engine).get_table_names())
    applied = set(db.applied_migrations()) if "jarvis_schema_migrations" in tables else set()
    unknown = applied - set(MIGRATION_BY_REVISION)
    if unknown:
        raise RuntimeError(f"Database has unknown migration revisions: {sorted(unknown)}")

    # Adopt schemas created before the revision ledger was introduced without
    # rebuilding or rewriting their existing data.
    if "jarvis_kv" in tables and "001_initial_kv_store" not in applied:
        db.schema_migrations.create(engine, checkfirst=True)
        db.record_migration("001_initial_kv_store")
        applied.add("001_initial_kv_store")

    for migration in MIGRATIONS:
        if migration.revision in applied:
            continue
        migration.upgrade(engine)
        db.record_migration(migration.revision)
        applied.add(migration.revision)
        print(f"[migrate] applied {migration.revision}")
    print(f"[migrate] backend: {make_url(db.database_url()).render_as_string(hide_password=True)}")


def create_schema() -> None:
    """Backward-compatible entry point used by migration tests."""
    upgrade_schema()


def seed_defaults() -> None:
    upgrade_schema()
    start_backend()
    print("[migrate] seeded default roles & permissions")


def check_schema() -> int:
    engine = db.get_engine()
    tables = set(inspect(engine).get_table_names())
    revisions = db.applied_migrations() if "jarvis_schema_migrations" in tables else []
    expected_tables = set(db.metadata.tables)
    expected_revisions = [migration.revision for migration in MIGRATIONS]
    if expected_tables.issubset(tables) and revisions == expected_revisions:
        print(f"[check] OK — {len(tables)} table(s), latest revision {MIGRATION_VERSION}")
        return 0
    print(
        "[check] FAIL — database schema is not current "
        f"(missing tables: {sorted(expected_tables - tables)}, revisions: {revisions})"
    )
    return 1


def migration_status() -> None:
    tables = set(inspect(db.get_engine()).get_table_names())
    applied = db.applied_migrations() if "jarvis_schema_migrations" in tables else []
    for migration in MIGRATIONS:
        state = "APPLIED" if migration.revision in applied else "PENDING"
        print(f"{state:7} {migration.revision}")


def downgrade(revision: str) -> None:
    applied = db.applied_migrations()
    if not applied or applied[-1] != revision:
        raise RuntimeError("Only the most recently applied revision can be downgraded.")
    migration = MIGRATION_BY_REVISION.get(revision)
    if migration is None or migration.downgrade is None:
        raise RuntimeError(f"Migration {revision} has no supported safe downgrade.")
    migration.downgrade(db.get_engine())
    db.remove_migration(revision)
    print(f"[migrate] downgraded {revision}")


def reset_data() -> None:
    if os.environ.get("JARVIS_ENV", "").lower() == "production":
        raise RuntimeError("--reset is forbidden in production.")
    db.ensure_schema()
    db.reset_database()
    print("[migrate] truncated jarvis_kv (all collections cleared)")


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS revisioned database migration tool")
    parser.add_argument("--upgrade", action="store_true", help="apply all pending revisions (default)")
    parser.add_argument("--seed", action="store_true", help="also seed default roles and permissions")
    parser.add_argument("--check", action="store_true", help="verify all registered revisions and tables")
    parser.add_argument("--status", action="store_true", help="show applied and pending revisions")
    parser.add_argument("--downgrade", metavar="REVISION", help="apply a supported safe downgrade")
    parser.add_argument("--reset", action="store_true", help="truncate data (development only)")
    args = parser.parse_args()

    if args.status:
        migration_status()
        return
    if args.check:
        raise SystemExit(check_schema())
    if args.downgrade:
        downgrade(args.downgrade)
        return
    upgrade_schema()
    if args.seed:
        seed_defaults()
    if args.reset:
        reset_data()


if __name__ == "__main__":
    main()
