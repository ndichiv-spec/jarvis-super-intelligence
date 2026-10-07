"""Remote inference backend for the JARVIS Brain runtime.

When ``JARVIS_BRAIN_BACKEND=remote``, the Brain runtime forwards inference
requests to an OpenAI-compatible endpoint (e.g. a Hugging Face Inference
Endpoint) over HTTPS.  The local JARVIS host never downloads model weights;
it delegates generation to the remote provider and normalizes the response
into the same :class:`~brain_runtime.generation.BrainResult` contract used
by the local and stub backends.

Credential separation (spec section 5):
    * ``JARVIS_BRAIN_API_KEY`` authenticates the browser -> JARVIS path
      (the platform never sees this key).
    * ``JARVIS_BRAIN_REMOTE_API_KEY`` authenticates the Brain -> remote
      provider path (sent as ``Authorization: Bearer <remote_api_key>`` to
      the endpoint).  Neither key is ever returned in API responses.

The remote backend is provider-agnostic: any OpenAI-compatible endpoint
serves, with Hugging Face Inference Endpoints as the primary target.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from brain_runtime.backends.base import BrainBackend
from brain_runtime.generation import BrainGenerationConfig, BrainResult

if TYPE_CHECKING:
    import httpx  # noqa: F401 - only for type hints at runtime

# NVIDIA-hosted inference continues to provide the OpenAI-compatible surface
# but must be identified as ``nvidia`` (not the HF default) in reports.
_NVIDIA_HOSTS = ("integrate.api.nvidia.com", "nvcf.nvidia.com", "nim.nvidia.com")


def _is_nvidia_endpoint(endpoint: str) -> bool:
    return any(host in endpoint for host in _NVIDIA_HOSTS)


def _default_remote_model(endpoint: str) -> str:
    """Endpoint-appropriate default model id when none is configured."""
    if _is_nvidia_endpoint(endpoint):
        return "nvidia/nemotron-3-ultra-550b-a55b"
    return "jarvis-brain-qwen3-4b-v1"


class RemoteBrainError(RuntimeError):
    """Raised when the remote backend cannot complete a request."""


class RemoteBrainBackend(BrainBackend):
    """Delegates generation to an OpenAI-compatible remote endpoint.

    Parameters
    ----------
    endpoint
        Base URL of the remote inference endpoint, with ``/v1`` appended by
        this backend if not already present.  E.g.
        ``https://api-inference-hub.example.com/v1``.
    api_key
        Bearer token sent to the remote provider as
        ``Authorization: Bearer <api_key>``.  Distinct from the inbound
        ``JARVIS_BRAIN_API_KEY``.
    model
        Model identifier passed to the remote provider in chat/generate
        payloads.
    timeout
        Per-request timeout in seconds for remote inference.
    retries
        Bounded retries for transient upstream failures (404/429/5xx/timeouts)
        so a cold-starting hosted provider does not flap warmup/health.
    """

    def __init__(
        self,
        endpoint: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 120.0,
        retries: int = 0,
        *,
        stream: bool = True,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") if endpoint else ""
        if self._endpoint and not self._endpoint.endswith("/v1"):
            self._endpoint = self._endpoint + "/v1"
        self._api_key = api_key
        self.model_id = model or _default_remote_model(self._endpoint)
        self.provider = "nvidia" if _is_nvidia_endpoint(self._endpoint) else "hf-inference"
        self._timeout = timeout
        self._retries = max(0, int(retries))
        self.revision = "remote"
        self.backend = "remote"
        self.device = "remote-inference"
        self.parameters = 0  # not reported by the remote endpoint
        self.loaded = False
        self._client: Any = None  # lazy httpx.Client
        self._warmup_done = False
        # Real providers (NVIDIA NIM, Hugging Face Inference Endpoints) both
        # speak OpenAI-style server-sent-event streaming.  When False (e.g. a
        # non-streaming proxy), the server falls back to a single-content chunk.
        self.stream_support = bool(stream) and True

    @staticmethod
    def _sleep_seconds(attempt: int) -> None:
        """Short bounded backoff between retries (never blocks the event loop
        of the caller for long; attempts are expected to be rare)."""
        import time as _t

        _t.sleep(min(0.5 * (attempt + 1), 3.0))

    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _new_client(self) -> Any:
        """Create a real httpx.Client (lazy import to keep test import cheap)."""
        import httpx

        return httpx.Client(timeout=self._timeout)

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        """Validate connectivity to the remote endpoint (no weight download).

        Raises :class:`RemoteBrainError` if the endpoint is unreachable, if
        authentication fails, or if the configured model is not available at
        the remote provider.  No local weights are downloaded.
        """
        if not self._endpoint:
            raise RemoteBrainError("JARVIS_BRAIN_REMOTE_ENDPOINT is not configured")
        self._check_endpoint()
        if self._client is None:
            self._client = self._new_client()
        self.loaded = True

    def warmup(self, prompt: str) -> str:
        """Run a tiny remote generation to confirm the endpoint is usable."""
        if not self.loaded:
            self.load()
        cfg = BrainGenerationConfig(model=self.model_id, max_tokens=16, temperature=0.0)
        result = self.generate([{"role": "user", "content": prompt}], cfg)
        self._warmup_done = True
        return result.text

    # ------------------------------------------------------------------ #
    def _check_endpoint(self) -> None:
        """Probe ``GET /v1/models`` to verify reachability + auth + model."""
        if self._client is None:
            self._client = self._new_client()
        try:
            resp = self._client.get(
                f"{self._endpoint}/models",
                headers=self._headers(),
            )
        except Exception as exc:
            exc_name = type(exc).__name__
            if "Timeout" in exc_name:
                raise RemoteBrainError(f"endpoint unreachable (timeout): {exc_name}") from exc
            raise RemoteBrainError(f"endpoint unreachable ({exc_name})") from exc

        if resp.status_code == 401:
            raise RemoteBrainError("authentication failed (401) — check JARVIS_BRAIN_REMOTE_API_KEY")
        if resp.status_code == 403:
            raise RemoteBrainError("forbidden (403) — check remote API key scopes")
        if resp.status_code != 200:
            raise RemoteBrainError(f"endpoint returned HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise RemoteBrainError("invalid JSON from remote /v1/models") from exc

        remote_models = []
        for entry in data.get("data", []):
            if isinstance(entry, dict):
                remote_models.append(entry.get("id", ""))
        if remote_models and self.model_id not in remote_models:
            raise RemoteBrainError(
                f"remote model {self.model_id!r} not found in endpoint model list "
                f"(available: {', '.join(remote_models[:5])})"
            )

    # ------------------------------------------------------------------ #
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            self._client = self._new_client()
        last: RemoteBrainError | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.post(
                    f"{self._endpoint}{path}",
                    headers=self._headers(),
                    json=body,
                )
            except Exception as exc:  # noqa: BLE001 - transport errors
                exc_name = type(exc).__name__
                if "Timeout" in exc_name:
                    last = RemoteBrainError(f"request timed out ({exc_name})")
                else:
                    last = RemoteBrainError(f"request failed ({exc_name})")
                if attempt < self._retries and ("Timeout" in exc_name or "Connect" in exc_name):
                    self._sleep_seconds(attempt)
                    continue
                raise last
            if resp.status_code == 401:
                raise RemoteBrainError("authentication failed (401) — check JARVIS_BRAIN_REMOTE_API_KEY")
            if resp.status_code in (404, 429) or resp.status_code >= 500:
                # Transient upstream failure (hosted providers cold-start /
                # throttle): retry up to the bounded limit; otherwise surface
                # the real code so configuration problems stay visible.
                if attempt < self._retries:
                    self._sleep_seconds(attempt)
                    continue
                raise RemoteBrainError(f"remote inference returned HTTP {resp.status_code}")
            if resp.status_code != 200:
                raise RemoteBrainError(f"remote inference returned HTTP {resp.status_code}")

            try:
                return resp.json()
            except ValueError as exc:
                raise RemoteBrainError("invalid JSON response from remote endpoint") from exc
        assert last is not None  # unreachable (loop always raises or returns)
        raise last

    def generate(self, messages: list[dict], configuration: BrainGenerationConfig) -> BrainResult:
        """Send a chat completion request to the remote OpenAI-compatible endpoint."""
        if not self.loaded:
            raise RuntimeError("Brain remote backend is not loaded")

        body: dict[str, Any] = {
            "model": configuration.model or self.model_id,
            "messages": messages,
            "temperature": configuration.temperature,
            "max_tokens": configuration.max_tokens,
            "top_p": configuration.top_p,
            "stream": False,
        }
        if configuration.top_k is not None:
            body["top_k"] = configuration.top_k
        if configuration.repetition_penalty != 1.0:
            body["repetition_penalty"] = configuration.repetition_penalty

        start = time.monotonic()
        data = self._post("/chat/completions", body)
        latency_ms = round((time.monotonic() - start) * 1000, 2)

        # Parse the OpenAI-compatible chat completion response.
        choices = data.get("choices", [])
        if not choices:
            raise RemoteBrainError("remote returned an empty response")

        first = choices[0]
        message = first.get("message", {})
        content = message.get("content", "") or ""

        # Honesty guard: empty content is never a real answer.
        if not content.strip():
            raise RemoteBrainError("remote returned an empty response")

        usage = data.get("usage", {}) or {}

        # Provider metadata from the remote response (normalized, never fabricated).
        remote_model = data.get("model", configuration.model or self.model_id)
        if data.get("provider") or data.get("backend"):
            provider = data.get("provider") or data.get("backend")
        elif _is_nvidia_endpoint(self._endpoint):
            provider = "nvidia"
        else:
            provider = "hf-inference"

        in_tokens = usage.get("prompt_tokens", 0) if usage else 0
        out_tokens = usage.get("completion_tokens", 0) if usage else 0

        return BrainResult(
            text=content,
            model=remote_model,
            revision=self.revision,
            finish_reason=first.get("finish_reason", "stop"),
            tokens_input=in_tokens or 0,
            tokens_generated=out_tokens or 0,
            latency_ms=latency_ms,
            device=self.device,
            backend=self.backend,
            metadata={
                "backend": self.backend,
                "device": self.device,
                "provider": provider,
                "remote_model": remote_model,
                "endpoint": self._endpoint,
                "model": remote_model,
                "latency_ms": latency_ms,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        )

    # ------------------------------------------------------------------ #
    # Real token streaming (spec Part O)
    # ------------------------------------------------------------------ #
    def stream(
        self, messages: list[dict], configuration: BrainGenerationConfig
    ):
        """Stream OpenAI-compatible SSE ``chat.completion.chunk`` events.

        Each yielded value is a parsed chunk dict (the JSON object that appears
        after ``data:``).  The final ``data: [DONE]`` sentinel is *not* yielded;
        callers emit ``[DONE]`` themselves so the server controls the wire
        format.  Non-2xx responses surface as :class:`RemoteBrainError` so the
        service can mark the backend offline / trigger fallback honestly.
        """
        if not self.loaded:
            raise RuntimeError("Brain remote backend is not loaded")

        body: dict[str, Any] = {
            "model": configuration.model or self.model_id,
            "messages": messages,
            "temperature": configuration.temperature,
            "max_tokens": configuration.max_tokens,
            "top_p": configuration.top_p,
            "stream": True,
        }
        if configuration.top_k is not None:
            body["top_k"] = configuration.top_k
        if configuration.repetition_penalty != 1.0:
            body["repetition_penalty"] = configuration.repetition_penalty

        import json as _json

        if self._client is None:
            self._client = self._new_client()
        try:
            with self._client.stream(
                "POST",
                f"{self._endpoint}/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=self._timeout,
            ) as resp:
                if resp.status_code == 401:
                    raise RemoteBrainError(
                        "authentication failed (401) — check JARVIS_BRAIN_REMOTE_API_KEY"
                    )
                if resp.status_code != 200:
                    raise RemoteBrainError(
                        f"remote streaming returned HTTP {resp.status_code}"
                    )
                # The endpoint may stream SSE ``data:`` chunks, or (some proxies
                # ignore ``stream=True``) return a single complete chat.completion
                # JSON object.  We honor whichever the upstream actually sends.
                sse_found = False
                complete_parts: list[str] = []
                for raw in resp.iter_lines():
                    line = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        sse_found = True
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            yield _json.loads(payload)
                        except ValueError:
                            # Malformed SSE line: skip rather than kill the stream.
                            continue
                    else:
                        if not sse_found:
                            # Buffer a non-SSE body so a complete response can be
                            # replayed as a single content-bearing chunk below.
                            complete_parts.append(line)
                if not sse_found:
                    # Non-streaming upstream: replay the complete message content
                    # as one OpenAI-style delta chunk (honest: real content, just
                    # not token-by-token).  The server emits the stop chunk + DONE.
                    body_text = "\n".join(complete_parts).strip()
                    try:
                        data = _json.loads(body_text)
                    except ValueError as exc:
                        raise RemoteBrainError(
                            "invalid JSON from remote streaming endpoint"
                        ) from exc
                    content = ""
                    choices = data.get("choices", [])
                    if choices:
                        content = (
                            choices[0].get("message", {}).get("content", "")
                            or choices[0].get("delta", {}).get("content", "")
                            or ""
                        )
                    model = data.get("model", configuration.model or self.model_id)
                    yield {
                        "id": f"chatcmpl-stream",
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": None,
                            }
                        ],
                    }
        except RemoteBrainError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport/stream errors
            exc_name = type(exc).__name__
            if "Timeout" in exc_name:
                raise RemoteBrainError(f"stream timed out ({exc_name})") from exc
            raise RemoteBrainError(f"stream request failed ({exc_name})") from exc

    # ------------------------------------------------------------------ #
    def list_models(self) -> list[dict[str, Any]]:
        """Return the ``data`` array from remote ``GET /v1/models``."""
        if not self.loaded:
            self.load()
        data = self._post_raw("GET", "/models")
        return data.get("data", [])

    def _post_raw(self, method: str, path: str) -> dict[str, Any]:
        if self._client is None:
            self._client = self._new_client()
        try:
            if method == "GET":
                resp = self._client.get(f"{self._endpoint}{path}", headers=self._headers())
            else:
                raise ValueError(f"unsupported method {method}")
        except Exception as exc:
            exc_name = type(exc).__name__
            if "Timeout" in exc_name:
                raise RemoteBrainError(f"request timed out ({exc_name})") from exc
            raise RemoteBrainError(f"request failed ({exc_name})") from exc

        if resp.status_code != 200:
            raise RemoteBrainError(f"remote returned HTTP {resp.status_code}")
        return resp.json()

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - best effort
                pass
            self._client = None
        self.loaded = False

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass
