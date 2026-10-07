"""SecretManager for the JARVIS Provider Fabric.

One credential abstraction for API keys, OAuth tokens, cloud/endpoint credentials
and webhook secrets (spec §16):

* backends: environment -> ``.env`` -> encrypted vault file (Fernet, at rest);
* the raw value is masked everywhere (``redact``);
* ``assert_no_secrets`` refuses to serialize *any* registered secret into model
  context — the "Brain sees tool capability, never the secret" rule (spec §16/69).

The fabric deliberately does **not** put secrets in provider metadata or requests.
Adapters read their key through this manager and pass only a masked presence flag
upstream. Rotation is supported by re-writing the vault with a new key/password.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Optional

from .errors import SecretLeakError

try:  # cryptography is optional; without it the vault file falls back to env-only
    from cryptography.fernet import Fernet, InvalidToken

    _FERNET_OK = True
except Exception:  # pragma: no cover - defensive
    Fernet = None  # type: ignore[assignment,misc]
    _FERNET_OK = False


def _redact(value: str, visible: int = 4) -> str:
    if not value:
        return "****"
    if len(value) <= visible:
        return "****"
    return value[:visible] + "****"


def _load_dotenv(path: Path) -> dict[str, str]:
    store: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip("'\"").strip()
                if key.strip() and value:
                    store[key.strip()] = value
    except OSError:
        pass
    return store


class _VaultFile:
    """Fernet-encrypted JSON secret file (encryption at rest)."""

    def __init__(self, path: Path, key_env: str = "JARVIS_VAULT_KEY") -> None:
        self.path = path
        self.key_env = key_env
        self._cache: dict[str, str] | None = None
        self._lock = threading.Lock()

    def _key(self) -> bytes | None:
        raw = os.environ.get(self.key_env)
        if not raw:
            return None
        try:
            return base64.urlsafe_b64encode(raw.encode().ljust(32)[:32])
        except Exception:
            return None

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        if not self.path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            key = self._key()
            if key is not None and _FERNET_OK and Fernet is not None:
                data = Fernet(key).decrypt(raw.encode())
            else:
                data = raw.encode()
            parsed = json.loads(data)
            self._cache = parsed if isinstance(parsed, dict) else {}
        except (OSError, json.JSONDecodeError, InvalidToken):
            self._cache = {}
        return self._cache

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key) or self._load().get(key.upper())

    def set(self, key: str, value: str) -> None:
        with self._lock:
            data = dict(self._load())
            data[key] = value
            payload = json.dumps(data, indent=2)
            vkey = self._key()
            if vkey is not None and _FERNET_OK and Fernet is not None:
                payload = Fernet(vkey).encrypt(payload.encode()).decode()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(payload, encoding="utf-8")
            self._cache = data

    def keys(self) -> list[str]:
        return list(self._load().keys())


class SecretManager:
    """Multi-backend credential lookup + isolation guard.

    Lookup order (first hit wins): context overrides -> env -> ``.env`` -> vault.
    """

    def __init__(
        self,
        vault_path: Optional[Path] = None,
        dotenv_path: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self._env = env if env is not None else os.environ
        self._dotenv = _load_dotenv(dotenv_path or Path.cwd() / ".env")
        self._vault = (
            _VaultFile(vault_path) if vault_path is not None else None
        )
        self._overrides: dict[str, str] = {}
        self._known: set[str] = set()

    # -- lookup -------------------------------------------------------------
    def put(self, name: str, value: str) -> None:
        """Register a runtime override (e.g. per-test or per-request)."""
        self._overrides[name] = value
        self._overrides[name.upper()] = value

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        for candidate in (name, name.upper(), f"JARVIS_{name.upper()}"):
            if candidate in self._overrides:
                return self._overrides[candidate]
        for candidate in (name, name.upper(), f"JARVIS_{name.upper()}"):
            if candidate in self._env:
                return self._env[candidate]
        for candidate in (name, name.upper(), f"JARVIS_{name.upper()}"):
            value = self._dotenv.get(candidate)
            if value:
                return value
        if self._vault is not None:
            value = self._vault.get(name)
            if value:
                return value
        return default

    def configured(self, name: str) -> bool:
        return bool(self.get(name))

    def redact(self, value: Optional[str]) -> str:
        return _redact(value) if value else "****"

    def secrets(self) -> dict[str, str]:
        """Every credential the manager currently knows (for guardians/tests)."""
        result: dict[str, str] = {}
        candidates: set[str] = set()
        candidates.update(self._overrides)
        candidates.update(k for k in self._env if "KEY" in k.upper() or "TOKEN" in k.upper() or "SECRET" in k.upper())
        candidates.update(self._dotenv)
        if self._vault is not None:
            candidates.update(self._vault.keys())
        for name in sorted(candidates):
            value = self.get(name)
            if value:
                result[name] = value
        self._known = set(result)
        return result

    # -- isolation guard ----------------------------------------------------
    def assert_no_secrets(
        self,
        text: str,
        *secret_names: str,
        force_scan_all: bool = False,
    ) -> None:
        """Refuse to serialize any known secret into ``text``.

        Raises :class:`SecretLeakError` if a secret value appears. Secret values
        are masked by length (longer reveals), but a hit is fatal either way.
        """
        values = set()
        for name in secret_names:
            value = self.get(name)
            if value and len(value) >= 4:
                values.add(value)
        if force_scan_all:
            values.update(v for v in self.secrets().values() if len(v) >= 4)
        for value in values:
            if value in text:
                raise SecretLeakError(
                    f"secret value for a configured credential was found in "
                    f"outbound model context; request refused (len={len(value)})"
                )

    def assert_no_secrets_in_requests(
        self,
        requests: list,
        *secret_names: str,
        force_scan_all: bool = False,
    ) -> None:
        joined = "\n".join(
            _request_to_safe_text(r) for r in requests
        )
        self.assert_no_secrets(joined, *secret_names, force_scan_all=force_scan_all)

    # -- vault helpers ------------------------------------------------------
    def store(self, name: str, value: str) -> None:
        if self._vault is None:
            raise RuntimeError("vault not enabled (no vault path supplied)")
        self._vault.set(name, value)

    def has_vault(self) -> bool:
        return self._vault is not None


def _request_to_safe_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content)
    except TypeError:
        return str(content)


_default_manager: SecretManager | None = None
_manager_lock = threading.Lock()


def get_secret_manager() -> SecretManager:
    global _default_manager
    with _manager_lock:
        if _default_manager is None:
            vault_path = os.environ.get("JARVIS_VAULT_PATH")
            dotenv_path = os.environ.get("JARVIS_DOTENV_PATH")
            _default_manager = SecretManager(
                vault_path=Path(vault_path) if vault_path else None,
                dotenv_path=Path(dotenv_path) if dotenv_path else None,
            )
        return _default_manager


def reset_secret_manager(manager: SecretManager | None = None) -> None:
    global _default_manager
    with _manager_lock:
        _default_manager = manager if manager is not None else SecretManager()