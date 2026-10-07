"""AWS Bedrock configuration (spec §8).

``JARVIS_AWS_REGION``: region (e.g. ``us-east-1``).
``JARVIS_AWS_ACCESS_MODE``: ``env`` (default), ``profile``, ``sso`` or
``federated``. Static long-lived keys are never required; boto3 uses the standard
credential chain, and Workload Identity Federation / SSO short-lived creds are
preferred for external workloads (spec §8/55).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..secrets import SecretManager, get_secret_manager


@dataclass
class AwsConfig:
    region: Optional[str] = None
    access_mode: str = "env"
    profile: Optional[str] = None
    model: Optional[str] = None
    timeout: float = 180.0
    _present: bool = field(default=False, repr=False)

    @classmethod
    def from_environ(
        cls, secrets: Optional[SecretManager] = None, env: Optional[dict] = None
    ) -> "AwsConfig":
        sm = secrets or get_secret_manager()
        env_or = env or os.environ
        region = secrets.get("JARVIS_AWS_REGION") or env_or.get("AWS_REGION")
        access_mode = (
            env_or.get("JARVIS_AWS_ACCESS_MODE")
            or sm.get("JARVIS_AWS_ACCESS_MODE")
            or "env"
        )
        profile = env_or.get("AWS_PROFILE") or sm.get("AWS_PROFILE")
        model = sm.get("JARVIS_AWS_MODEL") or sm.get("AWS_BEDROCK_MODEL")
        timeout = float(env_or.get("JARVIS_AWS_TIMEOUT", "180") or 180)
        return cls(
            region=region,
            access_mode=access_mode,
            profile=profile,
            model=model,
            timeout=timeout,
            _present=bool(region),
        )

    @property
    def configured(self) -> bool:
        return bool(self.region)