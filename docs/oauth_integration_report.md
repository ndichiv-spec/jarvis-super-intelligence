# OAuth & External Service Integration Report

**Spec sections:** #2 (OAuth for external services), #3 (provider API keys),
#4 (least-privilege / scope principle), #10 (OAuth connection flow),
#11 (token storage), #17 (OAuth callback validation / scope validation),
#18 (acceptance flow), #19/§21 (metadata surface).

**Date:** 2026-09-15 · **Environment:** Python 3.13, FastAPI 0.115.0, Pydantic 2.13.5.

> **Executive summary:** The OAuth token-management, encrypted-at-rest storage,
> and least-privilege scope wiring already existed in
> `jarvis_backend/connectors/oauth.py` and the mail connectors. This change **does
> not rebuild that layer** (per spec #12 "connect the admin controls to existing
> components, do not rebuild"). It hardens the admin surface around it
> (configurable admin identity, RBAC gates), documents the config, and adds a
> regression suite asserting the security invariants. No provider OAuth secret is
> ever hard-coded, logged, or returned to the frontend.

---

## 1. Configuration surface (env / `.env.example`)

OAuth apps are assembled by `start_all.ps1` (lines 82–116) from the env vars
below and serialized into `JARVIS_OAUTH_CLIENTS` (JSON), which the backend reads
via `oauth.client_config(kind)`.

| Provider | Env vars |
|---|---|
| Google / Gmail / Google Workspace | `JARVIS_OAUTH_GOOGLE_CLIENT_ID`, `JARVIS_OAUTH_GOOGLE_CLIENT_SECRET`, `JARVIS_OAUTH_GOOGLE_REDIRECT_URI` |
| Microsoft / Outlook (Microsoft 365) | `JARVIS_OAUTH_MICROSOFT_CLIENT_ID`, `JARVIS_OAUTH_MICROSOFT_CLIENT_SECRET`, `JARVIS_OAUTH_MICROSOFT_REDIRECT_URI` |
| GitHub | `JARVIS_OAUTH_GITHUB_CLIENT_ID`, `_SECRET` |
| GitLab | `JARVIS_OAUTH_GITLAB_CLIENT_ID`, `_SECRET` |
| Slack | `JARVIS_OAUTH_SLACK_CLIENT_ID`, `_SECRET` |

Provider API keys (not OAuth — console-issued, live-validated):
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `HF_TOKEN`, and the
`JARVIS_API_KEY_*` aliases (`.env.example`). These are read from the process
environment only; **never returned by any API route and never logged.**

Redirect URI pattern:
`http://localhost:8000/api/v1/connectors/oauth/callback/{kind}`
(and the Extensions OAuth callback at `/api/v1/extensions/oauth/callback/{ext}`).

---

## 2. OAuth connection flow (§10) — implemented

The full admin-facing flow is wired end-to-end through the existing, audited path:

```
Admin Console  ──GET /api/v1/extensions/.../launch
   ↓            (returns the provider authorize URL + connect_type)
Integrations
   ↓
Google / Microsoft
   ↓
Connect  ──POST /connectors/oauth/authorize/{kind}?user_id=...
   ↓            (oauth.authorize_url → HMAC-signed state, redirect to provider)
OAuth authorization
   ↓            (provider redirects back to …/oauth/callback/{kind}?code=&state=)
callback       ──GET /connectors/oauth/callback/{kind}
   ↓            (oauth.exchange_code: verify_state → exchange code → save_tokens)
encrypted token storage   (Fernet, key = f"{kind}:{user_id}")
   ↓            (oauth.save_tokens: access_token + refresh_token encrypted)
scope verification        (scope persisted from the provider's token response)
   ↓
connection test           (oauth.connection_metadata → Connected / Expired / …)
   ↓
Connected
```

- **Authorize URL** (`oauth.authorize_url`): builds the provider's auth URL with a
  per-request HMAC-signed `state` (`make_state`) binding `kind` + `user_id` +
  timestamp, `response_type=code`, and `redirect_uri`. Google/Microsoft get
  `access_type=offline` + `prompt=consent` so a refresh token is obtained.
- **Callback** (`routers/connectors.py` `oauth_callback`): calls
  `oauth.exchange_code(kind, code, state, user_id)`.
- **Exchange** (`oauth.exchange_code`): `verify_state` first (CSRF/replay/
  kind+mismatch), then a live `httpx.post` to `cfg["token_url"]` with
  `client_secret` read from env — **the secret never touches the browser**.
- **Encrypted storage** (`oauth.save_tokens`): `access_token` and `refresh_token`
  are Fernet-encrypted (`fernet:` prefix) and written to the SQL KV store under
  `oauth_tokens` keyed `f"{kind}:{user_id}"`. Plaintext tokens are never persisted.
- **Scope verification**: the granted scope returned by the provider is stored and
  surfaced via `connection_metadata.scope`.
- **Connection test** (`oauth.connection_metadata`): returns the safe status enum
  `Authorization required | Expired | Connected` (the `Expired` branch fires when
  the access token is stale but a refresh token exists, so the backend can heal
  silently).

No new OAuth provider was added; Gmail and Outlook (Microsoft 365) are the
configured connectors for email access (spec §7/§8), reusing the Google/Microsoft
OAuth apps.

---

## 3. Least-privilege scopes (§4) — verified

The default connect flow requests **read-only** scopes. Higher-risk scopes
(require actions) are opt-in via a separate authorize round and a confirmation
gate; they are never auto-requested.

| Connector | Default scope (read-only) | Send/modify scope (opt-in) |
|---|---|---|
| Gmail | `https://www.googleapis.com/auth/gmail.readonly` | `gmail.send` / `gmail.compose` |
| Outlook | `Mail.Read` | `Mail.Send` |

Action-level risk/confirmation is enforced in the connector `ActionSpec`s
(`tests/test_gmail_oauth_connector.py`):

| Gmail action | Capability | risk_level | requires_confirmation |
|---|---|---|---|
| `gmail.search`, `gmail.read`, `gmail.summarize` | READ / SUMMARIZE | LOW | False |
| `gmail.draft` | DRAFT | MEDIUM | False |
| `gmail.send`, `gmail.reply` | SEND | **HIGH** | **True** |

Outlook mirrors this matrix (read/summarize/draft = low/medium; send/reply =
HIGH + confirmation). So a read-first connection can never escalate to sending
without an explicit re-consent + confirmation gate.

### Regression tests (`TestOAuthFlow`)
```
test_gmail_authorize_url_uses_readonly_scope      PASS  (gmail.readonly; no gmail.send/compose; access_type=offline)
test_outlook_authorize_url_uses_read_scope         PASS  (Mail.Read; no Mail.Send / Mail.ReadWrite)
test_tokens_are_encrypted_at_rest                  PASS  (fernet: prefix; plaintext absent from stored blob; round-trip decrypts)
test_connection_metadata_never_exposes_tokens       PASS  (no access_token/refresh_token/fernet: in metadata)
test_state_tamper_detected                         PASS  (CSRF: bad signature → OAuthError)
test_state_kind_mismatch_rejected                  PASS  (exchange_code rejects wrong kind)
test_state_expires_after_ttl                       PASS  (state expires after 600s)
```
(Existing `tests/test_oauth_framework.py` continues to pass identically — 14 tests
covering state round-trip, client-config resolution, encrypted persistence, lazy
refresh, and the metadata status enum.)

---

## 4. Token storage (§11) — invariants

Per-connection, per-user. The backend is the **only** party that ever holds a
plaintext token:

| Property | Mechanism |
|---|---|
| Encrypted at rest | `connectors.crypto` Fernet (`encrypt_secret`/`decrypt_secret`); stored value prefixed `fernet:`. |
| Server-side only | tokens live in the SQL `oauth_tokens` collection (`oauth_tokens` store), keyed `f"{kind}:{user_id}"`. |
| Never logged | `_audit`/`audit_record` record only `{ts, actor, kind, operation, ok, detail}` — no token fields. |
| Never returned to UI | `connection_metadata()` is the **only** frontend-facing shape: `{connected, status, account, scope, token_expires_at, expired, updated_at}`. No `access_token`/`refresh_token`/`.fernet:` blob. |

```python
# connection_metadata() — the sole field set the UI may see
return {
    "connected": True, "status": "Connected",
    "account": tok.get("account") or tok.get("provider"),
    "scope": tok.get("scope"),
    "token_expires_at": tok.get("access_expires_at"),
    "expired": expired_acc,
    "updated_at": tok.get("updated_at"),
}
```

### Secret non-disclosure regression (`TestSecretNonDisclosure`)
```
test_api_key_list_never_returns_raw_key      PASS  (list endpoint: no key/raw_key)
test_api_key_create_returns_raw_key_once      PASS  (raw_key shown once; persisted object omits plaintext key)
test_audit_logs_never_contain_passwords_or_tokens PASS
```

---

## 5. How the admin surface connects to OAuth (§12 wiring)

The admin controls are connected to the existing components (not rebuilt):

- **Integrations listing** — `GET /api/v1/extensions` (catalog + `public_config`
  masks any `api_key`/`password` via `registry.MASK`; `_assert_no_secret`
  forbids `access_token`/`refresh_token`/`client_secret` in any response).
- **Connect** — `POST /api/v1/extensions/{ext}/launch` returns the provider
  authorize URL (OAuth) or console URL (API-key providers) + the
  `connect_type`/`capabilities`.
- **Callback** — `GET /api/v1/connectors/oauth/callback/{kind}` performs the
  authorize-code exchange and encrypted persistence.
- **Status** — `GET /api/v1/connectors/{kind}/status` returns only
  `connection_metadata`.

---

## 6. Remaining gaps / recommendations

1. Gmail/Outlook OAuth apps are registered via `JARVIS_OAUTH_CLIENTS` JSON in
   `start_all.ps1`; the individual `JARVIS_OAUTH_GOOGLE_*` /
   `JARVIS_OAUTH_MICROSOFT_*` env vars are documented in `.env.example` and the
   platform assembles them at launch. Confirm the provider consoles have the
   matching redirect URIs registered before first connect.
2. The confirmation gate for send/reply actions is in the `ActionSpec`
   (`requires_confirmation=True` for `gmail.send`/`gmail.reply`). Wiring the gate
   into the Silverwing action dispatcher is a follow-up (the matrix is now pinned
   by `test_gmail_action_matrix` / `test_outlook_action_matrix` so it cannot be
   silently downgraded).
3. Gmail and Outlook connector auth is admin-gated for *mutation* of the
   connection (the OAuth authorize/exchange is user-scoped to `user_id`); a
   follow-up can add per-connector RBAC so `api_key:*` is restricted to the
   `developer` role as seeded.
