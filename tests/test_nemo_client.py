"""Tests for the NeMo Microservices client (spec §5, §31-§33).

All tests use an injectable HTTP client mock — no real network calls.
"""

from __future__ import annotations

import pytest

from providers.nemo import (
    NeMoClient, NeMoConfig, NeMoJobStatus,
    NemError, NeMoRequestError, NeMoUnconfigured,
    NEMO_CAPABILITIES, nemo_health_probe,
)
from providers.nemo.capabilities import NEMO_SERVICES, NeMoService
from providers.secrets import SecretManager


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class TestNeMoConfig:
    def test_unconfigured_without_key(self):
        config = NeMoConfig()
        assert not config.configured

    def test_configured_with_key(self):
        sm = SecretManager()
        sm.put("JARVIS_NEMO_API_KEY", "test-key")
        config = NeMoConfig.from_environ(secrets=sm)
        assert config.configured
        assert config.api_key == "test-key"

    def test_from_environ_custom_endpoint(self):
        sm = SecretManager()
        sm.put("JARVIS_NEMO_API_KEY", "key")
        sm.put("JARVIS_NEMO_ENDPOINT", "https://custom.nemo.com/v1")
        sm.put("JARVIS_NEMO_PROJECT_ID", "my-project")
        config = NeMoConfig.from_environ(secrets=sm)
        assert config.endpoint == "https://custom.nemo.com/v1"
        assert config.project_id == "my-project"

    def test_default_endpoint(self):
        config = NeMoConfig()
        assert config.endpoint == "https://api.nvidia.com/nemo/v1"


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
class TestNeMoCapabilities:
    def test_all_capabilities_true(self):
        caps = NEMO_CAPABILITIES
        assert caps.synthetic_data is True
        assert caps.fine_tuning is True
        assert caps.evaluation is True
        assert caps.safety_audit is True
        assert caps.guardrails is True
        assert caps.dataprep is True
        assert caps.inference is True
        assert caps.customizer is True

    def test_all_list(self):
        caps = NEMO_CAPABILITIES
        assert len(caps.all) == 8

    def test_supports_method(self):
        assert NEMO_CAPABILITIES.supports("synthetic_data") is True
        assert NEMO_CAPABILITIES.supports("nonexistent") is False

    def test_services_registered(self):
        assert len(NEMO_SERVICES) == 8
        names = [s.name for s in NEMO_SERVICES]
        assert "synthetic-data" in names
        assert "fine-tuning" in names
        assert "evaluation" in names
        assert "safety" in names
        assert "guardrails" in names
        assert "dataprep" in names
        assert "inference" in names
        assert "customizer" in names


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
class TestNeMoHealth:
    def test_unconfigured_health(self):
        config = NeMoConfig()
        health = nemo_health_probe(config=config)
        from providers.health import HealthStatus
        assert health.status == HealthStatus.UNCONFIGURED

    def test_health_with_mock_client(self):
        from providers.health import HealthStatus

        class MockResp:
            status_code = 200
            text = "ok"

        class MockClient:
            def sync_get(self, url, timeout=None):
                return MockResp()

        config = NeMoConfig(api_key="test-key", endpoint="https://test.nemo.com/v1")
        health = nemo_health_probe(http_client=MockClient(), config=config)
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms >= 0

    def test_health_no_client(self):
        from providers.health import HealthStatus
        config = NeMoConfig(api_key="test-key", endpoint="https://test.nemo.com/v1")
        health = nemo_health_probe(http_client=None, config=config)
        assert health.status == HealthStatus.OFFLINE


# --------------------------------------------------------------------------- #
# Client — unconfigured behavior
# --------------------------------------------------------------------------- #
class TestNeMoClientUnconfigured:
    def test_unconfigured_client(self):
        client = NeMoClient()
        assert not client.configured

    def test_methods_require_configured(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.synthetic_data.generate(
                model="x", prompt="y", num_samples=1
            ))

    def test_fine_tuning_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.fine_tuning.start(
                base_model="x", training_data="y"
            ))

    def test_evaluation_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.evaluation.run(
                model="x", benchmark="y"
            ))

    def test_safety_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.safety.check(text="hello"))

    def test_guardrails_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.guardrails.apply(
                request={"prompt": "hello"}
            ))

    def test_dataprep_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.dataprep.prepare(
                source_uri="s3://bucket/data.jsonl"
            ))

    def test_inference_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.inference.infer(
                model="x", prompt="y"
            ))

    def test_customizer_requires_config(self):
        client = NeMoClient()
        with pytest.raises(NeMoUnconfigured):
            import asyncio
            asyncio.run(client.customizer.customize(
                model="x", dataset="y"
            ))


# --------------------------------------------------------------------------- #
# Client — configured with mock HTTP
# --------------------------------------------------------------------------- #
class _MockResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text
        self.content = json_data  # truthy when there's content

    def json(self):
        return self._json


