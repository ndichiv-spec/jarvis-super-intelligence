# JARVIS Security Architecture — SEC-1: Unified Authentication, Authorization & Credential Boundary

> Scope: harden the backend authentication/authorization boundary, the `system.py`
> host-operation surface, and the provider-credential flow. Reused existing
> primitives; did **not** invent a second auth architecture.

## 1. Authentication Flow

```
Client
  → POST /api/v1/auth/login  (or OIDC callback / api-key bearer)
    → password verified via PBKDF2-HMAC-SHA256  (core.verify_password)
    → API-key bearer verified via PBKDF2 hash   (core.get_current_user)
    → JWT access + refresh issued  (core.create_token / core.create_refresh_token)
  → client stores tokens in memory only; sends `Authorization: Bearer <jwt>`
  → every protected request: core.get_current_user decodes JWT, looks up user
```

**Primitives reused** (all in `jarvis_backend/core.py`):

| Primitive | Role | Notes |
|-----------|------|-------|
| `get_current_user(authorization)` | authenticates every protected route | JWT HS256 (sig+expiry via `decode_token`) **or** `jarvis_` API-key bearer (PBKDF2 hash lookup); raises `401` on invalid/missing/expired |
| `get_optional_user(authorization)` | optional principal for public-but-attributed endpoints | returns user or `None` |
| `create_token` / `decode_token` / `create_refresh_token` / `refresh_access_token` | JWT lifecycle | HS256, `JARVIS_SECRET_KEY`; refresh tokens hashed at rest, expiry enforced |
| `hash_password` / `verify_password` | credential hashing | PBKDF2-HMAC-SHA256, 200 000 iters, 32-byte salt |
| `api_key_prefix` / `generate_api_key` / `is_api_key_expired` | API-key material | raw key returned once, **never persisted**; only PBKDF2 hash + `jarvis_` prefix stored |

> No new auth layer was added. The 11 routers that already imported
> `get_current_user` continue to do so; `system.py` now imports it too.

## 2. Authorization Flow

```
Client → Authentication → Current User/Session → Authorization Policy → Router → Service → Tool → Provider
```

**Single authorization boundary** (`core.py`):

| Predicate | Meaning | Tiers (SEC-1 §4) |
|-----------|---------|------------------|
| `is_admin(user)` | `"admin"` in roles **OR** `user.is_admin` **OR** any role with `*` (owner) resolved against the seeded roles store | developer/admin |
| `is_developer(user)` | `"developer"` in roles **OR** `user.developer` | developer |
| `_require_auth(user)` | any authenticated user | authenticated |
| `_require_admin(user)` | `is_admin(user)` else `403` | privileged-host |
| `_require_owner(user)` | canonical owner email match | privileged-host |

The canonical role set (seeded by `_seed_canonical_roles`) is:
`owner`, `admin`, `operator`, `developer`, `analyst`, `viewer`, `user`.
`owner` and `admin` carry the `*` wildcard permission.

`system.py` enforces **privileged-host** for destructive/host-capability
endpoints by combining `get_current_user` + `is_admin` (deny-list-first, see §5).
RBAC role management stays in `routers/rbac.py` (its own `_require_admin` is
unchanged and consistent with `core.is_admin`).

## 3. Credential Boundary

```
AI / Agent → capability request → authorization policy → credential broker → provider adapter → external provider
```

**Invariant (enforced + test-verified):** the AI/Brain layer NEVER receives raw
provider secrets. The model receives neither API keys, OAuth client secrets,
bearer tokens, passwords, private keys, nor encryption keys.

**Canonical credential abstraction** (reusing existing stores, not replacing them):

| Scheme | Where | Purpose | State |
|--------|-------|---------|-------|
| **PBKDF2** | `connectors/crypto.py` `hash_password`/`verify_password` | passwords, API keys | one-way hash, never reversible |
| **Fernet** | `connectors/crypto.py` `encrypt_secret`/`decrypt_secret` (`ferrat:`/`fernet:` prefix) | connector OAuth tokens, provider secrets | ciphertext at rest, keyed off `JARVIS_SECRET_KEY` |
| **SecretManager** | `providers/secrets.py` | provider credential broker | resolves creds **only to authorized adapters**, `assert_no_secrets()` guards model-facing payloads |

