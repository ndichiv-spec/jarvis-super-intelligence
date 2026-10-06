# JARVIS Backend Upgrade Plan
## Combining the Best of Codex, Claude Code, and Enterprise AI Platform Architecture

> **Goal**: Privately upgrade the JARVIS backend to use the same advanced backend technologies as OpenAI Codex, Anthropic Claude Code, and other leading AI platforms — with a focus on real-time performance, security, observability, and future growth.

> **Note on "Maestral"**: "Maestral" is an open-source Dropbox client (Python-based), not an AI platform. The upgrade plan below synthesizes the best backend technologies from OpenAI Codex (Rust core, MCP, sandboxing), Anthropic Claude Code (TypeScript agent loop, permission model, security), and general enterprise AI platform best practices.

---

## 1. Technology Analysis: What Other AI Platforms Use

### OpenAI Codex (Rust-native architecture)
**Source: `github.com/openai/codex` (codex-rs/ workspace, 599 Rust crates)**

| Layer | Technology | Key Rust Crates |
|-------|-----------|-----------------|
| **Agent Runtime** | Rust (tokio async runtime) | `core`, `async-utils`, `exec` |
| **Tool Execution** | Rust + bubblewrap sandboxing | `bwrap`, `linux-sandbox`, `mxc-sandbox`, `process-hardening` |
| **Transport** | WebSocket + App Server protocol | `app-server`, `app-server-transport`, `app-server-protocol`, `websocket-client`, `websocket-auth` |
| **Tool Integration** | MCP (Model Context Protocol) | `ext/mcp`, `rmcp-client` |
| **Multi-Agent** | Agent graph store + message board | `agent-graph-store`, `agent-message-board-client`, `agent-identity`, `agent-roles` |
| **Observability** | OpenTelemetry | `otel`, `otel-trace-websocket` |
| **TUI** | Rust curses/TUI | `tui`, `ansi-escape` |
| **Frontend** | TypeScript + Vite | `package.json` → Node 22, pnpm, `@modelcontextprotocol/sdk`, `hono` |
| **Packaging** | Single binary per platform | Pre-built musl binaries (`aarch64-apple-darwin`, `x86_64-unknown-linux-musl`) |

### Anthropic Claude Code (TypeScript/Node.js)
**Source: `github.com/anthropics/claude-code`**

| Layer | Technology | Key Details |
|-------|-----------|-------------|
| **Agent Loop** | TypeScript (Node.js ≥18) | Packaged as binary, npm package `@anthropic-ai/claude-code` |
| **Security** | Permission modes + egress firewall | `--permission-mode auto`, `--disallowedTools`, GitHub-hosted `ubuntu-24.04-firewall` runner |
| **Plugin System** | `.claude` plugin directory | Custom plugin architecture |
| **CI Integration** | GitHub Actions | `claude-code-action` with `--permission-mode auto` |
| **Tool Schema** | JSON Schema | Standard function calling schema |

### Enterprise AI Platforms (Common Patterns)
| Layer | Technology |
|-------|-----------|
| **Service Mesh** | gRPC + Protocol Buffers |
| **State Management** | Redis (pub/sub, KV, streams) |
| **Persistence** | PostgreSQL (primary), object storage (artifacts) |
| **Orchestration** | Kubernetes (Docker in dev) |
| **Observability** | OpenTelemetry + Prometheus + Grafana |
| **Secrets** | Vault or sealed-secrets |
| **API Gateway** | Envoy/Nginx + JWT/OAuth |
| **CI/CD** | GitHub Actions/GitLab CI |

---

## 2. Current JARVIS Stack Assessment

### What's Already Good
| Component | Current Tech | Status |
|-----------|-------------|--------|
| API Layer | FastAPI, Pydantic, Uvicorn | ✅ Solid |
| Persistence | SQLAlchemy + PostgreSQL/SQLite | ✅ Good |
| Auth | JWT + OAuth2 + RBAC | ✅ Solid (SEC-1 hardened) |
| Capabilities | Registry + Common Contract | ✅ Solid |
| Providers | OpenAI, Anthropic, Google, NVIDIA, HF, Stability, Ollama | ✅ Real providers |
| Browser Automation | Playwright, Selenium, HTTP engine | ✅ Real execution |
| Tools/Connectors | GitHub, PostgreSQL, Browser tools | ✅ Real integration |
| Event Fabric | In-memory + DB persistence | ✅ Good |
| Observability | Basic tracing in `observability.py` | ⚠️ Needs OpenTelemetry |
| Real-time | WebSocket (partial) | ⚠️ Needs structured protocol |

