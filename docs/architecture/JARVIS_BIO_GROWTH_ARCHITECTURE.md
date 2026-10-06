# JARVIS Bio-Growth Backend Architecture

> **CLASSIFIED — Private project infrastructure. Not for external distribution.**
> 
> This document describes the bio-growth intelligence layers added atop JARVIS's
> enterprise-grade backend (Phase 15+). These systems operate entirely within
> the private network boundary — no data egress without explicit authorization.

## Vision

JARVIS evolves from an orchestrated capability platform into a **bio-growth
cognitive architecture**: an internet-aware intelligence that discovers,
ingests, digests, and synthesizes technological knowledge following a
biological growth curve — from "birth" (seed knowledge) through "growth"
(accretion and consolidation) to "mastery" (cross-domain synthesis) and
"infinity" (self-transcending capability expansion).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         JARVIS BIO-GROWTH LAYERS                       │
│                                                                         │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐ │
│  │ Autonomous Research │  │ Scientific Engine   │  │ Tech Evolution  │ │
│  │ Cortex (ingestion)  │  │ (reasoning)         │  │ Tracker         │ │
│  │                     │  │                     │  │                 │ │
│  │ • RSS/arXiv/Web     │  │ • SymPy symbolic    │  │ • Tech radar    │ │
│  │ • Semantic digest   │  │ • NumPy numerics    │  │ • Frontier map  │ │
│  │ • Knowledge DAG     │  │ • Hypothesis test   │  │ • Cross-domain  │ │
│  └──────────┬──────────┘  └──────────┬──────────┘  └────────┬────────┘ │
│             │                        │                      │          │
│             └───────────┬────────────┴─────────────┬────────┘          │
│                         │                          │                   │
│                    ┌────▼────┐              ┌─────▼─────┐             │
│                    │ BIO-    │              │ Knowledge │             │
│                    │ LEARNER │◄─ digest ────►│ Graph     │             │
│                    │         │  ingest    │ │           │             │
│                    │ • Curriculum │          │ • Concepts│             │
│                    │ • Memory     │          │ • Links   │             │
│                    │ • Maturity   │          │ • Sources │             │
│                    └────┬────┘              └───────────┘             │
│                         │                                          │
│                    ┌────▼────────────────────────────────────────┐ │
│                    │    JARVIS Core (Phase 15+):                 │ │
│                    │    FastAPI(8000) + gRPC(50051) + MCP(/mcp) │ │
│                    │    + OTel + Sandbox + Docker Compose        │ │
│                    └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Layer Descriptions

### 1. Autonomous Research Cortex (Internet-Aware Ingestion)

**Purpose**: Actively discover, fetch, and digest technological knowledge
from the internet — RSS feeds, academic APIs (arXiv, PubMed), GitHub
trending, technical blogs, and web crawling.

**Key Components**:
- `FeedMonitor` — Polls RSS/Atom feeds on configurable schedules
- `PaperHarvester` — Queries arXiv and PubMed APIs for papers in tracked domains
- `TrendWatcher` — Monitors GitHub trending, Hacker News, tech blogs
- `SemanticDigester` — Extracts key concepts, summaries, and relationships
- `KnowledgeDAG` — Builds a directed acyclic graph of knowledge entities and their relationships

**Growth Pattern**: Starts with seed feeds (Phase 0), gradually expands to
discover new sources organically through link-following and citation analysis.

### 2. Scientific Reasoning Engine (Symbolic & Numerical)

**Purpose**: Native science and mathematical reasoning using JARVIS's "own
based style" — combining symbolic derivation (SymPy), numerical simulation
(NumPy/SciPy), and hypothesis testing.

**Key Components**:
- `SymbolicEngine` — Algebraic manipulation, calculus, equation solving
- `NumericalEngine` — Numerical integration, optimization, Monte Carlo simulation
- `HypothesisTester` — Formulate, simulate, and validate scientific hypotheses
- `ProofBuilder` — Construct step-by-step mathematical derivations
- `FormulaLibrary` — Curated collection of domain-specific formula templates

**Growth Pattern**: Begins with basic arithmetic, progresses through algebra,
calculus, and domain-specific modeling (physics, economics, etc.).

### 3. Bio-Growth Learning Framework (Curriculum & Memory)

**Purpose**: Implements biological-style learning growth — from "birth"
(seed knowledge) through "growth" (knowledge accretion), "mastery"
(cross-domain synthesis), to "infinity" (self-transcending exploration).

**Key Components**:
- `MaturityScorer` — Scores knowledge domains from 0 (unfamiliar) to ∞ (expert)
- `CurriculumPlanner` — Progressive learning path following difficulty curves
- `MemoryConsolidator` — Spaced repetition scheduling (SM-2 algorithm)
- `ForgettingCurve` — Models knowledge decay and reinforcement
- `SynthesisEngine` — Cross-domain concept combination for innovation

