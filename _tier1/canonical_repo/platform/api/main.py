"""Compatibility entry point for the legacy ``api.main`` import path."""

from __future__ import annotations

from fastapi import FastAPI

from jarvis_backend.main import app


def create_application() -> FastAPI:
    return app


__all__ = ["app", "create_application"]
