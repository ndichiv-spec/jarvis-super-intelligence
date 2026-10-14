# JARVIS World Workspace and AI cooperation audit

**Assessment date:** 2026-10-13
**Status:** A bounded natural-language web-search capability now runs through the existing JARVIS runtime and was exercised against real DuckDuckGo. The broader autonomous World Workspace and AI cooperation acceptance criteria are not complete.

## Canonical runtime and discovery

- HTTP chat entry points remain the existing JARVIS routes and
  `jarvis_backend/chat_service.py::ChatService`.
- `ChatService._discover_conversation_action` recognizes a scoped set of
  research/lookup/compare requests. It selects the existing `browser.search`
  operation without requiring a dashboard selection.
- `ChatService._execute_conversation_action` checks server permission
  `tool.browser`, confirms that the existing canonical tool capability is
  registered, creates an `ExecutionContext`, emits runtime lifecycle events,
  and dispatches through `CapabilityOrchestrator.execute_capability`.
- The tool registry remains the existing `ToolCapability` and the
  checkout-local `research_engine.ToolRegistry`/capability contracts. The
  existing `BrowserTool` delegates search to `HttpBrowserEngine`; no duplicate
  provider registry or planner was introduced.
- Runtime discovery currently means runtime invocation of the configured web
  search provider (DuckDuckGo, with the existing Wikipedia fallback). It does
  not discover arbitrary websites, APIs, MCP servers, or service accounts,
  and it does not infer that a discovered URL permits automation.

## Results, provenance, and verification

`BrowserTool.execute("search")` returns actual provider results, validates
that each destination has an HTTP(S) scheme and no embedded URL credentials,
and identifies the `HttpBrowserEngine.search` provider and URLs. Its
provenance deliberately says `page_content_fetched: false`. Total search
provider failure is surfaced as an error; an empty successful response is
distinct from provider outage. When model synthesis is unavailable,
`ChatService` returns a partial result with observed source URLs and
`search_provider_response_only` verification metadata.

The opt-in live test performed a real search, recorded tool-call provenance,
persisted chat messages, and observed durable `request_created` and
`request_completed` events. It used a synthetic owner principal directly at
the service boundary, not a production login. It did not fetch the returned
pages, independently validate factual claims, invoke an AI model, or run on
production PostgreSQL/Redis. The search request itself was sent to DuckDuckGo;
no conversation memory, files, credentials, or unrelated messages were
included.

## AI cooperation

The existing gateway/provider boundary is retained. This recovery checkout's
`providers/__init__.py` is a delegation shim; the authoritative provider
fabric it expects is absent at the expected location. `ProviderStatusTool`
reports `provider_fabric: UNAVAILABLE` rather than implying readiness. No
model endpoint was called during the live search test. Model selection,
parallel/sequential consultation, independent model verification, external
data minimization policy, cost/latency controls, and live provider failure
handling are therefore not verified. Agreement or availability of a model
must never be treated as proof of truth.

## Durable task lifecycle and runtime events

The existing `jarvis_backend/routers/commands.py` command endpoints persist
owner-scoped command records and events in the current database store. The
worker path uses existing Celery/execution-fabric code, idempotency keys,
atomic worker claims, leases, and expired-lease recovery. Runtime events are
retained and replayed by the existing `runtime_events`/event services.
Locally tested command states include queue/receive, plan, waiting for owner
authorization, ready/executing, completion/failure/cancellation and expired
worker recovery. These API-specific states do not add a competing task
manager.

The task panel uses that API, carries the current conversation ID, submits in
`SUPERVISED` mode, polls persisted status, presents capability/risk metadata,
and submits owner approval explicitly. The backend now waits for every
pending authorization node rather than releasing a multi-action task after
one approval. This path has local UI/API tests, but no real queue worker or
production restart test was run.

## Adaptive presentation

The existing presentation registry and chat output remain the presentation
authority. The frontend supports chat responses with sources and execution
metadata, and a task lifecycle/approval panel. Registry startup conflicts for
shared presentation definitions were fixed and regression-tested. A general
runtime-generated presentation contract for websites, media playback, maps,
documents, and interactive applications is not implemented by this change;
the UI must not report such capabilities as available without a renderer and
authorized browser/runtime.

## Owner access and security controls

- JARVIS auth/core remains the single identity and authorization authority;
  production owner identity is server-configured through
  `JARVIS_ADMIN_EMAIL`. Client user IDs and hidden UI controls are not
  authorization.
- Search checks `tool.browser` before execution; authenticated route adapters
  forward their server-derived principal into `ChatService`.
- The task API scopes command reads/approval to the authenticated owner.
  Device endpoint tests cover owner-scoped enrollment, session attachment, and
  revocation/disconnect behavior.
- Search results are untrusted data, not permission or policy. The browser
  search path does not fetch page bodies automatically. Full prompt-injection
  protection across fetched webpages/documents, comprehensive SSRF/DNS
  controls, sensitive-query blocking/redaction, and external model data
  policies are not established here.
- Supabase Auth/RLS/Storage/Realtime are not configured. Backend ownership is
  still required if a Supabase PostgreSQL endpoint is used through the
  privileged SQLAlchemy path.

## External service integration matrix

| Capability | Implemented | Local / integration verification | Production verification | Blocker |
|---|---|---|---|---|
| Natural-language web search | Yes | Local regression plus one real DuckDuckGo search through canonical runtime | No | Search only; no page fetch/claim verification. |
| Owner-scoped durable command | Yes | Command/lease/authorization tests and task UI tests | No | Need PostgreSQL/Redis/Celery staging restart test. |
| AI cooperation | Existing integration point, unavailable provider fabric | Unavailable reporting only | No | Provider source and credentials. |
| Supabase | No service configured; server PostgreSQL URL path is compatible | No Supabase project | No | Project URL, TLS/pooler/secret configuration and migrations. |
| Private HTTPS deployment | Compose/Caddy config exists | 12 static deployment validation tests | No | Docker, host, domain/DNS/firewall, certificate, secrets. |

The exact test outcomes and capability-by-capability status are in
`JARVIS_WORLD_WORKSPACE_IMPLEMENTATION.md`,
`JARVIS_EXTERNAL_SERVICE_CAPABILITY_MATRIX.md`,
`JARVIS_OWNER_ONLY_SECURITY_MODEL.md`, and
`JARVIS_DEPLOYMENT_VERIFICATION.md`.
