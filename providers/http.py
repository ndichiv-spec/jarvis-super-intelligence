"""Thin OpenAI-compatible HTTP client shared by the JARVIS Provider Fabric.

Most providers (OpenAI, NVIDIA NIM, Hugging Face Inference, Vertex OpenAI-compat,
vLLM/llama.cpp/Ollama) speak the same ``/v1/chat/completions`` surface. Rather than
duplicating JSON/SSE plumbing five times, adapters reuse this client and stay honest
about which endpoints they probe.

* uses ``requests`` when present, otherwise stdlib ``urllib``;
* auth header is attached only when an api key is configured;
* streaming returns decoded SSE ``data:`` JSON chunks;
* ``chat_completions`` never invents parameters the caller did not pass.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional

from .errors import (
    ProviderAuthenticationError,
    ProviderContractError,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
)

try:
    import requests

    _REQUESTS = True
except Exception:  # pragma: no cover - bare environment
    requests = None  # type: ignore[assignment]
    _REQUESTS = False


@dataclass
class HttpClientOptions:
    timeout: float = 60.0
    verify: bool = True
    headers: Mapping[str, str] = field(default_factory=dict)


class OpenAICompatibleClient:
    """Minimal client for OpenAI-style REST/SSE endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        options: Optional[HttpClientOptions] = None,
        extra_auth_header: str = "Authorization",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.options = options or HttpClientOptions()
        self._headers: dict[str, str] = dict(self.options.headers)
        self._headers.setdefault("Content-Type", "application/json")
        if api_key:
            self._headers[extra_auth_header] = f"Bearer {api_key}"

    def _url(self, path: str) -> str:
        # Base urls like "https://api.openai.com/v1" already carry the API
        # version segment; the shared request paths ("/v1/models", ...) repeat
        # it. Idempotently drop the duplicate so ".../v1" + "/v1/chat/..." does
        # not produce ".../v1/v1/chat/...". Bases without "/v1" are untouched.
        if path.startswith("/v1") and self.base_url.endswith("/v1") and len(self.base_url) > 3:
            path = path[3:] or "/"
        return self.base_url + ("/" if not path.startswith("/") else "") + path

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> tuple[int, dict]:
        """Return ``(status, parsed_json)``. Raises typed errors on failure."""
        t0 = time.monotonic()
        try:
            if _REQUESTS and requests is not None:
                resp = requests.request(
                    method,
                    self._url(path),
                    json=json_body,
                    params=params,
                    headers=self._headers,
                    timeout=timeout or self.options.timeout,
                    verify=self.options.verify,
                )
                status = resp.status_code
                body = resp.text or ""
            else:  # pragma: no cover - exercised only when requests is missing
                import urllib.error
                import urllib.request

                data = json.dumps(json_body).encode() if json_body is not None else None
                req = urllib.request.Request(
                    self._url(path),
                    data=data,
                    headers=self._headers,
                    method=method,
                )
                try:
                    with urllib.request.urlopen(
                        req, timeout=timeout or self.options.timeout
                    ) as resp:
                        status = resp.status
                        body = resp.read().decode("utf-8", "replace")
                except urllib.error.HTTPError as err:
                    status = err.code
                    try:
                        body = err.read().decode("utf-8", "replace")
                    except Exception:  # pragma: no cover
                        body = ""
        except Exception as exc:  # network-level
            raise ProviderUnavailable(
                f"{method} {path} failed: {exc.__class__.__name__}"
            ) from exc

        if status in (401, 403):
            raise ProviderAuthenticationError(
                f"{method} {path} -> HTTP {status} (credentials rejected)"
            )
        if status >= 500:
            raise ProviderUnavailable(
                f"{method} {path} -> HTTP {status}: {body[:200]}"
            )
        if status >= 400:
            raise ProviderContractError(
                f"{method} {path} -> HTTP {status}: {body[:200]}"
            )
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ProviderContractError(
                f"{method} {path} -> non-JSON body ({status})"
            ) from exc
        return status, parsed

    # -- provider surfaces ------------------------------------------------
    def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        _, body = self.request("GET", path, params=params)
        return body

    def post_json(self, path: str, body: dict) -> dict:
        _, parsed = self.request("POST", path, json_body=body)
        return parsed

    def list_models(self) -> list[str]:
        """``GET /v1/models`` -> model ids. ``[]`` when the endpoint is missing."""
        try:
            _, body = self.request("GET", "/v1/models")
        except (ProviderUnavailable, ProviderAuthenticationError, ProviderContractError):
            return []
        data = body.get("data", body.get("models", []))
        if not isinstance(data, list):
            return []
        ids: list[str] = []
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.append(item["id"])
            elif isinstance(item, str):
                ids.append(item)
        return ids

    # -- chat/completions ---------------------------------------------------
    def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict],
        stream: bool = False,
        tools: Optional[list[dict]] = None,
        response_format: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if tools:
            body["tools"] = tools
        if response_format is not None:
            body["response_format"] = response_format
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if extra:
            body.update(extra)
        _, parsed = self.request("POST", "/v1/chat/completions", json_body=body)
        return parsed

    def stream_chat_completions(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        response_format: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> Iterator[dict]:
        """Iterate parsed SSE ``data:`` objects from a streamed completion."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            # Without this, OpenAI-compatible endpoints omit the usage block from
            # the stream, so streamed calls report zero tokens and silently
            # under-report real spend. Callers can override via ``extra``.
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = tools
        if response_format is not None:
            body["response_format"] = response_format
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if extra:
            body.update(extra)
        t0 = time.monotonic()
        try:
            if _REQUESTS and requests is not None:
                with requests.post(
                    self._url("/v1/chat/completions"),
                    json=body,
                    headers=self._headers,
                    timeout=self.options.timeout,
                    stream=True,
                    verify=self.options.verify,
                ) as resp:
                    if resp.status_code >= 400:
                        raise ProviderContractError(
                            f"stream -> HTTP {resp.status_code}"
                        )
                    yield from _iter_sse_lines(resp.iter_lines(decode_unicode=True))
            else:  # pragma: no cover - bare environment
                raise ProviderUnavailable("requests library not installed")
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailable(f"stream failed: {exc.__class__.__name__}") from exc


def _iter_sse_lines(lines) -> Iterator[dict]:
    for line in lines:
        if not line:
            continue
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            break
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue