# JARVIS Control Center — Architecture Proposal

## Purpose

Modernize the existing Settings section (`/dashboard/settings`) into a
production-grade **Control Center** for AI providers, extensions, connections,
credentials, permissions, and system configuration.

This document describes how to compose the existing abstractions into a unified
surface **without duplicating** the Provider fabric, identity layer, or
observability systems.

---

## Phase 1 — Audit Findings (summary)

### Backends already exist — DO NOT reimplement

| Concern | Module | Key types / functions |
|---|---|---|
| Provider connection status | `identity/provider_center.py` | `ProviderConnectionManager` · `all_status_safe()` · `test()` · `disconnect()` · `rotate()` |
| Provider health + capabilities | `providers/control_center.py` | `ProviderControlCenter` · `check_provider()` · `connect()` · `inspect_capabilities()` |
| Provider adapter base | `providers/base.py` | `ProviderAdapter` · `ProviderRequest` · `Message` |
| Secret management | `providers/secrets.py` | `SecretManager` · `redact()` · `set_override()` |
| Provider health enum | `providers/health.py` | `HealthStatus` (UNCONFIGURED, HEALTHY, DEGRADED, etc.) |
| Extension catalogue | `routers/extensions.py` | 59 extensions in `_rows()` · `installed`/`enabled`/`connected`/`status` |
| Connector CRUD | `routers/connectors.py` | Email/IMAP/SMTP · `public_config()` (masks secrets) · `/test` endpoint |
| RBAC / permissions | `routers/rbac.py` · `identity/permission_center.py` | `/users` · `/roles` · `/permissions` · `/audit-logs` |
| Auth (JWT + admin) | `jarvis_backend/core.py` | `get_current_user()` · `_signing_key()` · `_require_admin()` |

### APIs already serving

| Route | Router | What it returns |
|---|---|---|
| `GET /api/v1/admin/providers` | identity | Safe provider status list (no secrets) |
| `POST /api/v1/providers/{id}/test` | identity | Health probe result |
| `DELETE /api/v1/providers/{id}` | identity | Disconnect a provider |
| `POST /api/v1/admin/providers/{id}/connect` | identity | Credential-rotation / OAuth-URL hint |
| `GET /api/v1/extensions` | extensions | Extension catalogue |
| `POST /api/v1/extensions/{id}/install` | extensions | Install an extension |
| `POST /api/v1/extensions/{id}/connect` | extensions | Connect an extension |
| `GET /api/v1/connectors` | connectors | Connector list (masked) |
| `POST /api/v1/connectors/{kind}/test` | connectors | Live test (IMAP login + SMTP EHLO) |
| `GET /api/v1/system/provider-settings` | system | Legacy provider settings blob |
| `PUT /api/v1/system/provider-settings` | system | Update legacy provider settings |
| `GET /api/v1/ai/models` | ai | Phase-6 provider catalog (models, health, capabilities) |
| `GET /api/v1/rbac/users` | rbac | User/role listing (admin) |
| `GET /api/v1/rbac/permissions` | rbac | Permission listing (admin) |
| `GET /api/v1/rbac/audit-logs` | rbac | Audit log entries |

### Frontend already exists

- `lib/api-client.ts` — authenticated client (`apiClient`) with `AuthError`,
  `clearAuthToken()`, 401-refresh handling ✅ use this
- `features/auth/store.ts` — zustand auth store with `clearAuth()`
- `components/ui/*` — shadcn/ui: card, button, input, label, switch, select,
  table, tabs, dialog, badge, separator, slider, scroll-area, toast, tooltip
- `app/dashboard/settings/page.tsx` (650 lines) — legacy settings page to
  evolve, not replace
- `app/dashboard/connections/page.tsx` (540 lines) — existing email connector
  page, shows the pattern for `apiClient` + masked secrets + test
- `design-tokens.ts` — cyberpunk token system (hsl colors, gradients, shadows)

### Missing abstractions

