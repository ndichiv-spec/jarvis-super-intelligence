# JARVIS Current Platform Map

**Version:** Phase 1 Documentation  
**Date:** 2026-10-01  
**Purpose:** Document existing components for evolution toward distributed, persistent, browser-accessible platform

---

## 1. OVERVIEW

### Repository Structure

```
F:/AI/
├── providers/                    # Provider Fabric (parent workspace)
│   ├── __init__.py              # Fabric bootstrap
│   ├── base.py                  # ProviderAdapter contract (spec §3, §7)
│   ├── bootstrap.py             # Fabric initialization
│   ├── capabilities.py          # Capability enum/types
│   ├── errors.py                # Provider error types
│   ├── health.py                # HealthState/ProviderHealth (spec §13, §31)
│   ├── http.py                  # HTTP utilities
│   ├── models.py                # ProviderModel, ModelRef
│   ├── registry.py              # ProviderRegistry
│   ├── routing.py               # ProviderRouter, PolicyEngine
│   ├── secrets.py               # SecretManager
│   ├── telemetry.py             # Provider telemetry
│   ├── openai_compat.py         # OpenAI compatibility layer
│   ├── aws/                     # AWS Bedrock adapter
│   ├── google/                  # Google Vertex/Gemini adapter
│   ├── huggingface/             # Hugging Face adapter
│   ├── nvidia/                  # NVIDIA NIM adapter
│   ├── nemo/                    # NVIDIA NeMo adapter
│   └── openai/                  # OpenAI adapter
│
├── jarvis_brain/                 # JARVIS Brain reasoning layer
│   ├── __init__.py              # Plugin exports
│   ├── contract.py              # Brain I/O contract
│   ├── budget.py                # TaskBudget constraints
│   ├── context_engine.py        # ContextPack, ContextLimits
│   ├── plan_validator.py        # 6-stage validation
│   ├── orchestrator.py          # PLAN→REPLAN loop
│   ├── protocol.py              # Brain↔Control state machine
│   ├── audit.py                 # Audit events, cost accounting
│   └── adapters.py              # BrainAdapter implementations
│
├── identity/                     # Platform identity (OIDC/GCP integration)
│   ├── __init__.py
│   ├── oidc.py                  # OIDC provider configuration
│   ├── router.py                # Identity routes
│   ├── session.py               # Session management
│   ├── rbac.py                  # Role-based access control
│   └── provider_center.py       # Provider Connection Center
│
├── silverwing/                   # Silverwing model/training ecosystem
│   ├── (model training code)
│
├── silverwing-backend/           # Silverwing API runtime
│   ├── main.py                  # FastAPI server (port 8010)
│   ├── model_provider.py        # ModelManager/Registry
│   └── training_advisor/        # Training advisor package
│
├── Jarvis-super-intelligence-/  # Main JARVIS platform project
│   ├── jarvis_backend/          # Backend API (main code)
│   │   ├── main.py              # Entry point, FastAPI app
│   │   ├── core.py              # Store, JWT, auth, security
│   │   ├── db.py                # SQLAlchemy KV store
│   │   ├── gateway.py           # ProviderGateway
│   │   ├── websocket.py         # WebSocket support
│   │   └── routers/             # 27 API routers
│   │
│   ├── frontend/web/            # Next.js frontend
│   │   ├── package.json         # Next 16.2.4
│   │   └── src/                 # Frontend source
│   │
│   ├── start_jarvis.py          # Launcher script
│   ├── jarvis_api.py            # Legacy entry point (uvicorn)
│   ├── jarvis_runtime.py        # Runtime integration
│   └── tests/                   # Test suite
│
└── tests/                       # Integration tests (parent workspace)
```

---

## 2. EXISTING COMPONENTS

### 2.1 Backend Entry Points

| Component | Location | Port | Status |
|-----------|----------|------|--------|
| JARVIS Backend | `jarvis_backend/main.py` | 8000 | ✅ Running |
| Silverwing Runtime | `silverwing-backend/main.py` | 8010 | ✅ Running |
| Frontend | `frontend/web/` | 3000 | ✅ Running |

### 2.2 API Routers (FastAPI)

| Router | File | Purpose | Auth Required |
|--------|------|---------|---------------|
| `ai.py` | `jarvis_backend/routers/ai.py` | AI/chat endpoints | ✅ Yes |
| `agents.py` | `jarvis_backend/routers/agents.py` | Agent management | ✅ Yes |
| `auth.py` | `jarvis_backend/routers/auth.py` | Authentication | ✅ Yes |
| `browser.py` | `jarvis_backend/routers/browser.py` | Browser engine | ✅ Yes |
| `capabilities.py` | `jarvis_backend/routers/system.py` | System capabilities | ❌ Public |
| `connectors.py` | `jarvis_backend/routers/connectors.py` | Connector API | ✅ Yes |
| `health.py` | `jarvis_backend/routers/health.py` | Health checks | ❌ Public |
| `identity.py` | `jarvis_backend/routers/identity.py` | Platform identity | ✅ Yes |
| `knowledge.py` | `jarvis_backend/routers/knowledge.py` | Knowledge base | ✅ Yes |
| `memory.py` | `jarvis_backend/routers/memory.py` | Memory operations | ✅ Yes |
| `models.py` | `jarvis_backend/routers/models.py` | Model registry | ✅ Yes |
| `platform_identity.py` | `jarvis_backend/routers/platform_identity.py` | Platform identity | ✅ Yes |
| `provider_status.py` | `jarvis_backend/routers/provider_status.py` | Provider status | ✅ Yes |
| `system.py` | `jarvis_backend/routers/system.py` | System operations | ⚠️ 11/15 unauthenticated |
| `monitoring.py` | `jarvis_backend/routers/monitoring.py` | Monitoring endpoints | ✅ Yes |
| `search.py` | `jarvis_backend/routers/search.py` | Search API | ✅ Yes |
| `voice.py` | `jarvis_backend/routers/voice.py` | Voice services | ✅ Yes |
| `rbac.py` | `jarvis_backend/routers/rbac.py` | Role management | ✅ Yes |
| `sandbox.py` | `jarvis_backend/routers/sandbox.py` | Sandbox operations | ✅ Yes |
| `websocket.py` | `jarvis_backend/routers/websocket.py` | WebSocket routing | ✅ Yes |

**Total Routers:** 27

### 2.3 ProviderGateway / ModelRouter

| Component | Location | Dependencies | Status |
|-----------|----------|--------------|--------|
| ProviderGateway | `jarvis_backend/gateway.py` | `providers/` fabric | ✅ Implemented |
| ModelRouter | `providers/routing.py` | ProviderRegistry | ✅ Implemented |
| ProviderRegistry | `providers/registry.py` | Provider adapters | ✅ Implemented |

**Routing Tiers (gateway.py):**
1. Local torch (Silverwing)
2. Phase-6 fabric
3. Model gateway
4. Remote Brain

**Honesty Guards:** 5 layers preventing fake/echo responses

### 2.4 ModelRegistry

| Component | Location | Status |
|-----------|----------|--------|
| Provider Model Registry | `providers/models.py` | ✅ Implemented |
| Silverwing Model Catalog | `silverwing-backend/model_catalog.py` | ✅ Implemented |
| Platform Model Router | `jarvis_backend/routers/models.py` | ✅ Implemented |

### 2.5 Capability Registry

| Component | Location | Status |
|-----------|----------|--------|
| System Capabilities | `jarvis_backend/routers/system.py` (`/system/capabilities`) | ✅ Live, Public |
| Provider Capabilities | `providers/capabilities.py` | ✅ Implemented |
| Tool Capabilities | `tools/` infrastructure | ✅ Present |

**Status:** §1 (Capability Registry) is verified live and tested.

### 2.6 Platform Identity

| Component | Location | Status |
|-----------|----------|--------|
| JWT Authentication | `jarvis_backend/core.py` | ✅ PBKDF2-HMAC-SHA256 |
| Refresh Tokens | `jarvis_backend/core.py` | ✅ Rotating, revocable |
| Session Management | `identity/session.py` | ✅ Implemented |
| OIDC Integration | `identity/oidc.py` | ✅ Implemented |
| Provider Center | `identity/provider_center.py` | ✅ Implemented |
| RBAC | `identity/rbac.py` | ✅ Configured |

**Status:** §2 (Platform Identity) is verified live and tested.

### 2.7 Database Usage

| Database | Purpose | Location | Status |
|----------|---------|----------|--------|
| SQLite | KV store, sessions, users | `jarvis_data/jarvis.db` | ✅ Running |
| SQLite | Silverwing persistence | `silverwing-backend/silverwing_persist.db` | ✅ Running |
| PostgreSQL | (optional) | Configured via `DATABASE_URL` | ⚠️ Not active |
| MongoDB | (optional) | Not configured | ⚠️ Not present |
| Redis | (optional) | Not configured | ⚠️ Not present |

**Store Types (core.py):**
- `users`, `sessions`, `refresh_tokens`, `oauth_identities`, `api_keys`
- `knowledge`, `memory`, `agents`, `tasks`, `missions`
- `executions`, `audits`, `chat_sessions`, `search_history`
- Browser state: `browser_sessions`, `browser_tabs`, `browser_history`

### 2.8 Connector/Tool Infrastructure

| Component | Location | External Systems | Status |
|-----------|----------|------------------|--------|
| Connector Pattern | `jarvis_backend/connectors/` | Various | ✅ Framework exists |
| Crypto | `connectors/crypto.py` | Fernet encryption | ✅ PBKDF2/Fernet |
| GitHub | `tools/` scripts | GitHub API | ⚠️ Scripts exist |
| Kaggle | `_kaggle_*.py` scripts | Kaggle API | ⚠️ Scripts exist |
| Browser | `browser_engine.py` | Browser automation | ✅ Running |
| n8n | Integration scripts | n8n workflows | ✅ Integrated |

### 2.9 JARVIS Brain Integration

| Component | Location | Status |
|-----------|----------|--------|
| Brain Adapter | `jarvis_brain/adapters.py` | ✅ Implemented |
| Context Engine | `jarvis_brain/context_engine.py` | ✅ Implemented |
| Plan Validator | `jarvis_brain/plan_validator.py` | ✅ Implemented |
| Orchestrator | `jarvis_brain/orchestrator.py` | ✅ Implemented |
| Budget System | `jarvis_brain/budget.py` | ✅ Implemented |

**Integration:** Brain is available but `ai_enabled=False` by default.

### 2.10 Silverwing Integration

| Component | Location | Status |
|-----------|----------|--------|
| Silverwing Runtime | `silverwing-runtime/` | ✅ Running on :8010 |
| Silverwing Backend API | `silverwing-backend/main.py` | ✅ Running |
| Model Provider | `silverwing-backend/model_provider.py` | ✅ Implemented |
| Health Check | `/v1/health` | ✅ Returns healthy |

**Integration Point:** Launcher starts runtime first, waits for health, then starts platform.

### 2.11 Training/Evaluation Systems

| Component | Location | Status |
|-----------|----------|--------|
| Training Scripts | `training/`, `silverwing_train.py` | ✅ Present |
| Evaluations | `evaluations/` | ✅ Present |
| Dataset Builds | `build_*.py` scripts | ✅ Present |
| Checkpoints | Various `.db` files | ✅ Available |

### 2.12 Frontend Architecture

| Component | Location | Type | Status |
|-----------|----------|------|--------|
| Framework | Next.js 16.2.4 | React/Turbopack | ✅ Running |
| Port | - | - | :3000 |
| State | Zustand (16 stores) | State mgmt | ⚠️ Duplicates exist |
| API Client | 3 modules | HTTP/WebSocket | ⚠️ Duplicated |
| Auth | JWT Bearer | Auth | ✅ Configured |

**Known Issues:**
- 4 duplicated hook names
- Duplicated `SystemCapability` type
- ~10 dashboards use `Math.random()` for telemetry

### 2.13 WebSocket/Streaming

| Component | Location | Status |
|-----------|----------|--------|
| FastAPI WebSocket | `jarvis_backend/websocket.py` | ✅ Running |
| Frontend WS Hook | `frontend/web/src/hooks/useWebSocket.ts` | ⚠️ Duplicated |
| Streaming Support | Via ProviderAdapter | ✅ Via SSE |

### 2.14 Authentication/Security

| Component | Implementation | Status |
|-----------|----------------|--------|
| Password Hashing | PBKDF2-HMAC-SHA256, 200K iterations | ✅ Secure |
| JWT Tokens | HS256, configurable TTL | ✅ Implemented |
| API Keys | PBKDF2 hash, `jarvis_` prefix | ✅ Implemented |
| Secret Isolation | Fernet encryption | ✅ Configured |
| Security Headers | Middleware in `core.py` | ✅ Applied |

### 2.15 GitHub Integration

| Component | Location | Status |
|-----------|----------|--------|
| Repository Awareness | Git metadata | ✅ Available |
| Change Detection | `_audit*.py` scripts | ✅ Present |
| CI/CD Pipeline | Not present | ⚠️ Missing |

### 2.16 Health/Monitoring

| Component | Location | Status |
|-----------|----------|--------|
| Health Endpoint | `routers/health.py` | ✅ Running |
| Provider Health | `providers/health.py` | ✅ Implemented |
| Runtime Status | `runtime_status.py` | ✅ Integrated |
| Metrics | Various monitoring routers | ✅ Available |

**Health States:** UNCONFIGURED, UNKNOWN, AUTHENTICATION_FAILED, OFFLINE, UNAVAILABLE, DEGRADED, HEALTHY, ERROR, FORBIDDEN, RATE_LIMITED, TIMEOUT

### 2.17 Startup/Deployment Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `start_jarvis.py` | Full launcher | ✅ Running |
| `start_all.ps1` | PowerShell launcher | ✅ Present |
| `stop_all.ps1` | Stop all services | ✅ Present |
| `run_10m.cmd` | Runtime start | ✅ Present |

### 2.18 Tests

| Test Category | Location | Count | Status |
|---------------|----------|-------|--------|
| Authentication | `tests/test_auth.py` | ✓ | ✅ |
| Security | `tests/test_sec1_security.py` | 25 | ✅ |
| Platform Identity | `tests/test_platform_identity.py` | ✓ | ✅ |
| Health | `tests/test_health.py` | ✓ | ✅ |
| Integration | `tests/test_integration*.py` | ✓ | ✅ |
| Provider | `tests/test_provider_*.py` | ✓ | ✅ |

**Total Tests:** 100+ tests across multiple files

### 2.19 Persistence/Recovery

| Component | Location | Status |
|-----------|----------|--------|
| Database Backups | `jarvis_data/` | ✅ SQLite files |
| Schema Migrations | `db.py` | ✅ Initial |
| Recovery Scripts | `_persist*.py` scripts | ✅ Present |
| Checkpoint Files | `*_checkpoint*` files | ✅ Available |

---

## 3. CURRENT RUNTIME STATE

### Services Running

```
✅ Silverwing Runtime    : http://127.0.0.1:8010  (health: healthy)
✅ JARVIS Platform       : http://127.0.0.1:8000  (platform ready)
✅ Frontend              : http://localhost:3000   (dev mode)
```

### Key Endpoints Verified

| Endpoint | Response | Status |
|----------|----------|--------|
| `GET /health` | 200 OK | ✅ |
| `GET /api/v1/system/capabilities` | 200 (17 capabilities) | ✅ |
| `GET /api/v1/system/dashboard` | 200 OK | ✅ |
| `GET /platform/identity` | 200 (developer_identity) | ✅ |
| `POST /system/launch {"app":"shutdown"}` | 403 Forbidden | ✅ (secure) |
| `GET /v1/health` (Silverwing) | {"status":"healthy"...} | ✅ |

---

## 4. WHAT ALREADY WORKS

### Core Functionality
- ✅ FastAPI backend with 27 routers
- ✅ JWT authentication with PBKDF2 passwords
- ✅ SQL-based KV persistence
- ✅ Provider fabric with secret isolation
- ✅ WebSocket support
- ✅ Health monitoring
- ✅ OAuth/OIDC integration
- ✅ Browser automation
- ✅ Silverwing runtime integration
- ✅ Security architecture (SEC-1 verified)

### Security
- ✅ Password hashing (PBKDF2-HMAC-SHA256)
- ✅ JWT token lifecycle
- ✅ API key security (one-way hash)
- ✅ Secret isolation (Fernet encryption)
- ✅ Security headers middleware
- ✅ Host command deny-list
- ✅ Path traversal protection
- ✅ 403 on shutdown command

### Verified Live
- ✅ Capability Registry (public)
- ✅ Platform Identity (authenticated)
- ✅ System dashboard (public)
- ✅ Provider center integration

---

## 5. WHAT IS INCOMPLETE

### Security Gaps
- ⚠️ 11 of 15 routers have **no authentication** (system.py public, others unauthenticated)
- ⚠️ Provider settings use **plaintext** (legacy migration not complete)
- ⚠️ No production CORS configuration

### AI/Provider Status
- ⚠️ `ai_enabled=False` - no provider keys configured
- ⚠️ Phase-6 fabric providers unconfigured
- ⚠️ Silverwing route mismatch in model provider
- ⚠️ No real inference happening

### Frontend Issues
- ⚠️ 10 dashboards use `Math.random()` for telemetry
- ⚠️ 4 duplicated Zustand hook names
- ⚠️ Duplicated `SystemCapability` types
- ⚠️ 3 client modules (duplicated)

### Data Stores
- ⚠️ PostgreSQL not active
- ⚠️ MongoDB not configured
- ⚠️ Redis not configured

### Registries
- ⚠️ 4 non-converging registries (system, agents, Phase-6, frontend)
- ⚠️ No lifecycle state tracking
- ⚠️ No capability status metadata

---

## 6. WHAT SHOULD BE UPGRADED

### Phase 1 Priority (Security First)

| Priority | Component | Change | Risk |
|----------|-----------|--------|------|
| 1 | Auth boundary | Add auth to 11 public routers | Medium |
| 2 | Credential isolation | Migrate all provider settings to Fernet | High |
| 3 | Provider health | Implement real health probes | Medium |
| 4 | Model registry | Add lifecycle states | Medium |
| 5 | Capability registry | Add status/metadata | Low |
| 6 | Platform identity | Add deployment revision | Low |
| 7 | Health aggregation | Unified health model | Medium |
| 8 | Connector contract | Standardize interface | Medium |
| 9 | GitHub awareness | Change detection pipeline | Medium |
| 10 | Recovery architecture | Distributed recovery plan | High |

---

## 7. WHAT MUST REMAIN UNCHANGED

### Preserved Components

| Component | Reason |
|-----------|--------|
| Security headers middleware | Prevents clickjacking, XSS |
| Shutdown deny-list | Prevents destructive command abuse |
| PBKDF2 password hashing | Industry standard, already implemented |
| Fernet secret encryption | Already applied to connectors |
| ProviderAdapter contract | Spec §3, prevents fake capabilities |
| Health state enumeration | Honest status reporting required |
| JWT refresh token pattern | Industry standard for auth |
| SQLKV store | Already working, SQLite/PostgreSQL compatible |

### Not To Be Replaced

- ❌ No second auth system
- ❌ No fake provider responses
- ❌ No hardcoded credentials
- ❌ No mirror runtimes
- ❌ No parallel architectures

---

## 8. CONNECTOR CONTRACT REFERENCES

### Native Capabilities (spec §4)
Every connector must expose:

| Method | Provider Interface |
|--------|-------------------|
| `identity` | `ProviderAdapter.provider_id`, `display_name` |
| `capabilities` | `declared_capabilities` property |
| `health` | `health()` method → `ProviderHealth` |
| `permissions` | SecretManager + authz policy |
| `connect` | Adapter `__init__` with secrets |
| `read/query` | Provider-specific methods |
| `write/execute` | Capability-based access |
| `stream` | `stream()` returning `Iterator[StreamChunk]` |
| `subscribe` | WebSocket connection |
| `audit` | Audit log append |

### Health States Reference
```python
class HealthStatus(str, Enum):
    UNCONFIGURED = "unconfigured"  # no credentials
    UNKNOWN = "unknown"              # not probed
    AUTHENTICATION_FAILED = "authentication_failed"
    OFFLINE = "offline"              # unreachable
    UNAVAILABLE = "unavailable"      # explicit unavailable
    DEGRADED = "degraded"            # partial
    HEALTHY = "healthy"              # real probe succeeded
    ERROR = "error"                  # probe exception
    FORBIDDEN = "forbidden"          # HTTP 403
    RATE_LIMITED = "rate_limited"    # HTTP 429
    TIMEOUT = "timeout"              # latency issue
```

---

## 9. FILE LOCATIONS INDEX

### Backend
- `jarvis_backend/main.py` — Entry point (FastAPI app)
- `jarvis_backend/core.py` — Store, JWT, auth, security
- `jarvis_backend/db.py` — SQLAlchemy persistence layer
- `jarvis_backend/gateway.py` — ProviderGateway

### Provider Fabric
- `providers/__init__.py` — Fabric bootstrap
- `providers/base.py` — ProviderAdapter ABC
- `providers/health.py` — Health model
- `providers/routing.py` — ProviderRouter, PolicyEngine
- `providers/registry.py` — ProviderRegistry
- `providers/secrets.py` — SecretManager

### Brain
- `jarvis_brain/__init__.py` — Plugin exports
- `jarvis_brain/orchestrator.py` — PLAN loop
- `jarvis_brain/adapters.py` — BrainAdapter

### Identity
- `identity/router.py` — Identity routes
- `identity/session.py` — Session management
- `identity/rbac.py` — RBAC

### Silverwing
- `silverwing-backend/main.py` — FastAPI server (:8010)
- `silverwing-backend/model_provider.py` — ModelManager
- `silverwing-backend/silverwing_persist.db` — Persistence

### Frontend
- `frontend/web/package.json` — Next.js 16.2.4
- `frontend/web/src/` — Source code

### Tests
- `tests/test_auth.py` — Authentication tests
- `tests/test_sec1_security.py` — Security tests (25 tests)
- `tests/test_platform_identity.py` — Identity tests

---

## 10. NEXT STEPS (PHASE 1 IMPLEMENTATION PLAN)

See `/docs/architecture/PHASE1_IMPLEMENTATION_PLAN.md`

---

*Document created to support evolutionary upgrade of JARVIS platform toward distributed, persistent, browser-accessible architecture.*

---

## 11. PHASE 1 RECOVERY REPORT (2026-10-01)

### System.py Recovery: SUCCESS

**Issue:** File `jarvis_backend/routers/system.py` was corrupted with duplicated content (3950+ lines of repeated docstrings/functions).

**Resolution:**
- Backup created: system.py.corrupted-backup-20261001_133146
- Restored from: F:/AI/_tier1/canonical_repo/platform/jarvis_backend/routers/system.py (813 lines)
- Verified: Python syntax check passed

**SEC-1 Test Results: 25/25 PASSED**
- _confined_path() - Path traversal protection verified
- launch_app() - Shutdown deny-list verified (403)
- All system endpoints properly authenticated

### Silverwing Integration: VERIFIED

**Integration Status:**
- SILVERWING_BACKEND_ROOT -> F:/AI/Jarvis-super-intelligence-/silverwing-backend
- main.app imports successfully (FastAPI)
- Health check: /v1/health -> {"status":"healthy",...}

### Services Status

| Service | Port | Status |
|---------|------|--------|
| Silverwing Runtime | 8010 | RUNNING |
| JARVIS Platform | 8000 | RUNNING |
| Frontend | 3000 | RUNNING |

---

*Document updated to reflect Phase 1 recovery and verification status*
