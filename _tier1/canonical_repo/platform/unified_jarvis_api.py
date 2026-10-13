#!/usr/bin/env python3
"""Legacy alias for :mod:`jarvis_api`.

Keeps the historical ``unified_jarvis_api:app`` import path working.  The
single backend application still lives in :mod:`jarvis_backend.main`; this
module re-exports the same object so every entry point serves one app.

Run:
  python unified_jarvis_api.py
"""

from __future__ import annotations

from jarvis_api import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
