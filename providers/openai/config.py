"""OpenAI provider configuration.

Reads ``JARVIS_OPENAI_*`` through the fabric :class:`SecretManager` (env ->
``.env`` -> encrypted vault). The raw key is never exposed to adapters' upstream
surfaces and never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..secrets import SecretManager, get_secret_manager


@dataclass
class OpenAIConfig:
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 120.0
    _present: bool = field(default=False, repr=False)

    @classmethod
    def from_environ(
        cls, secrets: Optional[SecretManager] = None, env: Optional[dict] = None
    ) -> "OpenAIConfig":
        sm = secrets or get_secret_manager()
        api_key = sm.get("JARVIS_OPENAI_API_KEY") or sm.get("OPENAI_API_KEY")
        model = sm.get("JARVIS_OPENAI_MODEL") or sm.get("OPENAI_MODEL")
        base_url = (env or os.environ).get(
            "JARVIS_OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        timeout = float((env or os.environ).get("JARVIS_OPENAI_TIMEOUT", "120") or 120)
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            _present=bool(api_key),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def is_configured(self) -> bool:
        return self.configured