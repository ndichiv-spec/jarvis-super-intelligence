"""NeMo Microservices client (spec §5, §31-§33).

Provides async HTTP methods for each NeMo Microservices endpoint:

  * Synthetic data generation (`POST /v1/synthetic-data/generate`)
  * Fine-tuning (`POST /v1/fine-tuning/start`, etc.)
  * Evaluation (`POST /v1/evaluation/run`)
  * Safety audit (`POST /v1/safety/check`)
  * Guardrails (`POST /v1/guardrails/apply`)
  * Data preparation (`POST /v1/dataprep/prepare`)
  * Managed inference (`POST /v1/inference/infer`)
  * Customizer (`POST /v1/customizer/customize`)

All methods use ``httpx.AsyncClient`` under the hood.  An injectable
``http_client`` can be passed for tests — the client never makes real
HTTP calls unless the caller provides a real httpx client.

**NeMo is optional** — methods raise :class:`NeMoUnconfigured` when
``JARVIS_NEMO_API_KEY`` is not set.  Local operation does not require NeMo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from ..secrets import SecretManager, get_secret_manager
from .capabilities import NEMO_CAPABILITIES, NEMO_SERVICES as nemo_services, NeMoService
from .config import NeMoConfig
from .errors import NeMoUnconfigured, NeMoRequestError


@dataclass
class NeMoJobStatus:
    """Status of an asynchronous NeMo job (fine-tuning, dataprep, etc.)."""

    job_id: str
    status: str  # "pending", "running", "completed", "failed", "cancelled"
    progress: float = 0.0  # 0.0 to 1.0
    result_uri: str = ""
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")


class NeMoClient:
    """Async client for NVIDIA NeMo Microservices (spec §5).

    Example::

        client = NeMoClient()  # reads JARVIS_NEMO_* env vars
        if client.configured:
            result = await client.synthetic_data.generate(
                model="nvidia/nemo-llm",
                prompt="Generate synthetic QA pairs...",
                num_samples=100,
            )
    """

    def __init__(
        self,
        config: Optional[NeMoConfig] = None,
        secrets: Optional[SecretManager] = None,
        http_client: Any = None,
    ) -> None:
        self.config = config or NeMoConfig.from_environ(secrets=secrets)
        self._http_client = http_client  # injectable; None → create on demand

    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def capabilities(self) -> "NeMoCapabilities":
        return NEMO_CAPABILITIES

    @property
    def services(self) -> list[NeMoService]:
        return nemo_services

    def _require_configured(self) -> None:
        """Raise if NeMo is not configured (spec §5: never fabricate)."""
        if not self.configured:
            raise NeMoUnconfigured(
                "NeMo Microservices is not configured. "
                "Set JARVIS_NEMO_API_KEY and JARVIS_NEMO_ENDPOINT to enable. "
                "This is optional — local operation does not require NeMo."
            )

    @property
    def _base(self) -> str:
        return self.config.endpoint.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "JARVIS-NeMo-Client/0.1",
        }

    async def _request(
        self, method: str, path: str, *, body: dict[str, Any] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to NeMo (spec §5)."""
        self._require_configured()
        url = f"{self._base}{path}"
        headers = self._headers()
        timeout = timeout or self.config.timeout

        if self._http_client is not None:
            resp = await self._http_client.request(
                method, url, headers=headers, json=body, timeout=timeout,
            )
        else:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url, headers=headers, json=body, timeout=timeout,
                )

        if resp.status_code >= 400:
            raise NeMoRequestError(
                f"NeMo API error: {resp.status_code} {resp.text[:500]}",
                status_code=resp.status_code,
                body=body,
            )
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------ #
    # Synchronous convenience wrapper for tests / non-async contexts.
    async def _request_async(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """Alias for _request — kept for API symmetry with other providers."""
        return await self._request(method, path, **kwargs)

    # ------------------------------------------------------------------ #
    # Synthetic Data Service (spec §5: synthetic data generation)
    # ------------------------------------------------------------------ #
    @property
    def synthetic_data(self) -> "_SyntheticDataService":
        return _SyntheticDataService(self)

    # ------------------------------------------------------------------ #
    # Fine-tuning Service (spec §5: model customization)
    # ------------------------------------------------------------------ #
    @property
    def fine_tuning(self) -> "_FineTuningService":
        return _FineTuningService(self)

    # ------------------------------------------------------------------ #
    # Evaluation Service (spec §5: evaluation)
    # ------------------------------------------------------------------ #
    @property
    def evaluation(self) -> "_EvaluationService":
        return _EvaluationService(self)

    # ------------------------------------------------------------------ #
    # Safety Service (spec §5: safety auditing)
    # ------------------------------------------------------------------ #
    @property
    def safety(self) -> "_SafetyService":
        return _SafetyService(self)

    # ------------------------------------------------------------------ #
    # Guardrails Service (spec §5: guardrails)
    # ------------------------------------------------------------------ #
    @property
    def guardrails(self) -> "_GuardrailsService":
        return _GuardrailsService(self)

    # ------------------------------------------------------------------ #
    # Data Preparation Service (spec §5)
    # ------------------------------------------------------------------ #
    @property
    def dataprep(self) -> "_DataprepService":
        return _DataprepService(self)

    # ------------------------------------------------------------------ #
    # Inference Service (spec §5: inference management)
    # ------------------------------------------------------------------ #
    @property
    def inference(self) -> "_InferenceService":
        return _InferenceService(self)

    # ------------------------------------------------------------------ #
    # Customizer Service (spec §5: model customization / adaptation)
    # ------------------------------------------------------------------ #
    @property
    def customizer(self) -> "_CustomizerService":
        return _CustomizerService(self)

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    async def health_check(self) -> NeMoJobStatus:
        """Check NeMo endpoint readiness."""
        self._require_configured()
        url = f"{self._base}/v1/health"
        headers = self._headers()

        if self._http_client is not None:
            resp = await self._http_client.get(url, headers=headers, timeout=self.config.timeout)
        else:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=self.config.timeout)

        return NeMoJobStatus(
            job_id="health",
            status="completed" if resp.status_code == 200 else "failed",
            progress=1.0 if resp.status_code == 200 else 0.0,
            created_at=time.time(),
            updated_at=time.time(),
        )


