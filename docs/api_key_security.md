# API-key at-rest security (§3-§20)

This document describes how JARVIS issues, stores, authenticates, and retires
service API keys (`jarvis_…` bearer tokens) so that the **raw secret is never
persisted, logged, or recoverable**.

## Design principle

API keys are a **one-way secret**, like a password — not a token that needs to be
decrypted later.

```
raw key                  KV store
  │        ┌─────────┐    ┌──────────┐
  ├─generate           │    │          │
  │                    │    │          │
  ├─display ONCE       │    │          │
  │                    │    │          │
  ├─PBKDF2 hash  ─────►│    │  hash    │
  │   (per-key salt)   │    │  prefix  │
  │                    │    │  scopes  │
  ├─discard raw        │    │  status  │
  │                    │    │  ...     │
  └────────────────────┘    └──────────┘
```

Authentication compares by **re-hashing the supplied secret** and checking the hash
in constant time — never by comparing raw strings.

- **Algorithm:** PBKDF2-HMAC-SHA256, 200,000 iterations, 32-byte random **per-key** salt.
  Stored form: `pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>`.
- **Why not Argon2id?** `argon2-cffi` is not installed in this runtime.
- **Why not bcrypt?** `bcrypt` is present, but `core.py` deliberately standardizes on
  stdlib PBKDF2 (`hash_password` docstring: *"stdlib only, no bcrypt/passlib"*). Reusing
  the existing, reviewed implementation avoids introducing a second crypto code path.
- **Why not `SHA256(raw)`?** A fast, unsalted hash makes offline guessing trivial (§3).
  PBKDF2 with a per-key salt and high iteration count is the approved, existing
  mechanism and is reused here.
- Verification uses `hmac.compare_digest` (constant-time).

## What is persisted vs. what is not

Persisted record (`api_keys` KV store):

| Field | Purpose |
|---|---|
| `id`, `key_id` | UUID, primary key |
| `user_id`, `owner` | owning user |
| `name`, `description` | human label |
| `scopes` | authorization scopes (`["admin"]`, `["read"]`, …) |
| `prefix` | `jarvis_` + first 8 hex of the key body — **display/lookup only** |
| `hash` | `pbkdf2_sha256$…` one-way hash — **the raw key cannot be derived from this** |
| `created_at`, `expires_at`, `last_used_at` | lifecycle timestamps (UTC) |
| `status` | `active` \| `disabled` \| `revoked` |
| `revoked_at` | set on revocation |

**Never persisted:** `key`, `raw_key`, `secret`, `token`, or any reversible
encryption of the key.

## Lifecycle

### 1. Create (admin-gated)
`POST /api/v1/auth/api-keys` (requires an admin-scoped principal).

```jsonc
{
  "key_id": "c9e0…",
  "prefix": "jarvis_9f1a2b3c",
  "key": "jarvis_9f1a2b3c7e…",   // FULL raw key — shown ONCE, never again
  "warning": "Store this key securely. It will not be shown again."
}
```

Steps: generate 256-bit random raw key → return it once → hash with a fresh salt →
persist `hash`/`prefix`/`owner`/`scopes`/`expires_at`/`status` → **discard the raw
key**. The `api_key` object in the response is stripped of `hash`/`key`.

### 2. List
`GET /api/v1/auth/api-keys` — owner-scoped; returns only `key_id`, `prefix`, `name`,
`scopes`, `created_at`, `expires_at`, `last_used_at`, `expired`, `status`. Never
returns `hash` or the raw `key`.

### 3. Authentication
`Authorization: Bearer jarvis_…`:

1. `get_current_user` sees the `jarvis_` prefix → `find_api_key(token)`.
2. **Identify by prefix** — match the first 8 hex chars to a candidate record
   (the prefix is for lookup only; it is **not** used as authentication).
3. **Verify** — `verify_api_key(supplied, record["hash"])` (constant-time).
4. **Reject** if `revoked`/`disabled`, `is_api_key_expired(expires_at)`, or the
   scope is insufficient for the route.
5. Principal: `{roles: [], is_admin: "admin" in scopes}` — a key derives authority
   from its **scopes**, never from the owner’s roles (so a read-scoped key owned by
   an admin still cannot perform admin actions).

The raw bearer token is never written back to storage and never logged.

### 4. Revoke / disable / expire
- `DELETE /api/v1/auth/api-keys/{key_id}` → soft-revoke (`status="revoked"`,
  `revoked_at` set). The audit record is retained (not deleted). A revoked key
  returns 401 on the next request.
- `expires_at` is honored (timezone-aware UTC); expired keys fail auth (401).

### 5. Rotate
`POST /api/v1/auth/api-keys/{key_id}/rotate` (admin-gated):

```
old key ──verify(hash)──►  issue new key (displayed once)  ──►  hash+persist
        ──revoke old (status="revoked")                   ──►  old key 401s
```

The old raw key is never re-disclosed.

## Backward compatibility (§12)

Plaintext `key` records from before this change are **not silently broken**:

- **Lazy migration at auth:** when `find_api_key` matches a legacy record that still
  carries a plaintext `key` (and no `hash`), it verifies the raw key with
  `hmac.compare_digest`, then atomically upgrades the record — writes `hash` +
  `prefix`, sets `status="active"`, and `del record["key"]` — preserving the live key
  without an outage. An `api_key_migrated` audit event is emitted.
- **Migration CLI:** a one-shot tool migrates any remaining plaintext records in bulk:

  ```bash
  python -m jarvis_backend.migrate_api_keys            # migrate in place
  python -m jarvis_backend.migrate_api_keys --dry-run  # counts only
  ```

  Raw secrets are **never printed**. Verified: exits 0, `records migrated: 0`
  against an already-hashed store.

## Telemetry / audit safety

- `_audit_api_key(action, actor_id, detail)` records only the **key name** or safe
  **prefix** — never the raw key, hash, or any secret.
- `_strip_key_secrets(record)` removes `hash`/`key` from any record before it leaves
  a response (create one-time view, list).
- `get_current_user` uses the bearer token for lookup/verification only; it is never
  assigned to a model field or persisted.

## Constants

| Constant | Value |
|---|---|
| `API_KEY_PREFIX` | `"jarvis_"` |
| `_API_KEY_HEX_LEN` | 32 (256-bit entropy) |
| `_API_KEY_PREFIX_HEX` | 8 (safe identification prefix) |
| PBKDF2 iterations | 200,000 |
| PBKDF2 digest | SHA-256 |
| Salt | 32 random bytes, per key |
