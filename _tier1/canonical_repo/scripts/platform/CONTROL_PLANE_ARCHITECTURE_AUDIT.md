# JARVIS Control Plane Architecture Audit Report

## Executive Summary

This audit examines the JARVIS control-plane architecture across 12 key areas, documenting existing capabilities, storage backends, and implementation patterns.

---

## A. Architecture Map

### Core Control Plane Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    JARVIS Control Plane                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Main API  │───▶│    Gateway   │───▶│   Provider Fabric │   │
│  │   (FastAPI) │    │  (Provider  │    │   (Phase 6)      │   │
│  │             │    │   Gateway)  │    │                  │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Service    │    │  Capability  │    │  Health/Observer │   │
│  │  Registry   │    │  Registry    │    │                   │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Desired/   │    │   Store      │    │    Cache         │   │
│  │  Observed   │    │   (PostgreSQL│    │   (Redis/Memory) │   │
│  │   State     │    │    /SQLite)  │    │                  │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## B. Existing Control-Plane Components

### 1. Model Registry

**Location:** `F:/AI/Jarvis-super-intelligence-/jarvis_data/model_lifecycle/model_lifecycle.jsonl`

**Status:** FILESYSTEM-BACKED (JSONL)

**Structure:** Lines are JSON objects with fields:
- `record_id`, `provider`, `model_id`, `lifecycle_type`
- `name`, `family`, `revision`, `lifecycle_stage`
- `capabilities`, `deployment`, `architecture`
- `source`, `discovered_at`, `history`
- `metadata` (source_evidence_id, evaluation_results, etc.)

**Lifecycle Types Found:**
- `jarvis_base` - Base models (Qwen3-4B Base)
- `jarvis_candidate` - SFT candidates
- `local_model` - Silverwing models

**Missing:** No durable SQL-backed model registry exists in the control plane.

### 2. Provider Registry

**Location:** `F:/AI/backend/control_plane/` and `F:/AI/providers/`

**Canonical Implementation:** `F:/AI/providers/` (source truth for Phase 6)

**Components:**
| Component | Path | Purpose |
|-----------|------|---------|
| `registry.py` | `providers/registry.py` | ProviderRegistry singleton - holds adapters |
| `bootstrap.py` | `providers/bootstrap.py` | bootstrap_fabric() - constructs adapters |
| `routing.py` | `providers/routing.py` | ProviderRouter - routes by capability/cost |

**Registered Providers (from bootstrap.py):**
- `openai` - OpenAI GPT models
- `nvidia` - NVIDIA NIM
- `google` - Google Gemini
- `aws` - AWS Bedrock
- `huggingface` - HuggingFace Inference API

**Additional Providers (from silverwing-backend/model_provider.py):**
- `anthropic` - Claude API
- `groq` - GroqCloud
- `deepseek` - DeepSeek API
- `ollama` - Local Ollama
- `llamacpp` - Local llama.cpp
- `bedrock` - AWS Bedrock
- `vertex` - Google Vertex AI
- `local` - Local rule fallback
- `silverwing` - Silverwing runtime

### 3. Secret/Credential Architecture

**Canonical Implementation:** `F:/AI/infrastructure/vault/manager.py`

**Secret Resolution Path:**
```
provider_adapter ──via──> SecretManager.get() ──through──> [EnvBackend, DotenvBackend, VaultFileBackend]
```

**Secret Management Flow:**
1. `providers/bootstrap.py` - Creates adapters with `secrets=SecretManager()`
2. `infrastructure/vault/manager.py` - `SecretsManager` class with fallback backends
3. `infrastructure/config/settings.py` - Settings that reference secrets

**Key Files:**
- `infrastructure/vault/manager.py` - Primary (canonical) secrets manager
- `providers/secrets.py` - Provider fabric secrets (imports from vault/manager.py)
- `jarvis_backend/gateway.py` - Uses `get_secrets_manager()` for brain keys
- `jarvis_backend/core.py` - Uses `os.environ` for JWT secret key

