"""Apply additive durable command execution schema changes.

Usage from the platform directory:
    python scripts/migrate_runtime_execution.py

The migration uses SQLAlchemy ``create_all`` and never drops or rewrites
existing command, user, or application records.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis_backend.db import create_db_and_tables  # noqa: E402

if __name__ == "__main__":
    create_db_and_tables()
    print("Runtime execution schema is present.")
