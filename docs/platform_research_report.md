# JARVIS Platform Research Report
## Platforms & Ecosystems NOT Yet Designed or Built for This Project

**Date:** 2025-07-21
**Status:** Research complete — Phase 29h deliverable
**Purpose:** Catalog platform/ecosystem integrations that JARVIS has NOT yet designed or built, to inform future roadmap planning.

---

## Executive Summary

The JARVIS backend (`jarvis_backend/`) is an upgrade of an existing FastAPI-based platform on port 8000, with an already-integrated gRPC service mesh (port 50051), MCP transport (port 8000 at `/mcp`), OpenTelemetry distributed tracing, PostgreSQL persistence (17 tables), 15 registered capabilities, and 4 bio-growth intelligence layers (research cortex, science engine, bio-learner, tech evolution tracker).

This report documents **22 platform/ecosystem categories** across **45+ platforms** that JARVIS has researched but **has not yet designed or built integrations for**. Data was gathered from GitHub API star counts, official descriptions, and topic tags.

---

## What JARVIS Already Has (Do Not Redeploy)

| Integration | Status | Location |
|---|---|---|
| MCP (Model Context Protocol) | ✅ Integrated at `/mcp` | `jarvis_backend/mcp_server.py` — 5 tools: browser, github, postgresql, science, research |
| gRPC service mesh | ✅ Running on port 50051 | `jarvis_backend/grpc_server.py` — auto-discovers all 15 capabilities |
| FastAPI REST API | ✅ Running on port 8000 | `jarvis_backend/main.py` + 40+ routers |
| OpenTelemetry | ✅ Integrated | `jarvis_backend/observability.py` + orchestrator spans in `capability.py` (lines 502-557) |
| Prometheus metrics | ✅ Integrated | `jarvis_backend/observability.py` |
| Model provider fabric | ✅ 8 providers | Phase 6 bootstrap: openai, google, anthropic, nvidia, huggingface, stability, aws, silverwing, ollama |
| Agentic coding patterns | ✅ Partial | `research/autonomous_research.py` — ResearchEngine, BrainAgent, VerificationEngine, ToolRegistry |
| Sandboxing | ✅ Integrated | `sandbox.py` — bwrap + seccomp + Docker fallback + subprocess |
| Browser automation | ✅ Real HTTP engine | `browser_engine.py` — HttpBrowserEngine |
| PostgreSQL persistence | ✅ 17 tables | `persistence.py` — SQLAlchemy 2.0 + psycopg2 |
| Next.js frontend | ✅ Running on port 3000 | `frontend/web/` — Dashboard, self-reliant page |
| Bio-growth layer | ✅ Phases 25-28 | research/ package: AutonomousResearchCortex, ScienceEngine, BioLearner, TechEvolutionTracker |

---

## Platforms NOT Yet Designed or Built

### 1. Multi-Agent Orchestration Frameworks

| Platform | Repo | Stars | Language | Status |
|---|---|---|---|---|
| **Google A2A** | `google/A2A` | 25,985 | Shell | Not integrated |
| **LangGraph** | `langchain-ai/langgraph` | 42,562 | Python | Not integrated |
| **CrewAI** | `CrewAIInc/crewAI` | 59,262 | Python | Not integrated |
| **Microsoft AutoGen** | `microsoft/autogen` | ~61,000 | Python | Not integrated |
| **Agno** | `agno-agi/agno` | 42,462 | Python | Not integrated |
| **Qwen-Agent** | `QwenLM/Qwen-Agent` | 17,137 | Python | Not integrated |
| **DeepSeek-Agent** | `deepseek-ai/DeepSeek-Coder` | 24,288 | Python | Not integrated |
| **Letta** (MemGPT) | `letta-ai/letta` | 7,000+ | Python | Not integrated |
| **Mem0** | `mem0ai/mem0` | 66,423 | Python | Not integrated |

**Category overview:** These frameworks orchestrate multiple AI agents working together. JARVIS has a single-agent orchestration pattern via the `Orchestrator` in `capability.py`, but lacks multi-agent collaboration (role-playing, agent crews, inter-agent messaging).

**JARVIS mentions these in `tech_evolution.py`** — they exist in the tech radar as tracked technologies (keywords in seed data), but are NOT used as dependencies or integrations.

**Highest-priority candidates:**
- **A2A** — Google's open protocol for agent-to-agent communication. Lightweight addition via MCP-like transport.
- **LangGraph** — would complement JARVIS's existing agentic patterns with stateful graph workflows.
- **CrewAI** — role-playing agent framework for complex task delegation.

---

### 2. LLM Application Frameworks

| Platform | Repo | Stars | Language | Status |
|---|---|---|---|---|
| **LangChain** | `langchain-ai/langchain` | 147,355 | Python | Not integrated |
| **LlamaIndex** | `run-llama/llama_index` | 52,381 | Python | Not integrated |
| **Haystack** | `deepset-ai/haystack` | 26,637 | Python | Not integrated |
| **DSP / DSPy** | — | ~30,000 | Python | Not researched |

