"""
JARVIS Test Configuration
==========================
Pytest fixtures and configuration for test suite.
"""

import os
import sys
from pathlib import Path
import asyncio

import pytest


# Test configuration
TEST_DB_URL = "sqlite+aiosqlite:///./test_jarvis.db"
os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
for _var in (
    "NVIDIA_API_KEY", "NVIDIA_API_TOKEN", "NIM_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "GCLOUD_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HF_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN", "JARVIS_HF_TOKEN", "HF_API_TOKEN",
    "GROQ_API_KEY", "DEEPSEEK_API_KEY", "TOGETHER_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY",
    "JARVIS_BRAIN_API_KEY", "JARVIS_BRAIN_ENDPOINT",
    "SILVERWING_ENDPOINT",
):
    os.environ.pop(_var, None)


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    from unittest.mock import Mock

    config = Mock()
    config.APP_NAME = "JARVIS Test"
    config.APP_VERSION = "0.1.0"
    config.DATABASE_URL = TEST_DB_URL
    config.API_PREFIX = "/api/v1"
    config.DEBUG = True
    config.LOG_LEVEL = "DEBUG"
    config.RATE_LIMIT_REQUESTS = 100
    config.RATE_LIMIT_PERIOD = 60
    config.CORS_ORIGINS = ["*"]
    config.CORS_ALLOW_CREDENTIALS = True
    config.CORS_ALLOW_METHODS = ["*"]
    config.CORS_ALLOW_HEADERS = ["*"]
    return config


@pytest.fixture
async def test_client():
    """Create test HTTP client."""
    from httpx import AsyncClient, ASGITransport
    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_ai_response():
    """Mock AI response data."""
    return {
        "response": "Test response",
        "model": "test-model",
        "confidence": 0.95,
        "tokens_used": 10,
    }


@pytest.fixture
def mock_search_results():
    """Mock search results."""
    return [
        {
            "title": "Test Result 1",
            "url": "https://example.com/1",
            "snippet": "Test snippet 1",
            "score": 0.9,
        },
        {
            "title": "Test Result 2",
            "url": "https://example.com/2",
            "snippet": "Test snippet 2",
            "score": 0.8,
        },
    ]


def _seed_test_user() -> None:
    """Ensure a canonical test user exists for bearer-token auth.

    The auth middleware resolves the caller from the JWT subject and refuses to
    authenticate if the user row is absent. Earlier runs of the suite could
    delete the backing SQLite file and leave the user table empty, so no
    request succeeded until the test user was restored.
    """
    from jarvis_backend.core import get_store, hash_password, now_iso

    users = get_store("users").load()
    user_id = "testuser"
    if not any((u.get("id") == user_id or u.get("username") == "testuser") for u in users.values()):
        users[user_id] = {
            "id": user_id,
            "email": "testuser@jarvis.local",
            "username": "testuser",
            "full_name": "Test User",
            "password_hash": hash_password("test-password"),
            "status": "active",
            "roles": ["user"],
            "email_verified": True,
            "created_at": now_iso(),
        }
        get_store("users").save()


@pytest.fixture
def auth_token():
    """Create test auth token using the real signing implementation."""
    _seed_test_user()
    from jarvis_backend.core import create_token

    return create_token({"sub": "testuser", "user_id": "test-id"})