# --------------------------------------------------------------------------- #
# Service classes — each NeMo Microservices endpoint group.
# --------------------------------------------------------------------------- #
class _SyntheticDataService:
    """NeMo Synthetic Data Microservices (spec §5 — synthetic data generation)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.synthetic_data

    async def generate(self, *, model: str, prompt: str,
                        num_samples: int = 10,
                        temperature: float = 0.7,
                        max_tokens: int = 2048,
                        **kwargs: Any) -> dict[str, Any]:
        """Generate synthetic data samples (spec §5/§33)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/synthetic-data/generate",
            body={
                "model": model,
                "prompt": prompt,
                "num_samples": num_samples,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs,
            },
        )

    async def augment(self, *, dataset_id: str,
                       num_samples: int = 50,
                       strategy: str = "paraphrase") -> dict[str, Any]:
        """Augment an existing dataset with synthetic samples."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/synthetic-data/augment",
            body={
                "dataset_id": dataset_id,
                "num_samples": num_samples,
                "strategy": strategy,
            },
        )


class _FineTuningService:
    """NeMo Fine-tuning Microservices (spec §5 — model customization)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.fine_tuning

    async def start(self, *, base_model: str, training_data: str,
                     epochs: int = 1, learning_rate: float = 1e-5,
                     **kwargs: Any) -> dict[str, Any]:
        """Start a fine-tuning job (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/fine-tuning/start",
            body={
                "base_model": base_model,
                "training_data": training_data,
                "epochs": epochs,
                "learning_rate": learning_rate,
                **kwargs,
            },
        )

    async def stop(self, job_id: str) -> dict[str, Any]:
        """Stop a running fine-tuning job."""
        self._client._require_configured()
        return await self._client._request(
            "POST", f"/v1/fine-tuning/{job_id}/stop",
        )

    async def status(self, job_id: str) -> NeMoJobStatus:
        """Get the status of a fine-tuning job."""
        self._client._require_configured()
        result = await self._client._request("GET", f"/v1/fine-tuning/{job_id}")
        return NeMoJobStatus(
            job_id=job_id,
            status=result.get("status", "unknown"),
            progress=result.get("progress", 0.0),
            result_uri=result.get("result_uri", ""),
            error=result.get("error", ""),
            created_at=result.get("created_at", time.time()),
            updated_at=result.get("updated_at", time.time()),
        )


class _EvaluationService:
    """NeMo Evaluation Microservices (spec §5 — evaluation)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.evaluation

    async def run(self, *, model: str, benchmark: str,
                   dataset: str = "",
                   **kwargs: Any) -> dict[str, Any]:
        """Run an evaluation benchmark (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/evaluation/run",
            body={
                "model": model,
                "benchmark": benchmark,
                "dataset": dataset,
                **kwargs,
            },
        )

    async def results(self, eval_id: str) -> dict[str, Any]:
        """Get evaluation results."""
        self._client._require_configured()
        return await self._client._request("GET", f"/v1/evaluation/{eval_id}/results")


class _SafetyService:
    """NeMo Safety Microservices (spec §5 — safety auditing)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.safety_audit

    async def check(self, *, text: str, model: str = "nvidia/safety-llama",
                     **kwargs: Any) -> dict[str, Any]:
        """Check content for safety violations (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/safety/check",
            body={"text": text, "model": model, **kwargs},
        )

    async def audit(self, *, dataset_id: str, **kwargs: Any) -> dict[str, Any]:
        """Audit a dataset for safety issues."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/safety/audit",
            body={"dataset_id": dataset_id, **kwargs},
        )


