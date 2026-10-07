"""NeMo Microservices configuration (spec §5, §31).

``JARVIS_NEMO_API_KEY`` / ``JARVIS_NEMO_ENDPOINT`` / ``JARVIS_NEMO_PROJECT_ID``.

NeMo is OPTIONAL — never required for local operation (spec §5).  The
client degrades gracefully when unconfigured: all methods raise
:class:`NeMoUnconfigured` rather than crashing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..secrets import SecretManager, get_secret_manager

_DEFAULT_ENDPOINT = "https://api.nvidia.com/nemo/v1"
_DEFAULT_TIMEOUT = 120.0


@dataclass
class NeMoConfig:
    """Configuration for the NeMo Microservices client."""

    api_key: Optional[str] = None
    endpoint: str = _DEFAULT_ENDPOINT
    project_id: Optional[str] = None
    region: str = "us-central1"
    timeout: float = _DEFAULT_TIMEOUT
    _present: bool = field(default=False, repr=False)

    @classmethod
    def from_environ(
        cls, secrets: Optional[SecretManager] = None, env: Optional[dict] = None
    ) -> "NeMoConfig":
        sm = secrets or get_secret_manager()
        e = env or os.environ
        api_key = sm.get("NEMO_API_KEY") or sm.get("JARVIS_NEMO_API_KEY")
        endpoint = e.get("JARVIS_NEMO_ENDPOINT") or (
            sm.get("JARVIS_NEMO_ENDPOINT") or _DEFAULT_ENDPOINT
        )
        project_id = sm.get("JARVIS_NEMO_PROJECT_ID") or e.get("JARVIS_NEMO_PROJECT_ID")
        timeout = float(e.get("JARVIS_NEMO_TIMEOUT", str(_DEFAULT_TIMEOUT)) or _DEFAULT_TIMEOUT)
        region = e.get("JARVIS_NEMO_REGION", "us-central1")
        return cls(
            api_key=api_key,
            endpoint=endpoint,
            project_id=project_id,
            region=region,
            timeout=timeout,
            _present=bool(api_key),
        )

    @property
    def configured(self) -> bool:
        """True only when an API key is set — never fabricates availability."""
        return bool(self.api_key)
