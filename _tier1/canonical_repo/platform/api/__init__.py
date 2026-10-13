"""Compatibility package for the legacy ``api`` import path."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .main import app, create_application

__all__ = ["app", "create_application"]
