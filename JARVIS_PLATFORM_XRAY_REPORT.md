# JARVIS Platform X-Ray — 20-Point Report (A–T)

Repository: `F:\AI\Jarvis-super-intelligence-` · Audit artifacts: `.jarvis/platform-audit/*.json` · See `JARVIS_PLATFORM_XRAY.md` for the full how-to-read. Discovery-only (no production source modified).

---

**A. Authenticated surface is the exception, not the rule** · **SECURITY-RISK · CRITICAL**
11 of 15 auditable backend routers serve endpoints with **no authentication**. `system.py`, `health.py`, `platform_identity.py`, `stark.py`, `misc.py`, `ai.py`, `media.py`, `voice.py`, `codegen.py`, `billing.py`, `global_knowledge.py`, `monitoring.py`, `multimodal.py` import no `get_current_user`/`get_optional_user` (`security-map.json` auth_boundary). Only `agents`, `browser`, `developer`, `connectors`, `automation`, `auth`, `legacy`, `search`, `sandbox`, `rbac`, `extensions` are auth-gated.
*Chain stops at:* the HTTP edge — `/api/v1/system/dashboard`, `/system/launch`, `/system/provider-settings` are reachable by any caller with network access.

**B. Provider settings are stored in PLAINTEXT** · **SECURITY-RISK · CRITICAL**
`system.py update_provider-settings` (L284–296) writes `openai_api_key`, `anthropic_api_key`, `google_gemini_api_key`, `huggingface_api_key`, `stability_api_key`, `replicate_api_key`, `aws_secret_access_key`, `tavily_api_key`, `serper_api_key`, `news_api_key`, `openweathermap_api_key` **unencrypted** into the `misc` KV store (`security-map.json` provider_settings_plaintext). Contrast with connector keys (Fernet) and API keys (PBKDF2) — three schemes for one concept.
*Chain stops at:* disk — keys sit readable in `sqlite:///jarvis_data/jarvis.db` `kv_store.value`.

**C. Host-launch deny-list is real, but `/launch` is unauthenticated** · **SECURITY-RISK · CRITICAL**
`_DENY_COMMANDS` (L376–380) blocks `shutdown/reboot/halt/poweroff/...` and `POST /system/launch` returns **403** on a deny hit (verified live 09:28). Every launch is audited via `_audit_system_launch` → `audit_logs` store. But because `system.py` has no auth gate, any caller can launch an *allowed* command (e.g. `cmd.exe /c echo ok` → 200).
*Chain stops at:* authorization — the deny-list is defense-in-depth, not a substitute for auth.

**D. `localhost` (not `127.0.0.1`) self-callbacks + permissive CORS** · **SECURITY-RISK · HIGH**
Hardcoded `http://localhost:3000` in `system.py:38`, `connectors/oauth.py:202-203`, `extensions.py:596 & 922`, `connectors.py:270`; Ollama base `localhost:11434` (`core.py:593`); CORS allowlist `["http://localhost:3000","http://localhost:5173","http://localhost:5003"]` (`core.py:677`). On IPv6-default hosts `localhost`→`::1`, which can defeat loopback-pinned expectations / SSRF guards.
*Chain stops at:* the network stack — loopback identity is not pinned to `127.0.0.1`.

**E. RBAC has no object-level authorization and unbounded pagination** · **PRODUCTION-INCOMPLETE · HIGH**
`GET /rbac/users` returns `{users,total,page,per_page}` with `per_page` defaulting to 20 and **no upper bound** (verified live — unbounded `page`/`per_page` → resource-exhaustion vector). `/roles`, `/permissions`, `/audit-logs` (admin-gated 401). No per-resource ownership filter.
*Chain stops at:* the row level — any authenticated user enumerates all users/roles/permissions.

**F. Three inconsistent credential schemes for one problem** · **SECURITY-RISK · HIGH**
Connector keys: Fernet (✓); API keys: PBKDF2 hash + `jarvis_` prefix (`core.py` L458–486, ✓); provider settings: **plaintext** (✗, see B). Plus the frontend `ProviderApiKeys` type (`lib/api.ts` L327–339) and `dashboard/settings/page.tsx` placeholders expose the **shape** of every secret (`sk-…`, `AKIA…`, `tvly_…`, `hf_…`, `r8_…`).
*Chain stops at:* consistency — a future engineer stores the next keyset in plaintext because provider settings already do.

