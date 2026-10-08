"""Hugging Face configuration (spec §9).

``JARVIS_HF_TOKEN`` (or ``HF_TOKEN``): registry/dataset/artifact access.
``JARVIS_HF_INFERENCE_ENDPOINT``: any valid remote OpenAI-compatible inference
endpoint — never assumed, never confused with a repo id.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..secrets import SecretManager, get_secret_manager


@dataclass
class HuggingFaceConfig:
    token: Optional[str] = None
    inference_endpoint: Optional[str] = None
    model: Optional[str] = None
    api_base: str = "https://huggingface.co"
    timeout: float = 120.0
    _present: bool = field(default=False, repr=False)

    @classmethod
    def from_environ(
        cls, secrets: Optional[SecretManager] = None, env: Optional[dict] = None
    ) -> "HuggingFaceConfig":
        sm = secrets or get_secret_manager()
        env_or = env or os.environ
        token = sm.get("HF_TOKEN") or sm.get("JARVIS_HF_TOKEN")
        endpoint = (
            env_or.get("JARVIS_HF_INFERENCE_ENDPOINT")
            or sm.get("JARVIS_HF_INFERENCE_ENDPOINT")
        )
        model = sm.get("JARVIS_HF_MODEL") or sm.get("HF_MODEL")
        api_base = env_or.get("JARVIS_HF_API_BASE", "https://huggingface.co")
        timeout = float(env_or.get("JARVIS_HF_TIMEOUT", "120") or 120)
        return cls(
            token=token,
            inference_endpoint=endpoint,
            model=model,
            api_base=api_base,
            timeout=timeout,
            _present=bool(token),
        )

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def run_configured(self) -> bool:
        """Registry + inference both configured."""
        return bool(self.token) and bool(self.inference_endpoint)