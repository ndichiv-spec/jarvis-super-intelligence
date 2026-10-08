# JARVIS Super Intelligence — Phase 1 Audit & Mapping

Audit date: 2026-09-18 · Scope: `F:\AI` + `F:\AI\Jarvis-super-intelligence-` (the git repo).
Read-only audit. No files were modified by this audit.

This document maps the existing implementation onto the checklist in spec §73 and
records the evidence for each mapped area. It exists so Phase 1 implementation is
grounded in reality and never fabricates provider availability or capabilities.

---

## 1. What actually exists today

### Runtime topology (active services)

| Service | Port | Address | Implements | Status |
|---|---|---|---|---|
| JARVIS platform (FastAPI) | 8000 | `jarvis_backend/main:app` via `jarvis_api.py` | chat, auth, extensions, connectors, agents, memory, RBAC, n8n automation, mounts `/silverwing` | live |
| Silverwing runtime | 8010 | `silverwing_runtime/server.py` | OpenAI-compatible `/v1/chat/completions`, `/v1/generate`, `/v1/models`, `/v1/health` | live (TorchBackend) |
| JARVIS Brain runtime | 8011 | `brain_runtime/server.py` | OpenAI-compatible `/v1/chat/completions`, `/v1/generate`, `/v1/models`, `/health`; backends: transformers / remote / stub | currently `stub` backend |
| frontend (Next.js 16) | 3000 | `frontend/web` | active UI, proxies `/api/*` to 8000 | live |
| n8n (automation) | 5678 | managed by `start_all.ps1` | workflows calling JARVIS tool API | optional |

### Existing model/provider layer — key files

- `Jarvis-super-intelligence-/silverwing-backend/model_provider.py` — `ModelProvider` ABC
  with 13 concrete providers: OpenAI, Anthropic, Gemini, Groq, Ollama, DeepSeek,
  LlamaCpp, Bedrock, Vertex, VLLM, OpenAICompatible, Local, Silverwing.
- `backend/model_gateway/` — platform-side `ModelGateway` + `SilverwingClient` (:8010)
  + `BrainClient` (:8011). Honesty gates reject stub/unavailable brains.
- `brain_runtime/backends/` — `BrainBackend` ABC + `TransformersBackend`, `RemoteBrainBackend`, `StubBackend`.
- `silverwing_runtime/inference.py` — `InferenceBackend` ABC + `TorchBackend`.

### Chat request flow today

```
POST /api/chat (or /api/v1/ai/process, /api/chat/stream, ws /ws/chat)
  -> ChatService._generate -> providers.ProviderGateway.chat
     -> 1. JARVIS Brain (:8011) if configured (health-gated)
     -> 2. Silverwing runtime (:8010) through ModelGateway (health-gated)
     -> 3. cloud providers through ModelRouter.route_and_chat (silverwing-backend)
     -> 4. honest failure (no fake replies)
```

### Data plane

- Storage: `jarvis_kv` single SQL table (SQLite `jarvis_data/jarvis.db`, Postgres via
  `DATABASE_URL`). Stores: agents, audit_logs, chat_sessions, executions, extensions,
  knowledge, memory, permissions, refresh_tokens, roles, sessions, users.
- Secrets: env/`.env` backends for `infrastructure/vault/manager.py` `SecretsManager`;
  `VaultFileBackend` (Fernet) exists but is **never instantiated** (dead code).
  Connector OAuth tokens: Fernet-encrypted via `connectors/crypto.py` (key = SHA-256 of
  `JARVIS_SECRET_KEY`). Extensions OAuth tokens: **stored plaintext** in `extensions`
  KV (routers/extensions.py:950). Hardened API keys: PBKDF2-hashed, non-recoverable.
- Memory: live = simple short/long-term JSON store (`routers/memory.py`); the
  `memory/` package (memory_manager, context_store, database) is 0-byte stubs; a
  Postgres schema exists in `memory/migrations/001_initial_schema.sql` (unwired).
- RAG: `infrastructure/knowledge/` (ingest, index, retrieval, rag, learning) is fully
  built but **referenced only from tests**. Live chat context = keyword overlap scoring.
- Knowledge graph: only a sample endpoint with `edges: []`. No traversal/persistence.
- Observability: request metrics live (`/api/v1/metrics`); gateway events are recorded
  into `GATEWAY_EVENT_LOG` (ring buffer) but `gateway_metrics_snapshot` has **zero
  callers** — per-provider/per-model telemetry is invisible.
- Training: `brain_training/` orchestrates Kaggle-GPU SFT for Qwen3-4B (one run `v6`
  completed; promotion **blocked** — ACL on canonical HF namespace). Silverwing-120M is
  the only fully trained + verified local artifact. `brain_training/hardware.py`:
  CPU-only dev box (no CUDA), 8 GB RAM. No online/continuous training anywhere.