class _MockHttpClient:
    """Records requests and returns canned responses."""

    def __init__(self, default_json=None, default_status=200):
        self.requests: list[tuple[str, str, dict]] = []
        self.default_json = default_json or {}
        self.default_status = default_status

    async def request(self, method, url, headers=None, json=None, timeout=None):
        self.requests.append((method, url, json or {}))
        if self.default_status >= 400:
            return _MockResponse(self.default_status, text="error")
        return _MockResponse(self.default_status, self.default_json)

    async def get(self, url, headers=None, timeout=None):
        self.requests.append(("GET", url, {}))
        return _MockResponse(self.default_status, self.default_json)


class TestNeMoClientConfigured:
    def _make_client(self, mock_http=None, default_json=None, default_status=200):
        sm = SecretManager()
        sm.put("JARVIS_NEMO_API_KEY", "test-key")
        config = NeMoConfig.from_environ(secrets=sm)
        client = NeMoClient(config=config, http_client=mock_http or _MockHttpClient(
            default_json=default_json or {"ok": True},
            default_status=default_status,
        ))
        return client

    def test_configured(self):
        client = self._make_client()
        assert client.configured

    def test_service_properties(self):
        client = self._make_client()
        assert client.synthetic_data is not None
        assert client.fine_tuning is not None
        assert client.evaluation is not None
        assert client.safety is not None
        assert client.guardrails is not None
        assert client.dataprep is not None
        assert client.inference is not None
        assert client.customizer is not None

    def test_service_available_flags(self):
        client = self._make_client()
        assert client.synthetic_data.available is True
        assert client.fine_tuning.available is True
        assert client.evaluation.available is True
        assert client.safety.available is True
        assert client.guardrails.available is True
        assert client.dataprep.available is True
        assert client.inference.available is True
        assert client.customizer.available is True

    def test_synthetic_data_generate(self):
        client = self._make_client(
            default_json={"samples": [{"text": "example"}]},
        )
        mock = client._http_client
        import asyncio
        result = asyncio.run(client.synthetic_data.generate(
            model="nvidia/nemo-llm", prompt="generate QA",
            num_samples=50, temperature=0.7,
        ))
        assert result["samples"] == [{"text": "example"}]
        assert len(mock.requests) == 1
        method, url, body = mock.requests[0]
        assert method == "POST"
        assert "/v1/synthetic-data/generate" in url
        assert body["model"] == "nvidia/nemo-llm"
        assert body["num_samples"] == 50
        assert body["temperature"] == 0.7

    def test_synthetic_data_augment(self):
        client = self._make_client()
        mock = client._http_client
        import asyncio
        asyncio.run(client.synthetic_data.augment(
            dataset_id="ds-1", num_samples=10, strategy="paraphrase",
        ))
        assert len(mock.requests) == 1
        method, url, body = mock.requests[0]
        assert "/v1/synthetic-data/augment" in url
        assert body["dataset_id"] == "ds-1"
        assert body["num_samples"] == 10

    def test_fine_tuning_start(self):
        client = self._make_client(default_json={"job_id": "ft-1"})
        mock = client._http_client
        import asyncio
        result = asyncio.run(client.fine_tuning.start(
            base_model="llama-2", training_data="s3://data/train.jsonl",
            epochs=3, learning_rate=3e-5,
        ))
        assert result["job_id"] == "ft-1"
        assert len(mock.requests) == 1
        method, url, body = mock.requests[0]
        assert "/v1/fine-tuning/start" in url
        assert body["base_model"] == "llama-2"
        assert body["epochs"] == 3

    def test_fine_tuning_status(self):
        client = self._make_client(
            default_json={"status": "completed", "progress": 1.0},
        )
        import asyncio
        status = asyncio.run(client.fine_tuning.status("ft-1"))
        assert status.status == "completed"
        assert status.progress == 1.0
        assert status.is_terminal is True

    def test_fine_tuning_stop(self):
        client = self._make_client(default_json={"stopped": True})
        import asyncio
        asyncio.run(client.fine_tuning.stop("ft-1"))
        mock = client._http_client
        method, url, _ = mock.requests[-1]
        assert "/v1/fine-tuning/ft-1/stop" in url

    def test_evaluation_run(self):
        client = self._make_client(default_json={"eval_id": "eval-1", "score": 0.95})
        import asyncio
        result = asyncio.run(client.evaluation.run(
            model="rev-1", benchmark="mmlu", dataset="mmlu-v1",
        ))
        assert result["eval_id"] == "eval-1"
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/evaluation/run" in url
        assert body["benchmark"] == "mmlu"

    def test_evaluation_results(self):
        client = self._make_client(default_json={"accuracy": 0.92})
        import asyncio
        result = asyncio.run(client.evaluation.results("eval-1"))
        assert result["accuracy"] == 0.92

    def test_safety_check(self):
        client = self._make_client(default_json={"safe": True})
        import asyncio
        result = asyncio.run(client.safety.check(
            text="Hello world", model="nvidia/safety-llama",
        ))
        assert result["safe"] is True
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/safety/check" in url
        assert body["text"] == "Hello world"

    def test_safety_audit(self):
        client = self._make_client(default_json={"issues": []})
        import asyncio
        asyncio.run(client.safety.audit(dataset_id="ds-1"))
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/safety/audit" in url
        assert body["dataset_id"] == "ds-1"

    def test_guardrails_apply(self):
        client = self._make_client(default_json={"blocked": False})
        import asyncio
        asyncio.run(client.guardrails.apply(
            request={"prompt": "hello"}, guardrail_configs=["config-1"],
        ))
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/guardrails/apply" in url
        assert body["guardrail_configs"] == ["config-1"]

    def test_guardrails_list(self):
        client = self._make_client(default_json={"guardrails": ["g1"]})
        import asyncio
        result = asyncio.run(client.guardrails.list())
        assert result["guardrails"] == ["g1"]
        mock = client._http_client
        method, url, _ = mock.requests[0]
        assert "/v1/guardrails" in url

    def test_dataprep_prepare(self):
        client = self._make_client(default_json={"job_id": "dp-1"})
        import asyncio
        result = asyncio.run(client.dataprep.prepare(
            source_uri="s3://bucket/data.jsonl", job_type="pretrain",
        ))
        assert result["job_id"] == "dp-1"
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/dataprep/prepare" in url
        assert body["source_uri"] == "s3://bucket/data.jsonl"

    def test_dataprep_validate(self):
        client = self._make_client(default_json={"valid": True})
        import asyncio
        asyncio.run(client.dataprep.validate(dataset_id="ds-1"))
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/dataprep/validate" in url

    def test_dataprep_split(self):
        client = self._make_client(default_json={"split": "done"})
        import asyncio
        asyncio.run(client.dataprep.split(
            dataset_id="ds-1", train_ratio=0.7, val_ratio=0.2, test_ratio=0.1,
        ))
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/dataprep/split" in url
        assert body["train_ratio"] == 0.7

    def test_dataprep_status(self):
        client = self._make_client(
            default_json={"status": "running", "progress": 0.5},
        )
        import asyncio
        status = asyncio.run(client.dataprep.status("dp-1"))
        assert status.status == "running"
        assert status.progress == 0.5

    def test_inference_infer(self):
        client = self._make_client(default_json={"text": "Hello from NeMo"})
        import asyncio
        result = asyncio.run(client.inference.infer(
            model="nvidia/nemo-llm", prompt="Hello", temperature=0.5,
        ))
        assert result["text"] == "Hello from NeMo"
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/inference/infer" in url
        assert body["prompt"] == "Hello"

    def test_inference_deploy(self):
        client = self._make_client(default_json={"deployment_id": "dep-1"})
        import asyncio
        result = asyncio.run(client.inference.deploy(
            model="nvidia/nemo-llm", num_gpus=2,
        ))
        assert result["deployment_id"] == "dep-1"
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/inference/deploy" in url
        assert body["num_gpus"] == 2

    def test_inference_status(self):
        client = self._make_client(
            default_json={"status": "ready", "progress": 1.0},
        )
        import asyncio
        status = asyncio.run(client.inference.status("dep-1"))
        assert status.status == "ready"

    def test_customizer_customize(self):
        client = self._make_client(default_json={"job_id": "cust-1"})
        import asyncio
        result = asyncio.run(client.customizer.customize(
            model="nvidia/nemo-llm", dataset="ds-1",
        ))
        assert result["job_id"] == "cust-1"
        mock = client._http_client
        method, url, body = mock.requests[0]
        assert "/v1/customizer/customize" in url

    def test_customizer_status(self):
        client = self._make_client(
            default_json={"status": "completed", "progress": 1.0},
        )
        import asyncio
        status = asyncio.run(client.customizer.status("cust-1"))
        assert status.status == "completed"
        assert status.is_terminal is True

    def test_http_error_raises(self):
        client = self._make_client(default_status=500, default_json={})
        import asyncio
        with pytest.raises(NeMoRequestError):
            asyncio.run(client.synthetic_data.generate(
                model="x", prompt="y", num_samples=1,
            ))

    def test_job_status_terminal(self):
        s = NeMoJobStatus(job_id="1", status="completed", progress=1.0)
        assert s.is_terminal is True
        s2 = NeMoJobStatus(job_id="1", status="running", progress=0.5)
        assert s2.is_terminal is False

    def test_ne_error_is_base(self):
        assert issubclass(NeMoUnconfigured, NemError)
        assert issubclass(NeMoRequestError, NemError)
