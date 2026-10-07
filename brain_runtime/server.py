"""JARVIS Brain v1 inference API (OpenAI-compatible) on :8011.

Serves:

    GET  /health                  runtime health (unauthenticated; spec section 12)
    GET  /v1/models               registered Brain models (bearer authenticated)
    GET  /v1/models/{id}          a single model (bearer authenticated)
    POST /v1/chat/completions     OpenAI-compatible chat (bearer authenticated)
    POST /v1/generate             prompt-style generation (bearer authenticated)
    GET  /v1/telemetry            recent inference events (bearer authenticated)

Auth (spec section 5): every ``/v1/*`` route requires
``Authorization: Bearer <JARVIS_BRAIN_API_KEY>``.  Missing / invalid / malformed
headers yield 401 with a safe message.  The raw credential is never logged,
returned, or recorded in telemetry.

Honesty (spec section 13): the ``stub`` backend (``JARVIS_BRAIN_BACKEND=stub``)
serves the API contract for local development but reports
``available=false`` / ``production_health=false`` on ``/health`` so the platform
gateway treats it as unavailable and falls back to Silverwing.  It never reports
production health and every reply is visibly labeled ``[brain-stub]``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from brain_runtime.config import BrainConfig
from brain_runtime.generation import BrainGenerationConfig
from brain_runtime.health import BrainHealthState
from brain_runtime.model_registry import BrainCatalog, BrainModel
from brain_runtime.service import BrainService

log = logging.getLogger("brain_runtime.server")

_RESOURCES: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Schemas (OpenAI-compatible surface)
# --------------------------------------------------------------------------- #
class ChatCompletionMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="", description="jarvis-brain-qwen3-4b-v1 or -sft-v1")
    messages: list[ChatCompletionMessage] = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=1, le=16384)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    repetition_penalty: float = Field(default=1.0, ge=0.0, le=2.0)
    stream: bool = False


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str = ""
    max_new_tokens: int = Field(default=256, ge=1, le=16384)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    repetition_penalty: float = Field(default=1.0, ge=0.0, le=2.0)


# --------------------------------------------------------------------------- #
# Telemetry (no prompt content; secrets never recorded)
# --------------------------------------------------------------------------- #
_TELEMETRY: list[dict[str, Any]] = []


def _emit_event(event: dict[str, Any]) -> None:
    _TELEMETRY.append(event)
    if len(_TELEMETRY) > 10_000:
        _TELEMETRY.pop(0)


def telemetry_snapshot() -> list[dict[str, Any]]:
    return list(_TELEMETRY)


def _event(
    request_id: str,
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
        "endpoint": endpoint,
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
    }


def _safe_eq(a: str, b: str) -> bool:
    """Constant-time comparison to avoid timing leaks on the API key."""
    import hmac

    return hmac.compare_digest(a, b)


def port_in_use(host: str, port: int) -> bool:
    """True if something is already bound to (host, port)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(
    config: BrainConfig | None = None,
    service: BrainService | None = None,
    backend=None,
    catalog: BrainCatalog | None = None,
) -> FastAPI:
    """Build the Brain runtime API app (also safe to mount as a sub-app)."""
    cfg = config or BrainConfig()
    cat = catalog or BrainCatalog(cfg.model_repo)
    svc = service or BrainService(config=cfg, catalog=cat, backend=backend)
    _RESOURCES["service"] = svc

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        warmup = os.environ.get("JARVIS_BRAIN_WARMUP_ON_START", "1") != "0"
        if warmup:
            try:
                await asyncio.to_thread(svc.prepare)
            except Exception as exc:  # pragma: no cover - logged
                log.error("startup preparation failed: %s", type(exc).__name__)
        yield
        await asyncio.to_thread(svc.shutdown)

    app = FastAPI(
        title="JARVIS Brain Runtime",
        version="1.0.0",
        description="JARVIS BRAIN v1 - dedicated Qwen3-4B runtime (Layer 2).",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # Auth + helpers
    # ------------------------------------------------------------------ #
    def _mask(value: str | None) -> str:
        if not value:
            return "<none>"
        if len(value) <= 6:
            return "****"
        return value[:3] + "..." + value[-2:]

    def _auth_www() -> dict[str, str]:
        return {"WWW-Authenticate": 'Bearer realm="jarvis-brain"'}

    def _check_auth(authorization: str | None) -> None:
        """Enforce bearer-token auth; never expose the credential."""
        if not cfg.api_key:
            return  # auth disabled (dev without a key)
        if not authorization:
            raise HTTPException(
                status_code=401, headers=_auth_www(), detail="missing Authorization header"
            )
        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0] != "Bearer":
            # Do NOT log or echo the incoming header value.
            log.info("rejected malformed authorization (redacted)")
            raise HTTPException(
                status_code=401, headers=_auth_www(), detail="malformed Authorization header"
            )
        token = parts[1]
        if not _safe_eq(token, cfg.api_key):
            log.info("rejected invalid API key (redacted=%s)", _mask(token))
            raise HTTPException(status_code=401, headers=_auth_www(), detail="invalid API key")

    def _model_info(entry: BrainModel, now: int) -> dict[str, Any]:
        return {
            "id": entry.full_id,
            "object": "model",
            "created": now,
            "owned_by": "jarvis",
            "context_length": entry.context_length,
            "parameters": entry.parameter_count,
            "revision": entry.revision,
            "architecture": entry.architecture,
            "vocab_size": entry.vocab_size,
            "capabilities": list(entry.capabilities),
            "status": entry.status,
            "training_method": entry.training_method,
            "backend": entry.repository,
            "repository": entry.repository,
        }

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #
    @app.get("/")
    def root() -> dict[str, Any]:
        st = svc.health.current()
        return {
            "name": "jarvis-brain-runtime",
            "component": "brain-runtime",
            "version": "1.0.0",
            "endpoint": cfg.base_url,
            "backend": cfg.backend,
            "backend_type": cfg.backend_type,
            "provider": st.provider,
            "model": st.model,
            "stream_support": st.stream_support,
            "auth_required": bool(cfg.api_key),
            "models": [e.full_id for e in cat.list_models()],
            "model_ids": st.models,
            "health_path": "/health",
            "docs": {"openapi": "/openapi.json"},
        }

    @app.get("/health")
    def health() -> JSONResponse:
        st = svc.health.current()
        # A stub runtime answers HTTP but is never production-healthy.
        status_code = 200 if st.status in (BrainHealthState.HEALTHY,) else 503
        return JSONResponse(status_code=status_code, content=st.model_dump())

    @app.get("/v1/models")
    def list_models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _check_auth(authorization)
        now = int(time.time())
        data = [_model_info(e, now) for e in cat.list_models()]
        return {"object": "list", "data": data}

    @app.get("/v1/models/{model_id}")
    def get_model(model_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _check_auth(authorization)
        entry = cat.lookup(model_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"unknown model {model_id!r}")
        return _model_info(entry, int(time.time()))

    @app.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionRequest,
        authorization: str | None = Header(default=None),
    ) -> Any:
        _check_auth(authorization)
        ref = (body.model or cfg.model).strip()
        messages = [m.model_dump() for m in body.messages]
        brain_cfg = BrainGenerationConfig(
            model=ref,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            top_p=body.top_p,
            top_k=body.top_k,
            repetition_penalty=body.repetition_penalty,
            stream=body.stream,
        )
        request_id = uuid.uuid4().hex[:12]
        start = time.monotonic()
        # Resolve the active backend up front so we can branch on real streaming
        # support (Part O) without a speculative blocking call.  _ensure_backend
        # triggers load+warmup only if no backend is prepared yet.
        try:
            backend = await asyncio.wait_for(
                asyncio.to_thread(svc._ensure_backend), timeout=cfg.request_timeout
            )
        except TimeoutError:
            raise HTTPException(status_code=504, detail="generation timed out")
        except RuntimeError as exc:
            log.warning("brain backend not available (type=%s): %s", type(exc).__name__, exc)
            _emit_event(_event(request_id, "/v1/chat/completions", False, ref,
                               error="model_unavailable"))
            raise HTTPException(status_code=503, detail="model unavailable")
        # Real token streaming for backends that advertise stream_support.
        if body.stream and getattr(backend, "stream_support", False):
            return _real_stream(request_id, svc, backend, messages, brain_cfg, ref, cfg)
        # Non-streaming generation (and the single-content-chunk fallback for
        # backends like the stub that do not implement streaming).
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(svc.chat, messages, brain_cfg),
                timeout=cfg.request_timeout,
            )
        except TimeoutError:
            raise HTTPException(status_code=504, detail="generation timed out")
        except RuntimeError as exc:
            # Log the internal failure (type only + safe message; never secrets)
            # separately from the safe API response (spec Part B).
            log.warning("chat completion failed (type=%s): %s", type(exc).__name__, exc)
            _emit_event(_event(request_id, "/v1/chat/completions", False, ref,
                               error="model_unavailable"))
            raise HTTPException(status_code=503, detail="model unavailable")
        except Exception as exc:  # pragma: no cover - defensive
            _emit_event(_event(request_id, "/v1/chat/completions", False, ref,
                               error=type(exc).__name__))
            raise HTTPException(status_code=500, detail="generation failed")
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        _emit_event(
            _event(
                request_id, endpoint="/v1/chat/completions", success=True,
                model=result.model, revision=result.revision,
                latency_ms=latency_ms,
                input_tokens=result.tokens_input,
                output_tokens=result.tokens_generated,
                device=result.device, backend=result.backend,
            )
        )
        if body.stream:
            # Non-streaming backend requested with stream=True: fall back to a
            # single content chunk so the OpenAI streaming contract is honored
            # without fabricating token-by-token output.
            return _stream_chat(request_id, result, result.model)
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.model,
            "revision": result.revision,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.text},
                    "finish_reason": result.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": result.tokens_input,
                "completion_tokens": result.tokens_generated,
                "total_tokens": result.tokens_input + result.tokens_generated,
            },
            "device": result.device,
            "backend": result.backend,
            "provider": result.metadata.get("provider", ""),
            "latency_ms": latency_ms,
        }

    def _real_stream(request_id, svc, backend, messages, brain_cfg, ref, cfg) -> StreamingResponse:
        """Bridge a synchronous backend ``stream()`` generator to SSE token chunks.

        Each chunk from the backend is expected to be an OpenAI-style ``chunk``
        dict.  We drive ``next(gen)`` on a worker thread per token so the
        blocking network read does not stall the event loop (spec Part O).
        """
        gen = backend.stream(messages, brain_cfg)  # synchronous generator
        log.info("real SSE streaming started (backend=%s, model=%s)", backend.backend, ref)

        _SENTINEL = object()

        async def sse():
            created = int(time.time())
            # OpenAI convention: an initial role-only chunk.
            role_chunk = {
                "id": f"chatcmpl-{request_id}",
                "object": "chat.completion.chunk",
                "created": created,
                "model": ref,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(role_chunk)}\n\n"
            emitted = 0
            try:
                while True:
                    def _next():
                        # Catch StopIteration *inside* the worker thread: a
                        # StopIteration that escapes into a coroutine is converted
                        # by Python into a RuntimeError (PEP 479 / asyncio), which
                        # would wrongly terminate the stream.
                        try:
                            return next(gen)
                        except StopIteration:
                            return _SENTINEL
                    chunk = await asyncio.wait_for(
                        asyncio.to_thread(_next), timeout=cfg.request_timeout
                    )
                    if chunk is _SENTINEL:
                        break
                    yield f"data: {json.dumps(chunk)}\n\n"
                    emitted += 1
            except asyncio.TimeoutError:
                log.warning("stream generation timed out after %ds", cfg.request_timeout)
            except Exception as exc:
                log.warning("stream generation error (type=%s): %s", type(exc).__name__, exc)
            finally:
                try:
                    gen.close()
                except Exception:
                    pass
            # Final stop chunk + terminator.
            stop_chunk = {
                "id": f"chatcmpl-{request_id}",
                "object": "chat.completion.chunk",
                "created": created,
                "model": ref,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(stop_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            log.info("SSE streaming complete (backend=%s, chunks=%d)", backend.backend, emitted)

        return StreamingResponse(sse(), media_type="text/event-stream")

    def _stream_chat(request_id: str, result, ref: str) -> StreamingResponse:
        async def gen():
            created = int(time.time())
            chunk = {
                "id": f"chatcmpl-{request_id}",
                "object": "chat.completion.chunk",
                "created": created,
                "model": ref,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": result.text},
                    "finish_reason": None,
                }],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield f"data: {json.dumps({'id': f'chatcmpl-{request_id}', 'object': 'chat.completion.chunk', 'created': created, 'model': ref, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/v1/generate")
    async def generate(
        body: GenerateRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization)
        ref = (body.model or cfg.model).strip()
        brain_cfg = BrainGenerationConfig(
            model=ref,
            temperature=body.temperature,
            max_tokens=body.max_new_tokens,
            top_p=body.top_p,
            top_k=body.top_k,
            repetition_penalty=body.repetition_penalty,
        )
        request_id = uuid.uuid4().hex[:12]
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    svc.chat, [{"role": "user", "content": body.prompt}], brain_cfg
                ),
                timeout=cfg.request_timeout,
            )
        except TimeoutError:
            raise HTTPException(status_code=504, detail="generation timed out")
        except RuntimeError:
            raise HTTPException(status_code=503, detail="model unavailable")
        except Exception:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail="generation failed")
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        _emit_event(_event(request_id, "/v1/generate", True,
                           model=result.model, revision=result.revision,
                           latency_ms=latency_ms, input_tokens=result.tokens_input,
                           output_tokens=result.tokens_generated, device=result.device,
                           backend=result.backend))
        return {
            "id": f"brain-{request_id}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": result.model,
            "revision": result.revision,
            "choices": [{"index": 0, "text": result.text, "finish_reason": result.finish_reason}],
            "usage": {
                "prompt_tokens": result.tokens_input,
                "completion_tokens": result.tokens_generated,
                "total_tokens": result.tokens_input + result.tokens_generated,
            },
            "device": result.device,
            "backend": result.backend,
            "latency_ms": latency_ms,
        }

    @app.get("/v1/telemetry")
    def telemetry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        _check_auth(authorization)
        return {"count": len(_TELEMETRY), "events": telemetry_snapshot()[-200:]}

    @app.exception_handler(Exception)
    async def _unhandled(_request: Any, exc: Exception):
        # Never echo credentials; log only the exception type.
        log.exception("unhandled error (type=%s)", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": "internal server error"})

    return app


def main() -> None:
    """Run the Brain runtime standalone: ``python -m brain_runtime.server``."""
    import sys

    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    import uvicorn

    # Canonical config (spec Part Q / Part 21): load .env into this process so
    # the brain runtime is self-sufficient — no separate shell sourcing and no
    # divergence with the platform. setdefault-only: a real env value always
    # wins; get_env semantics are unchanged (os.environ-first).
    from brain_runtime.env import load_env_file

    load_env_file()

    cfg = BrainConfig()
    cfg.ensure_dirs()

    # Port-collision safety (spec section 1): :8011 is ours; :8010 is Silverwing.
    if port_in_use(cfg.host, cfg.port):
        raise SystemExit(
            f"[brain] port {cfg.host}:{cfg.port} is already in use. "
            "JARVIS BRAIN must run on 127.0.0.1:8011 (separate from Silverwing :8010)."
        )
    if port_in_use("127.0.0.1", 8010):
        log.info("[brain] Silverwing runtime detected on 127.0.0.1:8010 (preserved, unchanged).")
    else:
        log.info("[brain] NOTE: Silverwing runtime was not detected on :8010; "
                 "Silverwing fallback will be unavailable.")

    cat = BrainCatalog(cfg.model_repo)
    app = create_app(config=cfg, catalog=cat)

    log.info("[brain] starting JARVIS BRAIN v1 on http://%s:%d/v1 (model=%s, backend=%s, device=%s)",
             cfg.host, cfg.port, cfg.model, cfg.backend, cfg.device)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
