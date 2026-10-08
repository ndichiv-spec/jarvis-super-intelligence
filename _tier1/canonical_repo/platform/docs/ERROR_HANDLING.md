# Error Handling Taxonomy & Retry Matrix (Phase 1)

> Single source of truth: `jarvis_backend/errors.py`. Every failure in the chat
> path is normalised to a `ChatError` and surfaced with a stable JSON envelope
> and an HTTP status code.

## 1. The 15-category taxonomy

```python
class ErrorCategory(str, Enum):
    AUTHENTICATION_ERROR   = "AUTHENTICATION_ERROR"   # no/bad token
    AUTHORIZATION_ERROR    = "AUTHORIZATION_ERROR"    # forbidden (e.g. cross-user)
    INVALID_REQUEST        = "INVALID_REQUEST"        # bad route / unknown id
    VALIDATION_ERROR       = "VALIDATION_ERROR"       # pydantic 422
    RATE_LIMITED           = "RATE_LIMITED"           # 429 from provider
    PROVIDER_UNAVAILABLE   = "PROVIDER_UNAVAILABLE"   # no cloud key / local-only / empty
    STREAM_INTERRUPTED     = "STREAM_INTERRUPTED"    # SSE ended early
    RESOURCE_EXHAUSTED     = "RESOURCE_EXHAUSTED"     # OOM / pool / mem
    CONTEXT_LIMIT          = "CONTEXT_LIMIT"          # prompt too long
    CONTENT_POLICY         = "CONTENT_POLICY"         # blocked content
    MODEL_ERROR            = "MODEL_ERROR"            # provider-side model failure
    TIMEOUT                = "TIMEOUT"                # asyncio.wait_for / deadline
    NETWORK_ERROR          = "NETWORK_ERROR"          # ConnectionError / OSError
    INTERNAL_ERROR         = "INTERNAL_ERROR"         # unexpected 5xx
    UNKNOWN_ERROR          = "UNKNOWN_ERROR"          # anything else
```

## 2. Retryable categories

```python
RETRYABLE_CATEGORIES = {
    RATE_LIMITED, PROVIDER_UNAVAILABLE, STREAM_INTERRUPTED,
    RESOURCE_EXHAUSTED, TIMEOUT, NETWORK_ERROR,
    INTERNAL_ERROR, UNKNOWN_ERROR,
}
```

Non-retryable: `AUTHENTICATION_ERROR, AUTHORIZATION_ERROR, INVALID_REQUEST,
VALIDATION_ERROR, CONTEXT_LIMIT, CONTENT_POLICY, MODEL_ERROR`. A non-retryable
error is surfaced **immediately** (no backoff retries).

## 3. HTTP status map

`STATUS_BY_CATEGORY` (and per-instance override via `ChatError.category`/
`status_code`):

| Category | Status | Retryable |
|---|---|---|
| AUTHENTICATION_ERROR | 401 | no |
| AUTHORIZATION_ERROR  | 403 | no |
| INVALID_REQUEST      | 404 | no |
| VALIDATION_ERROR     | 422 | no |
| RATE_LIMITED         | 429 | yes |
| PROVIDER_UNAVAILABLE | 503 | usually no (no-cloud-key), **yes** if flaky |
| STREAM_INTERRUPTED   | 502 | yes |
| RESOURCE_EXHAUSTED   | 503 | yes |
| CONTEXT_LIMIT        | 400 | no |
| CONTENT_POLICY       | 400 | no |
| MODEL_ERROR          | 502 | no |
| TIMEOUT              | 504 | yes |
| NETWORK_ERROR        | 502 | yes |
| INTERNAL_ERROR       | 500 | yes |
| UNKNOWN_ERROR        | 502 | yes |

## 4. Error object

```python
ChatError(category, message, *, request_id=None, retryable=None,
          detail=None, status_code=None)
```

- `to_dict()` → `{"error": {"category", "message", "request_id",
  "retryable", "status_code"}}`.
- `summary()` → a one-line human description.
- Global handler registered in `jarvis_backend/main.py`:
  `@app.exception_handler(ChatError)` → `JSONResponse(status_code=exc.status_code,
  content=exc.to_dict())`.

Examples (verified in `test_backend.py` / `conftest` wiring):
- `AUTHORIZATION_ERROR` → 403
- `INVALID_REQUEST` → 404
- `PROVIDER_UNAVAILABLE` → 503

## 5. Normalisation

### `normalize_exception(exc, request_id=None)`
Turns arbitrary Python exceptions into `ChatError`:

| Exception | → Category | Retryable | Status |
|---|---|---|---|
| `asyncio.TimeoutError` / `TimeoutError` | `TIMEOUT` | yes | 504 |
| `ConnectionError` / `OSError` | `NETWORK_ERROR` | yes | 502 |
| *(anything else)* | `UNKNOWN_ERROR` | yes | 502 |

### `from_provider_exception(exc)`
Maps provider SDK exceptions by **class name + message hints**:

- `RateLimitError` / message contains `rate`/`429`/`quota` → `RATE_LIMITED`
- `TokenLimitError` / messages with `context`, `token`, `length`, `too long` → `CONTEXT_LIMIT`
- `ContentFilterError` / `policy`, `blocked`, `safety` → `CONTENT_POLICY`
- `TimeoutError` / message `timeout` → `TIMEOUT`
- auth failures (`Unauthorized`, `invalid_api_key`, `401`) → `PROVIDER_UNAVAILABLE`
- `RateLimitError`/`TimeoutError` otherwise → `RATE_LIMITED`/`TIMEOUT`
- fallback → `MODEL_ERROR` (non-retryable)

## 6. Retry / backoff

Used by `ChatService._generate` (retries `max_retries`, default `2` via
`JARVIS_AI_MAX_RETRIES` defaulting to `"2"`):

```python
attempt = 0
while True:
    try:
        return await self.gateway.chat(...)
    except ChatError as e:
        if not e.retryable or attempt >= self.max_retries:
            raise
        delay = (2 ** attempt) * 0.25 + 0.25 * (time.monotonic() % 1)   # jitter
        await asyncio.sleep(delay)
        attempt += 1
```

| attempt | base delay (25ms × 2^attempt) | + up-to 250ms jitter |
|---|---|---|
| 0 | 0.25 s | 0.25–0.50 s |
| 1 | 0.50 s | 0.50–0.75 s |

Tests:
- `test_phase1_chat.py::test_retry_then_completes` — `FlakyGateway` raises
  `TIMEOUT` once, succeeds on retry; expects 2 calls.
- `test_fatal_error_is_not_retried` — non-retryable `PROVIDER_UNAVAILABLE`
  surfaces after exactly 1 call.
- `test_idempotent_resend_returns_cached_reply` — repeat `client_message_id`
  returns cached reply without re-calling the gateway (1 call).

## 7. SSE error envelope

When streaming, a `ChatError` is emitted as the terminal event:

```
data: {"type": "error",
       "category": "PROVIDER_UNAVAILABLE",
       "message": "No cloud model key configured",
       "request_id": "...",
       "retryable": false,
       "status": 503,
       "message_id": "..."}
```

`test_streaming_provider_failure_emits_error_event` asserts the `error` event
type and `category == "PROVIDER_UNAVAILABLE"` for the no-cloud-key path.
