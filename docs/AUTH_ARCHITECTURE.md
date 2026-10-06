# Authentication & Authorization Architecture

> Phase 1 — `jarvis_backend`. Auth is owned by `jarvis_backend/core.py` and
> exposed through `jarvis_backend/routers/auth.py`. There is **no** `bcrypt` /
> `passlib` / Flask dependency; everything uses the Python standard library
> (`hashlib`, `hmac`, `secrets`, `jwt` via `python-jose`).

## 1. Secret key handling

| Concern | Implementation |
|---|---|
| Primary key | `JARVIS_SECRET_KEY` environment variable (`core._SECRET_KEY = os.environ.get("JARVIS_SECRET_KEY")`). |
| Fallback (dev / ephemeral) | `secrets.token_urlsafe(32)` — a **random** key generated per process. |
| Insecure default | **None.** There is no hard-coded `"jarvis-dev-secret-change-me"`; `_SECRET_KEY != "jarvis-dev-secret-change-me"` and `len >= 32` is asserted in `test_auth.py`. |
| Signal | When falling back to the ephemeral key, a `WARNING` is logged: *"`JARVIS_SECRET_KEY` is not set; using an ephemeral random secret. Tokens will not survive a restart. Set `JARVIS_SECRET_KEY` for production or a persistent dev environment."* |

> **Operational rule:** set `JARVIS_SECRET_KEY` for any environment where tokens
> must survive a restart or span multiple processes. In tests an ephemeral key
> is fine (tokens are short-lived per test).

## 2. Password hashing (pbkdf2-hmac-sha256)

Stored format: `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`

```python
import hashlib, os, hmac, base64
_PBKDF2_ITERATIONS = 200_000

def hash_password(password: str) -> str:
    salt = os.urandom(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        _, it, salt_hex, hash_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(digest.hex(), hash_hex)
    # Legacy fallback: "<salt_hex>$<digest_hex>" (2 parts)
    salt_hex, hash_hex = stored.split("$")
    legacy = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                bytes.fromhex(salt_hex), 100_000).hex()
    return hmac.compare_digest(legacy, hash_hex)
```

- 200,000 iterations (OWASP-aligned baseline; tunable).
- `hmac.compare_digest` for constant-time comparison.
- `verify_password` accepts both the 4-part `pbkdf2_sha256$…` scheme and the
  2-part legacy `salt$digest` scheme (`test_auth.py::test_password_verify_supports_legacy_hmac_fallback`).

## 3. Tokens

All tokens are signed JWTs (`HS256`, `core.create_token`) carrying `sub`,
plus optional `sid`/`jti`/`iat`/`exp`.

| Token | TTL | Payload | Purpose |
|---|---|---|---|
| Access | 7 days (`_TOKEN_TTL_HOURS = 168`) | `{sub, [sid]}` | Bearer auth on every protected route. `sub` = user id. |
| Refresh | 60 days (`_REFRESH_TTL_HOURS = 1440`) | `{sub, jti}` | mints a new access token; **jti**-tracked & revocable. |

Helpers in `core.py`:
- `create_token(payload, ttl_hours=...)` — sign.
- `decode_token(token)` — verify signature + expiry; returns payload or `None`.
- `create_refresh_token(user_id, session_id=None)` — mints a refresh JWT **and**
  writes a `{jti: {user_id, session_id, created_at}}` record to the
  `refresh_tokens` store (in-memory cache + persisted JSON).
- `refresh_access_token(refresh_token)` — validates the JWT, looks up `jti` in
  the store (revoked? → `None`), mints a **new** access token for the same
  `sub`.
- `revoke_refresh_token(refresh_token)` — removes the `jti` record; idempotent.

## 4. Router surface (`POST /api/v1/auth/*`)

- **`POST /register`** — `RegisterIn{email,username,password,full_name?}` →
  `{access_token, refresh_token, token_type:"bearer", expires_in:604800, user}`.
  Persists the user (pbkdf2 hash) and issues a session sid.
- **`POST /login`** — `LoginIn{email_or_username, password}` → same envelope.
  Verifies via `verify_password`; 401 on bad credentials.
- **`POST /logout`** — optional `Authorization: Bearer <access>` + optional body
  `{"refresh_token": <rt>}` (`Body(embed=True)`). Clears the session sid from the
  sessions store **and** revokes the supplied refresh token. Returns
  `{"success": true}`.
- **`POST /auth/refresh`** — `RefreshIn{refresh_token}` → `refresh_access_token`.
  `401` if the token is unknown / revoked / expired / malformed.
- **`GET /auth/me`** — returns the authenticated user (reads `sub` from the
  bearer token, never the client body).

### Logout wire format (note)
`/logout` uses `Body(default=None, embed=True)` so the refresh token is supplied
as `{"refresh_token": "..."}` in the JSON body, with the access token in the
`Authorization` header. The `embed=True` is required because a single scalar
`Body()` parameter otherwise expects the *raw* body string (which yields a 422
`Input should be a valid string` error).

## 5. Security invariants (tested)

- `_SECRET_KEY` is random/ephemeral when unset; never a hard-coded default.
- Access/refresh tokens are `HS256` JWTs signed with `_SECRET_KEY`; refresh
  tokens carry a `jti` and are stored/revocable.
- `test_auth.py` asserts: good password verifies, bad does not, legacy format
  still verifies, token expiry is honoured, refresh → new access → revoke → 401
  on reuse; no insecure default secret; isolation between users.
- `test_phase1_auth.py` exercises the **full HTTP lifecycle**: register →
  refresh (validates `sub` matches + new token decodes) → logout (revokes) →
  refresh again (401) → expired-token (401) → cross-user isolation.

## 6. Identity model (cross-cutting)

The authenticated principal is **always** derived from the bearer JWT `sub`:
```python
payload = decode_token(token)          # -> {"sub": user_id, ...}
user_id = payload["sub"]
```
No route trusts a `user_id` from the request **body**. See
[`DATA_OWNERSHIP.md`](./DATA_OWNERSHIP.md).
