"""NVIDIA provider configuration (spec §4).

``JARVIS_NVIDIA_API_KEY`` / ``JARVIS_NVIDIA_ENDPOINT`` / ``JARVIS_NVIDIA_MODEL``.
The endpoint defaults to NVIDIA-hosted inference (not local). Self-hosted NIMs
point ``JARVIS_NVIDIA_ENDPOINT`` at the NIM instance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..secrets import SecretManager, get_secret_manager

_DEFAULT_ENDPOINT = "https://integrate.api.nvidia.com/v1"


@dataclass
class NvidiaConfig:
    api_key: Optional[str] = None
    endpoint: str = _DEFAULT_ENDPOINT
    model: Optional[str] = None
    timeout: float = 180.0
    _present: bool = field(default=False, repr=False)

    @classmethod
    def from_environ(
        cls, secrets: Optional[SecretManager] = None, env: Optional[dict] = None
    ) -> "NvidiaConfig":
        sm = secrets or get_secret_manager()
        api_key = sm.get("NVIDIA_API_KEY") or sm.get("JARVIS_NVIDIA_API_KEY")
        endpoint = (env or os.environ).get(
            "JARVIS_NVIDIA_ENDPOINT",
            sm.get("JARVIS_NVIDIA_ENDPOINT") or _DEFAULT_ENDPOINT,
        )
        model = sm.get("JARVIS_NVIDIA_MODEL") or sm.get("NVIDIA_MODEL")
        timeout = float((env or os.environ).get("JARVIS_NVIDIA_TIMEOUT", "180") or 180)
        return cls(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            timeout=timeout,
            _present=bool(api_key),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)