### What's Missing / Needs Upgrading
| Gap | Current | Codex/Claude Standard | Priority |
|-----|---------|----------------------|----------|
| **Agent Runtime** | Python sync/async | Rust async runtime | Medium |
| **MCP Support** | Custom tool protocol | MCP (Model Context Protocol) | **HIGH** |
| **Observability** | Basic logging | OpenTelemetry distributed tracing | **HIGH** |
| **Schema Definition** | Pydantic models | Protocol Buffers | Medium |
| **Sandboxing** | Python RestrictedPython | Bubblewrap/seccomp | **HIGH** |
| **Service Mesh** | Direct HTTP calls | gRPC with typed stubs | Medium |
| **Deployment** | Manual processes | Docker Compose / Helm | **HIGH** |
| **Multi-Agent** | Single agent | Agent graph store | Medium |
| **Real-time Transport** | JSON WebSocket | Structured event protocol | Medium |

---

## 3. Upgrade Roadmap (6 Phases)

### Phase 1: MCP Integration (HIGH)
**Goal**: Adopt the Model Context Protocol — the emerging standard for tool/function integration used by Codex, Claude Code, and most modern AI agents.

**Current State**: JARVIS has a custom `tools/` connector system (GitHub, PostgreSQL, browser).

**Upgrade Plan**:
1. Add `mcp` Python package as a dependency
2. Create an MCP server adapter that wraps existing JARVIS tools
3. Create an MCP client that can consume external MCP servers
4. Bridge MCP tools → JARVIS capability registry
5. Expose `/api/mcp` endpoint for MCP server protocol

**Files to create**:
- `jarvis_backend/mcp_server.py` — Exposes JARVIS tools as MCP
- `jarvis_backend/mcp_client.py` — Connects to external MCP servers
- `jarvis_backend/capabilities/tools/mcp_tool.py` — MCP tool wrapper

**Estimated effort**: 2-3 days

### Phase 2: OpenTelemetry Observability (HIGH)
**Goal**: Full distributed tracing with correlation IDs across all services, matching Codex's `otel` + `otel-trace-websocket` pattern.

**Current State**: `observability.py` has basic tracing but no OTel SDK integration.

