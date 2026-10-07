"""Silverwing inference API (OpenAI-compatible).

Serves the runtime over HTTP:

    POST /v1/chat/completions   OpenAI-compatible chat (incl. SSE streaming)
    POST /v1/generate           runtime generation endpoint
    GET  /v1/models             registered models
    GET  /v1/models/{model_id}  one model (by full id or base id)
    GET  /v1/health             runtime health
    GET  /                      service banner + registry summary

Security (spec section 27): optional bearer-token auth (``SILVERWING_API_KEY``),
request validation, rate limiting, max-token caps and a hard request timeout.
Telemetry events are emitted per inference request (spec section 26) WITHOUT
storing prompt content unless explicitly permitted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from silverwing_runtime.config import RuntimeConfig
from silverwing_runtime.generation import GenerationConfig, GenerationRequest
from silverwing_runtime.health import HealthState
from silverwing_runtime.inference import InferenceService
from silverwing_runtime.model_loader import ModelLoader
from silverwing_runtime.model_registry import SilverwingRegistry

log = logging.getLogger("silverwing_runtime.server")

_SLOW_CALLER_MS = 30_000


# --------------------------------------------------------------------------- #
# Schemas (OpenAI-compatible surface)
# --------------------------------------------------------------------------- #
class ChatCompletionMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="", description="silverwing-120m-base-v1 or base id")
    messages: list[ChatCompletionMessage] = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, ge=1, le=4096)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    repetition_penalty: float = Field(default=1.0, ge=0.0, le=2.0)
    stream: bool = False
    stream_options: dict[str, Any] | None = None


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_new_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_k: int | None = Field(default=None, ge=1)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.0, ge=0.0, le=2.0)
    model: str = ""


class _ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "silverwing"
    context_length: int | None = None
    parameters: int | None = None
    revision: str = ""
    architecture: str = ""
    vocab_size: int = 0
    tokenizer_version: str = ""
    capabilities: list[str] = Field(default_factory=list)
    status: str = ""
    backend: str = ""
    health: str = ""


# --------------------------------------------------------------------------- #
# Telemetry
# --------------------------------------------------------------------------- #
_TELEMETRY: list[dict[str, Any]] = []


def _emit_event(event: dict[str, Any]) -> None:
    _TELEMETRY.append(event)
    if len(_TELEMETRY) > 10_000:
        _TELEMETRY.pop(0)


def _event(
    request_id: str,
    *,
    endpoint: str,
    success: bool,
    model: str = "",
    revision: str = "",
    latency_ms: float | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error: str | None = None,
    device: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model,
        "revision": revision,
        "latency_ms": latency_ms if latency_ms is not None else 0.0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "device": device or "",
        "backend": backend or "",
        "success": success,
        "error": error,
        "endpoint": endpoint,
    }


def telemetry_snapshot() -> list[dict[str, Any]]:
    return list(_TELEMETRY)


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(
    registry: SilverwingRegistry | None = None,
    loader: ModelLoader | None = None,
    inference: InferenceService | None = None,
    config: RuntimeConfig | None = None,
    startup_models: list[str] | None = None,
) -> FastAPI:
    """Build the runtime API app (also safe to mount as a sub-app)."""
    cfg = config or RuntimeConfig()
    reg = registry or SilverwingRegistry(cfg)
    reg.load()
    ldr = loader or ModelLoader(reg, config=cfg)
    svc = inference or InferenceService(ldr, cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Startup flow (spec section 12): registry lookup -> locate -> verify
        # hash -> load -> warmup inference -> healthy.
        warmup_on_start = os.environ.get("SILVERWING_WARMUP_ON_START", "1") != "0"
        if warmup_on_start:
            targets = startup_models or [
                e.full_id for e in reg.list_models() if e.status != "archived"
            ]
            if targets:
                try:
                    await asyncio.to_thread(svc.warmup, targets[0])
                except Exception as exc:
                    log.error("startup warmup failed for %s: %s", targets[0], exc)
        yield
        await asyncio.to_thread(svc.shutdown)

    app = FastAPI(
        title="Silverwing Runtime",
        version="0.1.0",
        description="Model inference runtime (Layer 2).",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # Auth + validation helpers
    # ------------------------------------------------------------------ #
    def _check_auth(authorization: str | None) -> None:
        if not cfg.api_key:
            return
        expected = f"Bearer {cfg.api_key}"
        if not authorization or authorization != expected:
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    def _resolve_model_ref(model: str) -> str:
        ref = model or svc._default_ref()
        entry = reg.lookup(ref)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown model {ref!r}")
        if entry.status == "archived":
            raise HTTPException(
                status_code=400,
                detail=f"model {ref!r} is archived and not servable",
            )
        return ref

    _rate_window: dict[str, list[float]] = {}

    def _rate_limit(key: str, limit: int = 60, window_sec: float = 60.0) -> None:
        now = time.monotonic()
        hits = [t for t in _rate_window.get(key, []) if now - t < window_sec]
        if len(hits) >= limit:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        hits.append(now)
        _rate_window[key] = hits

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #
    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "silverwing-runtime",
            "version": "0.1.0",
            "models": [e.full_id for e in reg.list_models()],
        }

    @app.get("/v1/health")
    def health() -> JSONResponse:
        st = svc.health.current()
        status_code = 200 if st.status in (HealthState.HEALTHY,) else 503
        return JSONResponse(status_code=status_code, content=st.model_dump())

    @app.get("/v1/models")
    def list_models() -> dict[str, Any]:
        now = int(time.time())
        data = [_model_info(e, now) for e in reg.list_models() if e.status != "archived"]
        return {"object": "list", "data": [d.model_dump() for d in data]}

    @app.get("/v1/models/{model_id}")
    def get_model(model_id: str) -> _ModelInfo:
        entry = reg.lookup(model_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown model {model_id!r}")
        return _model_info(entry, int(time.time()))

    def _backend_name(full_id: str) -> str:
        b = svc._backends.get(full_id)
        return getattr(b, "backend", "") if b else ""

    def _model_info(entry: Any, now: int) -> _ModelInfo:
        dep = entry.deployment
        back = _backend_name(entry.full_id)
        health = (
            "healthy"
            if dep.healthy
            else "loaded" if dep.loaded else "unloaded"
        )
        return _ModelInfo(
            id=entry.full_id,
            created=now,
            context_length=entry.context_length,
            parameters=entry.parameter_count,
            revision=entry.revision,
            architecture=entry.architecture,
            vocab_size=entry.vocab_size,
            tokenizer_version=entry.tokenizer_version,
            capabilities=list(entry.capabilities),
            status=entry.status,
            backend=back,
            health=health,
        )

    @app.post("/v1/generate")
    async def generate(
        body: GenerateRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization)
        _rate_limit("generate")
        ref = _resolve_model_ref(body.model)
        req = GenerationRequest(
            prompt=body.prompt,
            config=GenerationConfig(
                max_new_tokens=body.max_new_tokens,
                temperature=body.temperature,
                top_k=body.top_k,
                top_p=body.top_p,
                repetition_penalty=body.repetition_penalty,
            ),
        )
        request_id = uuid.uuid4().hex[:12]
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                svc.generate(req, model_ref=ref), timeout=cfg.request_timeout
            )
        except TimeoutError:
            raise HTTPException(status_code=504, detail="generation timed out")
        except Exception as exc:
            _emit_event(_event(request_id, endpoint="/v1/generate", success=False, error=str(exc)))
            raise HTTPException(status_code=500, detail=f"generation failed: {exc}")
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        _emit_event(
            _event(
                request_id,
                endpoint="/v1/generate",
                success=True,
                model=result.model,
                revision=result.revision,
                latency_ms=latency_ms,
                input_tokens=result.tokens_input,
                output_tokens=result.tokens_generated,
                device=svc.health.current().device,
                backend=svc.health.current().backend,
            )
        )
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": result.model,
            "revision": result.revision,
            "device": svc.health.current().device,
            "backend": svc.health.current().backend,
            "latency_ms": latency_ms,
            "choices": [
                {
                    "index": 0,
                    "text": result.text,
                    "finish_reason": result.finish_reason,
                }
            ],
            "usage": {
                "input_tokens": result.tokens_input,
                "output_tokens": result.tokens_generated,
                "total_tokens": result.tokens_input + result.tokens_generated,
            },
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionRequest,
        authorization: str | None = Header(default=None),
        x_forwarded_for: str | None = Header(default=None),
    ) -> Any:
        _check_auth(authorization)
        _rate_limit(x_forwarded_for or "chat")
        ref = _resolve_model_ref(body.model)
        messages = [m.model_dump() for m in body.messages]
        cfg_gen = GenerationConfig(
            max_new_tokens=body.max_tokens,
            temperature=body.temperature,
            top_k=body.top_k,
            top_p=body.top_p,
            repetition_penalty=body.repetition_penalty,
        )
        request_id = uuid.uuid4().hex[:12]
        start = time.monotonic()

        if body.stream:
            return _stream_response(svc, ref, messages, cfg_gen, request_id, start)

        try:
            result = await asyncio.wait_for(
                svc.chat(messages, generation_config=cfg_gen, model_ref=ref),
                timeout=cfg.request_timeout,
            )
        except TimeoutError:
            raise HTTPException(status_code=504, detail="generation timed out")
        except Exception as exc:
            _emit_event(_event(request_id, endpoint="/v1/chat/completions", success=False, error=str(exc)))
            raise HTTPException(status_code=500, detail=f"generation failed: {exc}")
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        input_tokens = result.usage.get("input_tokens", 0)
        output_tokens = result.usage.get("output_tokens", 0)
        _emit_event(
            _event(
                request_id,
                endpoint="/v1/chat/completions",
                success=True,
                model=result.model,
                revision=result.revision,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                device=svc.health.current().device,
                backend=svc.health.current().backend,
            )
        )
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.model,
            "revision": result.revision,
            "device": svc.health.current().device,
            "backend": svc.health.current().backend,
            "latency_ms": latency_ms,
            "choices": [
                {
                    "index": 0,
                    "message": result.message.model_dump(),
                    "finish_reason": result.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }

    @app.get("/v1/telemetry")
    def telemetry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _check_auth(authorization)
        return {"count": len(_TELEMETRY), "events": telemetry_snapshot()[-200:]}

    return app


def _stream_response(
    svc: InferenceService,
    ref: str,
    messages: list[dict[str, str]],
    cfg: GenerationConfig,
    request_id: str,
    _start: float,
) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        result = await svc.chat(messages, generation_config=cfg, model_ref=ref)
        chunk = {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": result.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": result.message.content},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        done = {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": result.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(done)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def main() -> None:
    """Run the runtime standalone: ``python -m silverwing_runtime.server``."""
    import uvicorn

    cfg = RuntimeConfig()
    cfg.ensure_dirs()
    reg = SilverwingRegistry(cfg)
    reg.refresh()
    loader = ModelLoader(reg, config=cfg)
    # Honor SILVERWING_MODEL (set by start_jarvis / _env) as the designated
    # startup model so the runtime warms up the intended local weights instead
    # of falling back to the registry first entry (jarvis-brain-qwen3-4b-v1,
    # which has no local weights and fails to load from HF). When unset,
    # behavior is unchanged (registry default order).
    _startup = os.environ.get("SILVERWING_MODEL")
    startup_models = [_startup] if _startup else None
    app = create_app(
        registry=reg, loader=loader, inference=None, config=cfg,
        startup_models=startup_models,
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("SILVERWING_PORT", "8010")))


import os  # used by main

if __name__ == "__main__":
    main()