**Important Distinction:** Two separate secret managers exist but are not duplicates:
- `infrastructure/vault/manager.py` - General platform secrets (canonical)
- `providers/secrets.py` - Provider fabric secrets (uses same pattern, different class)

### 4. Artifact Registry

**Location:** `F:/AI/Jarvis-super-intelligence-/jarvis_data/model_lifecycle/model_lifecycle.jsonl`

**Status:** FILESYSTEM-BACKED (JSONL)

**Missing:** No durable artifact/checksum tracking in database.

### 5. Job/Training Registry

**Status:** NOT IMPLEMENTED as durable service

**Existing:** 
- `F:/AI/Jarvis-super-intelligence-/jarvis_data/learning/` - Lesson JSON files
- `F:/AI/silverwing/training/` - Training scripts

**Missing:** No PostgreSQL-backed job registry, logs storage, or experiment tracking.

### 6. Knowledge/Memory

**Knowledge Store:**
- **Location:** `infrastructure/knowledge/`
- **Storage:** In-memory / filesystem (no PostgreSQL backing)
- **Components:** `KnowledgeStore`, `IndexManager`, `ContextManager`, `RAGPipeline`

**Memory (from core.py):**
- **Storage:** PostgreSQL-backed via `Store` class (`jarvis_kv` table)
- **Collections:** `knowledge`, `memory`, `sessions`, `chat_sessions`, etc.

**Status:** Mixed - Knowledge is filesystem/in-memory, Memory is PostgreSQL-backed.

### 7. Observability

**Location:** `F:/AI/infrastructure/observability/`

**Components:**
- `metrics.py` - Counters, gauges, histograms
- `tracer.py` - Distributed tracing with contextvars
- `middleware.py` - Observability middleware for FastAPI

**Also in Backend:**
- `jarvis_backend/observability.py` - Gateway event recording
- Tests: `tests/test_observation.py`, `tests/test_metrics.py`

**Status:** IN-MEMORY (no durable event storage)

### 8. API/Control Plane Endpoints

**Location:** `F:/AI/Jarvis-super-intelligence-/jarvis_backend/routers/`

**Endpoints Available:**
| Router | Key Endpoints | Auth Required |
|--------|---------------|---------------|
| `auth.py` | /login, /register, /logout, /api-keys | Mixed (some public) |
| `ai.py` | /chat, /generate, /models | User + optional system |
| `health.py` | /health, /api/v1/health/status, /api/providers, /api/models | Public |
| `provider_status.py` | Provider health endpoints | Mixed |
| `system.py` | System status | Public |
| `knowledge.py` | Knowledge CRUD | User |
| `memory.py` | Memory operations | User |
| `sandbox.py` | Code execution | User |
| `browser.py` | Browser automation | User |
| `research.py` | Research tools | User |

**Auth Pattern:** Uses `get_current_user` dependency from `core.py` with JWT tokens or API keys.

### 9. Security Boundaries

**Authentication:**
- JWT tokens (24h expiry)
- API keys (longer-lived, with scopes)
- OAuth (OIDC via `identity` module)

**Authorization:**
- Role-based (user, admin, developer)
- Scope-based for API keys
- `_require_admin()`, `_require_owner()` helpers in core.py

**Previously Identified Issues:**
- Some routers in `Jarvis-super-intelligence-/jarvis_backend/routers/` may have unauthenticated endpoints
- The `/health` endpoints are public by design
- Admin endpoints have proper gating via `_require_admin()`

### 10. Persistence Mapping

