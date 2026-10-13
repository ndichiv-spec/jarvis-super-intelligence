#!/usr/bin/env python3
"""Canonical JARVIS runtime entry point.

Serves the entire backend from ONE process on ONE port:
  - every /api/v1/** endpoint the clients consume
  - the Silverwing backend mounted at /silverwing
  - the WebSocket feeds (/ws/...)

The application object is :data:`jarvis_backend.main.app`.  This module only
exposes that object and, when executed directly, serves it with uvicorn.  It
does not own any runtime state, so the same app stays importable by tests and
by alternate clients.

Run:
  python jarvis_api.py
  python -m uvicorn jarvis_api:app --reload --port 8000
"""

from __future__ import annotations

import os

# Only strip a leaked ambient JARVIS_TEST_MODE when this module is the running
# program.  A leftover system-level value must never silently switch the
# production database to in-memory mode.  Importing this module (tests, other
# clients) must not mutate the environment.
if __name__ == "__main__":
    os.environ.pop("JARVIS_TEST_MODE", None)

from jarvis_backend.main import app  # noqa: E402

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
