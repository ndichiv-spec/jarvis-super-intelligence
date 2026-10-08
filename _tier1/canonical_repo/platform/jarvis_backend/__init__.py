"""JARVIS backend package.

Serves the JARVIS Next.js frontend API (/api/v1/**) and hosts the
Silverwing AI FastAPI backend as an integrated sub-application so the
whole system runs from a single backend process on a single port (8000).
"""

import jarvis_runtime

jarvis_runtime.bootstrap_runtime()


def _load_core():
    from .core import DATA_DIR, app, start_backend

    return DATA_DIR, app, start_backend


DATA_DIR, app, start_backend = _load_core()

__all__ = ["DATA_DIR", "app", "start_backend"]