class _GuardrailsService:
    """NeMo Guardrails Microservices (spec §5 — guardrails)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.guardrails

    async def apply(self, *, request: dict[str, Any],
                     guardrail_configs: list[str] = None,
                     **kwargs: Any) -> dict[str, Any]:
        """Apply guardrails to a request (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/guardrails/apply",
            body={
                "request": request,
                "guardrail_configs": guardrail_configs or [],
                **kwargs,
            },
        )

    async def list(self) -> dict[str, Any]:
        """List available guardrails."""
        self._client._require_configured()
        return await self._client._request("GET", "/v1/guardrails")


class _DataprepService:
    """NeMo Data Preparation Microservices (spec §5)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.dataprep

    async def prepare(self, *, source_uri: str,
                       job_type: str = "pretrain",
                       **kwargs: Any) -> dict[str, Any]:
        """Prepare a dataset from source (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/dataprep/prepare",
            body={
                "source_uri": source_uri,
                "job_type": job_type,
                **kwargs,
            },
        )

    async def validate(self, *, dataset_id: str) -> dict[str, Any]:
        """Validate a dataset."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/dataprep/validate",
            body={"dataset_id": dataset_id},
        )

    async def split(self, *, dataset_id: str,
                     train_ratio: float = 0.8,
                     val_ratio: float = 0.1,
                     test_ratio: float = 0.1) -> dict[str, Any]:
        """Split a dataset into train/val/test."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/dataprep/split",
            body={
                "dataset_id": dataset_id,
                "train_ratio": train_ratio,
                "val_ratio": val_ratio,
                "test_ratio": test_ratio,
            },
        )

    async def status(self, job_id: str) -> NeMoJobStatus:
        """Get data preparation job status."""
        self._client._require_configured()
        result = await self._client._request("GET", f"/v1/dataprep/{job_id}")
        return NeMoJobStatus(
            job_id=job_id,
            status=result.get("status", "unknown"),
            progress=result.get("progress", 0.0),
            created_at=result.get("created_at", time.time()),
            updated_at=result.get("updated_at", time.time()),
        )


class _InferenceService:
    """NeMo Inference Management Microservices (spec §5)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.inference

    async def infer(self, *, model: str, prompt: str,
                     **kwargs: Any) -> dict[str, Any]:
        """Run inference via NeMo managed endpoint (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/inference/infer",
            body={"model": model, "prompt": prompt, **kwargs},
        )

    async def deploy(self, *, model: str,
                      num_gpus: int = 1,
                      **kwargs: Any) -> dict[str, Any]:
        """Deploy a model to the NeMo inference endpoint."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/inference/deploy",
            body={"model": model, "num_gpus": num_gpus, **kwargs},
        )

    async def status(self, deployment_id: str) -> NeMoJobStatus:
        """Get inference deployment status."""
        self._client._require_configured()
        result = await self._client._request("GET", f"/v1/inference/{deployment_id}")
        return NeMoJobStatus(
            job_id=deployment_id,
            status=result.get("status", "unknown"),
            progress=result.get("progress", 0.0),
            created_at=result.get("created_at", time.time()),
            updated_at=result.get("updated_at", time.time()),
        )


class _CustomizerService:
    """NeMo Customizer Microservices (spec §5 — model customization)."""

    def __init__(self, client: NeMoClient) -> None:
        self._client = client

    @property
    def available(self) -> bool:
        return self._client.capabilities.customizer

    async def customize(self, *, model: str, dataset: str,
                         **kwargs: Any) -> dict[str, Any]:
        """Customize a model using NeMo Customizer (spec §5)."""
        self._client._require_configured()
        return await self._client._request(
            "POST", "/v1/customizer/customize",
            body={"model": model, "dataset": dataset, **kwargs},
        )

    async def status(self, job_id: str) -> NeMoJobStatus:
        """Get customization job status."""
        self._client._require_configured()
        result = await self._client._request("GET", f"/v1/customizer/{job_id}")
        return NeMoJobStatus(
            job_id=job_id,
            status=result.get("status", "unknown"),
            progress=result.get("progress", 0.0),
            created_at=result.get("created_at", time.time()),
            updated_at=result.get("updated_at", time.time()),
        )
