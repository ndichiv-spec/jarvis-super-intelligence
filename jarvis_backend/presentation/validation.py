"""Validation policies shared by presentation ingress and internal producers."""

from __future__ import annotations

import json
from typing import Any

from .schemas import PRESENTATION_VERSION, PresentationEnvelope


class UnsupportedPresentationVersionError(ValueError):
    """Raised when a client cannot safely interpret a presentation major version."""


class UnsafePresentationDataError(ValueError):
    """Raised for non-serializable or excessively complex contract values."""


def validate_supported_version(version: str) -> None:
    try:
        major = int(version.split(".", maxsplit=1)[0])
        supported_major = int(PRESENTATION_VERSION.split(".", maxsplit=1)[0])
    except (TypeError, ValueError) as exc:
        raise UnsupportedPresentationVersionError("Invalid presentation protocol version.") from exc
    if major != supported_major:
        raise UnsupportedPresentationVersionError(
            f"Unsupported presentation protocol major version: {major}."
        )


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 12:
        raise UnsafePresentationDataError("Presentation data exceeds the supported nesting depth.")
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        if len(value) > 1000:
            raise UnsafePresentationDataError("Presentation arrays may contain at most 1000 entries.")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 256 or not all(isinstance(key, str) for key in value):
            raise UnsafePresentationDataError("Presentation objects have invalid or excessive keys.")
        for item in value.values():
            _validate_json_value(item, depth=depth + 1)
        return
    raise UnsafePresentationDataError("Presentation values must be JSON-serializable primitives.")


def validate_envelope(envelope: PresentationEnvelope) -> PresentationEnvelope:
    validate_supported_version(envelope.version)
    payload = envelope.model_dump(mode="json")
    _validate_json_value(payload)
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 1_048_576:
        raise UnsafePresentationDataError("Presentation envelope exceeds the 1 MiB limit.")
    return envelope