| Entity | Current Storage | Durable? | PostgreSQL Model? | Redis Role? | Implementation |
|--------|-----------------|----------|-------------------|-------------|----------------|
| Users | `jarvis_kv` table | YES | YES | N/A | SQL-backed Store |
| Sessions | `jarvis_kv` table | YES | YES | N/A | SQL-backed Store |
| Chat Messages | `jarvis_kv` table | YES | YES | N/A | SQL-backed Store |
| Knowledge | `F:/AI/jarvis_data/knowledge/` | PARTIAL | NO | N/A | JSON files |
| Memory | `jarvis_kv` table | YES | YES | N/A | SQL-backed Store |
| Cache | Redis + Memory | YES | NO | PRIMARY | RedisCache (RESIDUAL) |
| Audit Logs | `jarvis_kv` table | YES | YES | N/A | SQL-backed Store |
| Model Registry | `.jsonl` file | PARTIAL | NO | N/A | Filesystem |
| Provider Registry | In-memory | NO | N/A | N/A | Singleton |
| Capability Registry | In-memory | NO | N/A | N/A | Singleton |
| Jobs/Training | Filesystem | PARTIAL | NO | N/A | JSON files |
| Events | Logs | NO | NO | NO | File logging |

### 11. Duplication Audit

| Subsystem | Implementations Found | Canonical |
|-----------|----------------------|-----------|
| Secret Store | 2 | `infrastructure/vault/manager.py` |
| Provider Registry | 2 | `providers/registry.py` |
| Model Registry | 1 | `model_lifecycle.jsonl` |
| Cache | 1 | `performance/cache_manager.py` |
| Database | 1 | `jarvis_backend/db.py` (primary), `backend/db.py` (unused) |
| Settings | 1 | `infrastructure/config/settings.py` |
| Authentication | 1 | `jarvis_backend/core.py` |

### 12. Test Coverage

| Component | Test File | Status |
|-----------|-----------|--------|
| Persistence | `test_phase2_persistence.py` | 9/9 PASS |
| Auth | `test_auth.py`, `test_phase1_auth.py` | EXISTS |
| Health | `test_health.py` | EXISTS |
| Redis/Cache | None found | MISSING |
| Provider Registry | `test_router_registry.py` | EXISTS |
| Security | `test_sec1_security.py` | EXISTS |

---

## C. Canonical Implementation for Each Subsystem

1. **Database:** `jarvis_backend/db.py` - SQLAlchemy backend
2. **Settings:** `infrastructure/config/settings.py` - Typed config
3. **Secrets:** `infrastructure/vault/manager.py` - Multi-backend secrets
4. **Providers:** `providers/` directory - Fabric and adapters
5. **Models:** `jarvis_data/model_lifecycle/` - JSONL registry
6. **Cache:** `performance/cache_manager.py` - Memory + Redis
7. **Knowledge:** `infrastructure/knowledge/` - In-memory RAG
8. **Memory:** `core.py` `Store` class - PostgreSQL-backed
9. **Auth:** `core.py` - JWT + API keys
10. **Health:** `health.py` router - Public endpoints
11. **Capability:** `control_plane/capabilities.py` - In-memory registry
12. **Service:** `control_plane/service_registry.py` - In-memory registry

---

## D. Duplicate/Legacy Implementations

| Duplicate | Location | Status | Recommendation |
|-----------|----------|--------|----------------|
| Database/db.py | `backend/db.py` | INACTIVE | Remove or integrate |
| Provider registry | `backend/model_gateway/` | SECONDARY | Keep as facade over providers/ |
| Health endpoint | Multiple | COEXISTENT | Consolidate under health.py router |
| Redis client | `performance/cache_manager.py` | ACTIVE | Fix RESP compatibility |

---

## E. PostgreSQL-Backed Components

| Component | Table Name | Purpose |
|-----------|------------|---------|
| KV Store | `jarvis_kv` | Universal key/value storage |
| Users | Via Store | User accounts |
| Sessions | Via Store | JWT sessions |
| Tokens | Via Store | Refresh tokens |
| Audit | Via Store | Audit logs |
| Knowledge | Via Store | Structured knowledge |
| Memory | Via Store | Conversation memory |

---

## F. Redis-Backed Components

| Component | Role | Status |
|-----------|------|--------|
| Cache | Primary cache | CONFIGURED (RESP2 fix needed) |

---

## G. Filesystem-Only Components

