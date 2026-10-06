# JARVIS Platform X-Ray

**Repository audit, integration & maturity report.**
Discovery-only — no production source files were modified during this phase. Only diagnostic artifacts under `.jarvis/platform-audit/` were written.

- **Repository root:** `F:\AI\Jarvis-super-intelligence-`
- **Backend entry:** `jarvis_api.py` → `uvicorn.run(app, host="0.0.0.0", port=8000)`, **no `--reload`**. Backend must be restarted after every backend edit.
- **Frontend:** `frontend/web` (Next 16.2.4 / Turbopack, :3000).
- **Verified live (09:17 / 09:28):** `GET /health`=200; `GET /api/v1/system/capabilities`=200 (17 capabilities); `POST /system/launch {app:"shutdown"}`=**403**; `GET /api/v1/system/dashboard`=200; `GET /platform/identity`=200 (`developer_identity:"dev-001"`, `verification_status:"verified"`); `PUT /platform/identity {api_key:"sk-..."}`=**400** ("Refusing secret-shaped field 'api_key'").
- **TypeScript:** `tsc --noEmit -p frontend/web/tsconfig.json` = 0.
- **Python:** `py_compile` = 0 on every touched router; `pytest tests/test_platform_identity.py` = 7 passed.

---

## Scope & method

This audit answers four questions the brief asked of §1–§5 (and the cross-cutting §8/§9/§10/§14 concerns):

1. **What exists?** — every sector/subsystem, enumerated from the repository itself (not filenames).
2. **How mature is each?** — classified by evidence: `REAL / PARTIAL / DISCONNECTED / DUPLICATED / MOCKED / HARDCODED / UNUSED / BROKEN / UNTESTED / SECURITY-RISK / PRODUCTION-INCOMPLETE / EXPERIMENTAL / DEPRECATED`.
3. **How do they talk to each other?** — cross-sector integration chains, and where each chain **stops**.
4. **What should change first?** — a prioritized, evidence-grounded upgrade sequence.

Every claim is traceable to a citation (file:line, live probe, or `rg` result). The pre-compaction discovery summary and a single `rg` re-survey per topic corroborate the narrative. Builders emit JSON via Python literals → `json.dump` (hand-serialized JSON was rejected because it produced `json.tool` delimiter errors).

> ⚠️ The `read` tool **misreports line numbers on large files** in this environment. All line numbers in the JSON artifacts are the **true disk line numbers** from `rg -n` / `py_compile` / `[IO.File]::ReadAllLines`, not the editor display. When editing builders, always re-grep the failing line with `rg -n` rather than trusting the editor ruler.

---

## The 10 artifacts (in `.jarvis/platform-audit/`)

| # | File | § | What it contains |
|---|------|---|------------------|
| 1 | `platform-inventory.json` | §1/§2 | Sector inventory: 27 routers + 34 components, each with backend/frontend location, APIs, stores, models, tests, deps, consumers/producers, current execution path. |
| 2 | `sector-state-classification.json` | §3 | 34 components classified (REAL/PARTIAL/DISCONNECTED/DUPLICATED/MOCKED/HARDCODED/UNUSED/BROKEN/UNTESTED/etc.) with per-class evidence. |
| 3 | `dependency-map.json` | §4a | Cross-sector import/call edges (who imports/depends on whom) with evidence. |
| 4 | `integration-map.json` | §4b | End-to-end chains (Provider→Registry→Router→Agent→Tool→Capability→Mission→Memory→Audit→UI) and the **exact point each chain stops**. |
| 5 | `registry-map.json` | §5 | 14 registries each answered against the 10-point questionnaire (source of truth / persistence / API / frontend+backend consumer / discovery / health / permissions / provenance / lifecycle), plus a duplication/convergence analysis. |
| 6 | `security-map.json` | §8/§14 | Auth-boundary matrix (11 of 15 routers unauthenticated), credential flow (Connector=Fernet, api-keys=PBKDF2, **provider settings=PLAINTEXT**), host-command lockdown, IPv6/localhost self-callbacks, RBAC object-level gap, audit surface. Risk register (5 CRITICAL / 9 HIGH / 3 MEDIUM / 2 LOW). |
| 7 | `truthfulness-report.json` | §9 | 10 dashboards simulating telemetry via `Math.random`; hardcoded/frontend-only state (APP_REGISTRY, backup_registry, scheduler stub, n8n stub); 3-way frontend client duplication; secret-shape exposure. |
| 8 | `frontend-architecture-map.json` | §6 | 3 client modules (jarvisAPI / apiClient / systemApi), 16 Zustand stores with **4 duplicated hook names**, duplicated `SystemCapability` type, duplicated websocket hook modules, DesktopProvider window-manager, CAPABILITIES/PLATFORM/SYSTEM_DASHBOARD data-flow. |
| 9 | `ai-execution-map.json` | §10/§11 | ProviderGateway's 4 routing tiers (local torch / Phase-6 fabric / model gateway / remote brain) + 5 honesty guards; provider/model matrix (Ollama offline, Brain unset, **Silverwing route-mismatched, Phase-6 unconfigured keys**); runtime `ai_enabled=False`. |
| 10 | `upgrade-recommendations.json` | — | 10-item prioritized first-upgrade sequence (SEC-1→SCHED-1) with evidence, files, and risk per item. |

Two narrative docs summarize the above:
- `JARVIS_PLATFORM_XRAY.md` — this file (overview + how-to-read).
- `JARVIS_PLATFORM_XRAY_REPORT.md` — 20-point report **A–T**.

---

## Headline findings (the shape of the platform)

