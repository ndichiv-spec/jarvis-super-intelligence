"""Connector configuration registry (persistent + keyed secrets).

Configs live in owner-scoped files in ``jarvis_data/connectors``. Secret
fields are encrypted at rest (see crypto) and only ever leave the API masked.
A masked value sent back in an update is treated as "keep", never as a real
secret.
"""

from __future__ import annotations

import hashlib
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


def _owner_id(config: Dict[str, Any]) -> Optional[str]:
    owner_id = config.get("owner_user_id") or config.get("oauth_user_id")
    if owner_id is None:
        return None
    return str(owner_id)


def _path(kind: str, user_id: Optional[str] = None) -> Path:
    if user_id is None:
        return CONNECTORS_DIR / f"{kind}.json"
    owner_key = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    return CONNECTORS_DIR / f"{kind}-{owner_key}.json"


def load(kind: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load one user's connector config without falling back across owners."""
    p = _path(kind, user_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ConnectorCryptoError(f"connector config unreadable for {kind}: {exc}") from exc
    owner_id = _owner_id(data)
    if user_id is not None and owner_id != str(user_id):
        return None
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
    owner_id = _owner_id(stored)
    oauth_user_id = stored.get("oauth_user_id")
    if oauth_user_id is not None and owner_id != str(oauth_user_id):
        raise ValueError("OAuth connector owner must match oauth_user_id")
    if owner_id is not None:
        stored["owner_user_id"] = owner_id
    for field in SECRET_FIELDS:
        if field in stored and isinstance(stored.get(field), str) and stored.get(field) != MASK:
            if not stored[field]:
                stored.pop(field, None)
            else:
                stored[field] = encrypt_secret(stored[field])
    CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        target = _path(config.get("kind", "email"), owner_id)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stored, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, target)
    return stored


def delete(kind: str, user_id: Optional[str] = None) -> bool:
    p = _path(kind, user_id)
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
    out.pop("owner_user_id", None)
    out.pop("oauth_user_id", None)
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


def read_audit(limit: int = 50, user_id: Optional[str] = None) -> list:
    if not AUDIT_FILE.exists():
        return []
    rows = []
    for line in reversed(AUDIT_FILE.read_text(encoding="utf-8").splitlines()):
        try:
            record = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if user_id is not None and str(record.get("user_id") or "") != str(user_id):
            continue
        rows.append(record)
        if len(rows) >= max(1, limit):
            break
    return rows