| Component | Location | Purpose |
|-----------|----------|----------|
| Model Registry | `jarvis_data/model_lifecycle/` | Model metadata |
| Knowledge | `jarvis_data/knowledge/` | Documents |
| Lessons | `jarvis_data/learning/` | Curriculum |
| Research | `jarvis_data/research/` | Evidence |
| Verification | `jarvis_data/verification/` | Fact checks |
| N8N | `jarvis_data/n8n/` | Workflows |

---

## H. In-Memory Components

| Component | Location | Purpose |
|-----------|----------|----------|
| Provider Registry | `providers/registry.py` | Adapter lookup |
| Capability Registry | `control_plane/capabilities.py` | Capability tracking |
| Service Registry | `control_plane/service_registry.py` | Service tracking |
| Sessions | `core.py` cache | KV cache |
| Cache | `cache_manager.py` | L1 memory cache |

---

## I. Security Gaps

| Gap | Location | Risk |
|-----|----------|------|
| No PostgreSQL secret encryption | All | Secrets in transit only |
| Raw env var fallback for JWT secret | `core.py` | Weak key possible |
| No secret rotation API | `secrets.py` | Manual rotation only |
| Audit logs not queryable | `Store` | Post-hoc analysis only |
| No RBAC in control plane | `control_plane/` | Auth runtime only |

---

## J. Durability Gaps

| Gap | Location | Impact |
|-----|----------|--------|
| Model registry is JSONL | `model_lifecycle/` | Not queryable, no relationships |
| No job/training tracking | Missing | No experiment history |
| No artifact checksums | JSONL | No integrity verification |
| Events not persisted | `observability/` | No historical analysis |
| Provider registry ephemeral | `providers/registry.py` | Loss on restart |
| Capability registry ephemeral | `control_plane/capabilities.py` | Loss on restart |

---

## K. API Gaps

| Missing API | Needed For | Current State |
|-------------|------------|---------------|
| Model Registry CRUD | Model management | Filesystem only |
| Artifact Management | Model lineage | JSONL only |
| Job/Training API | Experiment tracking | None |
| Event Query API | Observability | None |
| Capability Query | Dynamic routing | `api/capabilities` exists |
| Provider Catalog | Discovery | `api/providers` exists |

---

## L. Test Coverage

| Test Suite | Tests | Status |
|------------|-------|--------|
| Phase 2 Persistence | 9 | ALL PASS |
| Auth | 5+ | EXISTS |
| Health | 3 | EXISTS |
| Redis | 0 | MISSING |
| Control Plane | 1 | EXISTS |

---

## M. Recommended Implementation Sequence

### Phase 1: Stabilize Current State
1. ✅ **COMPLETE** - Fix Redis RESP2 compatibility (`cache_manager.py`)
2. ✅ **COMPLETE** - PostgreSQL setup and verification
3. ⏳ Run existing tests, add Redis connection tests

### Phase 2: Durable Model Registry
1. Create `models` table in PostgreSQL
2. Migrate JSONL data to database
3. Add CRUD API endpoints
4. Add artifact checksums and provenance tracking

### Phase 3: Job/Training Registry
1. Create `jobs` and `experiments` tables
2. Add job status, logs, checkpoints
3. Add training metadata and associations

### Phase 4: Event/Observability Storage
1. Create `events` table
2. Persist gateway events, health checks
3. Add query API

### Phase 5: Provider Enhancements
1. Make provider registry persistent
2. Add capability state persistence
3. Add health history tracking

---

## Conclusion

The JARVIS control-plane has a **robust but partially persistent** architecture:

- **Core services** (auth, users, sessions, memory) are PostgreSQL-backed
- **Cache** is Redis-backed (with RESP2 fix for compatibility)
- **Model registry** and **knowledge** remain filesystem-only
- **Provider/capability registries** are ephemeral

The Redis RESP2 compatibility fix is complete. PostgreSQL is operational. The next architectural step should be making the model registry durable with proper lineage tracking.

---

*Audit date: 2026-09-24*
*Auditor: Poolside Agent*