**Growth Curve**:
```
Maturity Score
    ∞  ┌───────────────────────────────── Mastery → Infinity
       │                              ╱
       │                           ╱
  100  │               Growth ────╱
       │                     ╱
   10  │    Birth ─────────╱
       │          ╱
    1  │        ╱  Consolidation
    0  └───────────────────────────────── Knowledge Domain
       Birth  Growth   Mastery  Infinity
```

### 4. Technology Evolution Tracker

**Purpose**: Discover technological species — emerging technologies,
research frontiers, and cross-domain innovation patterns.

**Key Components**:
- `TechRadar` — Classifies technologies as Adopt, Trial, Assess, Hold
- `ResearchFrontierMapper` — Identifies active research frontiers from paper analysis
- `CrossDomainSynthesizer` — Finds connections between distant technology domains
- `LifecycleModeler` — Models technology adoption lifecycles (innovation → diffusion → maturity)
- `TrendPredictor` — Extrapolates growth patterns using time-series analysis

**Growth Pattern**: Starts by tracking known technologies, evolves to predict
emergent combinations and identify breakthrough potential.

## Data Architecture

The target design is durable persistence in the existing JARVIS database
(SQLite/Postgres) using SQLAlchemy. In the current backend, the SQL-backed
`jarvis_kv` collection store persists Bio-Growth snapshots under
`bio_learning`; the following named domain tables are target boundaries, not
all currently provisioned tables:

| Table | Purpose |
|-------|---------|
| `jarvis_knowledge_graph` | Concepts, entities, and their relationships (DAG) |
| `jarvis_research_papers` | Harvested papers from arXiv/PubMed with metadata |
| `jarvis_science_solutions` | Mathematical proofs, derivations, and computations |
| `jarvis_learning_episodes` | Curriculum learning sessions with outcomes |
| `jarvis_tech_frontiers` | Technology lifecycle stages and frontier positions |
| `jarvis_growth_metrics` | Maturity scores, consolidation logs, synthesis events |

## Capability Integration

Each layer is implemented as a standard JARVIS `Capability` with truthful
health checks:

```
brain.reasoning        # Orchestrates all 4 layers
research.ingest        # Autonomous Research Cortex
science.solve          # Scientific Reasoning Engine
learning.curriculum    # Bio-Growth Learning Framework
tech.frontiers         # Technology Evolution Tracker
```

All layers emit events on the `EventBus` for OTel tracing and use the
existing sandbox for safe ingestion. MCP tools expose key operations
for Claude Code / Codex CLI integration.

## Security & Privacy

- All ingestion happens within the JARVIS sandbox (bwrap/Docker/subprocess)
- No data leaves the private network boundary
- Credentials accessed only via vault/secrets manager
- All operations auditable via the event log
- Rate-limited external API access (arXiv, RSS, etc.)

## Growth Stages

| Stage | Characteristics | Capabilities |
|-------|----------------|-------------|
| Birth (0-1) | Seed knowledge, basic patterns | science.solve (basic), research.ingest (seed feeds) |
| Growth (1-100) | Knowledge accretion, consolidation | research.ingest (expanded), science.solve (calculus), learning.curriculum |
| Mastery (100-∞) | Cross-domain synthesis, prediction | tech.frontiers, learning.synthesis, science.hypothesis |
| Infinity (∞+) | Self-transcending exploration | All capabilities operating autonomously |


---

## Phase 15+ Live Status — Vision Layers Now Implemented (Phase 34)

The four bio-growth *vision* layers above are **live and verified** (Phase 34,
`12/12` e2e + `76/76` frontend-contract assertions on port 8000). They are not
aspirational — each maps to a real `jarvis_backend/` module:

| Vision layer | Real module(s) | Health (e2e) |
|---|---|---|
| Autonomous Research Cortex | `capabilities/research_cortex.py`, `research/autonomous_research.py`, `research/tech_evolution.py`, `capabilities/tools/browser_tool.py`, `capabilities/tools/research_tool.py` | `research.ingest` READY |
| Scientific Reasoning Engine | `capabilities/science.py`, `research/science_engine.py`, `capabilities/tools/science_tool.py` | `science.engine` READY (SymPy/SciPy) |
| Bio-Growth Learning Framework | `capabilities/bio_learner.py`, `research/bio_learner.py` | `bio.learner` READY (5 domains; `_domain_mastery` AttributeError fixed) |
| Technology Evolution Tracker | `capabilities/tech_tracker.py`, `research/tech_evolution.py` | `tech.evolution` READY |
| Knowledge Graph (spine) | `capabilities/knowledge.py`, `capabilities/tools/research_tool.py`, `embeddings.py` (384-dim TF-IDF, cosine related=0.8289 / unrelated=−0.0089) | `knowledge.search` READY |

