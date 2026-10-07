"""Inference backends for the Silverwing runtime.

* :class:`~silverwing_runtime.backends.echo.EchoBackend` — explicit
  development/test backend (``SILVERWING_BACKEND=echo``; never a fallback).
* :class:`~silverwing_runtime.backends.torch_backend.TorchBackend` —
  production default (``SILVERWING_BACKEND=torch``), real weights.
"""

from silverwing_runtime.backends.base import InferenceBackend
from silverwing_runtime.backends.echo import EchoBackend
from silverwing_runtime.backends.torch_backend import TorchBackend

__all__ = ["InferenceBackend", "EchoBackend", "TorchBackend"]