"""NVIDIA NeMo Microservices integration (spec §5, §31-§33).

**NeMo is OPTIONAL** — never required for local operation.  When
``JARVIS_NEMO_API_KEY`` is not set, all client methods raise
:class:`~providers.nemo.errors.NeMoUnconfigured` rather than producing
fake results or crashing.

Services provided (spec §5):
  * Synthetic data generation
  * Model customization (fine-tuning / SFT / DPO)
  * Evaluation
  * Safety auditing
  * Guardrails
  * Data preparation
  * Managed inference
  * NeMo Customizer

Usage::

    from providers.nemo import NeMoClient, NeMoConfig

    client = NeMoClient()  # reads JARVIS_NEMO_API_KEY from env
    if client.configured:
        result = await client.synthetic_data.generate(
            model="nvidia/nemo-llm",
            prompt="Generate synthetic QA pairs...",
            num_samples=100,
        )
"""

from __future__ import annotations

from .capabilities import NEMO_CAPABILITIES, NEMO_SERVICES, NeMoService
from .client import NeMoClient, NeMoJobStatus
from .config import NeMoConfig
from .errors import NemError, NeMoRequestError, NeMoUnconfigured
from .health import nemo_health_probe

__all__ = [
    "NEMO_CAPABILITIES",
    "NEMO_SERVICES",
    "NeMoClient",
    "NeMoConfig",
    "NeMoJobStatus",
    "NemError",
    "NeMoRequestError",
    "NeMoUnconfigured",
    "NeMoService",
    "nemo_health_probe",
]

__version__ = "0.1.0"
