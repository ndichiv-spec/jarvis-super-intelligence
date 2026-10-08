# Data Ownership Model (Phase 1)

> Rule of the system: **never trust a client-supplied `user_id`.** The owner of
> every chat resource is derived from the bearer JWT, never the request body.

## 1. Identity source

Every protected route resolves the caller from the `Authorization: Bearer <jwt>`
header (see `infrastructure/security/auth.py` middleware + `core.decode_token`):

```python
payload = decode_token(token)        # verifies HS256 + exp
user_id = payload["sub"]             # the ONLY authoritatively-typed identity
sid     = payload.get("sid")         # session id, when bound to a login session
```

The request **body** may also carry a `user_id`/`session_id` field, but it is
treated as untrusted and **MUST NOT** be used for ownership decisions. Routes
that accept a `user_id` argument from the body ignore it and use the token's
`sub`.

## 2. Resource ownership = token `sub`

All chat resources are keyed by the authenticated `user_id`:

| Resource | Owner key |
|---|---|
| A chat session | `sessions[session_id]["user_id"] == token.sub` |
| A message | belongs to its session; reachable only via `user_id` |
| A refresh token | `refresh_tokens[jti]["user_id"] == token.sub` |
| `/api/v1/auth/me` | returns the user from `token.sub` |

`ChatService._history(user_id, session_id)` calls `get_session(user_id, ...)``,
which enforces that the session row's `user_id` matches the token `sub`.

## 3. Enforcement matrix

| Action | Condition | Result |
|---|---|---|
| `POST /api/chat` without token | no/invalid bearer | `401` |
| `POST /api/chat` with token | message posted under `token.sub` | `200 COMPLETED/FAILED` |
| read / edit / delete a session | `sessions[sid].user_id != token.sub` | `403 AUTHORIZATION_ERROR` ("You are not authorized to access this session.") |
| read / edit / delete a session | `sid` not present | `404 INVALID_REQUEST` |
| list sessions | always scoped to `token.sub` | only the caller's sessions |
| `POST /auth/refresh` | refresh JWT's `jti` not in store (revoked/expired) | `401` |
| `POST /auth/logout` | revokes the supplied refresh token + clears session sid | `200 {success:true}` |

## 4. Cross-user isolation (tested)

`tests/test_phase1_ownership.py` asserts:

- A token for user A **cannot** send, read history, or delete a session owned
  by user B → `403` with `error.category == "AUTHORIZATION_ERROR"`.
- An unknown session id → `404` with `error.category == "INVALID_REQUEST"`.
- `GET /api/chat/sessions` returns **only** the caller's sessions (A never sees
  B's list).
- A `user_id` placed in the request body is **ignored** — the response reflects
  the token's `sub`.

## 5. Refresh-token ownership

Refresh tokens are minted **for** a specific `user_id` (stored under `jti`) and
are:
- bound to the user that registered/logged-in (`create_refresh_token(user_id)`);
- revocable independently of access tokens (`revoke_refresh_token(jti)`);
- rejected after logout (`refresh_access_token` returns `None` → `401`).

`test_phase1_auth.py::test_logout_revokes_refresh_token` confirms: after logout,
re-using the revoked refresh token at `POST /auth/refresh` returns `401`.

## 6. Test isolation

`tests/conftest.py::_reset_state` (autouse) clears the in-memory store cache
(`core.data.clear()`) and the on-disk JSON store (`DATA_DIR/*.json`) **before
and after every test**, so ownership tests start from a clean per-test ledger
and cannot leak users/sessions across cases.
