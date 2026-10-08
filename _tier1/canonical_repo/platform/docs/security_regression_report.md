# Security Regression Report

**Spec sections covered:** #6 (auth testing), #8 (expiration bug), #7 (admin config),
#9 (RBAC), #10/§17 (OAuth callback validation / scope validation), #3/#11
(secret non-disclosure), #6/#18 (admin audit logging).

**Date:** 2026-09-15 · **Environment:** Python 3.13, FastAPI 0.115.0, Pydantic 2.13.5,
pytest 9.1.1, `asyncio_mode=auto`, in-memory SQLite (`JARVIS_TEST_MODE=1`).

---

## 1. Test results (before → after)

### AUTH TESTS BEFORE (baseline, run before any code change)
```
pytest tests/test_auth.py tests/test_phase1_auth.py \
       tests/test_secret_leakage.py tests/test_oauth_framework.py -q
→ 41 passed
```
Broader pre-existing suite (8 files incl. backend/gmail/connectors): **78 passed, 1 skipped**.

### AUTH TESTS AFTER (same surface + hardened paths + new regression suite)
```
pytest tests/test_auth.py tests/test_phase1_auth.py \
       tests/test_secret_leakage.py tests/test_oauth_framework.py \
       tests/test_backend.py tests/test_gmail_oauth_connector.py \
       tests/test_security_regression.py -q
→ 93 passed   (53 existing + 40 new regression tests)
```

### RBAC TESTS AFTER
All 8 RBAC cases in `tests/test_security_regression.py::TestRBAC` pass, and every
`jarvis_backend/routers/rbac.py` route is now authenticated:
```
TestRBAC ........ 8 passed
```

### REGRESSIONS
Full collected suite after changes:
```
pytest tests/ -q   →  221 passed, 1 skipped   (exit 0)
```
The single skip is **pre-existing** (identical to the baseline); zero failures
were introduced. No existing test was modified to pass.

> **Verdict: no regressions.** The `.dict()` → `.model_dump()` change, the
> `now_iso()` UTC fix, the `expires_at` fix, and the new RBAC auth gates are all
> covered by passing tests.

---

## 2. Bugs fixed

| # | Location | Bug | Fix |
|---|----------|-----|-----|
| 1 | `routers/auth.py` `create_api_key` | `expires_at` was set to `now_iso()` → every expiring API key was **immediately expired**; `expires_in_days` was ignored. | Now `iso_expire_at(body.expires_in_days)` (future, `days` from now, UTC). New `core.is_api_key_expired()` helper + `expired` flag on the key-listing endpoint. |
| 2 | `routers/rbac.py:207`, `routers/system.py:204` | Deprecated Pydantic v1 `.dict()` on v2 (emits `PydanticDeprecationWarning`; silent shim today, removed in future Pydantic). | `.model_dump()` (v2 API); compatibility preserved (`exclude_none=True` equivalent). |
| 3 | `routers/rbac.py` (all routes) | The entire RBAC admin surface (`/rbac/users`, `/roles`, `/audit-logs`, `/tenant/settings`, mutations) had **no authentication dependency** → unauthenticated anyone could list/create/delete users and roles. | Added `_require_admin` on mutations + `_require_auth` on reads (see `rbac_report.md`). |
| 4 | `core.py` `now_iso()` / `now()` | Used `datetime.utcnow()` (deprecated in 3.12+, returns a **naive** datetime that silently mis-compares with timezone-aware values — the root class of tz/`expires_at` hazards). | `datetime.now(timezone.utc)` (+ `.isoformat()` with `Z` suffix). `now()` now timezone-aware. |

### The `expires_at` bug — root-cause analysis (§8)
- **Timezone handling:** the old `now_iso()` returned a *naive* datetime. The OAuth
  token layer (`connectors/oauth.py`) stores `access_expires_at` as a **numeric
  epoch** and compares with `float(exp) <= time.time() + 30` (correct, in UTC).
  The API-key layer used a *string* timestamp from the buggy `now_iso()`. Mixing
  naive-string and epoch comparisons is what made expiry silently broken.
- **UTC consistency:** `now_iso()` is now timezone-aware UTC (`…Z`). `iso_expire_at`
  computes `now(timezone.utc) + timedelta(days)`.
- **Expiration comparison:** `is_api_key_expired()` parses ISO-8601-UTC *or* numeric
  epoch via `_iso_to_epoch()` (robust to `Z`/`+00:00`/bare numbers), so a key is
  expired iff `_iso_to_epoch(expires_at) < now`.
- **Refresh behavior:** OAuth refresh (`access_token()` in `oauth.py`) lazily
  re-exchanges via the stored refresh token; unaffected and already tested.
