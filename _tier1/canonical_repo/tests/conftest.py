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
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# The platform repository is needed for gateway fallback/catalog integration
# tests.
PLATFORM_REPO = WORKSPACE_ROOT / "Jarvis-super-intelligence-"
if str(PLATFORM_REPO) not in sys.path:
    sys.path.insert(0, str(PLATFORM_REPO))

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
    
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac
