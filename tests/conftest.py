"""Shared fixtures for the Silverwing model suite (F:\\AI root).

Hooks the workspace root onto ``sys.path`` so ``silverwing_runtime`` and
``backend`` packages are importable from tests regardless of the platform repo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_REPO = WORKSPACE_ROOT / "Jarvis-super-intelligence-"

# Several roots in this workspace carry divergent copies of the top-level
# ``providers`` and ``backend`` packages (the workspace root, the platform
# checkout, ``_tier1/canonical_repo``).  Insert the platform repo first and
# the workspace root last so the workspace copies win, then pin them in
# ``sys.modules`` before any test can prepend another root (some tests insert
# ``_tier1/canonical_repo/platform`` at import time, which would otherwise
# shadow ``providers``/``backend`` depending on collection order).
for _root in (PLATFORM_REPO, WORKSPACE_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import backend  # noqa: E402,F401
import providers  # noqa: E402,F401

# Default Silverwing runtime env for tests (the runtime serves real weights on
# port 8010 with TorchBackend).  Individual tests may override.
os.environ.setdefault("SILVERWING_ENDPOINT", "http://127.0.0.1:8010")
os.environ.setdefault("SILVERWING_MODEL", "silverwing-120m-base-v1")
os.environ.setdefault("SILVERWING_TIMEOUT", "300")


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing the FastAPI application.
    
    Yields an unauthenticated client for testing public endpoints and
    verifying that authenticated endpoints return 401 without credentials.
    """
    # Import the app and suppress startup events for testing
    from jarvis_backend.main import app

    # httpx >= 0.28 removed the ``app=`` shortcut; use ASGITransport so the
    # suite works on both old and new httpx versions.
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