**G. The AI stack is honest-by-design, dormant-by-default** · **REAL design · FUNCTIONAL gap · HIGH**
`ProviderGateway.chat()` (`gateway.py`) has **4 routing tiers** (local torch → Phase-6 fabric → model gateway → remote brain) and **5 layered honesty guards** that raise `ChatError` rather than returning a `local-rule`/`echo`/empty answer (`ai-execution-map.json` honesty_guards). But `ai_enabled=False`, 0 providers configured, `JARVIS_BRAIN_ENDPOINT` unset → **0 tiers reachable at runtime**.
*Chain stops at:* credential availability — the honesty architecture is correct but cannot be exercised.

**H. Silverwing backend path mismatch** · **DISCONNECTED · HIGH**
`main.py L87` expects `ROOT/"silverwing-backend"`; `gateway.py L50` expects `<jarvis_backend>/silverwing-backend`. The real Silverwing source lives at the `F:\AI` root (`silverwing`, `silverwing-runtime`, `silverwing_120m`, …). Result: `import main as silverwing_main` fails, the mount is skipped, and `GET /silvering/health` returns `integrated: false`.
*Chain stops at:* `main.py integrate_silverwing` (L96–102) — the brain path is never wired.

**I. Four non-convergent "what-can-this-system-do" registries** · **DUPLICATED · HIGH**
`system._CAPABILITIES` (17 static tuples, REAL), `agents._DEFAULT_AGENTS` (static + mutable `agents` store, PARTIAL), the Phase-6 `Provider/Model` registry (external, PARTIAL), and the frontend `APP_REGISTRY` (hardcoded window array, HARDCODED) all answer "what can the system do" with **no cross-references** (`registry-map.json` convergence #1). None share provenance.
*Chain stops at:* convergence — a capability enabled in one registry is invisible to the others.

**J. The Plugin Registry is dead code** · **DISCONNECTED / UNUSED · MEDIUM**
`infrastructure/plugins/{registry,loader,lifecycle,hook}.py` exists with `install/start/stop/uninstall`, but `rg` finds **no `from infrastructure.plugins`** anywhere in `jarvis_backend` or `main.py`; `main.build_app()` never loads plugins (`registry-map.json` Plugin Registry; `sector-state-classification.json` Plugin Registry = DISCONNECTED).
*Chain stops at:* `main.build_app()` — the package is importable but never invoked.

**K. `APP_REGISTRY` is a frontend-only authority** · **HARDCODED / frontend-only · MEDIUM**
`DesktopProvider.tsx L111` holds the static `APP_REGISTRY` array that backs every desktop window; `useDesktop` (L197) is pure client state, lost on refresh, with no `get_current_user` dependency. There is **no backend desktop router**.
*Chain stops at:* the browser — window authority lives entirely in a single TSX file.

**L. ~10 dashboards fabricate telemetry with `Math.random`** · **MOCKED / HARDCODED · HIGH**
`jarvis-v10-chambers.tsx`, `jarvis-smart-home.tsx`, `analytics-dashboard.tsx`, `supreme/page.tsx`, `holographic/page.tsx`, `neural-background.tsx`, `cascade-codeviewer.tsx`, `real-time-monitoring.tsx`, `modern-dashboard-system.tsx`, `omega/page.tsx`, `knowledge-hub/page.tsx:491`, `neural-activity-map.tsx` (`truthfulness-report.json` math_random_simulated_data). Operator metrics are indistinguishable from real ones.
*Chain stops at:* trust — until these are repointed to `/system/dashboard` or `/monitoring/*`, dashboard numbers are fiction.

**M. Frontend has 3 clients, 16 stores, 4 duplicated hooks, 2 duplicated types** · **DUPLICATED · HIGH**
`jarvisAPI` (`lib/api.ts`, canonical) + `apiClient` (`lib/api-client.ts`, axios) + `systemApi` (`features/system/api.ts`, thin facade over apiClient — consumed only by a duplicated system store). 16 Zustand stores; `useSystemStore`/`useMonitoringStore`/`useChatStore`/`useAuthStore` each exported from **both** `src/stores/*` and `src/features/*/store.ts`. `SystemCapability` defined in both `types.ts:26` and `features/system/types.ts:64`. Websocket hooks duplicated in `lib/websocket.ts` and `hooks/useWebSocket.ts`.
*Chain stops at:* the import path — the reader must guess which module is canonical.

**N. Capability notions are fragmented across 4 subsystems** · **DUPLICATED · MEDIUM**
`system._CAPABILITIES[needs_ai]` (system.py), `agents.capabilities=['codegen','review','execute','email']` (agents.py), connector `ActionSpec.capabilities`, and the RBAC `permissions` list — four capability vocabularies, none cross-referenced (`registry-map.json` convergence #3, `sector-state-classification.json`).
*Chain stops at:* unification — an agent's capability gate and a connector's capability gate and an RBAC permission never agree on a name.

**O. Scheduler + n8n automation are stubs** · **HARDCODED / PRODUCTION-INCOMPLETE · MEDIUM**
`agents.py:207` returns `{running:true,interval:60,next_run:None}` (static stub; `/system/dashboard` truthfully reports `scheduler_running:false`). `automation._n8n_headers()` returns empty when `N8N_API_KEY` is absent (no key in `.env`).
*Chain stops at:* execution — `GET /automation` lists tasks but nothing runs them on schedule.

**P. §1 Capability Registry + §2 Platform Identity are implemented, tested, live-verified** · **REAL · GREEN**
`system.py _CAPABILITIES` (17 tuples, L60–78): `GET /api/v1/system/capabilities` → 200, each entry carries `dependencies`, `provenance:"jarvis_backend/routers/system.py:capabilities"`, `last_checked(now_iso)`; `ai-backed=unavailable/offline`, `platform-backed=available/ok`. `platform_identity.py`: `GET /platform/identity` → 200 (`dev-001`/verified); `PUT` rejects secret-shaped fields → 400 (verified 09:28). `tests/test_platform_identity.py` = 7 passed.
*Chain is live end-to-end.*

**Q. `SystemMonitor.tsx` was repointed to live backend truth** · **REAL · GREEN**
Now fetches `/system/dashboard` every 5s → CAPABILITIES panel via `jarvisAPI.getCapabilities()`; fetches `/platform/identity` once → PLATFORM verification chip; no `psutil`, no `Math.random`, dropped `useMonitoringStore`/recharts (`frontend-architecture-map.json` data_flow_capabilities_and_platform). `tsc --noEmit` = 0.
*Chain is the template* for the remaining ~9 simulated dashboards (L).

**R. 27 routers, but only 15 carry auth** · **SECURITY-RISK · CRITICAL**
`rg -n "APIRouter|@router."` enumerates 27 routers (`agents, ai, automation, auth, billing, browser, codegen, connectors, developer, extensions, global_knowledge, health, knowledge, legacy, media, memory, misc, monitoring, multimodal, rbac, sandbox, search, stark, system, voice, platform_identity, websocket`) + root status/health/metrics. Auth dependencies (`get_current_user`/`get_optional_user`) appear in only ~half (`security-map.json` auth_boundary).
*Chain stops at:* the dependency scan — a router file existing does not imply it is protected.

**S. The KV store is a shared spine with 16+ collections but no registry backbone** · **PARTIAL · MEDIUM**
`get_store(` census yields `users, sessions, refresh_tokens, api_keys, knowledge, memory, agents, tasks, executions, roles, permissions, audit_logs, notes, reminders, chat_sessions, chat_history, collab_tasks, multimodal_files, rss_feeds, tenant, misc` + 19 `browser_*` collections + `search_history`, `browser_semantic_cache` (~190 call-sites). All flow through one `db.py` `kv_store` table. This is the *de facto* integration bus — but nothing in the store enforces the registry/capability/identity contracts of §5.
*Chain stops at:* the schema — a single `kv_store(store_name,key,value)` table holds identity, audit, browser telemetry, and capabilities with no type-level boundary.

**T. The first upgrade sequence (security-first, then AI enablement)** · **ACTION · see `upgrade-recommendations.json`**
1. Gate `system.py` host endpoints (`get_current_user` + admin) — kills the unauthenticated `/launch`/`/provider-settings`/processes/files surface.
2. Encrypt provider settings (Fernet via `crypto.py`); drop the `ProviderApiKeys` secret-name enum + settings placeholders.
3. Pin `localhost`→`127.0.0.1` in self-callbacks + CORS.
4. Clamp RBAC pagination + add object-level ownership.
5. Collapse frontend 3-client/4-duplicate-store/duplicated-types/websocket duplication.
6. Migrate the ~10 `Math.random` dashboards to `/system/dashboard`.
7. Configure provider credentials so `ai_enabled=True` **behind the existing honesty guards** (the single AI lever).
8. Fix the Silverwing path so `integrated:true`.
9. Retire or wire the dead/orphaned registries; begin capability unification.
10. Replace the scheduler stub; complete n8n wiring.

---

## Severity roll-up

| Severity | Points |
|---|---|
| CRITICAL (attacker surface / secrets) | A, B, C, R |
| HIGH | D, E, F, G, H, I, L, M |
| MEDIUM | J, K, N, O, S, T(partial) |
| GREEN | P, Q |

## What this is not

This is an **integration & maturity audit**, not an implementation pass. Per the brief, §3–§11 were **not** implemented: nothing here was built, only traced, classified, and prioritized. The recommendations in T carry per-item `risk` fields and are gated on verification commands repeated in `JARVIS_PLATFORM_XRAY.md`.
