"""Regression checks for the isolated backend test database."""

import os
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url


def test_backend_uses_the_configured_test_database():
    from jarvis_backend.db import database_url, get_engine

    database = make_url(database_url()).database
    assert database is not None

    actual_path = Path(database).resolve()
    configured_path = os.environ.get("JARVIS_TEST_DATABASE_PATH")
    if configured_path:
        assert actual_path == Path(configured_path).expanduser().resolve()
    else:
        assert actual_path.is_relative_to(Path(tempfile.gettempdir()).resolve())

    assert get_engine().url.database == database
