"""Legacy application factory for ``core.api.main``."""

from __future__ import annotations

from fastapi import FastAPI

from jarvis_backend.main import app


def create_application() -> FastAPI:
    return app

__all__ = ["app", "create_application"]