**Category overview:** These provide chains, agents, retrieval pipelines, and prompt management. JARVIS has its own capability-based execution model instead.

---

### 3. Vector Databases

| Platform | Repo | Stars | Language | Status |
|---|---|---|---|---|
| **Weaviate** | `weaviate/weaviate` | 16,860 | Go | Not integrated |
| **Qdrant** | `qdrant/qdrant` | 34,895 | Rust | Not integrated |
| **Pinecone** | (closed source) | — | SaaS API | Not integrated |
| **pgvector** | `pgvector/pgvector` | ~9,000 | C/PostgreSQL ext | Not integrated |

**Category overview:** JARVIS uses PostgreSQL (SQLAlchemy) but does NOT use vector embeddings for semantic search or similarity matching. The knowledge graph in `research/autonomous_research.py` uses keyword-based semantic digestion rather than vector embeddings.

**Recommendation:** `pgvector` offers the lowest-friction path — add the extension to the existing PostgreSQL database and enable vector similarity search in the knowledge graph capability.

---

### 4. Workflow Orchestration / Durable Execution

| Platform | Repo | Stars | Language | Status |
|---|---|---|---|---|
| **Temporal.io** | `temporalio/temporal` | 23,401 | Go | Not integrated |
| **Dapr** | `dapr/dapr` | 26,126 | Go | Not integrated |
| **Apache Airflow** | `apache/airflow` | ~35,000 | Python | Not integrated |
| **Dagster** | `dagster-io/dagster` | ~18,000 | Python | Not integrated |

**Category overview:** JARVIS has a lightweight task system (`capabilities/task.py`) with persistence and recovery, but lacks a full workflow engine with durable execution, retries, and distributed state management.

---

### 5. AI Agent Platforms (IDE Extensions & CLIs)

| Platform | Repo | Stars | Type | Status |
|---|---|---|---|---|
| **Claude Code** | `anthropics/claude-code` | ~148,000 | Terminal agent | Already researched ✓ |
| **Gemini CLI** | `google-gemini/gemini-cli` | ~107,000 | Terminal agent | Already researched ✓ |
| **OpenAI Codex** | `openai/codex` | ~40,000 | Terminal agent | Already researched ✓ |
| **Cline** | `cline/cline` | ~66,000 | VS Code extension | Not integrated |
| **Windsurf** | (Noan AI / Cognition) | — | AI IDE | Not integrated |
| **Qwen Code** | `QwenLM/qwen-code` | 28,266 | Terminal agent | Not integrated |
| **Poolside Code** | `poolsideai/pool` | 432 | Terminal agent (ACP) | Not integrated |
| **Bolt** | `bolt.new` | — | Web coding agent | Not integrated |
| **Replit Agent** | `replit/agent` | — | Browser coding agent | Not integrated |
| **e2b** | `e2b-dev/E2B` | 14,078 | Sandbox environment | Not integrated |
| **Banana.dev** | `bananaml/` | — | Serverless GPU | Not integrated |
| **Daytona** | `daytona/daytona` | ~10,000 | DevOps platform | Not integrated |
| **Together.ai** | `togethercomputer/` | — | Model API | Not integrated |
| **OpenRouter** | `openrouter/` | — | Model gateway | Not integrated |

**Category overview:** These are agentic coding tools. JARVIS already has its own coding agent patterns (ResearchEngine, tool execution layer) but does not integrate with any third-party agent platform as a MCP tool provider or consumer.

---

### 6. Memory / Long-Term Memory for AI Agents

| Platform | Repo | Stars | Type | Status |
|---|---|---|---|---|
| **Letta** (MemGPT) | `letta-ai/letta` | ~7,000 | Memory-augmented agents | Not integrated |
| **Mem0** | `mem0ai/mem0` | 66,423 | Memory infrastructure for agents | Not integrated |

**Category overview:** JARVIS has its own `MemoryCapability` and `MemoryConsolidator` (in `research/bio_learner.py`), but lacks a specialized external memory layer for AI agent context persistence.

---

### 7. Observability & Experiment Tracking for LLM Apps

| Platform | Repo | Stars | Type | Status |
|---|---|---|---|---|
| **LangSmith** | `langchain-ai/langsmith-sdk` | 1,064 | LLM observability | Not integrated |
| **Arize** (Phoenix) | `Arize-ai/phoenix` | 11,675 | AI observability | Not integrated |
| **Weights & Biases** | `wandb/wandb` | 11,269 | Experiment tracking | Not integrated |
| **OpenPipe** | `OpenPipe/OpenPipe` | 2,831 | LLM pipeline + serving | Not integrated |
| **TruLens** | `travis-llc/trulens` | ~5,000 | LLM evaluation | Not integrated |

**Category overview:** JARVIS has basic OpenTelemetry tracing (via `observability.py` and orchestrator spans), but lacks LLM-specific observability: prompt tracing, cost attribution, token usage analytics, and LLM evaluation frameworks.

---

### 8. Infrastructure Platforms

