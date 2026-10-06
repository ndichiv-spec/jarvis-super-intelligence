# JARVIS Upgrade Research — October 2026

> **PRIVATE — internal JARVIS architecture research. Do not publish or send project prompts, source, or user data to research services.**

## Research boundary

This review used public primary documentation for general implementation properties only. No JARVIS system prompt, credentials, source files, user conversations, or private architecture data were sent to external services. This document records project-specific conclusions for internal use.

## Primary-source findings

### Durable agent execution

Temporal describes workflows as deterministic code reconstructed from a durable event history. External side effects, including API calls, database operations, model calls, and file I/O, belong in Activities whose outcomes are recorded. This is a useful reliability boundary for JARVIS's long-running research, learning, and automation jobs; it is not a reason to claim durability when running only an in-process fallback.

Source: [Temporal — Workflows](https://docs.temporal.io/workflows)

LangGraph's persistence documentation distinguishes thread-scoped checkpoints from cross-thread stores, and notes that in-memory checkpointers are lost on process restart. This reinforces keeping turn execution state separate from durable cross-session bio-growth memory.

Source: [LangGraph — Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

### Streaming transport

The WHATWG Server-Sent Events format is UTF-8 text with event records separated by blank lines. Clients must parse complete frames rather than assuming network chunks align with frame boundaries. JARVIS uses authenticated POST requests and `fetch` streams, so retries should retain the same idempotency key rather than relying on native `EventSource` reconnect behavior.

Source: [WHATWG HTML — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)

FastAPI's `StreamingResponse` streams the response body directly; explicit response classes also affect what is documented in OpenAPI. The current JARVIS SSE endpoint already uses `StreamingResponse`, so typed additive events are a smaller and safer evolution than replacing the transport.

Source: [FastAPI — Custom responses](https://fastapi.tiangolo.com/advanced/custom-response/)

### Retrieval fusion

Reciprocal-rank fusion (RRF) combines independent ranked lists by rank position rather than assuming scores from different retrieval systems share a common scale. This fits JARVIS's current local embedding choices: a sentence-transformer cosine and a deterministic keyword/hash fallback are not calibrated against each other. The implementation keeps each retrieval signal visible and evaluates recall on a small offline fixture before changing production ranking.

Source: [Cormack, Clarke, and Buettcher — Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods (SIGIR 2009)](https://dl.acm.org/doi/10.1145/1571941.1572114)

## Project decisions

1. Keep FastAPI, the provider fabric, the capability registry, and the existing SQL-backed `jarvis_kv` persistence as the execution spine. Adopt capabilities only where they close a measured gap; do not add a second agent framework or database merely for stack breadth.
2. Keep streaming events typed and additive. Persist the assistant turn checkpoint in its existing owned chat session, keep a stable client message ID for replay, and do not describe replay-from-turn-start as token-level continuation.
3. Route internet observation through explicit source policies, rate limits, provenance, and the existing browser/research capabilities. Untrusted page content remains data, never policy or instructions.
4. Bio-growth is grounded in observed learning episodes, review outcomes, sourced knowledge, and reproducible scientific results. Maturity scores and technology forecasts must not imply expertise or certainty without evidence.
5. The browser remains inside JARVIS navigation surfaces. Third-party framing restrictions are a web-platform constraint; JARVIS's readable extraction view is an honest fallback, not a promise of full interactive remote browsing.
6. Keep project prompts and data private by default. External model or search providers receive only the data authorized by provider privacy policy and user configuration; research of public technology must never transmit JARVIS's private prompt.

## Implementation order

The initial practical increments are tool-call delta delivery through the provider-to-SSE path, durable turn checkpoints with idempotent replay, and frontend integration against existing bio-growth capability APIs. The next increment is improving semantic retrieval with measured offline evaluations before changing the current TF-IDF fallback. Each increment should have a truthful capability-health state and focused tests before it becomes a default path.

## Delivery notes

- Provider-originated tool-call fragments are accumulated by the OpenAI-compatible adapter, translated into typed gateway/SSE deltas, and shown incrementally in the chat clients. This is observability and transport groundwork; provider-directed tool execution still requires an explicit, permissioned dispatcher.
- Streaming chat turns now persist attempt/sequence/state metadata in the existing session record and reuse the same user/assistant turn for retry. Completed turns replay; interrupted turns can restart from the beginning. This is not token-level resume.
- The dashboard now exposes authenticated research ingestion/search, learning/review, science operations, and technology radar/frontier actions against the existing bio-growth routes. It presents service reachability separately from operation results and does not invent local/demo responses.
- Closing a stream immediately after its initial metadata frame marks the checkpoint interrupted, so the idempotent retry path is not blocked by a stale in-progress marker.
- Research retrieval fuses valid vector and keyword rankings with RRF. When stored embeddings are missing, malformed, or have a different dimension, keyword matches remain available and are labelled instead of being silently dropped. Table names are allowlisted before SQL construction. The local offline fixture checks recall for semantic-only, keyword-only, and hybrid matches; it is a regression baseline, not a claim of production relevance quality.
