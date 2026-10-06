# Admin Authentication & Identity Report

**Spec sections:** #7 (admin configuration test), #16 (admin surface end-to-end),
#5 (configurable admin email), #18 (admin surface must work end-to-end).

**Date:** 2026-09-15 · **Environment:** Python 3.13, FastAPI 0.115.0, Pydantic 2.13.5.

---

## 1. Design decision (response to the original question)

The original question asked whether the admin should use the developer's personal
email / phone number, or auto-create a production org email. The implemented
decision:

- The admin identity is **explicit configuration**, not auto-derived from a
  phone number or a real person's inbox.
- A single, auditable service-account-style email is configured once via
  `JARVIS_ADMIN_EMAIL` and used as the seeded admin sign-in for *every* backend
  product the platform fronts (OAuth providers, API-key services, automation).
- The platform never fabricates or signs up its own org email; the operator
  supplies the canonical admin address and password at deploy time
  (`start_all.psm1` / `start_all.ps1`).

This keeps sign-in ownership auditable, avoids tying the admin to a personal
inbox, and removes any hardcoded production identity from source.

---

## 2. Configuration surface

| Variable | Where | Purpose |
|---|---|---|
| `JARVIS_ENV` | `core.is_production()` | `development` (default) vs `production`/`prod`. Opt-in production mode. |
| `JARVIS_ADMIN_EMAIL` | `core.admin_email()` | The seeded admin's sign-in email. |
| `JARVIS_ADMIN_PASSWORD` | `core.start_backend()` | Password for the seeded admin (supplied by the launcher, never logged). |
| `JARVIS_SECRET_KEY` | `core._SECRET_KEY` | JWT + Fernet signing key. **Must be set in production** (random per-process otherwise). |

Documented in `.env.example`:

```dotenv
JARVIS_ENV=development
JARVIS_ADMIN_EMAIL=admin@jarvis.local
JARVIS_ADMIN_PASSWORD=
```

---

## 3. Behaviour matrix (`core.admin_email()`)

```
JARVIS_ADMIN_EMAIL  ──► configured admin identity (dev OR prod)
       │
  unset & JARVIS_ENV in {production, prod}  ──► RuntimeError  (fail-fast)
       │
  unset & anything else (dev / unset)       ──► admin@jarvis.local  (dev placeholder)
```

Rules:
1. **`JARVIS_ADMIN_EMAIL` wins** when set (development *or* production).
2. **Development default** `admin@jarvis.local` is used only when the variable
   is unset **and** `JARVIS_ENV` is not a production value.
3. **Production** (`JARVIS_ENV=production`/`prod`) **requires**
   `JARVIS_ADMIN_EMAIL`; the platform **refuses to start** with a clear
   `RuntimeError` instead of falling back to the placeholder.
4. The hardcoded placeholder is **never** treated as a real production identity.

### Startup wiring (`core.start_backend`)
`admin_email()` is resolved **before** the password-admin seeding block, so a
production misconfiguration fails at startup — not at first login:

```python
admin_email_address = admin_email()          # raises in prod if unset
admin_pw = os.environ.get("JARVIS_ADMIN_PASSWORD")
if admin_pw:
    ...users[uid] = { ..., "email": admin_email_address, "roles": ["admin"], ...}
```

---

## 4. Admin surface — end-to-end (§16)

The admin account (`id 00000000-0000-0000-0000-000000000001`, `roles: ["admin"]`)
is seeded by `start_backend()` when `JARVIS_ADMIN_PASSWORD` is set, and can:

1. **Sign in** at `POST /api/v1/auth/login` with the configured email + password.
   Returns `{access_token, refresh_token, token_type, expires_in, user}`.
2. **Manage users** — `GET/POST/PUT/DELETE /api/v1/rbac/users` (admin-gated).
3. **Manage roles** — `GET/POST/PUT/DELETE /api/v1/rbac/roles`.
4. **Manage tenant settings** — `GET/PUT /api/v1/rbac/tenant/settings`.
5. **Read audit** — `GET /api/v1/rbac/audit-logs` and `GET /audit-logs/export`.
6. **Issue/rotate API keys** — `POST /api/v1/auth/api-keys` (raw key shown once).

The admin email flows through as the authenticated principal via the JWT `sub`:
routes derive identity **only** from the bearer token, never from the request body
(see `AUTH_ARCHITECTURE.md` §6 / `DATA_OWNERSHIP.md`).

### Tests (`tests/test_security_regression.py::TestAdminSurface` + `::TestAdminConfig`)
```
test_dev_default_admin_email            PASS  → admin@jarvis.local
test_dev_uses_configured_email          PASS  → dev-team@example.com
test_prod_missing_admin_email_raises    PASS  → RuntimeError
test_prod_with_configured_email         PASS  → admin@example.org
test_prod_aliases_recognized            PASS  → "prod" recognized
test_start_backend_fail_fast_in_prod    PASS  → start_backend() raises
test_start_backend_seeds_configured_admin  PASS  → seeded user has configured email
test_admin_login_uses_configured_email  PASS  → login returns 200 + email
test_admin_login_uses_configured_prod_email PASS
```

---

## 5. UTC / token time hygiene (related, §8)

`now_iso()` previously used `datetime.utcnow()` (naive, deprecated in 3.12+). It
now returns timezone-aware ISO-8601 UTC with a `Z` suffix, and `now()` is
time-zone aware. This removes the class of bug where a naive "now" timestamp is
compared against an aware expiry and silently appears expired (the root cause of
the `expires_at` regression documented in the Security Regression Report).

```python
def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
```

**Test:** `test_utc_now_is_timezone_aware`.

---

## 6. Operational checklist for operators

- Set `JARVIS_SECRET_KEY` (32+ random chars) — never commit it.
- In production: `JARVIS_ENV=production` + `JARVIS_ADMIN_EMAIL=<real admin email>`.
- Set `JARVIS_ADMIN_PASSWORD` on first boot; rotate it immediately via
  `PUT /api/v1/auth/change-password` or a password reset flow.
- Do **not** run with the `admin@jarvis.local` placeholder in production — the
  platform will refuse to boot if you try.
