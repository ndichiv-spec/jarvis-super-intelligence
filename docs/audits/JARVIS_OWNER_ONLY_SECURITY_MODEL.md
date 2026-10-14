# JARVIS owner-only security model

## 2026-10-13 World Workspace access update

| Boundary | Implemented | Locally verified | Integration verified | Production verified | Blocked / limit |
|---|---|---|---|---|---|
| Canonical owner identity | Existing JARVIS auth/core policy remains authoritative; no Supabase or hardcoded owner identity was added. | Auth, email-security, cookie, owner, endpoint, command-owner, and runtime ownership tests pass in the latest selection (149 passed, 2 skipped, 1 stale legacy route test deselected). | The live search test called the service with a synthetic owner principal, not a real login session. | No. | Need an actual deployment-configured owner login and non-owner rejection test on staging PostgreSQL. |
| Device enrollment/revocation | Existing authenticated endpoint gateway remains the device path; frontend does not grant access by hiding controls. | `tests/test_endpoint_gateway.py`: 5 passed, including owner-scoped registration/session attachment and disconnect/revocation behavior. | No real second device connected. | No. | Production enrollment/reconnect/revoke test requires HTTPS host and configured owner session. |
| Task owner/approval | Existing `/api/v1/commands` checks task ownership; the task panel uses HttpOnly-cookie `apiClient` calls, shows pending capability/risk metadata, and only sends approval after an explicit click. Backend stays in `AWAITING_AUTHORIZATION` until every pending node is approved. | Component and command API tests cover single and multi-node approval; no worker resume occurs after only a partial approval. | No live task service/queue run. | No. | Staging owner approval and worker resume need verification; no delegated-user feature is exposed by this change. |
| External data sharing | Search sends the user-requested query to DuckDuckGo. The implementation did not attach memory, files, unrelated conversation, or credentials. | Local tests prove direct prompt-to-query behavior and provider-unavailable fallback. | One non-sensitive documentation query was sent to real DuckDuckGo. | No. | There is no demonstrated classifier/redactor that blocks private or sensitive data embedded in a requested search query. Do not describe data-sharing policy as complete. Provider fabric is unavailable, so model privacy routing has not been exercised. |
| Storage and database policies | JARVIS API/service ownership remains the enforcement layer; no frontend-supplied owner ID is used in the task panel. | Runtime/event/task ownership tests pass against local storage. | No external database/storage. | No. | Supabase RLS/storage policies and production multi-tenant isolation are not configured or tested. |

This update covers only the current World Workspace integration work. The
owner-only production policy and JARVIS identity design recorded below are
inherited from the recovery branch; this mission did not establish production
credentials or deploy the auth service.

## Canonical principal

JARVIS retains its existing authentication system as the sole session and
identity authority: `jarvis_backend/routers/auth.py` owns login, registration,
verification, refresh, and logout routes; `jarvis_backend/core.py` resolves
JWT/API-key principals, sessions, roles, and permissions. Supabase Auth is not
configured and must not be added as a second independent authority without a
reviewed migration/federation plan.

The canonical owner is the account whose normalized stored email matches the
server-configured `JARVIS_ADMIN_EMAIL`. Production startup already refuses to
use the development placeholder when the owner email is missing. The current
change adds `is_canonical_owner` and `require_canonical_owner` in
`jarvis_backend/core.py`, applies that check to authenticated JWT and API-key
principals and refresh-token rotation, rejects non-owner production login, and
disables public registration in production. It does not trust a client-supplied
owner ID or role as proof.

## Trust boundary and controls

| Boundary | Required control | Current implementation/evidence | Remaining verification |
|---|---|---|---|
| Login and session | Verify credentials, email/account status, then restrict production sign-in to configured canonical owner | JARVIS auth router and core owner predicate; targeted auth/security selection passed 82 tests after this change | Verify production owner login and non-owner rejection against actual deployment config/secret provisioning. |
| Authenticated API | Resolve server-side principal, require valid session/API key and owner identity in production before protected work | `core.get_current_user` checks user/session/API-key state then applies canonical owner gate | Review any route bypassing standard dependencies and verify the same boundary against production PostgreSQL. |
| Registration | No arbitrary public production accounts | `POST /api/v1/auth/register` returns 403 in production; development/test account workflows remain | Verify behavior with production-configured integration deployment and no open registration aliases. |
| Refresh/revocation | Reject unauthorized owner refresh and invalidate that refresh credential; logout/session revocation remains server-side | Both refresh helpers reject non-owner production principals; `rotate_refresh_token` consumes rejected tokens | Exercise rotation reuse, logout, and revocation against supported PostgreSQL backend. |
| API keys | Hash/verify, scope, expiry/revoke and bind to owner principal | Existing API key auth flow is retained and production principal passes owner gate | Existing focused security tests passed within 82-selection; full API-key matrix and PostgreSQL tests still required. |
| Devices/connectors | Authenticate every device operation; bind record and connector ownership to principal; revoke server-side credentials | Existing endpoint gateway and connector ownership checks remain unchanged; core auth identity gate applies to standard authenticated routes | Device enrollment/revocation and all connector read/update/dispatch/delete/audit history need live-endpoint regression coverage. |
| Data/storage | Enforce ownership in API/service and database/object store; never trust a client owner ID | Runtime events are owner/session scoped; artifact storage is private/local; privileged DB path relies on application authorization | No RLS or managed object storage. Test authorization for each future direct client/storage path. |
| Consequential actions | Explicit scope/confirmation and auditable outcome; autonomy is not authorization | Existing command/capability policy infrastructure is retained | Confirm each external action's policy, idempotency, cancellation and durable audit path before enabling in production. |
| Secrets and logs | Server-only credentials, least privilege, rotation, redaction; do not log private prompts/tokens/files indiscriminately | Production Compose uses mounted secret files for key credentials; existing masking/security tests | No real secrets examined. Rotation, secret-manager behavior, log redaction and incident response not operationally tested. |

## Threat assumptions and database boundary

The browser is an access surface, never an authority. Owner identity must be
derived from a valid server-verified session/API key and the configured account
record. Device names, browser fingerprints, email strings supplied in request
bodies, and client-selected owner IDs are not credentials.

The current direct SQLAlchemy database path is server-side and uses privileged
database credentials. If the database is Supabase PostgreSQL, that path may
bypass RLS. Therefore the API and service authorization checks are essential;
RLS would be an additional layer only if identity claims and database roles
are correctly propagated. Do not expose a service-role key or database
credential to a client. Supabase Auth/RLS/Storage remain unconfigured.

## Test evidence and rollout gates

- `tests/test_auth.py` now exercises production owner acceptance, non-owner
  authenticated API and login rejection, owner login acceptance, and
  production registration denial.
- `tests/test_security_regression.py`, `tests/test_endpoint_gateway.py`, and
  `tests/test_postgres_engine_config.py` were run with auth tests: **82 passed**.
- The full offline backend selection passed **2,572 tests**, with 14 skipped
  and 13 integration tests deselected in 506.65 seconds on a disposable SQLite
  database. Live PostgreSQL behavior was not available.
- Before public deployment, stage PostgreSQL and worker tests with isolated
  data, verify no non-owner sign-in,
  test device/session revocation and connector ownership, and perform an
  owner-controlled account recovery drill.
- Production must have one configured owner identity and a strong external
  secret for credentials; this report intentionally includes no values.