**Startup migration (P6):** `core._migrate_legacy_provider_secrets()` (called in
`start_backend` after `_seed_canonical_roles`) scans `misc.provider_settings` for
legacy plaintext secret-shaped fields and re-encrypts them to Fernet. It is
idempotent (already-`fernet:` values are skipped). Verified by
`test_plaintext_provider_secret_migrated_to_fernet` and
`test_migration_is_idempotent`.

**Broker path (P5):** provider credentials are resolved through
`providers/secrets.py` `SecretManager` and are never read into AI/model context.
The `/system/provider-settings` API never accepts or returns raw secret values
(SEE §6).

## 4. System Capability Boundary (`routers/system.py`)

Every endpoint was reviewed individually (not by filename). Authz tiers:

| Endpoint | Auth | Authz | Audit | Notes |
|----------|------|-------|-------|-------|
| `GET /system/status` | none | — | — | public by design (frontend depends) |
| `GET /system/capabilities` | none | — | — | public by design (no secrets) |
| `GET /system/dashboard` | none | — | — | public by design (reads audit summary; regression gate) |
| `GET /system/launch/apps` | none | — | — | static app catalog (metadata only) |
| `GET /system/processes` | required | admin | yes | host process list |
| `POST /system/processes/kill` | required | admin | yes | destructive |
| `GET /system/provider-settings` | required | admin | yes | secret values scrubbed to `***` |
| `PUT /system/provider-settings` | required | admin | yes | rejects secret-shaped fields → `400` |
| `GET /system/files` | required | admin | yes | path-confined to ROOT |
| `POST /system/files/read` | required | admin | yes | path-confined; `403` on traversal |
| `GET /system/clipboard` | required | admin | yes | host clipboard read |
| `POST /system/clipboard` | required | admin | yes | host clipboard write |
| `POST /system/launch` | required | admin | yes | deny-list FIRST; shutdown→403 |
| `POST /system/screenshot` | required | admin | yes | host screen capture |
| `GET /system/windows` | required | admin | yes | host window enumeration |
| `GET /system/file-structure` | required | admin | yes | host FS tree (depth-limited) |

### Destructive command lockdown (P4 — preserve, do NOT weaken)
`POST /system/launch {"app":"shutdown"}` → **403** `Refusing destructive host
command matching 'shutdown'`. The deny-list (`_DENY_COMMANDS`) is matched on the
**full command string before authentication**, so the 403 is returned even for an
unauthenticated caller — it can never be bypassed by obtaining a token. A
legitimate non-destructive launcher (`POST /system/launch {"app":"cmd","args":"/c echo hi"}`)
still works for an authorized admin.

### Path traversal (P4/P10)
`_confined_path` confines `files` / `files/read` to `ROOT`; any `..`/absolute path
resolves outside ROOT and returns `403 "Path is outside the allowed root"`.

### Error sanitization (P10)
Host-op handlers catch `Exception`, log the full trace with `logger.exception`
(server-side only), and return generic `400`/`403`/`404` messages. No traceback
or absolute host path is ever returned to the client.

## 5. Audit Boundary (P8)

`core._audit_system_action(status, action, resource, user_email, detail)` and
`system._audit_system_launch(status, app, args, actor, error)` append to the
`audit_logs` store. `actor` is the authenticated principal's email, or
`"anonymous"` for pre-auth deny-list hits (so the shutdown rejection is still
attributable without performing an authorization decision in the auditor).

Recorded: `ts`, `kind`, `status`, `action`/`resource`, `user`/`actor`, `detail`.
**Never recorded**: raw passwords, API keys, OAuth tokens, private keys, or
secret values.

## 6. Provider Settings — Secret-Shape Handling (P6/P7)