- A **Control Center API module** on the frontend that wraps the existing
  backend routes into typed helpers (the current `settings/page.tsx` uses the
  old `lib/api.ts` `jarvisAPI` which lacks 401 handling).
- A **ConnectionStatus** view model on the frontend that merges provider
  health from `ai/models` with connection status from `admin/providers`.
- A **CredentialReference** concept: the backend already never returns raw
  secrets — the frontend needs a UI pattern that reflects "set / unset /
  managed by vault" without ever inputting a plaintext key into the form.
- A **tab navigation** system for the Control Center.

---

## Phase 2 — Architecture

### New concepts (data models)

These are **frontend + thin-backend view models** that compose with existing
types, not duplicates.

#### 1. Extension Manifest (frontend type)

```typescript
interface ExtensionManifest {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  logo: string | null;
  installed: boolean;
  enabled: boolean;
  connected: boolean;
  status: "ready" | "error" | "unconfigured" | "connected" | "disabled";
  connect_type: "oauth" | "api_key" | "local" | "none";
  key_env: string | null;
  caps: string[];
}
```

> Source: `GET /api/v1/extensions` — already returns this shape from
> `extensions.py`.

#### 2. Connection Registry entry (frontend type)

```typescript
type ConnectionStatus = "connected" | "not_connected" | "expired" | "error" | "testing";

interface ProviderConnection {
  provider: string;
  display_name: string;
  connected: boolean;
  status: ConnectionStatus;
  capabilities: string[];
  model_count: number;
  detail: string;
  last_tested: string | null;
  expires_at: string | null;
  configured: boolean;
  health: "healthy" | "degraded" | "unconfigured" | "unreachable";
  latency_ms: number | null;
}
```

> Source: `GET /api/v1/admin/providers` + `GET /api/v1/ai/models` (Phase 6
> catalog).  The backend's `all_status_safe()` already returns the safe subset;
> the frontend merges model counts + health from the Phase 6 catalog.

#### 3. Credential Reference (frontend type)

```typescript
interface CredentialRef {
  key: string;            // env var name, e.g. "JARVIS_OPENAI_API_KEY"
  provider: string;       // provider_id
  label: string;          // human-readable name
  status: "set" | "unset";
  source: "env" | "vault" | "override";
}
```

> Never stores or displays the plaintext value.  Only the backend
> `SecretManager` ever holds the raw key.

#### 4. Permission Policy (frontend type)

```typescript
interface PermissionPolicy {
  user_id: string;
  email: string;
  role: string;
  permissions: string[];
  can_approve: boolean;
}
```

> Source: `GET /api/v1/rbac/users` + `GET /api/v1/rbac/permissions`.

### Backend changes (minimal — compose, don't duplicate)

No new provider systems.  Instead:

1. **`identity/router.py`** — add a single convenience endpoint that merges
   provider connection status + Phase 6 model catalog into one payload, so the
   frontend doesn't need two calls:

   ```
   GET /api/v1/control/status
   ```

   Returns `{ providers: ProviderConnection[], extensions_count, connections_count }`.

2. **`identity/provider_center.py`** — add a `CredentialReference` list method
   that reports which env vars are set/unset **without** returning values:

   ```python
   def credential_refs(self) -> list[dict]:
       # returns [{provider, key, label, status, source}] — NO VALUES
   ```

3. **Backend tests** in `tests/` for the new endpoints (admin gating, no
   secret leakage).

### Frontend architecture

```
app/dashboard/settings/
  page.tsx              ← refactored: tabs + routing
  layout.tsx            ← (new) tab navigation shell
  components/           ← (new) Control Center components
    ControlCenterTabs.tsx
    OverviewTab.tsx
    ProvidersTab.tsx
    ExtensionsTab.tsx
    ConnectionsTab.tsx
    CredentialsTab.tsx
    PermissionsTab.tsx
    SecurityTab.tsx
    DiagnosticsTab.tsx
    DeveloperTab.tsx
  lib/
    control-center-api.ts   ← (new) typed API wrappers using apiClient
    types.ts                ← (new) ExtensionManifest, ProviderConnection, etc.
```