- **Expired-token behavior:** `decode_token()` (JWT) returns `None` for `exp < now`;
  verified by `test_expired_token_rejected` + `test_phase1_auth` (401 on reuse).
- The exception was **not suppressed** — the comparison logic was corrected and
  asserted by `test_access_token_expiry_*` and `test_*_api_key_expired_*`.

---

## 3. Admin configuration (§7) — tested

| Scenario | `JARVIS_ENV` | `JARVIS_ADMIN_EMAIL` | `JARVIS_ADMIN_PASSWORD` | Result |
|---|---|---|---|---|
| Dev, unset | — | unset | — | defaults to `admin@jarvis.local` |
| Dev, configured | `development` | `dev-team@example.com` | — | uses configured email |
| **Prod, unset** | `production` | unset | — | **`RuntimeError`** (fail-fast) |
| Prod, configured | `production` | `prod-admin@example.com` | set | seeds admin with configured email |

`core.admin_email()` is the single source of truth; `start_backend()` calls it
**before** any admin seeding so production misconfiguration dies at startup, not
at first login. `admin@jarvis.local` is never used as a real production identity —
it is a dev-only placeholder.

```
test_admin_config_uses_production_email → PASS
test_prod_missing_admin_email_raises      → PASS  (RuntimeError)
test_start_backend_fails_in_prod        → PASS  (fail-fast via start_backend())
```

---

## 4. Token expiry (§8) — tested

| Case | Expectation | Test |
|---|---|---|
| valid token | `decode_token` returns payload | `test_valid_token_decodes` |
| near-expiry token | still valid (`exp == now` → accepted; strict `<` not `<=`) | `test_near_expiry_token_still_valid` |
| expired token | `decode_token` returns `None` | `test_expired_token_rejected` |
| refresh token lifecycle | valid → mints access; expired → `None` | `test_refresh_token_lifecycle`, `test_refresh_token_rejected_when_expired`, `test_phase1_auth` |
| API-key `expires_at` future | `_iso_to_epoch(exp) > now` | `test_expires_at_is_in_the_future`, `test_create_api_key_endpoint_sets_future_expiry` |
| API-key expired/none/grace | `is_api_key_expired` correct | `test_is_api_key_expired_helpers` |
| `now_iso()` tz-aware | ISO-8601 UTC, `Z` suffix, `tzinfo` set | `test_utc_now_is_timezone_aware` |

---

## 5. RBAC (§9) — tested

Canonical role set seeded by `core._seed_canonical_roles()`:
`owner`, `admin`, `operator`, `developer`, `analyst`, `viewer`.

| Check | Test |
|---|---|
| all 6 canonical roles present | `test_canonical_roles_seeded` |
| admin/owner carry `*` (wildcard) permissions | `test_admin_role_has_wildcard_permissions` |
| viewer is read-only (no `*` / no writes) | `test_least_privilege_viewer` |
| admin → 200 create role | `test_admin_authorized_to_create_role` |
| regular user → **403** | `test_regular_user_denied_create_role` |
| no auth → **401** | `test_no_auth_denied` |
| owner (via `*` perm in store) → 200 | `test_owner_role_grants_admin_access` |
| tenant-settings PUT (`.model_dump` path) → 200 | `test_tenant_settings_model_dump_works_for_admin` |

Full details: [`rbac_report.md`](./rbac_report.md).

---

## 6. OAuth callback validation + scope (§10/§17) — tested

| Check | Test |
|---|---|
| tampered state → `OAuthError` (CSRF defence) | `test_state_tamper_detected` |
| kind mismatch on exchange → `OAuthError` | `test_state_kind_mismatch_rejected` |
| state past TTL → `OAuthError` ("expired") | `test_state_expires_after_ttl` |
| Gmail authorize URL uses read-only `gmail.readonly` | `test_gmail_authorize_url_uses_readonly_scope` |
| Gmail never auto-requests `gmail.send`/`gmail.compose` | `test_gmail_authorize_url_uses_readonly_scope` |
| Outlook uses `Mail.Read`, not `Mail.Send`/`Mail.ReadWrite` | `test_outlook_authorize_url_uses_read_scope` |
| tokens **encrypted at rest** (Fernet, `fernet:` prefix; plaintext never persisted) | `test_tokens_encrypted_at_rest` |
| `connection_metadata` never exposes tokens | `test_connection_metadata_never_exposes_tokens` |

Full details: [`oauth_integration_report.md`](./oauth_integration_report.md).

---

## 7. Secret non-disclosure (§3/§11) — tested

