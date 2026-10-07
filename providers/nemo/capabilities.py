"""NeMo Microservices capabilities (spec §5).

Declares which NeMo Microservices are *available* (i.e. the client knows how
to talk to them) vs. which are *configured* (API key is set).  A capability
being available doesn't mean it's configured — :class:`NeMoConfig` handles
configuration status.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NeMoCapabilities:
    """Which NeMo Microservices the client can invoke (spec §5).

    All capabilities are available by default (the client has implementations
    for all documented NeMo services).  Whether they actually work depends on
    configuration (API key, endpoint, project permissions).
    """

    synthetic_data: bool = True
    fine_tuning: bool = True
    evaluation: bool = True
    safety_audit: bool = True
    guardrails: bool = True
    dataprep: bool = True
    customizer: bool = True  # model customization / SFT
    inference: bool = True  # NeMo inference management

    @property
    def all(self) -> list[str]:
        return [k for k, v in self.__dict__.items() if v]

    def supports(self, capability: str) -> bool:
        return getattr(self, capability, False)


NEMO_CAPABILITIES = NeMoCapabilities()


@dataclass
class NeMoService:
    """Metadata about a NeMo Microservices endpoint."""

    name: str
    path: str
    capabilities: list[str]
    description: str = ""


# Service registry — maps NeMo Microservices to HTTP paths (spec §5).
NEMO_SERVICES: list[NeMoService] = [
    NeMoService(
        name="synthetic-data",
        path="/v1/synthetic-data",
        capabilities=["generate_synthetic_data", "augment_dataset"],
        description="Synthetic data generation and dataset augmentation",
    ),
    NeMoService(
        name="fine-tuning",
        path="/v1/fine-tuning",
        capabilities=["start_finetune", "stop_finetune", "get_finetune_status"],
        description="Custom model fine-tuning (SFT, DPO)",
    ),
    NeMoService(
        name="evaluation",
        path="/v1/evaluation",
        capabilities=["run_evaluation", "get_eval_results"],
        description="Model evaluation and scoring",
    ),
    NeMoService(
        name="safety",
        path="/v1/safety",
        capabilities=["check_safety", "audit_content"],
        description="Safety auditing and content screening",
    ),
    NeMoService(
        name="guardrails",
        path="/v1/guardrails",
        capabilities=["apply_guardrail", "list_guardrails"],
        description="Guardrails application and management",
    ),
    NeMoService(
        name="dataprep",
        path="/v1/dataprep",
        capabilities=["prepare_dataset", "validate_dataset", "split_dataset"],
        description="Dataset preparation, validation, and splitting",
    ),
    NeMoService(
        name="inference",
        path="/v1/inference",
        capabilities=["infer", "get_inference_status"],
        description="Managed inference endpoint",
    ),
    NeMoService(
        name="customizer",
        path="/v1/customizer",
        capabilities=["customize_model", "get_customization_status"],
        description="NeMo Customizer for model adaptation",
    ),
]
