"""Secret at-rest encryption for connector credentials.

Credentials are encrypted with Fernet (cryptography) keyed off a SHA-256 of
``JARVIS_SECRET_KEY`` (the same stable key that signs JWTs).  A connector whose
key can no longer be derived reports its credentials as unrecoverable rather
than silently returning plaintext.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger("jarvis.connectors.crypto")


class ConnectorCryptoError(Exception):
    """Raised when a secret cannot be encrypted or decrypted."""


def _fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except Exception as exc:  # pragma: no cover - dependency failure path
        raise ConnectorCryptoError(
            f"cryptography is required for connector secrets: {exc}"
        ) from exc

    key_material = os.environ.get("JARVIS_SECRET_KEY", "").strip()
    if not key_material:  # stable fallback keyed to this install (ephemeral-safe)
        root = Path(__file__).resolve().parent.parent.parent.parent
        key_material = f"jarvis-connector-fallback::{root}"
        logger.warning(
            "JARVIS_SECRET_KEY not set; connector secrets will be encrypted with "
            "an install-local fallback key. Set JARVIS_SECRET_KEY for portability."
        )
    raw = hashlib.sha256(key_material.encode("utf-8")).digest()
    return Fernet(__import__("base64").urlsafe_b64encode(raw)), InvalidToken


def encrypt_secret(value: str) -> str:
    """Return ``fernet:<token>`` for a secret string."""
    if not value:
        raise ConnectorCryptoError("cannot encrypt an empty secret")
    try:
        f, _ = _fernet()
        return f"fernet:{f.encrypt(value.encode('utf-8')).decode('ascii')}"
    except ConnectorCryptoError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConnectorCryptoError(f"encryption failed: {exc}") from exc


def decrypt_secret(stored: str) -> str:
    """Decrypt a ``fernet:`` token back to plaintext."""
    if not stored:
        raise ConnectorCryptoError("stored secret is empty")
    token = stored
    if token.startswith("fernet:"):
        token = token[len("fernet:"):]
    try:
        f, InvalidToken = _fernet()
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ConnectorCryptoError(
            "credentials are unrecoverable (encryption key changed); "
            "re-enter the password to reconnect"
        ) from exc
    except ConnectorCryptoError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConnectorCryptoError(f"decryption failed: {exc}") from exc