Modeled on the Platform Identity pattern:

- `GET /system/provider-settings`: returns the provider-settings dict with every
  **secret-shaped** key (`key`,`secret`,`token`,`password`,`credential`,
  `private_key`) value replaced with `***`. Key names are safe metadata only.
- `PUT /system/provider-settings`: rejects any secret-shaped field with
  `400 Refusing secret-shaped field '<k>' via provider-settings API`. No raw
  provider secret is ever written through this API.
- Legacy plaintext provider secrets in `misc.provider_settings` are migrated to
  Fernet (`fernet:` prefix) at startup (see §3).

`_SECRET_SHAPES = ("key","secret","token","password","credential","private_key")`.

## 7. Security Headers & Transport (P9)

`core.SecurityHeadersMiddleware` (registered after CORS) sets on **every**
response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(), microphone=(),
geolocation=()`, `Cache-Control: no-store`.

CORS (`core.py`) defaults to localhost dev origins; in production mode
(`is_production()`) with no explicit `JARVIS_CORS_ORIGINS` the app **refuses to
start** (fail-closed) rather than serving permissive localhost origins.

## 8. Frontend Boundary (P11)

Verified by source scan (P14): the frontend contains **no hardcoded provider
secret values** — only empty-string defaults (`openai_api_key: ""`) and field
names. Provider secret *values* never reach the frontend: the GET returns only
`***` masks, and the PUT rejects secret-shaped fields.

The `/api/v1/system/status` and `/capabilities`/`/dashboard` endpoints are
intentionally **public** (the frontend depends on them unauthenticated); they
return no secrets. All authenticated calls use `Authorization: Bearer <jwt>` and
tokens are held in memory only.

## 9. Files Changed (SEC-1)

| File | Change |
|------|--------|
| `jarvis_backend/core.py` | `is_admin`/`is_developer` centralized predicates; `_require_admin` delegates to `is_admin`; `_migrate_legacy_provider_secrets` + call in `start_backend`; `SecurityHeadersMiddleware` + prod CORS fail-closed guard |
| `jarvis_backend/routers/system.py` | deny-list-first `launch` (shutdown→403); `get_optional_user`+`is_admin` authz on host ops; `_confined_path`; provider-settings scrub+reject; `_audit_system_launch(actor=...)`; `_actor_from_request`; `logger.exception`+generic errors; `/status`/`/dashboard`/`/capabilities`/`/launch/apps` public |
| `jarvis_backend/routers/platform_identity.py` | `_SECRET_SHAPES` rejection + audit (pre-existing, preserved) |
| `jarvis_backend/routers/auth.py`, `routers/rbac.py` | reused unchanged |
| `frontend/web/src/app/dashboard/knowledge/page.tsx` | `getCategoryColor` null-guard (user-reported crash) |
| `.jarvis/platform-audit/security-matrix.json` | regenerated (auth classifications updated) + runtime-mitigation annotations |
| `.jarvis/platform-audit/_gen/build_security_matrix.py` (regenerated) | matrix auth-classifications updated + runtime-mitigation annotations |
| `tests/test_sec1_security.py` | new SEC-1 suite (**25 tests**) |

## 10. Verification

- `python -m py_compile jarvis_backend/core.py jarvis_backend/routers/system.py` → OK
- `pytest tests/test_auth.py tests/test_security_regression.py tests/test_platform_identity.py tests/test_sec1_security.py` → **101 passed**
- `tsc --noEmit -p frontend/web/tsconfig.json` → **0 errors**
- Live: `POST /api/v1/system/launch {"app":"shutdown"}` → **403**; `GET /api/v1/system/dashboard` → **200** (public regression intact)
- Admin-positive gates (legit launcher 200, provider-settings GET 200 scrubbed, PUT→400, traversal 403, audit) verified via TestClient + admin fixture (live owner credential is not in `.env`, so admin gates are proven in-process).

See `sec1-verification.json` for the machine-readable results.