- **Substantial but fragmented.** The repository contains a fully wired FastAPI backend (`jarvis_backend/`), 27 routers, a SQLAlchemy KV store (`db.py`), a Zustand/Next frontend, an IDE-integrated Desktop/DesktopProvider shell, and a real observability+audit+identity layer. §1 (Capability Registry) and §2 (Platform Identity) are implemented, tested and **live-verified**.
- **Security is the single biggest deficit.** **11 of 15 routers** serve endpoints with **no authentication** (the audit lists each). The worst is `system.py`, which exposes `/launch` (host command execution — only deny-list protected), `/provider-settings` (writes secret keys **plaintext** into the `misc` KV store), `/processes`, `/files`, `/screenshot`, `/clipboard`, `/windows`, and `/dashboard` **without any auth gate**. Provider settings use **plaintext** while connector keys use **Fernet** and API keys use **PBKDF2** — three inconsistent schemes.
- **AI is structurally honest but functionally dormant.** `ProviderGateway` (`gateway.py`) has 4 routing tiers and **5 layered honesty guards** that refuse to return `local-rule`/empty/echo answers and raise `ChatError` instead. But **`ai_enabled=False`**: no provider keys are configured, `JARVIS_BRAIN_ENDPOINT` is unset, and the Silverwing backend directory is **absent from the path** `main.py`/`gateway.py` expect (`silverwing-backend` vs. the real `silverwing`/`silverwing-runtime`/etc. at the `F:\AI` root). So every honest tier is reachable only in code.
- **Frontend is the second big deficit.** ~10 dashboards still fabricate telemetry with `Math.random`. The frontend maintains **3 client modules** (2 real transport clients + 1 thin facade), **16 Zustand stores with 4 duplicated hook names** (`useSystemStore`, `useMonitoringStore`, `useChatStore`, `useAuthStore` each in `src/stores/*` **and** `src/features/*/store.ts`), a **duplicated `SystemCapability` type** (`types.ts:26` vs `features/system/types.ts:64`), and **duplicated websocket hook modules** (`lib/websocket.ts` vs `hooks/useWebSocket.ts`). The exception that proves the rule: `SystemMonitor.tsx` was repointed to `/system/dashboard` + `/platform/identity` + `/capabilities` and shows **0 `Math.random`/psutil** — the correct pattern, awaiting propagation to the other 9 dashboards.
- **Registries are orphaned and non-convergent.** There are **4 separate, non-converging** registries for essentially "what can this system do": `system._CAPABILITIES` (REAL), `agents._DEFAULT_AGENTS` (PARTIAL, dual-source), the Phase-6 `Provider/Model` registry (PARTIAL, external), and the frontend `APP_REGISTRY` (HARDCODED). The `Plugin Registry` (`infrastructure/plugins/`) is **dead** (never imported by `main.build_app()`). The `Device Registry` is **absent**. None support lifecycle state.
- **§1/§2 (Capability Registry, Platform Identity) are verified live** and are the one clean chain today: `/api/v1/system/capabilities` → SystemMonitor CAPABILITIES panel; `/platform/identity` → SystemMonitor PLATFORM chip; both 200, no secrets.

---

## How to read the artifacts

- **Classification legend** (§3): `REAL` = implemented + consumed + tested; `PARTIAL` = works but gated/limited/disconnected; `DISCONNECTED` = code exists but never wired to the running app; `DUPLICATED` = same concept in ≥2 places; `MOCKED`/`HARDCODED` = fabricated/static; `UNUSED`/`DEPRECATED` = not exercised; `UNTESTED` = no test coverage; `SECURITY-RISK`; `PRODUCTION-INCOMPLETE`; `EXPERIMENTAL`; `BROKEN`; `UNTESTED`. A component may carry several.
- **Evidence** is always attached (file:line, live probe, or `rg` result). If a claim has no evidence, it is not in this report.
- **"Where the chain stops"** (§4 integration-map) is the most important field: it names the exact boundary — e.g. `system.py (no auth) → /dashboard` stops at the network trust boundary; `Phase 6 fabric (no provider keys) → ai.py` stops at credential availability; `Silverwing backend (path mismatch)` stops at `main.py integrate_silverwing` mount being skipped.
- **Upgrade sequence** (§10) is **ordered by attacker-surface impact first, then functional enablement**. Items 1–4 are security/authorization that must precede exposing more surface; item 7 (configure provider credentials) is the single toggle that moves AI from "honest but dormant" to "live behind honesty guards."

---

## Verification commands (for the reviewer)

```powershell
# backend compile + (re)start, then:
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/v1/system/capabilities
curl -s -X POST http://localhost:8000/api/v1/system/launch -d "@{_payload_shutdown.txt}"  # expect 403
curl -s http://localhost:8000/api/v1/system/dashboard
curl -s http://localhost:8000/api/v1/platform/identity

# frontend type-check (from repo root):
C:\nodejs\node-v20.20.2-win-x64\node.exe frontend/web/node_modules/typescript/bin/tsc --noEmit -p frontend/web/tsconfig.json

# validate every audit JSON:
C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe -m json.tool .jarvis\platform-audit\*.json > $null
```

---

## Constraints honored

- Discovery-only: **no production source file** was modified. Only `.jarvis/platform-audit/` artifacts were written.
- No `python3`/`py`/`node`/`npm` on PATH — full paths used throughout.
- No `2>nul` (PS 5.1 device-file error); used `> $null` sink and `json.tool > $null`.
- No inline `&&` (PS parser error) — commands sequenced with `;` or run separately.
- `rg` scoped to real source dirs (no whole-repo `--files`, which only returned `node_modules`).
- Backend restarted after each backend edit; `tsc --noEmit` re-run to confirm type truth.
