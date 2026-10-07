"""Thin wrapper over ``google.genai`` for the Google provider adapter.

Kept behind one seam so the adapter is unit-testable with a fake object and so the
SDK stays an optional dependency (import failure => ProviderUnconfigured rather
than a crash).
"""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Sequence

from ..errors import ProviderAuthenticationError, ProviderUnconfigured, ProviderUnavailable


class GoogleModelsAPI:
    """Minimal, stable projection of the parts of google.genai we use."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
    ) -> None:
        from google import genai  # lazy, optional dependency

        if api_key:
            self._client = genai.Client(api_key=api_key)
        elif project and location:
            self._client = genai.Client(vertexai=True, project=project, location=location)
        else:
            raise ProviderUnconfigured(
                "google.genai needs an api_key or vertex project+location"
            )
        self._genai = genai

    @property
    def client(self) -> Any:
        return self._client

    def generate_content(
        self,
        model: str,
        contents: List[dict],
        *,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Any] = None,
    ) -> Any:
        config: dict = {}
        if system_instruction:
            config["system_instruction"] = system_instruction
        if temperature is not None:
            config["temperature"] = temperature
        if max_output_tokens is not None:
            config["max_output_tokens"] = max_output_tokens
        if response_mime_type:
            config["response_mime_type"] = response_mime_type
        if response_schema is not None:
            config["response_schema"] = response_schema
        from google.genai import types as gntypes

        return self._client.models.generate_content(
            model=model,
            contents=contents,
            config=gntypes.GenerateContentConfig(**config) if config else None,
        )

    def generate_content_stream(
        self,
        model: str,
        contents: List[dict],
        *,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Iterator[Any]:
        from google.genai import types as gntypes

        config: dict = {}
        if system_instruction:
            config["system_instruction"] = system_instruction
        if temperature is not None:
            config["temperature"] = temperature
        if max_output_tokens is not None:
            config["max_output_tokens"] = max_output_tokens
        return self._client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=gntypes.GenerateContentConfig(**config) if config else None,
        )  # type: ignore[return-value]

    def list_models(self) -> List[str]:
        try:
            iterator = self._client.models.list()
            names: List[str] = []
            for item in iterator:
                page_items = getattr(item, "items", None)
                if page_items is not None:
                    for m in page_items:
                        name = getattr(m, "name", None)
                        if name:
                            names.append(name)
                else:
                    name = getattr(item, "name", None)
                    if name:
                        names.append(name)
            return names
        except Exception as exc:
            message = str(exc)
            if "permission" in message.lower() or "401" in message or "403" in message:
                raise ProviderAuthenticationError(f"google.genai models.list: {message}") from exc
            raise ProviderUnavailable(f"google.genai models.list: {message}") from exc

    def embed_content(
        self, model: str, contents: Sequence[str]
    ) -> List[List[float]]:
        from google.genai import types as gntypes

        result = self._client.models.embed_content(
            model=model,
            contents=[gntypes.Content(parts=[gntypes.Part(text=t)]) for t in contents],
        )
        embeddings = result or []
        return [[float(v) for v in emb.values] for emb in (embeddings or [])]