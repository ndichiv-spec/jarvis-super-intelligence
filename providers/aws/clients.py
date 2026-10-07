"""boto3-backed client seam for the AWS Bedrock adapter.

Encapsulates the parts of boto3 we use so the adapter is unit-testable with an
injected fake and so boto3 stays an optional dependency (import failure or missing
region => ProviderUnconfigured, never a crash).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from ..errors import ProviderAuthenticationError, ProviderUnconfigured, ProviderUnavailable


class BedrockClients:
    def __init__(
        self,
        region: Optional[str],
        access_mode: str = "env",
        profile: Optional[str] = None,
    ) -> None:
        if not region:
            raise ProviderUnconfigured("aws: no region configured (JARVIS_AWS_REGION)")
        try:
            import boto3
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ProviderUnconfigured(f"aws: boto3 not importable ({exc})") from exc

        kwargs: dict[str, Any] = {}
        if access_mode == "profile":
            kwargs["profile_name"] = profile or region
        try:
            self._session = boto3.Session(region_name=region, **kwargs)
            self._bedrock = self._session.client("bedrock", region_name=region)
            self._runtime = self._session.client("bedrock-runtime", region_name=region)
        except Exception as exc:
            raise ProviderUnconfigured(f"aws: boto3 session init failed ({exc})") from exc

    def list_models(self) -> List[str]:
        try:
            resp = self._bedrock.list_foundation_models()
        except Exception as exc:
            raise _classify_aws_error(exc)
        summary = resp.get("modelSummaries") or []
        return [str(m.get("modelId", "")) for m in summary if m.get("modelId")]

    def converse(
        self,
        *,
        model: str,
        system: List[str],
        messages: List[dict],
        tools: Optional[List[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        body: dict[str, Any] = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {},
        }
        if system:
            body["system"] = [{"text": text} for text in system]
        if temperature is not None:
            body["inferenceConfig"]["temperature"] = temperature
        if max_tokens is not None:
            body["inferenceConfig"]["maxTokens"] = max_tokens
        if tools:
            body["toolConfig"] = {"tools": tools}
        try:
            return self._runtime.converse(**body)
        except Exception as exc:
            raise _classify_aws_error(exc)

    def converse_stream(
        self,
        *,
        model: str,
        system: List[str],
        messages: List[dict],
        tools: Optional[List[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[Dict]:
        body: dict[str, Any] = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {},
        }
        if system:
            body["system"] = [{"text": text} for text in system]
        if temperature is not None:
            body["inferenceConfig"]["temperature"] = temperature
        if max_tokens is not None:
            body["inferenceConfig"]["maxTokens"] = max_tokens
        if tools:
            body["toolConfig"] = {"tools": tools}
        try:
            stream = self._runtime.converse_stream(**body)
        except Exception as exc:
            raise _classify_aws_error(exc)
        for chunk in stream.get("stream", []):
            yield chunk

    def invoke_embedding(self, *, model: str, input_texts: List[str]) -> List[List[float]]:
        body = json.dumps({"inputText": input_texts})
        try:
            resp = self._runtime.invoke_model(modelId=model, body=body)
        except Exception as exc:
            raise _classify_aws_error(exc)
        payload = json.loads(resp["body"].read().decode("utf-8", "replace"))
        results = payload.get("embeddings") or [payload.get("embedding")] or []
        out: List[List[float]] = []
        for item in results:
            if isinstance(item, dict):
                item = item.get("embedding", [])
            out.append([float(v) for v in (item or [])])
        return out


def _classify_aws_error(exc: Exception):
    message = str(exc)
    lowered = message.lower()
    if any(k in lowered for k in ("unauthorized", "accessdenied", "access denied", "not authorized", "credential")):
        return ProviderAuthenticationError(f"aws: {message[:200]}")
    return ProviderUnavailable(f"aws: {message[:200]}")