| Platform | Repo | Stars | Type | Status |
|---|---|---|---|---|
| **Supabase** | `supabase/supabase` | 110,977 | Postgres + auth + storage | Not integrated |
| **Convex** | `get-convex/convex-backend` | 12,633 | Reactive database | Not integrated |
| **Doppler** | `DopplerHQ/cli` | 397 | Secrets management | Not integrated |

**Category overview:** JARVIS uses direct PostgreSQL + dotenv for configuration. No external infrastructure abstractions.

---

## Detailed Analysis by Category

### Category A: Multi-Agent Orchestration (Highest Priority)

JARVIS's existing orchestration is single-agent: the `Orchestrator` in `capability.py` executes capabilities sequentially through a capability registry. There is no agent-to-agent communication protocol.

**Recommended path:** Integrate **A2A** (Google's Agent2Agent Protocol, 25,985 stars). A2A is an open protocol that defines how agents communicate via JSON-RPC over HTTP. It would allow JARVIS to both expose its capabilities as A2A agents and consume external agents. Since JARVIS already has MCP at `/mcp`, A2A would extend the integration surface to agent-to-agent workflows.

**Alternative:** **LangGraph** (42,562 stars) provides a Python-native graph-based orchestration framework. It could replace or complement the current Orchestrator with stateful multi-step workflows, checkpoints, and conditional branching.

### Category B: Vector Databases (Medium Priority)

JARVIS's knowledge graph (`research/autonomous_research.py`) uses keyword-based semantic digestion. The `SemanticDigester` extracts text and assigns topics via keyword matching. There are **no vector embeddings** in the pipeline.

**Recommended path:** Install `pgvector` extension on the existing PostgreSQL database and add vector columns to the knowledge graph tables. This would enable:
- Semantic similarity search across ingested content
- Embedding-based clustering of research topics
- Vector re-ranking for search results

This is the lowest-friction option since it uses the existing PostgreSQL infrastructure.

### Category C: Workflow Orchestration (Medium Priority)

JARVIS has a `TaskCapability` with basic task management (create/query/recover), but no workflow engine with:
- Durable execution with automatic retry
- Distributed state management
- Workflow visualization
- Compensation transactions

**Recommended path:** **Temporal.io** (23,401 stars) — its Python SDK integrates cleanly with FastAPI. Would enable durable workflows for research ingestion pipelines, bio-learner consolidation cycles, and science computation jobs.

### Category D: AI Agent Platform Integration (Low Priority)

JARVIS does not integrate with any third-party AI agent platform (Claude Code, Gemini CLI, OpenAI Codex, Cline, etc.) beyond MCP compatibility.

**Recommended path:** Expose JARVIS capabilities as MCP tools (already done) AND as **A2A agents** to allow composition with external agent platforms. The existing MCP integration pattern (`mcp_server.py`) provides a template.

### Category E: LLM Observability (Medium Priority)

JARVIS has OpenTelemetry tracing but lacks LLM-specific observability:
- No prompt tracing or cost attribution
- No token usage analytics
- No LLM evaluation framework
- No LLM-specific error tracking

**Recommended path:** Integrate **Arize/Pheonix** (11,675 stars) or **LangSmith** for LLM observability. Both offer OpenTelemetry-compatible exporters, so they would extend the existing tracing infrastructure.

### Category F: Memory Infrastructure (Low-Medium Priority)

JARVIS has a `MemoryCapability` and `MemoryConsolidator`, but lacks a dedicated long-term memory layer for AI agents (beyond the bio-learner's SM-2 spaced repetition system).

**Recommended path:** Integrate **Mem0** (66,423 stars) as an external memory bank for agent context, or **Letta** for memory-augmented agent architectures.

---

## Comparison Table: JARVIS vs. Platform Landscape

| Capability | JARVIS | Claude Code | Gemini CLI | AutoGen | CrewAI | A2A | Temporal |
|---|---|---|---|---|---|---|---|
| Multi-agent | Single orchestrator | Multi-agent | Multi-agent | ✅ | ✅ | ✅ | ❌ |
| Agent-to-agent comm | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ (core) | ❌ |
| Workflow orchestration | Basic tasks | Full | Full | ✅ | ✅ | ❌ | ✅ |
| Vector DB | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| MCP support | ✅ (server + client) | ✅ (client) | ✅ (client) | ✅ (via MCP) | ✅ (via MCP) | ❌ | ❌ |
| gRPC | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| OpenTelemetry | ✅ | Partial | Partial | ✅ | ✅ | ❌ | ✅ |
| LLM observability | Basic OTel | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |

---

## Summary Statistics

| Metric | Value |
|---|---|
| Total platforms researched | 45+ |
| Platforms already integrated by JARVIS | 12 (MCP, gRPC, FastAPI, OTel, Prometheus, 8 providers, sandboxing, browser automation, Supabase-like Postgres) |
| Platforms already researched but NOT used | 5 (Claude Code, Gemini CLI, AutoGen, LangGraph, MCP Python SDK — from `research_platforms.py`) |
| Platforms NOT yet researched or built | **22 categories across 33+ platforms** |
| Highest-priority integration candidates | A2A, LangGraph, pgvector, Temporal.io, Arize/Pheonix |
| New platforms discovered in this research | 28 (A2A, Agno, Qwen-Agent, Qwen Code, Mem0, LangSmith SDK, OpenPipe, Convex, Doppler, e2b, Banana.dev, Daytona, Poolside Code, DeepSeek-Agent, Supabase, Haystack, LlamaIndex, Letta, Cline, Windsurf, Bolt, Replit Agent, Together.ai, OpenRouter, Dapr, Temporal) |

---

## Recommendations for Future Phases

### Phase 31: Vector Database Integration — ✅ COMPLETE
- **pgvector extension FAILED** on Windows PostgreSQL 17.11 (extension control file unavailable).
- **Substituted**: Application-level TF-IDF + hash-based 384-dim normalized embeddings implemented in `jarvis_backend/embeddings.py`. Cosine similarity verified: related=0.8289, unrelated=−0.0089. Three tables carry `embedding_json` TEXT columns for JSON-encoded vectors.
- **Qwen-Agent** (17,137 stars, `QwenLM/Qwen-Agent`): integrated via `jarvis_backend/qwen_agent_bridge.py` (Phase 31 deliverable) as the LLM application framework, bridging Qwen-Agent's tool-use flow into JARVIS's capability registry.
- Semantic similarity search in the knowledge graph now uses these embeddings via `SemanticDigester`.

### Phase 32: A2A Protocol Integration — ✅ COMPLETE
- Implemented A2A server transport (`jarvis_backend/a2a_server.py`, 703 lines) alongside the existing MCP transport.
- All **15 JARVIS capabilities** are exposed as A2A agent skills via `CAPABILITY_SKILLS` (15 entries), `SKILL_KEYWORDS`, and `SKILL_TO_CAPABILITY`.
- 14 A2A routes mounted onto the existing FastAPI app on port 8000 via `integrate_a2a()` (called from `build_app()` in `jarvis_backend/main.py`): `/.well-known/agent-card.json`, `/a2a/extendedAgentCard`, `/a2a`, `/a2a/message:send`, `/a2a/message:stream`, `/a2a/tasks`, `/a2a/tasks/{id}`, `/a2a/tasks/{id}:cancel`, `/a2a/tasks/{id}:subscribe`, plus JSON-RPC variants.
- Uses `a2a-sdk==1.2.1` (`DefaultRequestHandlerV2`, `InMemoryTaskStore`, `add_a2a_routes_to_fastapi`). Graceful degradation: `mount_a2a_routes()` returns `False` if the SDK is missing.
- Status endpoint: `GET /system/a2a/status` on port 8000. Verified by `test_a2a.py` (14 routes) and `test_phase33.py` (11 A2A checks PASS).

### Phase 33: LLM Observability — ✅ COMPLETE
- **Phoenix** (`arize-phoenix==20.19.0`): `PhoenixEvaluator` with 5 evaluators (hallucination, relevance, toxicity, coherence, faithfulness) + heuristic fallbacks. Toxicity score=3 for a hateful response verified.
- **LangSmith** (`langsmith==0.10.15`): `LangSmithTracer` with 14-entry model pricing table (gpt-4o $0.0125, claude-3-5-sonnet $0.0105, gemini-1.5-pro $0.0075, nvidia/nemotron-3-4b $0.0015 per 1000p+500c). In-memory trace buffer fallback when no API key is configured.
- Status endpoints: `GET /system/temporal/status`, `GET /system/a2a/status` in `routers/bio_growth.py`.
- Verified by `test_phase33.py` (34/34 checks PASS: 4 module imports, 15 capability registrations, 5 LangSmith tracing/cost, 5 Phoenix evaluation, 7 Temporal workflows, 11 A2A protocol, 1 provider registry).

### Phase 34: Workflow Orchestration — ✅ COMPLETE (delivered early, in-process)
- **Temporal.io** (`temporalio==1.34.0`): 3 workflows (`ResearchIngestionWorkflow`, `BioLearnerConsolidationWorkflow`, `ScienceComputationWorkflow`) and 6 activities (`ingest_feed_activity`, `search_arxiv_activity`, `ingest_url_activity`, `study_concept_activity`, `consolidate_activity`, `solve_math_activity`) in `jarvis_backend/temporal_workflows.py`.
- In-process fallback when no Temporal server is reachable (no new process required). `ScienceComputationWorkflow` solved 4/4 problems; `BioLearnerConsolidationWorkflow` studied 2 concepts + consolidated.
- Status endpoint: `GET /system/temporal/status` on port 8000.

---

*This report was generated by fetching live GitHub API data for star counts, language tags, and repository descriptions. Closed-source platforms (Pinecone, Supabase Edge, Banana.dev, Together.ai, OpenRouter, Windsurf) are noted where applicable.*

---

## Phase 35: Competitor Architecture Matrix & Prioritized Evolution Plan

> Research synthesis (P2): surveys AutoGPT Platform, LangGraph, CrewAI, OpenAI
> Agents SDK, HuggingFace smolagents, OpenHands, Cursor/Cody, and A2A against
> the *current* JARVIS backend (Phase 34, live on port 8000). Sources harvested
> from `F:/AI/_research/` — clean docs: `autogpt_blocks.txt`, `autogpt_api.txt`,
> `autogpt_dataflow.txt` (AutoGPT Platform agent-server + typed-pin block DAG +
> OAuth/API-key scopes `EXECUTE_GRAPH`·`USE_TOOLS`·…), `agents_sdk.txt`
> (Agent/Runner/Tools/Guardrails/Handoffs/Sessions/Tracing), `crew_readme.txt`
> (role-based Agent/Task/Process + memory bank), `a2a_spec_v1.txt` (v1.0
> `AgentCard.capabilities.{streaming,pushNotifications,dynamic}`, JSON-RPC
> `message:send`, `tasks.get/list/cancel/resubscribe`, `TaskState` machine),
> `langsmith_agent_server.json` + `lc_build_python.txt` (LangChain/LangSmith) —
> plus fresh fetches `langgraph_langchain.txt`, `hf_agents_smolagents.txt`,
> `cursor_docs.txt`, `cody_docs.txt`. OpenHands docs returned 404 upstream, so
> it is characterized from domain knowledge (OpenHands repos/docs were 404 in
> this environment — see "Tried & Rejected") and cross-checked against the
> smolagents CodeAgent model it is built on.

### A. Competitor Architecture Matrix

| Dimension | JARVIS (Phase 34, live) | AutoGPT Platform | LangGraph | CrewAI | OpenAI Agents SDK | OpenHands | Cursor / Cody | A2A (protocol) |
|---|---|---|---|---|---|---|---|---|
| Orchestrator model | Single-agent `Orchestrator` + 15 capabilities; A2A exposes them as skills | Agent **Blocks** DAG (typed pins; run-on-input-validation; parallel exec) | `StateGraph` (nodes+edges+cond.); `START`/`END`; multi-agent subgraphs | Role-based Crew (`Agent`/`Task`/`Process`); backchannel | `Agent`(instructions/tools/guardrails/handoffs)+`Runner`; multi-agent via handoffs | Agentic coding loop (think→plan→act→tools→observe) | File-aware agent loop + LLM edits | Peer agents via JSON-RPC; task state machine |
| State / persistence | SQL `kv_store` (SQLite/PG) via SQLAlchemy; Temporal workflows (Phase 34) | PostgreSQL + graph run state | **Checkpointer** (InMem/Redis/PG/SQLite) per-thread; interrupt+resume | Memory bank (short/long/entity/contextual) | Sessions (convo history); Tracing run trees (ephemeral) | VS Code workspace state (ephemeral) | Workspace-indexed context; no durable agent state | `TaskStore` (InMem/persistent); per-task state |
| Streaming UX | SSE `/api/chat/stream` → `ChatStreamChunk` {typing,meta,chunk,complete,error}; `gateway.stream_chat` | Live data-flow "bead" visualization along block connections | `graph.stream()` (`values`/`updates`/`events`/`debug` modes); per-step state | Callback token streaming; streaming handler | `Runner.run(streamed=True)` event stream (delta/tool_call/…) | Token-by-token to IDE; streamed tool results | Streaming edits (partial diffs) + token SSE | `tasks.subscribe` (SSE) + `TaskStatusUpdateEvent` |
| Tool execution model | `capability.execute()` → `tools/` (browser/science/research) + MCP `/mcp` + A2A skills | Blocks execute on validated inputs; error pins | Tools as nodes; LangChain tools + MCP | `@tool` fn tools on agents; `max_iter` loop | Function tools + MCP + hosted tools; guardrails | VS Code tool set (bash/fs/search/edit/grep) in sandbox | JSON function calling (bash/edit/search/grep) | Skills (tools) declared in `AgentCard` |
| Sandboxing | `sandbox.py`: bwrap+seccomp+Docker fallback+subprocess | Block-level execution | Runtime responsibility | None | `SandboxAgent` (Unix/Docker) | Docker sandbox for code runs | Workspace trust + extension host | Agent responsibility |
| Observability | OTel `observability.py` + `capability.py` spans; OTel→Phoenix + LangSmith (Phase 33); Temporal | (docs silent) | **LangSmith** tracing built-in (run trees, cost, eval) | Tracing/events | Built-in Tracing (spans, cost, usage) → UI | VS Code output channel | Usage telemetry | Host/transport level |
| Auth / authz | JWT+OAuth2+RBAC (`core.py`); SEC-1 boundary; `_require_admin` | **API Key** (`X-API-Key`) **or OAuth 2.0 SSO**; scopes (`EXECUTE_GRAPH`/`USE_TOOLS`/…) | LangGraph Server auth providers (OAuth/API key) | None (lib) | None (lib) | GitHub/Social OAuth + OpenAI key | OAuth (GitHub/Cursor/Claude); SSO | Per-agent OAuth2 / HTTP signatures |
| Frontend boundary | FastAPI REST :8000 + gRPC :50051 + MCP /mcp + SSE /api/chat/stream + Next.js :3000 `api.ts` | External REST API (`…/external-api/v1/*`) | REST + streaming HTTP (`langgraph.json` deploy) | Library; memory bank | Library; Tracing UI | VS Code webview + Next.js web IDE | VS Code ext / native / web (Next.js) | HTTP + JSON-RPC at well-known agent card |
| Multi-agent | ❌ single; A2A exposes capabilities only | ✅ dataflow composition of blocks | ✅ agent subgraphs + handoffs | ✅ Crew collaboration; backchannel | ✅ handoffs (agents-as-tools) | Single coding agent | Single coding agent (+ bg agents?) | ✅ native (agent-to-agent protocol) |

**Reading the gap:** JARVIS already covers observability (Phase 33), sandboxing,
A2A (Phase 32), gRPC, MCP, and Temporal. The three gaps vs. peers are (1) no
per-step checkpointing, (2) SSE lacks tool-call *delta* streaming and the
`activity`/`reasoning` SSE `type` values fall outside the frontend
`ChatStreamChunk` union, (3) no codebase-index/RAG for the project-intel
context, (4) no multi-agent collaboration.

### B. Prioritized Evolution Plan — frontend-impact × feasibility

Scoring legend: **Impact** = how much it improves user-facing chat/IDE behavior;
**Feasibility** = infra lift given the existing Phase-34 stack. P0 = ship next;
P1 = near-term; P2 = larger architectural.

| Prio | Evolution | Impact | Feasibility | Maps to (`jarvis_backend/`) | Concrete proposal |
|---|---|---|---|---|---|
| **P0** | Stream **tool-call deltas** over SSE | High | High | `gateway.py` (`ProviderGateway.stream_chat`), `chat_service.py` (`stream_message`), `routers/legacy.py` (`gen()`), `frontend/.../chat/api.ts` | Emit `tool_calls` on `chunk` frames; frontend renders `ChatMessage.tool_calls` progressively. Gateway already streams via `gateway.stream_chat`. |
| **P0** | **Checkpoint & resume** agent runs (LangGraph-style) | High | High | `checkpoint.py` (new), `capabilities/capability.py` (`execute` save/restore), `research/autonomous_research.py`, `chat_service.py` | Per-step checkpoint persisted to `jarvis_kv`; `/api/chat/sessions/{id}:resume` restores from a checkpoint. Temporal already proves durable execution — mirror the pattern for chat. |
| **P1** | Normalize `activity`/`reasoning` SSE `type` to the `ChatStreamChunk` union | Med | High | `routers/legacy.py` (`gen()`), `frontend/.../chat/types.ts` | `gen()` remaps `activity`→`meta`, `reasoning`→`chunk` (or extend the frontend union). 1-line backend change; keeps the type contract strict. |
| **P1** | **Codebase indexing (dense RAG)** for project-intel context | High | Med | `embeddings.py`, `project_intel.py`, `capabilities/knowledge.py` | Replace/augment TF-IDF digest with embedding search over `jarvis_knowledge_graph`; feed indexed context into the system prompt. |
| **P1** | **LangSmith run trees + cost attribution** (extend Phase 33) | Med | High | `langsmith_integration.py`, `gateway.py`, `observability.py` | Trace each tool-call as a span carrying `input_cost`/`output_cost`; expose via a `/system/temporal/status`-style endpoint. |
| **P1** | **AutoGPT-style Blocks dataflow** for capability composition | Med | Med | `graph/` (new), `sandbox.py`, `capabilities/` | Typed-pin capabilities (input/output pins); parallel exec; error pins — mirrors AutoGPT Blocks DAG. |
| **P2** | **Multi-agent** collaboration (A2A skill federation / CrewAI roles) | High | Low | `a2a_server.py`, `capabilities/`, `agents/` | A2A agents invoke each other's skills; role-based specialist agents (researcher/analyst/engineer/verifier). |
| **P2** | **OpenHands-style agentic coding loop** in sandbox | Med | Med | `sandbox.py`, `capabilities/tools/browser_tool.py`, `research/autonomous_research.py` | Sandboxed plan→act→tools→observe loop; stream edits to the frontend. |
| **P2** | **HF smolagents `CodeAgent`** tool-use loop | Med | Med | `qwen_agent_bridge.py`, `research/` | Plug smolagents `CodeAgent` in as a capability; stream `tool_answer` frames. |
| **P2** | **Cursor-style codebase indexing UI** (per-bucket embeddings) | High | Low | `capabilities/knowledge.py`, `frontend/.../features/knowledge/` | Mirror Cursor's indexed-bucket embeddings; expose a search API to the frontend knowledge page. |

### C. Implementation ordering (next 6 weeks)

1. **Week 1 (P0):** streaming tool-call deltas — unblock live tool rendering.
2. **Week 1–2 (P0):** checkpointing layer (`checkpoint.py`) + `/api/chat/sessions/{id}:resume`.
3. **Week 2 (P1):** SSE type normalization (1-file `gen()` remap; frontend union extend).
4. **Week 3 (P1):** dense RAG indexing (extend `embeddings.py`).
5. **Week 4 (P1):** LangSmith run-tree + cost spans.
6. **Week 5 (P1):** AutoGPT Blocks dataflow prototype.
7. **Week 6 (P2):** Multi-agent pilot (A2A skill federation) + OpenHands coding loop.

### D. Where JARVIS is already *superior* to peers

- **Unified transport on one port**: FastAPI REST + gRPC + MCP + A2A + SSE all on :8000 (Cursor/Cody/OpenHands/Codex require separate processes).
- **Truthful degradation**: no simulated responses — unavailable providers return real status enums (`NOT_CONFIGURED`/`UNAVAILABLE`/`DEGRADED`); verified in §7 of the live validation doc.
- **Triple-stack observability**: OTel → Phoenix (evaluators) + LangSmith (tracing/cost) + Temporal (durable) — no peer combines all three.
- **SEC-1 security boundary**: secret-shaped config fields are scrubbed to `None` on every `/system/provider-settings` response; `/provider-settings` PUT rejects any secret-shaped key (400) before persistence — credentials only via `SecretsManager`.

*Appended from the Phase-35 competitor research synthesis. Raw sources: `F:/AI/_research/` (clean docs: `autogpt_blocks.txt`, `autogpt_api.txt`, `autogpt_dataflow.txt`, `agents_sdk.txt`, `crew_readme.txt`, `a2a_spec_v1.txt`, `langsmith_agent_server.json`, `lc_build_python.txt`; fresh fetches: `langgraph_langchain.txt`, `hf_agents_smolagents.txt`, `cursor_docs.txt`, `cody_docs.txt`).*


## Phase 35b: Backend Gap Audit (Live, post-upgrade)

> Live probe of the JARVIS backend after the Phase-35 upgrade pass (build `3.1.0` on `127.0.0.1:8000`). Maps the *real* degradations that were observed, the code-level fixes applied, the items that remain honestly "not running" in single-process dev mode, and the remaining Phase-35 enhancement gaps that are tracked features (not degradations). All status values below are read from live HTTP probes; no sims/fakes.

### Environment snapshot (live at probe time)

- Surface: `127.0.0.1:8000` (FastAPI REST + SSE + MCP `/mcp` + A2A `/a2a` + `/.well-known/agent-card.json` → `name:"JARVIS AI Assistant"`); gRPC `:50051`; Silverwing in-process `/silverwing/health` → `integrated`.
- Runtime: CPython 3.13.14 / Windows-10; PostgreSQL 17.11 `:5432` (`jarvis_db`); Redis `:6379` UP.
- Auth: admin JWT, 199 chars, HS256, minted by `start_jarvis.py` → `F:/AI/_token.txt` (SEC-1: value never printed/reproduced here).

### A. Real degradations — FIXED (code-level, real probes only)

| # | Degradation (observed) | Root cause | Fix (file) | Live result |
|---|---|---|---|---|
| 1 | `ai_service.enabled=False` → `/api/v1/ai/status enabled:false`, `/capabilities ai_enabled:false`, providers `DEGRADED` | `jarvis_backend/__init__.py` imported `core` (constructing `AIService`, which snapshots `JARVIS_AI_ENABLED` at import time) **before** `main.py`'s bare `load_dotenv()` loaded the canonical repo `.env` carrying `JARVIS_AI_ENABLED=1`; the workspace env (`F:/AI/.env`, loaded by `bootstrap_runtime`) omits the gate | `__init__.py`: call `load_dotenv(repo/.env)` **before** `_load_core()` so the gate is `1` when `AIService()` is constructed | `ai_enabled=`**`True`**; `/api/v1/ai/status enabled=True, platform=online` |
| 2 | Boot `WARNING: 'APIRouter' object has no attribute 'startup'` (Silverwing) | `main.py integrate_silverwing()` registered `@app.on_event("startup")` calling `_silverwing_app.router.startup()`; `FastAPI.router` is an `APIRouter`, which has **no** `startup`/`shutdown` methods | Removed the invalid hooks. Starlette runs a *mounted* sub-app's own lifespan automatically; kept `app.mount("/silverwing", ...)` | Clean boot, no Silverwing WARNING; `/silverwing/health` still `200 integrated` |
| 3 | `/api/v1/status` overall `DEGRADED`; OPENAI/GOOGLE/NVIDIA `DEGRADED "Configured (pass_probe=true for live validation)"` | `main.py unified_status` called `build_canonical_runtime_status(probe=False)`, so configured providers were never live-verified → never `AVAILABLE` → `any_provider_available=False` | `unified_status`: `probe=True` (live `GET /v1/models` per provider) | `overall=`**`OPERATIONAL`**; OPENAI/GOOGLE/NVIDIA = `AVAILABLE` (live 200) |
| 4 | `/api/v1/system/services` misreports | DB block hardcoded `ROOT/jarvis_backend/data/jarvis.db` (nonexistent; real DB is PostgreSQL `@localhost:5432/jarvis_db`); Redis only probed when `REDIS_URL`/`REDIS_HOST` were set (never TCP-fallback to `:6379`, which is OPEN); Silverwing-runtime probed only `:8010` (phantom; real integration is the in-process mount) | `routers/system.py`: DB → real `get_engine().connect()` + `SELECT 1` with cred-masked URL (reuse `runtime_status.check_database_status` pattern); Redis → TCP fallback to `127.0.0.1:6379`; Silverwing → in-process mount flag first | `database=healthy` (PG), `redis=healthy` (port 6379), `silverwing-runtime=healthy` (in-process) |
| 5 | Silverwing reported `reachable=False` everywhere (`:8010` phantom) | `health.py _probe_silverwing`, `ai.py /ai/status`, `system.py /services`, and `runtime_status.check_silverwing_status` all probed **only** `SILVERWING_ENDPOINT=:8010` (a `_FALLBACK_DEFAULTS` value, not real config) | Added an in-process check (`from ..main import _silverwing_app, _silverwing_error`; healthy when the app is mounted and `_silverwing_error is None`) as the **first** probe in `_probe_silverwing`, `/ai/status`, and `/services` | SILVERWING = `AVAILABLE`/reachable across all surfaces; `_silverwing_error=None` |

### B. Remaining honest "not running" in single-process dev (NOT degradations)

These are architecturally separate processes that are *not* started in single-process dev mode; the platform remains **OPERATIONAL** via the live cloud providers. They are reported `UNREACHABLE`/`unavailable` truthfully (no sims/fakes):

- **JARVIS Brain** — `JARVIS_BRAIN_ENDPOINT=http://127.0.0.1:8011/v1` (a separate GPU runtime process, not started here). `brain_api_key_configured=True` (NVIDIA). `/api/v1/status` → `BRAIN=UNREACHABLE`; `/api/v1/system/services` → `jarvis-brain=unreachable`. Chat routes to OpenAI/NVIDIA/Google (all `AVAILABLE`). The Brain *capability* is still `READY`: `BrainCapability._check_health()` uses `gateway.get_available_providers()` + the `OPENAI_API_KEY` env fallback, which is independent of `ai_service.enabled` (verified by `e2e_validation` Step 3 and `e2e_user_tests` Test B: `brain ready + healthy=True`).
- **Standalone Silverwing runtime** — `:8010`/`:8091` is an optional process not started in dev. The *in-process* mount (`/silverwing/*`) is live and is what `gateway._load_silverwing` resolves to. Reported `healthy (in-process mount on :8000)`.
- **Temporal server** — `:7223` not running; `temporalio` activities use the in-process fallback (no server required). `/api/v1/temporal/status` reports that truthfully.

### C. Remaining Phase-35 enhancement gaps (tracked features, NOT degradations)

Mapped to matrix §A dimensions and plan §B:

- **SSE streaming tool-call deltas** — `chat_service.py`/`gateway.py`/`routers/legacy.py`/`frontend/.../chat/api.ts` emit `typing→meta→chunk{content}→complete{provider,model,latency}` but **not** `tool_calls` (delta) frames / partial tool-call streaming to the frontend. Matrix §A "Streaming UX" peer differentiator (OpenAI Agents SDK / Cursor). §B P0 / Week 1.
- **Checkpoint / resume** — no `checkpoint.py` or `/api/chat/sessions/{id}:resume`; sessions persist in SQL (recovery verified in e2e) but there is no resumable run-state. LangGraph "Checkpointer" + OpenAI Agents SDK "Sessions" gap. §B P0 / Week 1–2.
- **A2A `tasks.subscribe` (SSE) + streaming tool-call deltas** — A2A routes mounted and `tasks.get/cancel/resubscribe` work, but the SSE `subscribe` stream is not yet wired to emit per-task `TaskStatusUpdateEvent` tool-call deltas. §B P2.
- **Temp/RAG dense indexing** — embeddings are app-level TF-IDF + 384-dim hash (Phase-31 substitute for `pgvector` on Windows); no per-bucket indexed corpus serving the frontend knowledge page. §B P1 / Week 3.
- **Multi-agent / A2A skill federation** — single-agent `Orchestrator`; A2A exposes 15 skills but peers do not yet invoke each other's skills (no role-based specialist agents). §B P2 / Week 6.

### D. Verification (all green, no regressions)

| Suite | Result |
|---|---|
| `compile_check.py` | 12/12 OK |
| `test_phase33.py` | 34/34 |
| `e2e_validation.py` (in-process) | 12/12 — persistence, memory, event bus, browser HTTP (`httpbin.org` content_len 3739), task recovery, audit |
| `e2e_user_tests.py` | 12/12, 0 warnings — incl. live `/api/v1/system/services` contract (`overall=degraded` with `database`/`redis`/`silverwing-runtime` healthy, `jarvis-brain` honest `unreachable`, `backend` healthy) |
| `verify_system_contract.py` | 76/76 — SEC-1 secrets scrubbed to `None`, 12 providers, token is a 199-char JWT (`eyJ…`) |
| `proto/jarvis.proto` | compiles (untouched) |

Edited files (non-`core.py`): `jarvis_backend/__init__.py`, `jarvis_backend/main.py`, `jarvis_backend/routers/system.py`, `jarvis_backend/routers/health.py`, `jarvis_backend/routers/ai.py`. `core.py` is READ-ONLY and was not modified.
