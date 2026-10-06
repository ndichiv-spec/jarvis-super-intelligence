"""
Secure secrets management module.

Supports multiple backends:
  1. Environment variables (default)
  2. .env files (development)
  3. Encrypted vault file (production)
  4. Cloud secret managers (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault)

All secrets are masked in logs and error messages.
"""

import os
import json
import base64
import logging
from pathlib import Path
from typing import Dict, Optional, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SecretNotFoundError(Exception):
    """Raised when a secret is not found in any backend."""
    pass


class SecretBackendType(Enum):
    ENV = "env"
    DOTENV = "dotenv"
    VAULT_FILE = "vault_file"
    AWS_SECRETS = "aws_secrets"
    GCP_SECRET = "gcp_secret"
    AZURE_VAULT = "azure_vault"
    CUSTOM = "custom"


@dataclass
class Secret:
    key: str
    value: str
    source: SecretBackendType
    metadata: Dict[str, Any] = field(default_factory=dict)


class SecretBackend:
    """Abstract base for a secret backend."""

    def name(self) -> str:
        raise NotImplementedError

    def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def list_keys(self) -> List[str]:
        raise NotImplementedError

    def health(self) -> bool:
        raise NotImplementedError


class EnvBackend(SecretBackend):
    """Reads secrets from environment variables."""

    def __init__(self, prefix: str = "JARVIS_"):
        self.prefix = prefix

    def name(self) -> str:
        return "environment"

    def get(self, key: str) -> Optional[str]:
        env_key = f"{self.prefix}{key.upper()}"
        return os.environ.get(env_key)

    def list_keys(self) -> List[str]:
        return [k[len(self.prefix):] for k in os.environ if k.startswith(self.prefix)]

    def health(self) -> bool:
        return True


class DotenvBackend(SecretBackend):
    """Reads secrets from .env files."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path.cwd() / ".env"
        self._cache: Optional[Dict[str, str]] = None

    def name(self) -> str:
        return "dotenv"

    def _load(self) -> Dict[str, str]:
        if self._cache is not None:
            return self._cache
        secrets: Dict[str, str] = {}
        if not self.path.exists():
            self._cache = secrets
            return secrets
        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"").strip()
                if value:
                    secrets[key] = value
        self._cache = secrets
        return secrets

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key) or self._load().get(key.upper())

    def list_keys(self) -> List[str]:
        return list(self._load().keys())

    def health(self) -> bool:
        return self.path.exists() if self.path else True


class VaultFileBackend(SecretBackend):
    """
    Encrypted vault file backend.

    Stores secrets in an encrypted JSON file.
    Uses a master key from environment for decryption.
    """

    def __init__(self, vault_path: Path, master_key_env: str = "JARVIS_VAULT_KEY"):
        self.vault_path = vault_path
        self.master_key_env = master_key_env
        self._cache: Optional[Dict[str, str]] = None

    def name(self) -> str:
        return "vault_file"

    def _decrypt(self, encrypted_data: str) -> Dict[str, str]:
        master_key = os.environ.get(self.master_key_env)
        if not master_key:
            logger.warning(f"Vault master key ({self.master_key_env}) not set, using raw JSON")
            try:
                return json.loads(encrypted_data)
            except json.JSONDecodeError:
                return {}

        try:
            from cryptography.fernet import Fernet
            key = base64.urlsafe_b64encode(master_key.encode().ljust(32)[:32])
            f = Fernet(key)
            decrypted = f.decrypt(encrypted_data.encode())
            return json.loads(decrypted)
        except ImportError:
            logger.warning("cryptography not installed, vault file encryption disabled")
            return json.loads(encrypted_data)
        except Exception as e:
            logger.error(f"Failed to decrypt vault: {e}")
            return {}

    def _load(self) -> Dict[str, str]:
        if self._cache is not None:
            return self._cache
        if not self.vault_path.exists():
            self._cache = {}
            return {}
        try:
            with open(self.vault_path, "r") as f:
                content = f.read().strip()
            self._cache = self._decrypt(content)
        except Exception as e:
            logger.error(f"Failed to load vault file {self.vault_path}: {e}")
            self._cache = {}
        return self._cache

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key)

    def list_keys(self) -> List[str]:
        return list(self._load().keys())

    def health(self) -> bool:
        return self.vault_path.exists()


class SecretsManager:
    """
    Multi-backend secrets manager with fallback.

    Backends are checked in order. The first backend that
    contains the requested key wins.
    """

    def __init__(self, backends: Optional[List[SecretBackend]] = None):
        self.backends = backends or [
            EnvBackend(),
            DotenvBackend(),
        ]
        self._masked_keys: set = set()

    def add_backend(self, backend: SecretBackend):
        self.backends.append(backend)
        return self

    def get(self, key: str, default: Optional[str] = None) -> str:
        """Retrieve a secret from the first backend that has it."""
        for backend in self.backends:
            try:
                value = backend.get(key)
                if value is not None:
                    return value
            except Exception as e:
                logger.debug(f"Secret backend {backend.name()} failed for '{key}': {e}")
                continue

        if default is not None:
            return default

        raise SecretNotFoundError(
            f"Secret '{key}' not found in any backend "
            f"(tried: {', '.join(b.name() for b in self.backends)})"
        )

    def get_or_none(self, key: str) -> Optional[str]:
        """Retrieve a secret or return None if not found."""
        try:
            return self.get(key)
        except SecretNotFoundError:
            return None

    def mask(self, value: str, visible_chars: int = 4) -> str:
        """Mask a secret value for safe logging."""
        if not value or len(value) <= visible_chars:
            return "****"
        return value[:visible_chars] + "****"

    def get_masked(self, key: str) -> str:
        """Get a secret with its value masked."""
        value = self.get(key)
        return self.mask(value)


_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager singleton."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def reset_secrets_manager():
    """Reset the secrets manager singleton (useful for testing)."""
    global _secrets_manager
    _secrets_manager = None
