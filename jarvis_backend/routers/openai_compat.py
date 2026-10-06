"""OpenAI-compatible core API endpoints for JARVIS Phase 36."""
# ruff: noqa: B008

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import struct
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from infrastructure.model_registry import model_registry
from infrastructure.job_registry import JobInfo, JobRegistry, JobType
from infrastructure.artifact_registry import get_artifact_registry

from ..capabilities.voice import VoiceCapability
from ..capability import ExecutionContext
from ..core import (
    UPLOADS_DIR,
    _api_key_principal,
    find_api_key,
    get_current_user,
    get_store,
    is_api_key_expired,
)
from ..embeddings import _tokenize, embed_text
from ..errors import ChatError
from ..gateway import provider_gateway
from .media import ImageGenerateIn, image_generate


def _error_type(status_code: int) -> str:
    if status_code == 401:
        return "authentication_error"
    if status_code == 403:
        return "permission_error"
    if status_code == 429:
        return "rate_limit_error"
    if status_code >= 500:
        return "server_error"
    return "invalid_request_error"


def _error_body(message: str, status_code: int, code: str | None = None) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": _error_type(status_code),
            "param": None,
            "code": code,
        }
    }


class OpenAICompatRoute(APIRoute):
    """Translate FastAPI validation/auth errors into OpenAI error envelopes."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original_handler(request)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
                return JSONResponse(
                    status_code=exc.status_code,
                    content=_error_body(detail, exc.status_code),
                    headers={
                        **(exc.headers or {}),
                        "Jarvis-Version": "1",
                        "X-Request-ID": (request.headers.get("x-request-id") or str(uuid.uuid4())),
                    },
                )
            except RequestValidationError as exc:
                errors = [
                    {
                        "loc": [str(part) for part in error.get("loc", ())],
                        "msg": error.get("msg", "Invalid value"),
                        "type": error.get("type", "value_error"),
                    }
                    for error in exc.errors()
                ]
                return JSONResponse(
                    status_code=400,
                    content=_error_body(
                        "; ".join(f"{'.'.join(error['loc'])}: {error['msg']}" for error in errors),
                        400,
                        "invalid_request",
                    ),
                    headers={
                        "Jarvis-Version": "1",
                        "X-Request-ID": (request.headers.get("x-request-id") or str(uuid.uuid4())),
                    },
                )

        return handler


router = APIRouter(
    tags=["OpenAI-compatible API"],
    route_class=OpenAICompatRoute,
)


def _set_compat_headers(response: Response, request: Request) -> None:
    response.headers["Jarvis-Version"] = "1"
    response.headers["X-Request-ID"] = request.headers.get("x-request-id") or str(uuid.uuid4())


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    class Config:
        extra = "forbid"


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None
    n: int = 1
    user: str | None = None
    response_format: dict[str, Any] | None = None
    stream_options: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None

    class Config:
        extra = "forbid"


class TextCompletionRequest(BaseModel):
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    user: str | None = None

    class Config:
        extra = "forbid"


class EmbeddingsRequest(BaseModel):
    model: str = Field(min_length=1)
    input: str | list[str]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: int | None = None
    user: str | None = None

    class Config:
        extra = "forbid"


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: str | None = None
    n: int = Field(default=1, ge=1, le=4)
    size: Literal["256x256", "512x512", "1024x1024"] = "1024x1024"
    response_format: Literal["url", "b64_json"] = "url"
    quality: Literal["standard", "hd"] = "standard"
    user: str | None = None

    class Config:
        extra = "forbid"


class SpeechRequest(BaseModel):
    model: Literal["tts-1"] = "tts-1"
    input: str = Field(min_length=1, max_length=4096)
    voice: Literal["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"] = (
        "nova"
    )
    response_format: Literal["mp3"] = "mp3"

    class Config:
        extra = "forbid"


class ModerationRequest(BaseModel):
    input: str | list[str]
    model: str = "omni-moderation-latest"

    class Config:
        extra = "forbid"


class TokenCountRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(min_length=1)

    class Config:
        extra = "forbid"


class AnthropicTokenCountRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(min_length=1)
    system: str | list[dict[str, Any]] | None = None

    class Config:
        extra = "forbid"


class FineTuningCreateRequest(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    training_file: str = Field(min_length=1)
    validation_file: str | None = None
    suffix: str | None = Field(default=None, max_length=64)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class BatchCreateRequest(BaseModel):
    input_file_id: str = Field(min_length=1)
    endpoint: Literal["/v1/chat/completions", "/v1/embeddings"]
    completion_window: Literal["24h"] = "24h"
    metadata: dict[str, str] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


def _validate_chat_options(body: ChatCompletionRequest) -> None:
    unsupported = {
        "temperature": body.temperature,
        "top_p": body.top_p,
        "max_tokens": body.max_tokens,
        "max_completion_tokens": body.max_completion_tokens,
        "frequency_penalty": body.frequency_penalty,
        "presence_penalty": body.presence_penalty,
        "stop": body.stop,
    }
    supplied = [name for name, value in unsupported.items() if value is not None]
    if body.n != 1:
        supplied.append("n")
    response_format_type = (body.response_format or {}).get("type", "text")
    if response_format_type not in {"text", "json_object", "json_schema"}:
        supplied.append("response_format")
    if body.response_format and response_format_type == "json_schema":
        schema_block = body.response_format.get("json_schema")
        if not isinstance(schema_block, dict) or not isinstance(schema_block.get("schema"), dict):
            supplied.append("response_format.json_schema.schema")
    if body.tools:
        supplied.append("tools (provider tool-call execution is not enabled)")
    if body.tool_choice not in (None, "auto"):
        supplied.append("tool_choice")
    if body.stream_options and set(body.stream_options) - {"include_usage"}:
        supplied.append("stream_options")
    if supplied:
        raise HTTPException(
            status_code=400,
            detail=(
                "This JARVIS endpoint does not support these options yet: " + ", ".join(supplied)
            ),
        )


def _actual_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    if prompt is None or completion is None:
        return None
    try:
        prompt_tokens = int(prompt)
        completion_tokens = int(completion)
    except (TypeError, ValueError):
        return None
    if prompt_tokens < 0 or completion_tokens < 0:
        return None
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _openai_chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _stream_error(exc: ChatError) -> str:
    status_code = getattr(exc, "status_code", 502)
    body = _error_body(
        getattr(exc, "safe_message", "The model provider could not complete the request."),
        status_code,
        getattr(getattr(exc, "category", None), "value", None),
    )
    return f"data: {json.dumps(body, separators=(',', ':'))}\n\n"


def _structured_system_prompt(body: ChatCompletionRequest) -> str | None:
    response_format = body.response_format or {}
    format_type = response_format.get("type")
    if format_type not in {"json_object", "json_schema"}:
        return None
    instruction = "Return only a valid JSON value. Do not wrap it in markdown fences."
    if format_type == "json_schema":
        schema = response_format["json_schema"]["schema"]
        instruction += " The JSON value must conform to this JSON Schema:\n" + json.dumps(
            schema, separators=(",", ":"), ensure_ascii=False
        )
    return instruction


def _validate_structured_output(body: ChatCompletionRequest, content: str) -> str:
    response_format = body.response_format or {}
    if response_format.get("type") not in {"json_object", "json_schema"}:
        return content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="The model response was not valid JSON.",
        ) from exc
    if response_format.get("type") == "json_schema":
        try:
            from jsonschema import Draft202012Validator, SchemaError, ValidationError
        except ImportError as exc:
            raise HTTPException(
                status_code=501,
                detail="JSON Schema validation is unavailable on this server.",
            ) from exc
        schema = response_format["json_schema"]["schema"]
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise HTTPException(
                status_code=400, detail="The requested JSON Schema is invalid."
            ) from exc
        try:
            Draft202012Validator(schema).validate(parsed)
        except ValidationError as exc:
            raise HTTPException(
                status_code=502,
                detail="The model response did not match the requested JSON Schema.",
            ) from exc
    return json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)


@router.get("/v1/models")
def list_models(
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    models_by_id: dict[str, Any] = {}
    for status in ("approved", "deployed"):
        for model in model_registry.list_models(lifecycle_status=status):
            models_by_id[model.model_id] = model

    data = [
        {
            "id": model.model_id,
            "object": "model",
            "created": int(model.created_at or 0),
            "owned_by": model.provider_id or "jarvis",
        }
        for model in sorted(models_by_id.values(), key=lambda item: item.model_id)
    ]
    data.append(
        {
            "id": "jarvis-embedding-v1",
            "object": "model",
            "created": 0,
            "owned_by": "jarvis",
        }
    )
    return {"object": "list", "data": data}


@router.get("/v1/models/{model_id}")
def get_model(
    model_id: str,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    if model_id == "jarvis-embedding-v1":
        return {
            "id": model_id,
            "object": "model",
            "created": 0,
            "owned_by": "jarvis",
        }
    for status in ("approved", "deployed"):
        for model in model_registry.list_models(lifecycle_status=status):
            if model.model_id == model_id:
                return {
                    "id": model.model_id,
                    "object": "model",
                    "created": int(model.created_at or 0),
                    "owned_by": model.provider_id or "jarvis",
                }
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' was not found.")


@router.post("/v1/chat/completions")
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
):
    if not body.model.strip():
        raise HTTPException(status_code=400, detail="Model must not be empty.")
    _validate_chat_options(body)
    _set_compat_headers(response, request)
    messages = [message.dict(exclude_none=True) for message in body.messages]
    system_prompt = _structured_system_prompt(body)
    for message in messages:
        if message.get("role") in {"system", "developer"} and isinstance(
            message.get("content"), list
        ):
            raise HTTPException(status_code=400, detail="System message content must be text.")

    if not body.stream:
        try:
            kwargs = {"model": body.model}
            if system_prompt:
                kwargs["system"] = system_prompt
            result = await provider_gateway.chat(messages, **kwargs)
        except ChatError as exc:
            status_code = getattr(exc, "status_code", 502)
            return JSONResponse(
                status_code=status_code,
                content=_error_body(exc.safe_message, status_code, exc.category.value),
                headers={
                    "Jarvis-Version": "1",
                    "X-Request-ID": response.headers["X-Request-ID"],
                },
            )
        content = result.get("content")
        if not isinstance(content, str):
            raise HTTPException(
                status_code=502,
                detail="The configured model returned no valid text completion.",
            )
        content = _validate_structured_output(body, content)
        payload: dict[str, Any] = {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.get("model") or body.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }
        usage = _actual_usage(result.get("usage"))
        if usage is not None:
            payload["usage"] = usage
        return payload

    if system_prompt:
        raise HTTPException(
            status_code=400,
            detail="Structured JSON responses cannot be streamed before schema validation.",
        )
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    async def stream_events():
        yield (
            "data: "
            + json.dumps(
                _openai_chunk(completion_id, created, body.model, {"role": "assistant"}),
                separators=(",", ":"),
            )
            + "\n\n"
        )
        try:
            async for event in provider_gateway.stream_chat(
                model=body.model,
                messages=messages,
            ):
                event_type = event.get("type")
                if event_type == "delta" and event.get("text"):
                    chunk = _openai_chunk(
                        completion_id,
                        created,
                        body.model,
                        {"content": event["text"]},
                    )
                    yield "data: " + json.dumps(chunk, separators=(",", ":")) + "\n\n"
                elif event_type == "done":
                    if not event.get("streamed", True) and event.get("content"):
                        chunk = _openai_chunk(
                            completion_id,
                            created,
                            body.model,
                            {"content": event["content"]},
                        )
                        yield "data: " + json.dumps(chunk, separators=(",", ":")) + "\n\n"
                    final = _openai_chunk(
                        completion_id,
                        created,
                        event.get("model") or body.model,
                        {},
                        "stop",
                    )
                    yield "data: " + json.dumps(final, separators=(",", ":")) + "\n\n"
                    if body.stream_options and body.stream_options.get("include_usage"):
                        usage = _actual_usage(event.get("usage"))
                        if usage is not None:
                            usage_chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": event.get("model") or body.model,
                                "choices": [],
                                "usage": usage,
                            }
                            yield "data: " + json.dumps(usage_chunk, separators=(",", ":")) + "\n\n"
                elif event_type == "error":
                    error_body = _error_body(
                        str(
                            event.get("message")
                            or "The model provider could not complete the request."
                        ),
                        502,
                        str(event.get("category") or "provider_error"),
                    )
                    yield "data: " + json.dumps(error_body, separators=(",", ":")) + "\n\n"
                    yield "data: [DONE]\n\n"
                    return
        except ChatError as exc:
            yield _stream_error(exc)
            yield "data: [DONE]\n\n"
            return
        yield "data: [DONE]\n\n"

    stream_response = StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    _set_compat_headers(stream_response, request)
    return stream_response


@router.post("/v1/completions")
async def create_text_completion(
    body: TextCompletionRequest,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
):
    chat_body = ChatCompletionRequest(
        model=body.model,
        messages=[ChatMessage(role="user", content=body.prompt)],
        stream=body.stream,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        user=body.user,
    )
    chat_response = await create_chat_completion(chat_body, request, response, _user)
    if isinstance(chat_response, JSONResponse):
        return chat_response
    if isinstance(chat_response, StreamingResponse):

        async def text_completion_events():
            pending = ""
            async for part in chat_response.body_iterator:
                pending += part.decode() if isinstance(part, bytes) else part
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    if not line.startswith("data: "):
                        yield line + "\n"
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        yield line + "\n\n"
                        continue
                    if event.get("object") == "chat.completion.chunk":
                        event["object"] = "text_completion"
                        text_choices = []
                        for choice in event.get("choices", []):
                            delta_text = choice.get("delta", {}).get("content")
                            if delta_text is not None or choice.get("finish_reason") is not None:
                                text_choices.append(
                                    {
                                        "index": choice.get("index", 0),
                                        "text": delta_text or "",
                                        "logprobs": None,
                                        "finish_reason": choice.get("finish_reason"),
                                    }
                                )
                        event["choices"] = text_choices
                    yield "data: " + json.dumps(event, separators=(",", ":")) + "\n\n"
            if pending:
                yield pending

        return StreamingResponse(
            text_completion_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Jarvis-Version": "1",
                "X-Request-ID": response.headers["X-Request-ID"],
            },
        )

    content = chat_response["choices"][0]["message"]["content"]
    return {
        **chat_response,
        "id": f"cmpl-{uuid.uuid4().hex}",
        "object": "text_completion",
        "choices": [
            {
                "text": content,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
    }


@router.post("/v1/embeddings")
def create_embeddings(
    body: EmbeddingsRequest,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    if body.model != "jarvis-embedding-v1":
        raise HTTPException(
            status_code=400,
            detail="Only the JARVIS model 'jarvis-embedding-v1' is available.",
        )
    if body.dimensions not in (None, 384):
        raise HTTPException(
            status_code=400,
            detail="The JARVIS embedding model produces 384-dimensional vectors.",
        )

    inputs = [body.input] if isinstance(body.input, str) else body.input
    if not inputs or len(inputs) > 2048 or any(not text.strip() for text in inputs):
        raise HTTPException(status_code=400, detail="Input must contain non-empty text.")
    if any(len(text) > 100_000 for text in inputs):
        raise HTTPException(
            status_code=400,
            detail="Each embedding input must be at most 100,000 characters.",
        )
    if sum(len(text) for text in inputs) > 1_000_000:
        raise HTTPException(
            status_code=400,
            detail="Combined embedding input must be at most 1,000,000 characters.",
        )
    token_counts = [len(_tokenize(text)) for text in inputs]
    if any(count == 0 for count in token_counts):
        raise HTTPException(
            status_code=400,
            detail="Embedding input must contain at least one supported token.",
        )
    vectors = [embed_text(text, 384) for text in inputs]
    data = []
    for index, vector in enumerate(vectors):
        encoded: list[float] | str
        if body.encoding_format == "base64":
            encoded = base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode("ascii")
        else:
            encoded = vector
        data.append(
            {
                "object": "embedding",
                "index": index,
                "embedding": encoded,
            }
        )
    token_count = sum(token_counts)
    return {
        "object": "list",
        "data": data,
        "model": body.model,
        "usage": {
            "prompt_tokens": token_count,
            "total_tokens": token_count,
        },
    }


def _file_store() -> dict[str, Any]:
    return get_store("openai_compat_files").load()


def _owner_id(user: dict[str, Any]) -> str:
    return str(user.get("id") or user.get("user_id") or "")


def _owned_file(file_id: str, user: dict[str, Any]) -> dict[str, Any]:
    record = _file_store().get(file_id)
    if not record or record.get("owner_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="File not found.")
    return record


def _file_response(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "object": "file",
        "bytes": record["bytes"],
        "created_at": record["created_at"],
        "filename": record["filename"],
        "purpose": record["purpose"],
        "status": record["status"],
    }


def _store_compat_file(
    content: bytes,
    filename: str,
    purpose: str,
    owner_id: str,
    status: str,
) -> dict[str, Any]:
    file_id = f"file-{uuid.uuid4().hex}"
    extension = Path(filename).suffix.lower()
    storage_dir = UPLOADS_DIR / "openai_compat"
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{file_id}{extension}"
    with path.open("xb") as target:
        target.write(content)
    record = {
        "id": file_id,
        "owner_id": owner_id,
        "filename": filename,
        "purpose": purpose,
        "bytes": len(content),
        "created_at": int(time.time()),
        "status": status,
        "sha256": hashlib.sha256(content).hexdigest(),
        "path": str(path.resolve()),
    }
    files = _file_store()
    files[file_id] = record
    get_store("openai_compat_files").save()
    return record


def _image_store() -> dict[str, Any]:
    return get_store("openai_compat_images").load()


def _image_path(record: dict[str, Any]) -> Path:
    storage_dir = (UPLOADS_DIR / "openai_compat_images").resolve()
    path = Path(record["path"]).resolve()
    if path.parent != storage_dir or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return path


def _validate_jsonl(content: bytes, purpose: str) -> None:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSONL uploads must be UTF-8.") from exc
    if not lines:
        raise HTTPException(status_code=400, detail="JSONL upload must contain at least one row.")
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise HTTPException(
                status_code=400,
                detail=f"JSONL upload contains an empty line at {line_number}.",
            )
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON on line {line_number}.",
            ) from exc
        if not isinstance(row, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Each JSONL line must be an object (line {line_number}).",
            )
        if purpose == "batch" and not all(
            key in row for key in ("custom_id", "method", "url", "body")
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Batch JSONL line {line_number} requires custom_id, method, url, and body.",
            )
        if (
            purpose == "fine-tune"
            and "messages" not in row
            and not ("prompt" in row and "completion" in row)
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Fine-tuning JSONL line {line_number} requires messages or prompt/completion.",
            )


@router.post("/v1/files")
async def upload_file(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    purpose: str = Form(...),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    supported_purposes = {
        "fine-tune",
        "batch",
        "batch_output",
        "assistants",
        "vision",
        "user_data",
        "responses",
    }
    if purpose not in supported_purposes:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file purpose '{purpose}'.",
        )
    filename = Path(file.filename or "").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid filename is required.")
    extension = Path(filename).suffix.lower()
    if purpose in {"fine-tune", "batch"} and extension != ".jsonl":
        raise HTTPException(
            status_code=400,
            detail=f"Purpose '{purpose}' requires a .jsonl file.",
        )

    max_file_bytes = 50 * 1024 * 1024
    content = await file.read(max_file_bytes + 1)
    if len(content) > max_file_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the 50 MiB upload limit.")
    if not content:
        raise HTTPException(status_code=400, detail="Empty files are not accepted.")
    if extension == ".jsonl":
        _validate_jsonl(content, purpose)
    elif extension == ".json":
        try:
            json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="JSON file is invalid.") from exc
    elif extension == ".csv":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="CSV files must be UTF-8.") from exc

    record = _store_compat_file(content, filename, purpose, _owner_id(_user), "uploaded")
    return _file_response(record)


@router.get("/v1/files")
def list_files(
    request: Request,
    response: Response,
    purpose: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    after: str | None = None,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    owner = _owner_id(_user)
    records = [
        record
        for record in _file_store().values()
        if record.get("owner_id") == owner and (purpose is None or record.get("purpose") == purpose)
    ]
    records.sort(key=lambda item: (item.get("created_at", 0), item["id"]))
    if after:
        ids = [record["id"] for record in records]
        if after not in ids:
            raise HTTPException(status_code=400, detail="Invalid pagination cursor.")
        records = records[ids.index(after) + 1 :]
    page = records[:limit]
    return {
        "object": "list",
        "data": [_file_response(record) for record in page],
        "has_more": len(records) > limit,
        "first_id": page[0]["id"] if page else None,
        "last_id": page[-1]["id"] if page else None,
    }


@router.get("/v1/files/{file_id}/content")
def get_file_content(
    file_id: str,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
):
    _set_compat_headers(response, request)
    record = _owned_file(file_id, _user)
    storage_dir = (UPLOADS_DIR / "openai_compat").resolve()
    path = Path(record["path"]).resolve()
    if path.parent != storage_dir or not path.is_file():
        raise HTTPException(status_code=404, detail="File content not found.")
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(record["filename"])[0] or "application/octet-stream",
        filename=record["filename"],
        headers={
            "Jarvis-Version": "1",
            "X-Request-ID": response.headers["X-Request-ID"],
        },
    )


@router.get("/v1/files/{file_id}")
def get_file(
    file_id: str,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    return _file_response(_owned_file(file_id, _user))


@router.delete("/v1/files/{file_id}")
def delete_file(
    file_id: str,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    record = _owned_file(file_id, _user)
    path = Path(record["path"]).resolve()
    if path.parent != (UPLOADS_DIR / "openai_compat").resolve():
        raise HTTPException(status_code=404, detail="File content not found.")
    path.unlink(missing_ok=True)
    _file_store().pop(file_id, None)
    get_store("openai_compat_files").save()
    return {"id": file_id, "object": "file", "deleted": True}


@router.post("/v1/images/generations")
async def create_image(
    body: ImageGenerationRequest,
    request: Request,
    response: Response,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    generated = await image_generate(
        ImageGenerateIn(
            prompt=body.prompt,
            provider=(body.model.split(":", 1)[0] if body.model and ":" in body.model else None),
            model_name=(body.model.split(":", 1)[-1] if body.model else None),
            size=body.size,
            quality=body.quality,
            num_images=body.n,
        ),
        user,
    )
    data = []
    for item in generated.get("images", []):
        if body.response_format == "b64_json":
            encoded = item.get("base64")
            if not encoded:
                raise HTTPException(
                    status_code=502, detail="Image provider returned no image bytes."
                )
            data.append({"b64_json": encoded, "revised_prompt": body.prompt})
        else:
            url = item.get("url")
            if not url:
                encoded = item.get("base64")
                if not encoded:
                    raise HTTPException(
                        status_code=502, detail="Image provider returned no image data."
                    )
                try:
                    image_bytes = base64.b64decode(encoded, validate=True)
                except (ValueError, base64.binascii.Error) as exc:
                    raise HTTPException(
                        status_code=502,
                        detail="Image provider returned invalid image data.",
                    ) from exc
                if not image_bytes or len(image_bytes) > 20 * 1024 * 1024:
                    raise HTTPException(
                        status_code=502, detail="Image provider returned an invalid image size."
                    )
                image_id = f"image-{uuid.uuid4().hex}"
                image_dir = UPLOADS_DIR / "openai_compat_images"
                image_dir.mkdir(parents=True, exist_ok=True)
                image_path = image_dir / f"{image_id}.png"
                image_path.write_bytes(image_bytes)
                _image_store()[image_id] = {
                    "id": image_id,
                    "owner_id": _owner_id(user),
                    "path": str(image_path.resolve()),
                    "created_at": int(time.time()),
                }
                get_store("openai_compat_images").save()
                url = str(request.base_url).rstrip("/") + f"/v1/images/{image_id}"
            data.append({"url": url, "revised_prompt": body.prompt})
    if len(data) != body.n:
        raise HTTPException(
            status_code=502, detail="The image provider returned an incomplete result."
        )
    return {"created": int(time.time()), "data": data}


@router.get("/v1/images/{image_id}")
def get_generated_image(
    image_id: str,
    request: Request,
    response: Response,
    user: dict[str, Any] = Depends(get_current_user),
):
    _set_compat_headers(response, request)
    record = _image_store().get(image_id)
    if not record or record.get("owner_id") != _owner_id(user):
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(
        _image_path(record),
        media_type="image/png",
        headers={
            "Jarvis-Version": "1",
            "X-Request-ID": response.headers["X-Request-ID"],
        },
    )


@router.post("/v1/audio/transcriptions")
async def create_transcription(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    model: str = Form(...),
    response_format: Literal["json", "text"] = Form(default="json"),
    _user: dict[str, Any] = Depends(get_current_user),
):
    _set_compat_headers(response, request)
    if model != "whisper-1":
        raise HTTPException(status_code=400, detail="Only the 'whisper-1' model is supported.")
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}:
        raise HTTPException(status_code=400, detail="Unsupported audio file type.")
    audio = await file.read(25 * 1024 * 1024 + 1)
    if len(audio) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file exceeds the 25 MiB limit.")
    if not audio:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    capability = VoiceCapability()
    result = await capability.execute(
        {"action": "transcribe", "audio_data": {"data": audio, "filename": filename}},
        ExecutionContext(user_id=_owner_id(_user), session_id=f"openai-{uuid.uuid4().hex}"),
    )
    if not result.success:
        raise HTTPException(status_code=503, detail="Speech transcription is unavailable.")
    transcript = str(result.data.get("text") or "")
    if response_format == "text":
        return Response(
            content=transcript,
            media_type="text/plain; charset=utf-8",
            headers={
                "Jarvis-Version": "1",
                "X-Request-ID": response.headers["X-Request-ID"],
            },
        )
    return {"text": transcript}


@router.post("/v1/audio/speech")
async def create_speech(
    body: SpeechRequest,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
):
    _set_compat_headers(response, request)
    if body.model != "tts-1":
        raise HTTPException(
            status_code=400,
            detail="Only the 'tts-1' model and MP3 output are currently supported.",
        )
    capability = VoiceCapability()
    result = await capability.execute(
        {"action": "synthesize", "text": body.input, "voice": body.voice},
        ExecutionContext(user_id=_owner_id(_user), session_id=f"openai-{uuid.uuid4().hex}"),
    )
    if not result.success:
        raise HTTPException(status_code=503, detail="Speech synthesis is unavailable.")
    audio_data = result.data.get("audio_data")
    if not isinstance(audio_data, str):
        raise HTTPException(status_code=502, detail="The speech provider returned no audio data.")
    try:
        raw_audio = base64.b64decode(audio_data, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise HTTPException(
            status_code=502, detail="The speech provider returned invalid audio data."
        ) from exc
    return Response(
        content=raw_audio,
        media_type="audio/mpeg",
        headers={
            "Jarvis-Version": "1",
            "X-Request-ID": response.headers["X-Request-ID"],
        },
    )


@router.post("/v1/moderations")
async def create_moderation(
    body: ModerationRequest,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("JARVIS_API_KEY_OPENAI")
    if not api_key:
        raise HTTPException(status_code=503, detail="No moderation provider is configured.")
    if body.model not in {"omni-moderation-latest", "text-moderation-latest"}:
        raise HTTPException(status_code=400, detail="Unsupported moderation model.")
    try:
        from openai import APIError, AsyncOpenAI
    except ImportError as exc:
        raise HTTPException(
            status_code=503, detail="The moderation client is unavailable."
        ) from exc
    client = AsyncOpenAI(api_key=api_key)
    try:
        result = await client.moderations.create(input=body.input, model=body.model)
    except APIError as exc:
        raise HTTPException(
            status_code=502, detail="The moderation provider request failed."
        ) from exc
    return result.model_dump()


def _tokenizer_for_model(model: str):
    try:
        import tiktoken
    except ImportError as exc:
        raise HTTPException(
            status_code=503, detail="No token-counting tokenizer is installed."
        ) from exc
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No token-counting encoding is known for model '{model}'.",
        ) from exc


def _count_message_tokens(messages: list[dict[str, Any]], model: str) -> int:
    encoding = _tokenizer_for_model(model)
    return _count_messages_with_encoding(messages, encoding)


def _count_messages_with_encoding(messages: list[dict[str, Any]], encoding: Any) -> int:
    total = 3
    for message in messages:
        total += 3
        for key, value in message.items():
            if isinstance(value, str):
                total += len(encoding.encode(value))
            elif isinstance(value, (dict, list)):
                total += len(encoding.encode(json.dumps(value, ensure_ascii=False)))
            if key == "name":
                total += 1
    return total


def _anthropic_user(request: Request) -> dict[str, Any]:
    api_key = request.headers.get("x-api-key")
    if api_key:
        key_record = find_api_key(api_key)
        if not key_record or is_api_key_expired(key_record):
            raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
        return _api_key_principal(key_record)
    return get_current_user(request.headers.get("authorization"))


@router.post("/v1/messages/count_tokens")
def count_anthropic_tokens(
    body: AnthropicTokenCountRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    _anthropic_user(request)
    _set_compat_headers(response, request)
    messages: list[dict[str, Any]] = []
    if isinstance(body.system, str) or body.system:
        messages.append({"role": "system", "content": body.system})
    for message in body.messages:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"}:
            raise HTTPException(
                status_code=400, detail="Messages must use user or assistant roles."
            )
        if not isinstance(content, (str, list)):
            raise HTTPException(
                status_code=400, detail="Message content must be text or content blocks."
            )
        messages.append({"role": role, "content": content})
    try:
        import tiktoken
    except ImportError as exc:
        raise HTTPException(
            status_code=503, detail="No token-counting tokenizer is installed."
        ) from exc
    return {
        "input_tokens": _count_messages_with_encoding(
            messages, tiktoken.get_encoding("cl100k_base")
        )
    }


@router.post("/v1/chat/completions/count_tokens")
def count_chat_tokens(
    body: TokenCountRequest,
    request: Request,
    response: Response,
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _set_compat_headers(response, request)
    return {
        "object": "token_count",
        "model": body.model,
        "input_tokens": _count_message_tokens(body.messages, body.model),
        "tokenizer": "tiktoken-compatible model encoding; framing estimate included",
    }
