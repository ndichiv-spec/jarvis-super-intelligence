#!/usr/bin/env python3
"""
JARVIS Unified API Entry Point (legacy alias)
==============================================
Compatibility shim. The single main backend now lives in the
`jarvis_backend` package (see `jarvis_api.py`). This module keeps the old
`unified_jarvis_api:app` import path working.

Run:
  python unified_jarvis_api.py        # uvicorn on 0.0.0.0:8000
"""

from jarvis_api import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
