# JARVIS Brain API Key — Secret Storage & Redaction (§7)

## How the key is loaded
The remote JARVIS Brain API key (`JARVIS_BRAIN_API_KEY`) is retrieved **only**
through the project's existing secret-management layer (`infrastructure/vault/
manager.py` → `SecretsManager`), not read as a raw `os.environ` value in
application code. Routing is centralised in one accessor in
`jarvis_backend/gateway.py`:

```python
def _jarvis_brain_api_key() -> str:
    try:
        return (get_secrets_manager().get_or_none("brain_api_key") or "").strip()
    except Exception:
        return ""
```

`SecretsManager` resolves `brain_api_key` → `JARVIS_BRAIN_API_KEY` across its
configured backends (in order):

1. **Environment variables** (`EnvBackend`) — default; used when the deployment
   injects the secret into the process environment (the recommended production
   path).
2. **`.env` file** (`DotenvBackend`, `Path.cwd() / ".env"`) — development only.
3. **Encrypted vault file** (`FileBackend`, uses `cryptography.fernet`) —
   production encrypted-at-rest option (see "Production limitation" below).
4. Cloud secret managers (AWS / GCP / Azure) — pluggable via
   `SecretsManager.add_backend(...)`.

`SecretsManager.mask()` / `get_masked()` are available for any safe display.

## What is NOT done
- The key is **never** hardcoded in Python, TypeScript, React, HTML, tests, or
  docs. (Scanned by `TestBrainApiKeyLoading::test_brain_key_not_hardcoded_in_source`.)
- The key is **never** written to application logs, Observatory/structlog
  events, telemetry, error messages, or audit records.
  (Scanned by `TestBrainSecretNonDisclosure::test_brain_key_not_in_logs`.)
- The key is **never** returned from any `/api/v1/...` route.
  `/api/v1/ai/status` exposes only `brain_api_key_configured: bool` (a masked
  boolean indicator), plus `brain_endpoint`, `brain_model`, and the honest
  `brain` probe dict — never the credential.
  (Scanned by `test_status_exposes_only_masked_indicator`,
  `test_frontend_status_does_not_leak_key`, `test_probe_dict_never_contains_key`.)
- The key is **never** persisted to the application KV/database store. It is read
  at request time and used ephemerally by `_chat_via_remote_brain`, then
  discarded. `migrate_api_keys.py` and the API-key endpoints hash API keys
  (PBKDF2) and never store/recover raw values.
- The key is **never** sent to Silverwing or unrelated connectors/agents.
- `JARVIS_ADMIN_EMAIL` is never used as the API credential, and
  `JARVIS_BRAIN_API_KEY` is never used as an administrator identity (scanned by
  `TestAdminIdentity::test_admin_email_not_used_as_api_credential`).

## Brain request flow (§3/§5)
```
JARVIS  ->  Model Gateway (gateway.py)  ->  JARVIS_BRAIN_ENDPOINT
              Authorization: Bearer <JARVIS_BRAIN_API_KEY>   (only when key present)
```
Bearer auth is applied in `_chat_via_remote_brain`:
`headers["Authorization"] = f"Bearer {auth_token}"` — only when the vault
returns a non-empty key. The header is omitted (not sent) when the key is
absent, so the request fails honestly against the Brain rather than sending an
empty `Bearer ` token. The OpenAI-compatible `/v1/chat/completions` integration
and the Brain → Silverwing-fallback → cloud routing are unchanged.

## Brain health honesty (§5)
`probe_brain()` performs a real (tiny) inference against the Brain endpoint:
- endpoint unset → `{configured: False, healthy: False, detail: "JARVIS_BRAIN_ENDPOINT not set"}` (no HTTP call).
- endpoint + valid key + successful inference → `{configured: True, healthy: True, ...}`.
- endpoint + key rejected (HTTP 401) → `{configured: True, healthy: False, category: "PROVIDER_UNAVAILABLE", ...}`.
- endpoint unreachable → `{configured: True, healthy: False, category: "NETWORK_ERROR", ...}`.
- 200 with empty content → unhealthy (honesty guard).

Health is **never** fabricated from the presence of an endpoint or key alone.

## Production limitation (§7)
By default `SecretsManager()` is constructed with `[EnvBackend(), DotenvBackend()]`
only. In development this means the Brain key is read from `.env` (plaintext at
rest). To obtain **encrypted-at-rest** in production, the deployment must mount
the vault's encrypted `FileBackend`:

```python
from infrastructure.vault.manager import get_secrets_manager, FileBackend
get_secrets_manager().add_backend(FileBackend(vault_path, encryption_key=...))
```

The recommended production deployment therefore either (a) injects
`JARVIS_BRAIN_API_KEY` via the process environment from a cloud secret manager
(AWS/GCP/Azure), or (b) registers the encrypted `FileBackend`. The application
itself never writes the key to the normal KV store (`jarvis_kv`) or any
database table.