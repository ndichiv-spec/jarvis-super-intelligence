# Canonical Frontend Capability Census

Audit scope: `frontend/web/src/app` in the canonical project, plus directly referenced client stores where needed to distinguish connected surfaces from page-local UI. This is a source audit, not an end-to-end verification of every service operation. A page calling a client method is classified as connected only to the extent that the corresponding backend route exists; this does not prove that authorization, persistence, events, and execution are complete.

## Route inventory

| Route | Capability | Source/API evidence | Classification and known gap |
|---|---|---|---|
| `/` | Public landing | No page-level API call | UI only |
| `/billing` | Billing and usage | `/api/v1/billing/usage`, `/api/v1/billing/plan` | Connected reads; billing lifecycle not verified |
| `/dashboard` | Overview | `/api/v1/status` | Partial; verify all shown status fields against response and avoid implied capabilities |
| `/dashboard/admin` | Administration | RBAC client and tenant settings | Partial; some authoritative reads exist, tenant controls degrade unavailable on read failure; roles, policies, and actions need end-to-end audit |
| `/dashboard/advanced` | Collaboration agents, tasks, code generation | `getCollaborationAgents`, `getCollaborationTasks`, `createCollaborationTask`, `generateProject` | Partial/connected; generated code is model output, not a persisted project; deploy controls need audit |
| `/dashboard/agents` | Agents, schedules, executions | Agent/scheduler/task API methods | Partial; inspect failure/empty handling and confirm all actions against runtime |
| `/dashboard/api-keys` | API-key management | API-key list/create/revoke methods | Connected surface; security, one-time secret handling, and RBAC need verification |
| `/dashboard/cognitive` | Cognitive and memory analysis | Cognitive report/profile/memory/emotion methods | Partial; verify each operation, privacy, and persistence |
| `/dashboard/commands` | Command Center | `/api/v1/commands`, capabilities, command detail, authorization and cancellation endpoints | Connected; execution details are polled. Authenticated command event stream is not integrated in the page |
| `/dashboard/connections` | Service connectors | `/api/v1/connectors`, activity, per-connector and email-test endpoints | Connected surface; authorization methods, credential vault, capability discovery and service-level verification need audit |
| `/dashboard/developer/capabilities` | Developer capability controls | `/api/v1/developer/access`, `/api/v1/developer/capabilities` | Connected; authorization boundaries and runtime execution coverage need verification |
| `/dashboard/embedded-browser` | Browser workspace | Browser feature store and embedded-browser APIs | Partial; audit store operations, backend isolation, and failure states |
| `/dashboard/extensions` | Extension catalog and lifecycle | `/api/v1/extensions` install/launch/connect/uninstall endpoints | Connected surface; permissions, package integrity, OAuth, and actual runtime state need verification |
| `/dashboard/knowledge` | Knowledge entries and patterns | Knowledge entry/pattern APIs | Partial; verify empty/error distinction and persistence |
| `/dashboard/memory` | Memory center | No page-level API call identified | UI only / backend integration missing |
| `/dashboard/monitoring` | Host telemetry and health report | Shared platform monitoring metrics; `/api/v1/monitoring/health-report` | Connected telemetry; time series contains sampled backend readings only. Optimization/recovery are unavailable, not completed actions |
| `/dashboard/operational` | Operational controls | No page-level API call identified | UI only / backend integration missing |
| `/dashboard/phase3` | Training, datasets, extensions, PWA | No active data calls on this page | Explicitly unavailable; invented sample/job/plugin/install status removed |
| `/dashboard/search` | Cross-domain search | Knowledge, global knowledge, agent and memory graph APIs | Partial; endpoint failures may be converted to empty search results and need visible source-level error reporting |
| `/dashboard/security` | Security center | No page-level API call identified | UI only / backend integration missing |
| `/dashboard/self-reliant` | Workspace file inspector | Authenticated `listFiles` and `readFile` APIs | Connected read-only; writing, shell execution, indexing, and analysis are unavailable |
| `/dashboard/sessions` | Session management | Session list/revoke/revoke-all methods | Connected surface; verify session ownership and revocation behavior |
| `/dashboard/settings` | Provider and account settings | Provider settings read/update methods; local preferences | Partial; distinguish local preferences from backend configuration and remove dead controls |
| `/dashboard/system` | Processes, apps, clipboard and system utilities | Process, app, launch and clipboard API methods | Connected surface; verify safety approvals and action outcomes |
| `/dashboard/system-status` | Health and system metrics | Health status and dashboard system-metrics endpoints | Connected reads; verify the dashboard endpoint is authoritative and returns current host data |
| `/dashboard/tier4` | Runtime/enterprise overview | Persisted commands and host metrics endpoints | Connected to supported command/host data; enterprise control-plane features and connector aggregation are unavailable |
| `/desktop` | Desktop-style workspace | No page-level API call identified | UI only / backend integration missing |
| `/enterprise-sso` | Enterprise identity configuration | SSO test endpoint | Partial; endpoint returns not implemented; no identity provider is configured or claimed connected |
| `/forgot-password` | Password reset | Password-reset client methods | Connected surface; verify delivery/token lifecycle |
| `/holographic` | Holographic/brain status | `/api/v1/holographic/state` | Partial; mock fallback removed/needs confirmation across every panel |
| `/image-generation` | Image generation | Provider settings and `/api/v1/image/generate` | Connected execution surface; history, artifact provenance and persistence need verification |
| `/knowledge-hub` | Knowledge discovery | Global trends and knowledge search APIs | Partial; source has mock fallback content and must not display it as live results |
| `/login` | Authentication | Auth store/API login flow | Connected; identity/session security and workspace selection need full journey verification |
| `/oauth/callback/[extension_id]` | Extension OAuth callback | Redirect flow; no callback exchange identified in page source | Partial; callback must be proven to exchange and persist authorization server-side |
| `/omega` | Autonomous/system overview | Metrics and health-report methods | Simulated/partial; initial model/goal/upgrade/knowledge data and time-varying progress are not authoritative |
| `/plugins` | Plugin management | No page-level backend call identified | Simulated; timed actions must be replaced by real extension lifecycle operations or disabled |
| `/register` | Account registration | Registration client method | Connected surface; tenant/workspace lifecycle and verification need full journey testing |
| `/stark-control` | Cross-system status/control | AI, scheduler, memory, global observation, voice, knowledge, tier4, Stark, monitoring and goals APIs | Connected status fan-out; partial where endpoints fail independently or are presented as one global health state |
| `/supreme` | Chat/assistant | `jarvisAPI.chat` | Connected request path; command/capability authorization, event lineage, and artifacts are not established by the page call alone |
| `/upgrade` | Package/platform upgrades | Upgrade-status/check/execute API methods | Simulated/partial; source includes mock/progress behavior; a UI status must not imply updates were applied |
| `/video-analysis` | Video analysis | Analyze, extract-frames and video-info endpoints | Connected surface; artifact lifecycle and authorization need verification |
| `/voice` | Voice interaction | Voice status, WebSocket, speech and Stark chat methods | Partial; verify microphone permission, socket auth, real transcript and same command runtime |
| `/workflows` | Workflow designer | Automation task list/run/create methods | Partial; verify persistence, validation, authorization and actual workflow execution |