| Invariant | Test |
|---|---|
| `GET /api/v1/auth/api-keys` never returns `key`/`raw_key` | `test_api_key_list_never_returns_raw_key` |
| `POST /api/v1/auth/api-keys` returns `key` **once** (one-time display); the persisted record stores `hash` (PBKDF2), never the plaintext | `test_api_key_create_returns_raw_key_once` |
| API-key list/create responses contain **no** `hash`/`key`/`raw_key`; raw key absent from audit logs | `test_raw_key_not_persisted`, `test_no_secret_in_audit_logs`, `test_security_regression_raw_key_absent` |
| OAuth tokens are Fernet-encrypted in the KV store; plaintext absent from the stored blob | `test_tokens_encrypted_at_rest` |
| `connection_metadata` returns no `access_token`/`refresh_token`/`fernet:` | `test_connection_metadata_never_exposes_tokens` |
| audit logs contain no password hashes, reset passwords, or tokens | `test_audit_logs_never_contain_passwords_or_tokens` |

Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, …) are
read from environment / `JARVIS_API_KEY_*` per `.env.example`; they are never
returned by any API route and never logged.

---

## 8. Admin audit logging (§6/§18) — tested

`_audit(actor_id, action, detail)` appends `{id, actor_id, action,
resource_type:"auth", timestamp, detail}` to the `audit_logs` store for every
auth action.

| Event | Test |
|---|---|
| `register` + `login` actions recorded | `test_login_is_audited` |
| `create_api_key` recorded with the key name as `detail` | `test_api_key_creation_is_audited` |
| audit entry has the required shape + `resource_type == "auth"` | `test_audit_entry_shape` |
| audit entries never leak the plaintext password | `test_audit_logs_never_contain_passwords_or_tokens` |

The `rbac.py` admin-mutation routes (`create_role`, `delete_user`, …) write to the
same audit trail via `registry.audit` (OAuth) / the auth `_audit` path.

---

## 9. Files changed

| File | Change |
|---|---|
| `jarvis_backend/core.py` | `is_production()`, `admin_email()`; tz-aware `now_iso()`/`now()`; `_iso_to_epoch`, `iso_expire_at`, `is_api_key_expired`; `start_backend()` resolves+validates admin email (fail-fast in prod). |
| `jarvis_backend/routers/auth.py` | `create_api_key` `expires_at` bug fixed (`iso_expire_at`); `list_api_keys` strips raw key + adds `expired` status; create response no longer echoes plaintext `key`. |
| `jarvis_backend/routers/rbac.py` | `.dict()` → `.model_dump()`; `_require_admin` on mutations, `_require_auth` on reads (all 12 routes gated). |
| `jarvis_backend/routers/system.py` | `.dict()` → `.model_dump()`. |
| `jarvis_backend/core.py` | API-key at-rest: `generate_api_key`, `hash_api_key`/`verify_api_key` (PBKDF2-HMAC-SHA256, 200k iters, per-key random salt), `api_key_prefix`, `find_api_key` (prefix lookup + hash verify + lazy legacy migration), `_api_key_principal` (scopes, not inherited roles), `_strip_key_secrets`, api-key bearer auth in `get_current_user`. |
| `jarvis_backend/routers/auth.py` | API-key lifecycle routes: admin-gated `create` (one-time `key` display), `list` (secrets stripped), `delete` (soft-revoke), `rotate`; local `_require_admin`. |
| `jarvis_backend/migrate_api_keys.py` | **New** — `--dry-run` CLI to migrate any remaining plaintext `key` records to hashed `hash` (never prints secrets). |
| `tests/conftest.py` | `_reset_state` now scrubs dev/identity env vars after each test (teardown) to stop `test_env_bootstrap.py`'s global `os.environ` writes from leaking across tests. |
| `tests/test_security_regression.py` | **New** — 40 regression tests across the 7 sections above. |
| `.env.example` | Documents `JARVIS_ENV`, `JARVIS_ADMIN_EMAIL`, `JARVIS_ADMIN_PASSWORD`, Microsoft redirect URI. |

---

## 10. Remaining gaps / recommendations (not in scope but tracked)

1. **[RESOLVED] API keys were persisted with a plaintext `key` field in the `api_keys`
   store.** The *API* never disclosed it (list/create endpoints stripped it), but
   at-rest it was not hashed. Now resolved: API keys are stored one-way (PBKDF2-HMAC-SHA256,
   per-key random salt) and the plaintext is never persisted, logged, or recoverable.
   See §11 and `docs/api_key_security.md`.
2. **Frontend dev hint** (`frontend/web/src/app/login/page.tsx:174`) still prints
   `admin@jarvis.local / Admin#Jarvis1`. Accurate for dev; should be removed or
   env-driven for production builds.
3. **`core.py` module still imports fine without `python-jose`** — it is a
   hand-rolled HS256 JWT. `AUTH_ARCHITECTURE.md` still mentions `python-jose` in
   its header; doc-only, not a code defect.
