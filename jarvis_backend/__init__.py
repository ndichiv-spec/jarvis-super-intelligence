"""JARVIS backend package.

Serves the JARVIS Next.js frontend API (/api/v1/**) and hosts the
Silverwing AI FastAPI backend as an integrated sub-application so the
whole system runs from a single backend process on a single port (8000).
"""

import os

from dotenv import load_dotenv as _load_dotenv

import jarvis_runtime

from .secret_config import load_file_secrets as _load_file_secrets

jarvis_runtime.bootstrap_runtime()

# Load the canonical project .env *before* core is imported. core.py constructs
# ``ai_service`` at import time and snapshots ``JARVIS_AI_ENABLED`` then; the
# project .env (which carries ``JARVIS_AI_ENABLED=1`` alongside the provider
# keys) must be on os.environ before ``_load_core`` runs. Otherwise AI is
# silently frozen *disabled* even though every provider key is configured --
# the previous boot loaded the workspace env (which omits the gate) and then
# main.py's bare ``load_dotenv()`` only ran *after* core was already imported.
if os.environ.get("JARVIS_TEST_MODE") != "1":
    _load_dotenv(str(jarvis_runtime.PROJECT_ROOT / ".env"))

if os.environ.get("JARVIS_TEST_MODE") != "1":
    _load_file_secrets()


def _load_core():
    from .core import DATA_DIR, app, start_backend

    return DATA_DIR, app, start_backend


DATA_DIR, app, start_backend = _load_core()

__all__ = ["DATA_DIR", "app", "start_backend"]
