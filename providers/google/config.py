"""Google / Vertex configuration (spec §7).

Gemini dev/API key mode: ``JARVIS_GOOGLE_API_KEY`` (or ``GOOGLE_API_KEY``).
Vertex managed mode: ``JARVIS_VERTEX_PROJECT_ID`` + ``JARVIS_VERTEX_LOCATION``.
Model: ``JARVIS_GOOGLE_MODEL`` / ``JARVIS_VERTEX_MODEL``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..secrets import SecretManager, get_secret_manager


@dataclass
class GoogleConfig:
    api_key: Optional[str] = None
    project: Optional[str] = None
    location: Optional[str] = None
    model: Optional[str] = None
    timeout: float = 180.0
    _present: bool = field(default=False, repr=False)

    @classmethod
    def from_environ(
        cls, secrets: Optional[SecretManager] = None, env: Optional[dict] = None
    ) -> "GoogleConfig":
        sm = secrets or get_secret_manager()
        api_key = sm.get("GOOGLE_API_KEY") or sm.get("JARVIS_GOOGLE_API_KEY")
        project = sm.get("VERTEX_PROJECT_ID") or sm.get("JARVIS_VERTEX_PROJECT_ID")
        location = sm.get("VERTEX_LOCATION") or sm.get("JARVIS_VERTEX_LOCATION")
        model = (
            sm.get("JARVIS_GOOGLE_MODEL")
            or sm.get("JARVIS_VERTEX_MODEL")
            or sm.get("GOOGLE_MODEL")
        )
        timeout = float((env or os.environ).get("JARVIS_GOOGLE_TIMEOUT", "180") or 180)
        return cls(
            api_key=api_key,
            project=project,
            location=location,
            model=model,
            timeout=timeout,
            _present=bool(api_key or (project and location)),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key or (self.project and self.location))

    @property
    def vertex_mode(self) -> bool:
        return bool(self.project and self.location) and not self.api_key