4. **RBAC enforcement is role-based ("admin" or `*` permission).** Finer-grained
   per-permission enforcement (e.g. `api_key:write` gated to the `developer` role)
   is not yet wired into individual routes beyond the admin gate; the permission
   catalog is seeded and exposed at `GET /rbac/permissions` for a follow-up.

---

## 11. API-key at-rest protection (§3-§20) — resolved

**Weakness:** API-key records persisted the raw `jarvis_…` bearer token in the `api_keys`
KV store under a `key` field. Authentication compared `stored_raw_key == supplied_key`.
Although no endpoint disclosed the field, plaintext-at-rest is unacceptable for
production credential storage.

**Fix (one-way, not encryption):** the raw key is hashed before persistence and is
**never recoverable** from the store. Authentication now verifies by re-hash.

### Hashing
- Algorithm: **PBKDF2-HMAC-SHA256, 200,000 iterations, 32-byte random per-key salt**.
  Stored format: `pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>`.
- Reuses `core.hash_password`/`core.verify_password` (stdlib only; no new deps).
  Argon2id is **not** installed; bcrypt is installed but the codebase deliberately
  standardizes on stdlib PBKDF2 (`core.py` docstring: "stdlib only, no bcrypt/passlib").
- **Not** plain `SHA256(raw_key)` (rejected by §3) and **not** reversible encryption.

### Persisted record shape
```jsonc
{
  "id": "<uuid>",
  "key_id": "<uuid>",
  "user_id": "<owner uuid>",
  "owner": "<owner uuid>",
  "name": "my-key",
  "description": "...",
  "scopes": ["admin"],
  "prefix": "jarvis_b2b4f1a3",   // safe display/identification only
  "hash": "pbkdf2_sha256$200000$...",  // one-way; raw key not recoverable
  "created_at": "2026-...",
  "expires_at": "2026-...Z",
  "last_used_at": null,
  "status": "active"             // active | disabled | revoked
  // NO "key" / "raw_key" / "secret" / "token" fields
}
```

### Lifecycle
- **Create** (`POST /api/v1/auth/api-keys`, admin-gated): generates 256-bit random raw
  key (`jarvis_` + 32 hex), returns it `key`+`key_id`+`prefix`+`warning` **once**;
  persists `hash`+`prefix`+`owner`+`scopes`+`expires_at`+`status`; the `api_key` object
  in the response is stripped of `hash`/`key`.
- **List** (`GET /api/v1/auth/api-keys`): owner-scoped; returns only `key_id`, `prefix`,
  `name`, `scopes`, `created_at`, `expires_at`, `last_used_at`, `expired`, `status`.
  Never `hash`/`key`.
- **Identify by prefix**: `Authorization: Bearer jarvis_…` → `find_api_key()` extracts
  the prefix, loads candidate records, verifies via `verify_api_key` (constant-time
  `hmac.compare_digest` over PBKDF2). The prefix is for lookup only, **never** used as auth.
- **Auth** (`get_current_user`): bearer starts with `jarvis_` → `find_api_key`; checks
  revocation/disabled/expiry/scope. The raw token is never written back or logged.
- **Revoke/disable/expire** (`DELETE /api/v1/auth/api-keys/{key_id}`): soft-state change
  (`status="revoked"`, `revoked_at`); the audit record is retained. Revoked keys fail
  authentication immediately.
- **Rotate** (`POST /api/v1/auth/api-keys/{key_id}/rotate`, admin-gated): issues a new
  key once, revokes the old; the old raw key is never re-disclosed.
- **Expire**: `expires_at` honored (timezone-aware UTC); expired keys return 401.

### Backward compatibility
- **Lazy migration on auth**: `find_api_key()` detects legacy plaintext `key` records,
  verifies them with `hmac.compare_digest`, then writes `hash`+`prefix`, sets
  `status="active"`, and `del record["key"]` — upgrading in place without an outage.
- **Migration CLI**: `python -m jarvis_backend.migrate_api_keys [--dry-run]` migrates any
  remaining plaintext records in bulk. `--dry-run` reports counts only; **raw secrets are
  never printed**. Verified: exits 0, `records migrated: 0` against an already-hashed store.

### Verification (TestApiKeyAtRestSecurity)
255 passed, 1 skipped (exit 0). New regression class covers: create requires admin (403),
one-time raw `key` display, raw key **absent** from the persisted KV record (`hash`
present, `key`/`raw_key`/`secret`/`token` absent, not a fast unsalted SHA-256), list
never returns raw/hash, authenticate-succeeds / wrong-key 401 / expired 401 / revoked 401,
read-scoped key denied admin action (403), rotation (old revoked+401, new authenticates),
lazy migration of a plaintext record, and raw key absent from audit logs.