@pytest.fixture
def auth_headers(auth_token):
    """Auth headers for requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(autouse=True)
def cleanup_test_db():
    """Reset the project test database before and after each test.

    The suite uses a fixed SQLite file for deterministic auth/session tests, so
    stale rows from earlier runs or earlier tests must be purged before the next
    test begins. This prevents cross-user leakage and duplicate-registration
    failures caused by the previous test run leaving data behind.
    """
    test_db_paths = (
        Path("./test_jarvis.db"),
        _TEST_DB_PATH,
    )
    for db_path in test_db_paths:
        try:
            if db_path.exists():
                db_path.unlink()
        except PermissionError:
            pass

    try:
        from jarvis_backend.core import data
        for store in list(data.values()):
            if hasattr(store, "_data"):
                store._data = None
    except Exception:  # pragma: no cover - best effort isolation
        pass

    yield

    try:
        from jarvis_backend.db import reset_database
        reset_database()
    except Exception:  # pragma: no cover - cleanup is best effort only
        pass

    for db_path in test_db_paths:
        try:
            if db_path.exists():
                db_path.unlink()
        except PermissionError:
            pass


@pytest.fixture
def sample_knowledge():
    """Sample knowledge entry."""
    return {
        "key": "test_key",
        "value": "test_value",
        "category": "test",
        "tags": ["test", "sample"],
    }


@pytest.fixture
def sample_agent():
    """Sample agent config."""
    return {
        "name": "test_agent",
        "type": "chat",
        "config": {"model": "default"},
    }

# Session bootstrap.
#
#   1. Point the engine at an isolated SYNC SQLite file before anything creates
#      the cached global engine, and create it immediately so later imports
#      cannot re-resolve it against PostgreSQL.
#   2. Make the project and workspace importable.
#
# Deliberately does NOT load ``.env``: injecting live provider keys would make
# the committed chat tests observe reachable providers instead of the
# PROVIDER_UNAVAILABLE outcome they assert. Tests therefore run with no
# provider credentials - the honest default for a test environment.
_ROOT = Path(__file__).resolve().parents[1]
for _path in (_ROOT, _ROOT.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TEST_DB_PATH = Path(os.environ.get(
    "JARVIS_TEST_DB_PATH",
    str(_ROOT / "tests" / "_test_jarvis.db"),
)).resolve()


def _remove_test_db() -> None:
    """Best-effort removal of the per-run test database.

    The old code called ``unlink(missing_ok=True)`` unconditionally, so a stale
    SQLite handle from an earlier (possibly killed) run made conftest fail to
    import and took down every subsequent test file with it. Removal is an
    optimization, not a correctness requirement: the schema is created by
    ``create_all`` below, so a leftover file is harmless. Retry briefly, then
    continue with a warning rather than aborting the whole suite.
    """
    import time

    for attempt in range(5):
        try:
            _TEST_DB_PATH.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 4:
                print(
                    f"[conftest] warning: {_TEST_DB_PATH.name} is locked; "
                    "continuing with the existing file (schema is re-created)"
                )
                return
            time.sleep(0.4)
        except OSError:
            return


_remove_test_db()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["JARVIS_TEST_MODE"] = "1"

# Force engine creation now, while DATABASE_URL still points at the test DB.
from jarvis_backend.db import get_engine as _get_engine

_get_engine()

# Deterministic, provider-less test environment.
#
# The committed chat tests assert the *provider-unavailable* outcome
# (PROVIDER_UNAVAILABLE, no fabricated reply). Live provider keys are routinely
# present in the ambient environment, which would flip those assertions to a
# real completion. Scrubbing provider credentials keeps the test environment
# reproducible and matches what the tests were written against. Live-provider
# behaviour is covered by the integration/acceptance suites instead.
_PROVIDER_ENV_VARS = (
    "NVIDIA_API_KEY", "NVIDIA_API_TOKEN", "NIM_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "GCLOUD_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HF_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN", "JARVIS_HF_TOKEN", "HF_API_TOKEN",
    "GROQ_API_KEY", "DEEPSEEK_API_KEY", "TOGETHER_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY",
)
for _var in _PROVIDER_ENV_VARS:
    os.environ.pop(_var, None)


def _seed_test_user() -> None:
    """Ensure a user exists whose id matches the token ``sub`` claim."""
    try:
        from jarvis_backend.core import get_store

        users = get_store("users")
        store = users.load()
        if "testuser" not in store:
            store["testuser"] = {
                "id": "testuser",
                "email": "testuser@jarvis.local",
                "display_name": "Test User",
                "is_active": True,
                "roles": ["user"],
            }
            users.save(store)
    except Exception:  # noqa: BLE001
        pass


_seed_test_user()


@pytest.fixture
def client():
    """Synchronous HTTP client over the ASGI app.

    ``test_phase1_chat`` drives the API with blocking ``post``/``stream``
    calls, so it needs a sync client rather than the async ``test_client``.
    """
    from starlette.testclient import TestClient

    from jarvis_backend.main import app
    with TestClient(app) as http_client:
        yield http_client