### Phase 32–34 integrations (additive on port 8000, no new long-running process)
- **A2A v1** (`a2a_server.py`, `a2a-sdk==1.2.1`): 14 routes, 15 skills;
  `/a2a`, `/.well-known/agent-card.json`, `/system/a2a/status`.
- **Phoenix + LangSmith** (Phase 33): 5 evaluators + cost/tracing.
- **Temporal** (Phase 34): `temporal_workflows.py` — 3 workflows / 6 activities,
  in-process fallback; `GET /system/temporal/status`.
- **Qwen-Agent bridge** + TF-IDF embeddings (`embeddings.py`).

### P2 evolution (from competitor matrix, `docs/platform_research_report.md` §Phase 35)
- **P0** stream tool-call deltas over SSE (`chat_service.py` / `gateway.py` /
  `legacy.py` / `frontend/.../chat/api.ts`).
- **P0** checkpoint & resume (`jarvis_backend/checkpoint.py` + `jarvis_kv`).
- **P1** dense RAG indexing; **P1** LangSmith per-step cost spans.
- **P2** multi-agent (A2A skill federation / CrewAI roles); **P2** OpenHands-style
  sandboxed coding loop; **P2** Cursor-style codebase indexing.

Capability status reports availability and health; it is not proof that a
capability has produced a validated scientific result or an end-to-end
autonomous workflow. Historical phase-validation reports are time-bounded
snapshots of earlier checkout states, not a substitute for the operational
contracts and tests for the current backend below.

## Operational contracts (current backend)

The following contracts distinguish working backend operations from the
longer-term autonomy vision above:

- `POST /api/v1/automation/task/{task_id}/run` requires an authenticated
  administrator/developer. The built-in system report reads current capability
  and telemetry state; the knowledge digest computes metadata counts from the
  requesting user's and public knowledge entries without returning document
  content. Both persist execution outcomes and audit records.
- The built-in cleanup task has no local implementation. It requires an active
  n8n workflow; if n8n rejects or cannot accept the run, JARVIS records failure
  and does not claim local completion. An accepted n8n trigger is reported as
  `accepted`, not as a completed workflow.
- Bio-learning snapshots are persisted per authenticated user in the backend
  SQL-backed store. Studying a concept records exposure only; mastery changes
  only after a recall review. Review scores are self-assessed evidence and are
  explicitly not independent validation of the person or model's knowledge.
  Due-review and consolidation operations report work/evidence that exists;
  they do not manufacture replay or cross-domain discoveries.
- These built-ins are not a durable distributed workflow engine. Multi-step
  retries, worker leases, cancellation, and n8n completion callbacks still
  require a durable workflow backend and explicit integration. The frontend is
  a client for those backend operations, not the owner of Bio-Growth state.
- `BioGrowthResearchWorker` starts with the backend unless
  `JARVIS_BIO_GROWTH_WORKER_ENABLED=false`; it polls due bundled seed feeds,
  persists discovered research and graph rows, and records bounded run
  metadata. It runs once immediately, then at
  `JARVIS_BIO_GROWTH_POLL_SECONDS` intervals in embedded mode. Embedded mode
  is process-local; use one API process for it.
  Admins can inspect it at `GET /api/v1/research/workflow/status` or trigger an
  immediate cycle at `POST /api/v1/research/workflow/run`.
- The production Compose deployment sets `JARVIS_BIO_GROWTH_WORKER_MODE=celery`:
  a dedicated Celery Beat process schedules the research poll, Celery worker
  executes it, and a persistent, isolated Redis instance acts as the broker
  (`appendonly yes`, `appendfsync everysec`, `noeviction`). The API does not
  start an embedded scheduler in this mode. Tasks use late acknowledgement,
  worker-loss redelivery, bounded retries, JSON serialization, one-message
  prefetch, and the same idempotent database ingestion path. Celery/Redis being
  installed is not enough by itself; the Compose worker and Beat services must
  both be running for scheduled polling.
- Each worker cycle also refreshes the curated technology watch through the
  public GitHub Releases API. The watch is pinned to six upstream repositories,
  rate-limited to one refresh per six hours, and persists source-attributed
  release metadata. Release notes are untrusted reference data: JARVIS does
  not execute them or automatically change its own code. The technology
  updates response reports automatic refresh only while the worker is running.
- Outbound MCP connections are initialized from operator-provided
  `MCP_SERVERS` descriptors at backend startup and closed during shutdown.
  HTTP/SSE credentials are resolved from named environment variables through
  `headers_env`; tokens are not included in connection status or logs. Local
  stdio servers execute programs and therefore require the explicit
  `JARVIS_MCP_ALLOW_STDIO=true` opt-in. This enables connections only when
  real server endpoints and credentials are configured; it does not imply any
  third-party account is already connected.