**Upgrade Plan**:
1. Add `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-prometheus`
2. Instrument all capability execution with span creation
3. Propagate correlation IDs via WebSocket context (like Codex's `websocket-auth`)
4. Export metrics to Prometheus endpoint `/metrics`
5. Add trace sampling configuration

**Files to modify/create**:
- `jarvis_backend/observability.py` — Add OTel SDK
- `jarvis_backend/capability.py` — Instrument `execute()` with spans
- `jarvis_backend/event_fabric.py` — Add correlation_id propagation
- `jarvis_backend/routers/monitoring.py` — Add `/metrics` endpoint

**Estimated effort**: 1-2 days

### Phase 3: Sandboxed Execution (HIGH)
**Goal**: Secure tool execution using bubblewrap/seccomp (like Codex's `bwrap`, `linux-sandbox`, `process-hardening`).

**Current State**: Silverwing has `sandbox.py` with some isolation, but JARVIS uses Python's RestrictedPython.

**Upgrade Plan**:
1. Add `bubblewrap` (bwrap) as the sandboxing layer on Linux
2. Create a Rust or Python sandbox manager that:
   - Spawns each tool execution in a bwrap container
   - Sets seccomp filters (no network, no file writes outside allowed paths)
   - Captures stdout/stderr/exit code
3. Bridge to the existing capability execution layer
4. Fall back to Docker/Podman when bwrap unavailable (Windows)

**Files to create**:
- `jarvis_backend/sandbox.py` — Main sandbox manager
- `jarvis_backend/routers/sandbox.py` — API endpoints for sandbox status

**Estimated effort**: 3-4 days

### Phase 4: Protocol Buffers Schema Layer (Medium)
**Goal**: Add Protocol Buffers for type-safe inter-service communication (like Codex's `app-server-protocol`).

**Current State**: Pydantic models for API schemas only.

**Upgrade Plan**:
1. Install `grpcio`, `grpcio-tools`, `protobuf`
2. Create `.proto` files for key message types:
   - `capability.proto` — Capability execution request/response
   - `event.proto` — Event fabric events
   - `tool.proto` — Tool execution
   - `session.proto` — Conversation sessions
3. Generate Python stubs
4. Add gRPC server alongside FastAPI for internal services
5. Keep REST API for external compatibility

**Files to create**:
- `proto/jarvis.proto` — Root proto with imports
- `proto/capability.proto`, `proto/event.proto`, `proto/tool.proto`, `proto/session.proto`
- `jarvis_backend/grpc_server.py` — gRPC server

**Estimated effort**: 2-3 days

### Phase 5: Docker Compose Private Deployment (HIGH)
**Goal**: Single-command private self-hosted deployment (like running `docker compose up`).

**Current State**: Manual startup via `start_jarvis.py`.

**Upgrade Plan**:
1. Create `docker-compose.yml` with:
   - `jarvis-backend` — Main API service
   - `silverwing-runtime` — LLM inference runtime
   - `postgres` — Primary database
   - `redis` — Cache and session store
   - `prometheus` — Metrics scraping
   - `grafana` — Dashboard (optional)
   - `otel-collector` — Trace collection
2. Create `Dockerfile` for backend
3. Create `.env.example` with all configurable options
4. Add health checks for all services
5. Add nginx reverse proxy with TLS termination (self-signed cert for private use)

**Files to create**:
- `docker-compose.yml`
- `Dockerfile`
- `.env.example`
- `nginx/nginx.conf`
- `docker/start.sh`

**Estimated effort**: 2-3 days

### Phase 6: Agent Graph Store + Multi-Agent (Medium)
**Goal**: Multi-agent orchestration with persistent agent state (like Codex's `agent-graph-store`, `agent-message-board`).

**Current State**: Single-agent interaction loop.

**Upgrade Plan**:
1. Add Redis-backed agent graph store
2. Create agent lifecycle manager (spawn, pause, resume, terminate)
3. Add agent collaboration protocol (message passing via event fabric)
4. Create specialist agent framework (researcher, analyst, engineer, verifier)
5. Add agent memory isolation

**Files to create**:
- `jarvis_backend/agents/graph_store.py` — Redis-backed agent graph
- `jarvis_backend/agents/lifecycle.py` — Agent lifecycle manager
- `jarvis_backend/agents/specialist.py` — Specialist agent base class

**Estimated effort**: 3-5 days

---

## 4. Implementation Priority

| Priority | Component | Reason |
|----------|-----------|--------|
| **P0** | MCP Integration | Codex, Claude Code, and all major platforms use this — it's the new standard |
| **P0** | OpenTelemetry | Critical for debugging distributed agent execution |
| **P0** | Docker Compose | Required for private self-hosted deployment |
| **P1** | Sandboxed Execution | Security boundary for autonomous tool use |
| **P1** | Protocol Buffers | Type safety across services |
| **P2** | Agent Graph Store | Enables complex multi-agent workflows |

---

## 5. Architecture Diagram (Target State)

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js/TS)                     │
│  localhost:3000                                                  │
├──────────────┬──────────────────────────────────────────────────┤
│              │             TRANSPORT LAYER                        │
│  WebSocket   │  ┌──────────┐  ┌──────────────┐  ┌───────────┐   │
│  (OTel traces)│  │ gRPC     │  │ REST/JSON    │  │ MCP       │   │
│              │  │ (internal)│  │ (external)   │  │ (tools)   │   │
│              │  └──────────┘  └──────────────┘  └───────────┘   │
├──────────────┴──────────────────────────────────────────────────┤
│                    BACKEND (Python/FastAPI)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ MCP Server   │  │ MCP Client   │  │ gRPC Server  │           │
│  │ (exposes     │  │ (consumes    │  │ (internal    │           │
│  │ JARVIS tools │  │ external     │  │ services)    │           │
│  │ as MCP)      │  │ MCP servers) │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │   CAPABILITY REGISTRY                                      │ │
│  │  ┌────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐    │ │
│  │  │ Brain  │ │ Browser  │ │ Memory   │ │ Knowledge   │    │ │
│  │  │ +GPT   │ │ +Playwrgt│ │ +Vector │ │ +RAG        │    │ │
│  │  └────────┘ └──────────┘ └──────────┘ └─────────────┘    │ │
│  │  ┌────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐    │ │
│  │  │ Voice  │ │ Vision   │ │ Image    │ │ Tool/MCP    │    │ │
│  │  │ +STT   │ │ +Vision  │ │ +DALL-E  │ │ +sandboxed  │    │ │
│  │  └────────┘ └──────────┘ └──────────┘ └─────────────┘    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │   PROVIDER LAYER (Phase 6)                                 │ │
│  │  OpenAI, Anthropic, Google, NVIDIA, HF, Stability,        │ │
│  │  Silverwing, Ollama, Local                                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │   SANDBOXED EXECUTION                                      │ │
│  │  bubblewrap/seccomp containers for each tool call         │ │
│  └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE (Docker Compose)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐        │
│  │ Postgres │ │ Redis    │ │ Prom     │ │ Grafana     │        │
│  │ (data)   │ │ (state)  │ │ (metrics)│ │ (dashboards)│        │
│  └──────────┘ ┌──────────┐ ┌──────────┐ ┌─────────────┐        │
│  ┌──────────┐ │ Silver-  │ │ OTEL     │ │ Nginx       │        │
│  │ JARVIS   │ │ wing     │ │ Collector│ │ (TLS proxy) │        │
│  │ Backend  │ │ Runtime  │ │ (tracing)│ │             │        │
│  └──────────┘ └──────────┘ └──────────┘ └─────────────┘        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Private Deployment (Docker Compose)

The target deployment is a single `docker compose up -d` that starts everything:

```yaml
services:
  jarvis:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis, otel-collector]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      
  silverwing:
    build: ./silverwing-backend
    ports: ["8010:8010"]
    env_file: .env
    
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: jarvis_db
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]
    
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    
  otel-collector:
    image: otel/opentelemetry-collector:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes: ["./otel-collector-config.yaml:/etc/otel-collector-config.yaml"]
```

---

## 7. Backward Compatibility

All upgrades are **additive** — the existing FastAPI REST API remains the primary interface. New layers (gRPC, MCP, OTel) operate alongside without breaking existing integrations:

- FastAPI REST → ✅ unchanged (external API)
- Capability registry → ✅ unchanged (internal contract)
- Persistence layer → ✅ unchanged (SQLAlchemy)
- New gRPC server → Internal use (agent runtime, tool execution)
- New MCP endpoints → `/mcp/*` (new clients can use MCP; existing clients unaffected)
- OTel traces → Background telemetry (no API impact)

---

## 8. Next Steps

1. **Phase 1 (MCP)**: Install `mcp` package, create MCP server adapter for JARVIS tools
2. **Phase 2 (OTel)**: Add OpenTelemetry SDK, instrument capability execution
3. **Phase 5 (Docker)**: Create `docker-compose.yml` for private self-hosted deployment
4. **Phase 3 (Sandbox)**: Add bubblewrap-based sandboxing for tool execution
5. **Phase 4 (Protobuf)**: Add protobuf schema layer for internal services
6. **Phase 6 (Agent Graph)**: Multi-agent orchestration with persistent state

---

## 9. Phase 31–33 Completion (Bio-Growth Intelligence Stack)

The original 6-phase plan has been superseded by the bio-growth intelligence stack
(Phases 25–33). Phases 31–33 are now **COMPLETE** and verified green. All changes
are additive on the existing FastAPI app on port 8000 — no new backend, no new
database, no new long-running process.

### Phase 31: Embeddings + Qwen-Agent LLM Framework
- **pgvector fallback**: The `pgvector` PostgreSQL extension failed to install on
  Windows PostgreSQL 17.11 (extension control file unavailable). Replaced with
  application-level TF-IDF + hash-based 384-dim normalized embeddings in
  `jarvis_backend/embeddings.py`. Cosine similarity verified: related=0.8289,
  unrelated=−0.0089.
- **Qwen-Agent bridge**: `jarvis_backend/qwen_agent_bridge.py` integrates
  `qwen-agent==0.0.34`, bridging its tool-use flow into the JARVIS capability
  registry and `ProviderGateway`.

### Phase 32: A2A Protocol Integration
- `jarvis_backend/a2a_server.py` (703 lines): `JarvisAgentExecutor`,
  `create_a2a_agent_card()`, `mount_a2a_routes()`, `CAPABILITY_SKILLS` (15
  entries), `SKILL_KEYWORDS`, `SKILL_TO_CAPABILITY`.
- Uses `a2a-sdk==1.2.1` primitives directly (`DefaultRequestHandlerV2`,
  `InMemoryTaskStore`, `add_a2a_routes_to_fastapi`) — the legacy
  `A2AServer` import does not exist in this SDK version.
- 14 routes mounted onto FastAPI via `integrate_a2a()` in `build_app()`.
- Proto types used correctly: `Message(role=Role.ROLE_AGENT, ...)`,
  `TaskState.TASK_STATE_COMPLETED`, `AgentProvider(url, organization)`,
  `AgentInterface(url, protocol_binding, tenant, protocol_version)`.
- Graceful degradation: `mount_a2a_routes()` returns `False` if `a2a-sdk` is
  missing.
- Status endpoint: `GET /system/a2a/status`.

### Phase 33: LLM Observability (Phoenix + LangSmith)
- `jarvis_backend/phoenix_integration.py`: `PhoenixEvaluator` with 5 evaluators
  (hallucination, relevance, toxicity, coherence, faithfulness) + heuristic
  fallbacks. `arize-phoenix==20.19.0`.
- `jarvis_backend/langsmith_integration.py`: `LangSmithTracer` with 14-entry
  model pricing table + in-memory trace buffer fallback. `langsmith==0.10.15`.
- `jarvis_backend/temporal_workflows.py`: 3 workflows + 6 activities +
  in-process fallback. `temporalio==1.34.0`.
- `jarvis_backend/gateway.py`: LangSmith tracing integrated into the provider
  gateway request/response path.
- Status endpoints: `GET /system/temporal/status`, `GET /system/a2a/status`
  in `jarvis_backend/routers/bio_growth.py`.

### Verification Evidence (all green)
| Suite | Command | Result |
|---|---|---|
| Compile check | `python3 F:/AI/compile_check.py` | 12/12 FILES COMPILED OK |
| Phase 33 tests | `python3 F:/AI/test_phase33.py` | 34 passed, 0 failed (34 total) |
| E2E user tests | `python3 F:/AI/e2e_user_tests.py` | 12 passed, 0 failed, 0 warnings |
| E2E validation | `python3 F:/AI/e2e_validation.py` | 12/12 steps PASS, 0 warnings (incl. bio.learner health) |

**15 capabilities registered** (conversation, research_cortex, science.engine,
memory, task, voice, vision, image.generate, browser, github, postgresql,
bio_learner, brain, knowledge.search, tech.evolution) with **14 READY** +
voice DEGRADED + bio_learner READY.


---

## Phase 34: Durable Workflow Orchestration — ✅ COMPLETE (in-process)

- **Temporal.io** (`temporalio==1.34.0`): `jarvis_backend/temporal_workflows.py`
  — 3 workflows (`ResearchIngestionWorkflow`, `BioLearnerConsolidationWorkflow`,
  `ScienceComputationWorkflow`) + 6 activities (`ingest_feed_activity`,
  `search_arxiv_activity`, `ingest_url_activity`, `study_concept_activity`,
  `consolidate_activity`, `solve_math_activity`).
- In-process workflow fallback when no Temporal server is reachable — **no new
  long-running process**; runs on the existing FastAPI app on :8000.
- `ScienceComputationWorkflow` solved 4/4 problems;
  `BioLearnerConsolidationWorkflow` studied 2 concepts + consolidated.
- Status: `GET /system/temporal/status`. Verified by `test_temporal.py` and
  `test_phase33.py` (7 Temporal checks PASS). (Original §3 listed Temporal as
  "Medium" priority; now delivered.)

## Phase 35: Research-Informed Frontend Evolution (P2 synthesis)

> Full matrix: `docs/platform_research_report.md` §Phase 35. Sources:
> `F:/AI/_research/` (clean: `autogpt_blocks.txt`, `autogpt_api.txt`,
> `autogpt_dataflow.txt`, `agents_sdk.txt`, `crew_readme.txt`,
> `a2a_spec_v1.txt`, `langsmith_agent_server.json`, `lc_build_python.txt`;
> fresh fetches: `langgraph_langchain.txt`, `hf_agents_smolagents.txt`,
> `cursor_docs.txt`, `cody_docs.txt`).

### Next priorities (frontend-impact x feasibility)

| Prio | Evolution | Impact | Feasibility | Maps to |
|---|---|---|---|---|
| P0 | Stream tool-call **deltas** on SSE `chunk` | High | High | `gateway.py` `stream_chat`, `chat_service.py` `stream_message`, `legacy.py` `gen()`, `chat/api.ts` |
| P0 | **Checkpoint & resume** agent runs | High | High | new `checkpoint.py` + `jarvis_kv`; `capabilities/capability.py`; `chat_service.py` |
| P1 | Normalize `activity`/`reasoning` SSE `type` -> `ChatStreamChunk` union | Med | High | `legacy.py` `gen()` + `chat/types.ts` |
| P1 | Dense RAG indexing (replace/augment TF-IDF) | High | Med | `embeddings.py`, `project_intel.py`, `knowledge.py` |
| P1 | LangSmith run trees + per-step cost spans | Med | High | `langsmith_integration.py`, `gateway.py` |
| P1 | AutoGPT-style Blocks dataflow DAG | Med | Med | new `graph/` + `sandbox.py` + `capabilities/` |
| P2 | Multi-agent (A2A skill federation / CrewAI roles) | High | Low | `a2a_server.py`, `capabilities/`, `agents/` |
| P2 | OpenHands-style sandboxed coding loop | Med | Med | `sandbox.py`, `capabilities/tools/` |
| P2 | HF smolagents `CodeAgent` tool-use loop | Med | Med | `qwen_agent_bridge.py`, `research/` |
| P2 | Cursor-style codebase indexing UI | High | Low | `knowledge.py`, `features/knowledge/` |

#### Implementation ordering (next 6 weeks)
1. **Wk 1 (P0):** streaming tool-call deltas.  2. **Wk 1-2 (P0):** `checkpoint.py` + `/api/chat/sessions/{id}:resume`.  3. **Wk 2 (P1):** SSE type normalization (1-line `gen()` remap).  4. **Wk 3 (P1):** dense RAG indexing.  5. **Wk 4 (P1):** LangSmith cost spans.  6. **Wk 5 (P1):** AutoGPT Blocks prototype.  7. **Wk 6 (P2):** multi-agent pilot + OpenHands coding loop.

### Live verification (P0.10 — no regressions, live HTTP on :8000)
```
python3 F:/AI/compile_check.py          -> ALL 12 FILES COMPILED OK
python3 F:/AI/test_phase33.py           -> 34 passed, 0 failed
python3 F:/AI/e2e_validation.py         -> 12/12 PASS
python3 F:/AI/e2e_user_tests.py         -> 12 passed, 0 failed, 0 warnings
python3 F:/AI/verify_system_contract.py -> PASS=76 FAIL=0
```
`start_jarvis.py` boots `build_app()` (FastAPI + gRPC :50051 + MCP + A2A) ->
seeds admin -> mints REAL admin JWT -> `uvicorn.run(app, 127.0.0.1:8000)`.
`system.py` owns uptime via `_BACKEND_START`; `core.py` untouched. SEC-1
scrubbed: secret-shaped `/provider-settings` fields return `None`; PUT rejects
secret-shaped keys with `400`. SSE verified live: `typing`->`meta`->`chunk`->`complete` (google/gemini-2.5-flash).

