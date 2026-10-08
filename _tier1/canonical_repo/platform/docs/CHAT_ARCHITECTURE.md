# Chat Architecture (Phase 1)

> Backend: runnable `jarvis_backend`. The chat path talks to the **existing
> Silverwing gateway** mounted at `/silverwing` — never to the old mock
> `ai_service`.

## 1. Component map

```
HTTP client
  │  POST /api/chat            ──┐
  │  POST /api/chat/stream (SSE)│
  │  /api/chat/sessions...      │
  ▼
jarvis_backend.main (FastAPI app)
  │  ChatService  (jarvis_backend/chat_service.py)
  │     └─ self.gateway  (ProviderGateway singleton, jarvis_backend/gateway.py)
  │          │
  │          │  imports & mounts silverwing at /silverwing
  │          ▼
  │     silverwing-backend/ (main.py)  ── ModelRouter ── LocalProvider | cloud providers
  ▼
jarvis_backend/routers/* (auth, chat routes, etc.)
```

- `gateway.py`: `_SILVERWING_BACKEND = ROOT / "silverwing-backend"`; Silverwing is
  imported lazily and wired via `integrate_silverwing()` in `main.py`.
- `chat_service.py`: `ChatService.__init__(self, gateway=None)`;
  `self.gateway = gateway or provider_gateway` (module singleton).

## 2. The no-fake contract

In this environment `ModelConfig().any_cloud_key() == False`, so Silverwing
resolves to `LocalProvider` (`provider == "local"`). The gateway **never**
synthesises a reply:

```python
# gateway.py  (abridged)
def _resolve_router(): ...           # ModelRouter from silverwing.backends.model_provider
async def chat(self, messages, model=None, system=None, timeout=None):
    if not _has_cloud_key(self._silverwing):   # any_cloud_key() False
        raise ChatError(ErrorCategory.PROVIDER_UNAVAILABLE,
                        "No cloud model key configured", retryable=False,
                        status_code=503)
    resp = await asyncio.wait_for(router.route_and_chat(ModelRequest(...),
                                                        task="jarvis.chat"), timeout)
    if resp.provider in ("local", "local-rule") or not resp.content:
        raise ChatError(ErrorCategory.PROVIDER_UNAVAILABLE, ...)   # never echo
    return {"content", "model": f"{provider}:{model}", "provider",
            "latency_ms", "usage"}
```

Consequences:
- No cloud key → `PROVIDER_UNAVAILABLE` (HTTP 503, `retryable=false`).
- Local-rule provider or empty content → `PROVIDER_UNAVAILABLE` (same).
- The HTTP layer maps this to `status: "FAILED"` with `error.category =
  "PROVIDER_UNAVAILABLE"` — **no canned text leaks** (`assert not data.get("reply")`).

Verified directly:
```
python3 -c "from jarvis_backend.gateway import ProviderGateway; ..."
ProviderGateway().chat([...]) ->
  ChatError(PROVIDER_UNAVAILABLE, retryable=False, status_code=503)  # never a local-rule reply
```

## 3. ChatService bridge

`ChatService._generate` now calls the gateway instead of `ai_service.chat`:

```python
# chat_service.py (abridged)
def _generate(self, user_id, session_id, message):
    return asyncio.run(self.gateway.chat(
        self._history(user_id, session_id), model=self.model, system=_SYSTEM_PROMPT
    ))

def _history(self, user_id, session_id):
    session = self.get_session(user_id, session_id)   # ownership-enforced
    return session["messages"]                        # O(user message + replies)
```

- `_require_session(user_id, session_id)`: cross-user →
  `ChatError(AUTHORIZATION_ERROR, "You are not authorized to access this session.", 403)`;
  not-found → `ChatError(INVALID_REQUEST, ..., 404)`.
- On success, `send_message`/`stream_message` persist `usage` and `provider`
  on the message record.

## 4. HTTP routes (`jarvis_backend/main.py`)

| Route | Behaviour |
|---|---|
| `POST /api/chat` | 401 without auth; otherwise → `ChatService.send_message`. 200 JSON `{status:"COMPLETED"|"FAILED", reply, model, provider, error?}` |
| `POST /api/chat/stream` | SSE. 401 without auth. |
| `POST /api/chat/sessions` | list/create a session for the token user. |
| `GET  /api/chat/sessions/{id}` | session detail (ownership-checked). |
| `GET  /api/chat/history/{id}` | messages (ownership-checked). |
| `POST /api/chat/messages/{sid}/{mid}/regenerate` | regenerate (ownership-checked). |
| `POST /api/v1/ai/process`, `/api/v1/ai/generate`, `/llm/chat` | **410 Gone** — deprecated, no canned replies (see `routers/ai.py`). |
| `GET /api/v1/status` | `{name:"JARVIS Unified System", silverwing:{integrated: true, ...}}` |
| `GET /silverwing/health` | Silverwing sub-app health (mounted at `/silverwing`). |

## 5. SSE streaming protocol

`stream_message` (and the legacy `legacy_chat_stream` path) emit newline-delimited
`data:` events:

```
data: {"type": "typing"}
data: {"type": "meta",     "session_id": ..., "message_id": ...}
data: {"type": "chunk",    "content": "...24 chars...", "text": "full-so-far"}   # chunk_size = 24
data: {"type": "chunk",    "content": "...", "text": "..."}
...
data: {"type": "complete", "session_id": ..., "content": "<full reply>",
       "status": "COMPLETED", "message_id": ...}
```

On a `ChatError` (e.g. `PROVIDER_UNAVAILABLE`):
```
data: {"type": "error", "category": "PROVIDER_UNAVAILABLE", "message": "...",
       "request_id": "...", "retryable": false, "status": 503, "message_id": ...}
```

`tests/test_phase1_chat.py::test_streaming_emits_sse_events` and
`test_streaming_provider_failure_emits_error_event` assert this envelope.

## 6. Resilience: retry / backoff

```python
# chat_service.py
delay = (2 ** attempt) * 0.25 + (2 ** attempt) * 0.0   # jittered
# effectively: delay = (2 ** attempt) * 0.25 + 0.25 * (time.monotonic() % 1)
retries = self.max_retries        # default 2 (JARVIS_AI_MAX_RETRIES env, "2")
```

- Retryable categories only: `RATE_LIMITED, PROVIDER_UNAVAILABLE,
  STREAM_INTERRUPTED, RESOURCE_EXHAUSTED, TIMEOUT, NETWORK_ERROR,
  INTERNAL_ERROR, UNKNOWN_ERROR`.
- Fatal (non-retryable) categories — e.g. `PROVIDER_UNAVAILABLE` with
  `retryable=False` in the no-cloud-key case — surface immediately:
  `test_fatal_error_is_not_retried` asserts a single gateway call.
- Idempotency: a client-supplied `client_message_id` is stored on the message;
  a repeat send returns the cached reply without re-invoking the provider
  (`test_idempotent_resend_returns_cached_reply`).
