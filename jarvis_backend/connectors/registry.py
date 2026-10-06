"""Connector configuration registry (persistent + keyed secrets).

Configs live in ``jarvis_data/connectors/<kind>.json``.  Secret fields are
encrypted at rest (see crypto) and only ever leave the API masked.  A masked
value sent back in an update is treated as "keep", never as a real secret.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ..core import DATA_DIR
from .crypto import ConnectorCryptoError, decrypt_secret, encrypt_secret

CONNECTORS_DIR = DATA_DIR / "connectors"
AUDIT_DIR = DATA_DIR / "audit"

MASK = "\u2022\u2022\u2022\u2022\u2022\u2022"  # •••••• (length-6 mask)
SECRET_FIELDS = ("password", "api_key", "token", "secret")
AUDIT_FILE = AUDIT_DIR / "connectors.jsonl"

_lock = threading.Lock()


class ConnectorNotFound(Exception):
    """No connector of this kind has been configured yet."""


def _path(kind: str) -> Path:
    return CONNECTORS_DIR / f"{kind}.json"


def load(kind: str) -> Optional[Dict[str, Any]]:
    """Return the raw config with secrets decrypted (or None if unset)."""
    p = _path(kind)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ConnectorCryptoError(f"connector config unreadable for {kind}: {exc}") from exc
    for field, value in list(data.items()):
        if field in SECRET_FIELDS and isinstance(value, str) and value.startswith("fernet:"):
            try:
                data[field] = decrypt_secret(value)
            except ConnectorCryptoError:
                data[field] = None  # unrecoverable -> surface honestly
    return data


def save(config: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a config (encrypting secret fields).  Returns the stored copy."""
    stored = dict(config)
    for field in SECRET_FIELDS:
        if field in stored and isinstance(stored.get(field), str) and stored.get(field) != MASK:
            if not stored[field]:
                stored.pop(field, None)
            else:
                stored[field] = encrypt_secret(stored[field])
    CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        tmp = _path(config.get("kind", "email")).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stored, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, _path(config.get("kind", "email")))
    return stored


def delete(kind: str) -> bool:
    p = _path(kind)
    if not p.exists():
        return False
    with _lock:
        p.unlink()
    return True


def public_config(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Masked representation safe to return to clients."""
    if raw is None:
        return None
    out = dict(raw)
    for field in SECRET_FIELDS:
        if field in out:
            present = bool(out[field])
            out[field] = MASK if present else ""
            out[f"{field}_set"] = present
    return out


def audit(record: Dict[str, Any]) -> None:
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=str) + "\n"
        with _lock:
            with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:  # noqa: BLE001 - audit must never break the request
        pass


def read_audit(limit: int = 50) -> list:
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-max(1, limit):]:
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows[::-1]