---

## 2. Mapping against spec §73 checklist

### current providers
- Exists: `ModelProvider` ABC (silverwing-backend) + platform ModelGateway + brain
  backends. Uses OpenAI/Anthropic/Gemini/Groq/Ollama/DeepSeek/LlamaCpp/Bedrock/
  Vertex/vLLM/OpenAI-compatible.
- Missing: NVIDIA NIM provider; first-class Hugging Face provider class; `jarvis:`
  provider alias is advertised in catalog but unwired (falls through to LocalProvider).
- No `ProviderAdapter` type with **declared capabilities on the provider itself**
  (capabilities exist only as per-model catalog data, in three parallel abstractions
  with incompatible return types).

### current Model Gateway
- `backend/model_gateway/routing.py` `ModelGateway` with policy list
  (`silverwing_first`, `local_first`, `best_quality`, `low_cost`, `private_only`) and
  fallback order Brain → Silverwing → cloud. `TASK_CAPABILITIES` static mapping.
- Cost/privacy-aware routing exists only in the silverwing `ModelRouter`
  (model_provider.py); two independent routers, not unified.

### current authentication
- Local email/password only, PBKDF2-SHA256(200k), hand-rolled HS256 JWT
  (access 168 h, refresh 1440 h, no rotation/reuse-detection/expiry), Bearer tokens in
  localStorage, sessions DB rows with `ip/user_agent = None` and no expiry,
  `get_current_user` never checks session/refresh/status. No PKCE (HMAC `state` only),
  no HttpOnly cookies, **no OIDC user sign-in**, id_token signature never verified.
- RBAC: roles+permission catalog seeded, but enforcement is an all-or-nothing admin
  gate (`_require_admin`). No per-resource checks. `JARVIS_ADMIN_EMAIL` seeds the admin
  `00000000-…-000000000001` (roles ["admin"]); production fails fast if unset.

### current Admin Console
- `/dashboard/admin` = RBAC panel only (Users / Roles / Permissions / Audit Logs /
  Tenant Settings / Advanced JSON). No Providers / Models / Secrets / Training /
  Learning / Cloud / Cost / Security center. Silverwing Laboratory+Observatory APIs
  exist but have **no UI consumer**.

### current memory
- Short/long-term JSON store via `/api/v1/cognitive/memory/*`; simple. Working /
  episodic / semantic / procedural exist only as an unwired in-memory prototype
  (`drive_engine/knowledge_graph.py`).

### current RAG
- Built (`infrastructure/knowledge`) but unused outside tests; default embedder is a
  mock; live chat uses keyword overlap, not RAG.

### current training code
- `brain_training/` (pipeline, dataset, kaggle, hf, evaluation, promote, deploy,
  registry, status) — honest, gated, blocked at promotion. `silverwing/` CPU training
  path. Kaggle kernels for Qwen3-4B SFT + LoRA pilots. No lessons/arena/teacher node.

### current observability
- Request metrics live; gateway ring-buffer events collected but never surfaced;
  cost tracking absent; Prometheus/OTel infra unwired; analytics/alerting engines
  unreferenced.

### current secrets
- Fragmented: env → .env → Fernet vault (never wired) → Fernet connector tokens →
  plaintext extensions OAuth tokens → PBKDF2-hashed API keys → plaintext legacy
  `developer.py` keys. No key rotation (changing `JARVIS_SECRET_KEY` orphans stored
  secrets), vault not encrypted at rest by default.

---

## 3. Confirmed gaps driving Phase 1

1. No provider abstraction that **declares capabilities on the provider** and refuses
   to fake them (capabilities are only per-model catalog data).
2. No NVIDIA NIM adapter; no first-class HF adapter; `jarvis:` provider unwired.
3. No `/v1/responses`, no real streaming in gateway path, no embeddings/reranking
   endpoints, vision/audio declared but no part-type support.
4. Secrets fragmented + plaintext leakage paths (extensions OAuth tokens,
   `developer.py` raw keys, reset tokens in response body, id_token unverified).
5. No provider-level telemetry/cost exposed; no end-to-end provenance.
6. No resource governor, no teacher node, no learning arena/lesson pipeline.
7. Routing is duplicated (platform ModelGateway vs silverwing ModelRouter) and not a
   single capability router.

---

## 4. Phase 1 surface (what will be built next)

The provider fabric is implemented as a new self-contained package
`F:\AI\providers\` (core abstraction + adapters for OpenAI, NVIDIA, Google Vertex,
AWS Bedrock, Hugging Face; capability registry; per-provider health; configurable
routing/fallback; provider telemetry; secret isolation guard). It is layered on top
of the existing platform and does **not** disturb the working Brain/Silverwing paths.
See `JARVIS_PROVIDER_FABRIC.md`.