- Each tab is a lazy component (`next/dynamic` or direct import).
- Tabs use `useSearchParams` / `useRouter` for deep-linking
  `?tab=providers`.
- All API calls go through `apiClient` (NOT `jarvisAPI`) for consistent
  401 handling + token refresh.
- All secret fields use `type="password"` with a "show / mask" toggle and
  **never** persist the plaintext value to zustand or localStorage.
- Loading states: skeleton cards + `aria-busy`.
- Error states: inline error banner + retry button.
- All actions audited: the backend already records audit entries via
  `audit = _get_audit_log()`.

### Design-system adherence

- Colors: `design-tokens.ts` (hsl-based cyberpunk palette)
- Components: `@/components/ui/*` (shadcn/ui)
- Layout: `dashboard-shell.tsx` wrapper, `sidebar.tsx` navigation
- Icons: `lucide-react` (already imported in sidebar)
- Motion: `framer-motion` (already used in `dashboard-shell.tsx`)
- Toasts: `sonner` (already used in settings page)

### Security principles (enforced)

- **No plaintext secrets in API responses** — backend `public_config()`
  masks passwords; `SecretManager` never returns raw values outside its
  own `get()` method.
- **No credentials to frontend after storage** — the frontend only ever
  sees `{ status: "set" | "unset" }`.
- **Admin gating** — all Control Center write endpoints require
  `_require_admin()`.
- **Audit trail** — every connect/disconnect/test action records an audit
  event with user, provider, operation, permission, decision, result.

---

## Phase 3 — Frontend Control Center

### Tab structure

| Tab | Description | Key API calls |
|---|---|---|
| Overview | Dashboard summary: provider status tiles, extension count, system health | `GET /control/status` |
| AI Providers | List of providers with health tiles, Test / Connect / Disconnect actions | `GET /admin/providers`, `POST /providers/{id}/test`, `DELETE /providers/{id}` |
| Extension Hub | Browse 59 extensions, install/connect, see connected status | `GET /extensions`, `POST /extensions/{id}/install` |
| Connected Services | Email/IMAP/SMTP connectors with masked passwords | `GET /connectors`, `POST /connectors/email/test` |
| Credentials | Credential references: set/unset, rotate — no plaintext display | `GET /control/credentials` |
| Permissions | Users, roles, permissions, pending approvals | `GET /rbac/users`, `GET /rbac/permissions` |
| Security | MFA status, passkey, recent audit log | `GET /admin/identity`, `GET /admin/audit` |
| Diagnostics | System status, provider health details, env info | `GET /system/status`, `GET /ai/status` |
| Developer Settings | Model priority, local endpoints, debug flags | `GET /system/provider-settings` |

---

## Phase 4 — Implementation Plan

1. **Data models** — `control-center-api.ts` types + `types.ts`
2. **Backend** — `GET /api/v1/control/status` + `GET /api/v1/control/credentials`
3. **Frontend API** — `control-center-api.ts` wrapper around `apiClient`
4. **Tab components** — one per tab, reusing `@/components/ui/*`
5. **Settings page refactor** — `page.tsx` with tab router
6. **Tests** — backend tests for new endpoints; frontend component smoke tests

---

## Phase 5 — Validation Checklist

- [ ] Existing tests pass (`pytest tests/ --ignore=tests/test_silverwing_evaluation.py -q`)
- [ ] New backend endpoints return 401 for unauthenticated, 403 for non-admin
- [ ] New backend endpoints never return raw secret values
- [ ] Frontend loads all tabs without hydration mismatch
- [ ] Frontend shows loading / error / empty states
- [ ] Auth error (401) redirects to /login (existing `AuthError` handling)
- [ ] No plaintext secrets in network tab or localStorage
