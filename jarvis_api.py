#!/usr/bin/env python3
"""
JARVIS Unified Backend (single main backend)
=============================================
Serves the entire JARVIS system from ONE backend process on ONE port (8000):
  - all /api/v1/** endpoints required by the JARVIS Next.js frontend
  - the Silverwing AI backend integrated as a mounted sub-application at /silverwing
  - WebSocket feeds (/ws/chat, /ws/health, ... ) and socket.io chat

Run:
  python jarvis_api.py                 # uvicorn on 0.0.0.0:8000
  python -m uvicorn jarvis_api:app --reload --port 8000
"""

import os

from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Runtime environment preparation
# --------------------------------------------------------------------------- #
# This is the *application* entrypoint, not the test entrypoint.  Tests set
# ``JARVIS_TEST_MODE`` themselves (and import db.py directly); the normal
# runtime must NEVER honour a leftover system-level ``JARVIS_TEST_MODE`` that
# would silently switch SQLite to in-memory mode and destroy all persistence.
# Clearing it here guarantees the production file-based database is used no
# matter what the ambient system environment looks like.  If ``JARVIS_TEST_MODE``
# is present in a .env file, load_dotenv() will set it after this pop and it
# will be respected — but neither project .env nor workspace .env defines it.
os.environ.pop("JARVIS_TEST_MODE", None)

load_dotenv()

from jarvis_backend.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
