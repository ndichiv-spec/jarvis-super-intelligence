"""Inference backends for the Silverwing runtime.

* :class:`~silverwing_runtime.backends.echo.EchoBackend` — explicit
  development/test backend (``SILVERWING_BACKEND=echo``; never a fallback).
* :class:`~silverwing_runtime.backends.torch_backend.TorchBackend` —
  production default (``SILVERWING_BACKEND=torch``), real weights.
"""

from silverwing_runtime.backends.base import InferenceBackend
from silverwing_runtime.backends.echo import EchoBackend

__all__ = ["InferenceBackend", "EchoBackend", "TorchBackend"]


def __getattr__(name: str):
    """Import ``TorchBackend`` lazily.

    Importing this package (and therefore ``backends.base``, ``backends.echo``
    or ``backends.architecture``) must not require ``torch`` — the dependency
    only applies when the torch backend is actually constructed.  Requesting
    ``TorchBackend`` without torch installed still fails loudly.
    """
    if name == "TorchBackend":
        from silverwing_runtime.backends.torch_backend import TorchBackend

        return TorchBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")