## Cross-cutting runtime findings

- The canonical dashboard shell already has a shared Zustand platform store at `frontend/web/src/stores/platform-store.ts` for identity, backend/provider/host state, activity, notifications, workspace preferences and navigation context.
- The dashboard layout and shell both initialized the platform runtime and subscribed to `/ws/monitoring`; the monitoring page and browser store added additional listeners. Initialization and event subscription are now owned by `DashboardShell`; route pages consume shared state.
- Host resource normalization previously substituted zero for missing readings. It now rejects incomplete/unavailable samples, clears current readings on failure, and retains a bounded history of actual CPU samples only.
- The monitoring API contract is now represented with the backend's actual health-report shape. The page uses shared host metrics rather than polling a second copy of the same metric snapshot.
- `/ws/{topic}` previously acknowledged client messages without publishing host state. `/ws/monitoring` now emits snapshots from the real monitoring sampler; the dashboard shell owns the single subscription. API polling remains available as fallback.
- Persisted command and capability snapshots now live in the shared platform store. The shell polls the owner-scoped command list more frequently while any command is active; Command Center consumes that shared state instead of creating its own polling loop. The per-command event WebSocket `/ws/commands/{command_id}` is not yet integrated: it requires an Authorization header, which the browser's built-in WebSocket API cannot set. Do not put a bearer token in a query string as a workaround.
- Feature-specific auth, chat, and monitoring stores remain alongside the platform store. Broad consolidation should be incremental and preserve their established API/security boundaries.

## High-priority disconnected or simulated surfaces

1. `/omega`, `/plugins`, `/upgrade`, and `/knowledge-hub` contain mock data or simulated progress/action behavior; they must be wired to verified APIs or visibly marked unavailable.
2. `/dashboard/memory`, `/dashboard/security`, `/dashboard/operational`, `/desktop`, and other pages without a page-level backend call require component/store tracing before they can be considered connected.
3. `/dashboard/search` must distinguish a source error from a successful empty result.
4. SSO/OAuth callback, GitHub connector authorization and repository operations have not been verified end-to-end in the canonical app.
5. The app currently exposes several WebSocket wrappers/channels. The monitoring topic is not a server-published event stream, and command events use a separate owner-scoped endpoint.

## Classification key

- **REAL + CONNECTED**: page uses an API corresponding to a backend route; this is not a blanket production-readiness claim.
- **PARTIAL**: some real state/actions exist, but the full lifecycle, error semantics, permissions, events, or persistence are not established.
- **UI ONLY / BACKEND MISSING**: visible capability is not connected from the route.
- **SIMULATED**: display or action path includes fabricated values, timed outcomes, or mock fallback data.
- **UNAVAILABLE**: the surface explicitly indicates that implementation or a deployment service is absent.

## Verification boundary

This census is an implementation inventory, not a claim that the full 43-route acceptance suite has passed. End-to-end execution, per-role access checks, live authorization, audit persistence, workspace isolation, connector secret handling, and event delivery remain to be verified. Route imports and nested components can make additional API calls; each route's classification should be refined as those component chains are audited.
