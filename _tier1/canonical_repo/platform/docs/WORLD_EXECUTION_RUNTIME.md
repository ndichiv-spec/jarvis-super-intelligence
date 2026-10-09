# World Execution Runtime

## Current integration

Natural-language requests with a registered intent are resolved inside the
existing conversation and command path. The World Resolver does not own tool
registration, authorization, dispatch, persistence, or runtime events.

| Responsibility | Existing owner |
| --- | --- |
| Capability registration, tool schemas, invocation, permissions, risk policy, and secret scrubbing | `research_engine/tool_registry.py` and `research_engine/capability_tools.py` |
| Capability metadata, operation mappings, intent patterns, evidence requirements, and confirmation scope | `research_engine/capability_contract.py` |
| Matching registered intent metadata, schema compatibility, candidate eligibility/ranking, and result selection | `platform/jarvis_backend/world_resolver.py` |
| Plan validation, invocation authorization, evidence, and bounded re-planning | `jarvis_brain/orchestrator.py` and `jarvis_brain/plan_validator.py` |
| Authenticated durable command/execution lifecycle and ordered correlated events | `platform/jarvis_backend/routers/commands.py` and `platform/jarvis_backend/runtime.py` |
| Session ownership, conversation persistence, request dispatch, and presentation persistence | `platform/jarvis_backend/chat_service.py` |
| Versioned semantic contract, approved components, data-reference validation, fallback policy, and non-web text renderer | `platform/jarvis_backend/presentation_contract.py` |
| Contract transport/history restoration and web interpretation | `platform/frontend/web/src/features/chat/{api,store,types}.ts`, `presentation-adapter.mjs`, and `components/chat/chat-message.tsx` |
| HTTP page retrieval, public search, and text extraction | `platform/jarvis_backend/browser_engine.py` and `research_engine/tool_registry.py::BrowserSearchTool` |

The resolver consumes the existing registry and its contracts. Contract
permissions are copied onto the same `ToolRegistry` invocation boundary, so
metadata permissions are enforced during both selection and execution rather
than being catalogue-only. Tools marked `requires_confirmation` are denied by
the registry unless the policy instance can verify a user/tool-scoped approval.
The plan validator routes such denials through its existing approval gate.

It ranks only
registered providers of the requested operation, checks mapped inputs against
the tool schema, verifies declared evidence paths against the output schema,
requires a declared execution surface and observability, checks inventory
availability, endpoint/network constraints, accepted cost policy, and calls
the existing `ToolRegistry.authorize` policy. If a contract explicitly
requires service authentication, the resolver requires verified service
identifiers from its caller; absent or unknown authentication does not pass.
Unknown health, cost, latency, or authentication metadata remain unknown;
unknown is not reported as healthy, free, or authenticated.

Alternative candidates are passed to the existing bounded Brain re-planning
path. They are not assumed interchangeable: each must register the same
operation and pass the same schema, availability, authorization, and
observability checks. The registered natural-language operations currently
include public `web.search`, media `media.discovery`, and offline
`workspace.search`.
`workspace.search` executes the existing, bounded `project.search` tool inside
the configured core workspace and requires `project:read`; it is not a search
of a user's endpoint filesystem. `web.search` and `media.discovery` both use
the existing `search_web` tool. There is currently no second registered
provider for either public web operation, so alternate-surface fallback is
implemented in the resolver/Brain retry path but is not demonstrated against
two production providers.

The workspace tool defaults its root to the installed source tree rather than
a developer-specific drive. Deployments can set `JARVIS_WORKSPACE_ROOT` and
`JARVIS_PROJECT_ROOT` to the intended core-owned workspace and project
subdirectory. Workspace paths remain confined to the configured root.

## Browser boundary

`HttpBrowserEngine` uses HTTP requests. Its declared capabilities are:

* `public_web_search`: DuckDuckGo Lite, with Wikipedia API fallback.
* `http_fetch`: stateless HTTP/HTTPS retrieval.
* `page_extraction`: extraction of readable content from retrieved pages.

If all configured search backends raise errors, search now reports a tool
failure rather than an empty successful result. A backend that successfully
returns no results remains an observed empty search result.

This engine is not a JavaScript browser. It does not implement general
clicking, form submission, authenticated or persistent browser sessions,
service-specific streaming control, or media playback. Page retrieval is not
equivalent to interactive navigation. The public media-discovery path asks the
user's explicit request to authorize read-only web search; it does not grant
arbitrary browsing, external writes, downloads, purchases, messages, or device
control. Results are presented as observed links with an explicit caveat that
discovery does not establish regional licensing or playback access.

## Runtime and authorization boundaries

Chat requests retain their request and conversation/session identifiers when
creating a command. The canonical HTTP request ID is passed into each
`ToolContext.correlation_id`; `ToolContext.request_id` remains a distinct
per-invocation result/tool ID. The durable command and execution identifiers
flow into the existing runtime event store. Events describe resolution,
selection, capability start/completion/failure, observed results, and
presentation. Event payloads use the existing secret scrubber and do not
include provider credentials.

Command, execution-list, plan, and runtime-event routes first enforce command
ownership. Conversation sessions are keyed and checked by authenticated user.
Ordinal result selection uses only completed result links in that user's
conversation; it returns an external link and does not claim that JARVIS
navigated, authenticated, or played anything.

The runtime and its durable store remain deployment-bound. A browser or
endpoint disconnect does not itself set core readiness to offline, but this
repository does not prove that a runtime hosted on a powered-off machine
survives, nor that conversations/tasks automatically hand off to another
device. Only registered capabilities that declare offline support can be used
without network access.

## Semantic presentation boundary

The chat UI previously rendered assistant Markdown and optional source strings
directly, with no shared presentation contract. `presentation_contract.py` is
the backend owner of version `1.1` and reads stored version `1.0` contracts; it creates text-first contracts for normal
conversation and derives research/workspace components only from successful
command evidence. The contract contains semantic components, hierarchy/focus,
assistant state, permission-labelled user-gesture interactions, accessibility
and responsive requirements, fallback/error behavior, data references, and
request/session/conversation/command/execution correlation. It contains no
React, DOM, Tailwind, route, or executable code.

Version `1.1` adds canonical task status, source type and observed-at
provenance, selected/focused view state, an explicit unknown-preferences value,
and renderer compatibility requirements. Provenance timestamps are generated
when the execution result is observed. Media references are rejected until an
authorized media storage/service boundary exists; no binary data or
unverified media URL is accepted.

Approved components currently include `conversation.markdown`,
`research.source_list`, `workspace.match_list`, and the validated
`geospatial.point_map`. Data references are scoped to the command execution,
checked against the backend-generated reference set, and revalidated before
rendering. Interactions currently allow only user-initiated external source
navigation labelled `web:read`; presentation metadata does not authorize tools
or consequential actions. Unsupported modalities and components fall back to
observed conversation text.

The chat renderer consumes `geospatial.point_map` using MapLibre, public Esri
street tiles, map navigation controls, and validated user-provided coordinates.
It does not infer device location or claim that a map tile is live satellite,
traffic, route, or navigation data. The separate
`frontend/web/src/app/locations/page.tsx` retains its own geography experience.
The `openai.images`
extension handler can call the OpenAI Images API only through its explicit
admin-only extensions route; it is not registered in the World Execution
Runtime, returns provider URLs directly, and does not persist protected media.
It is therefore not a chat image-presentation capability. The voice router
reports TTS only when its optional local module is present; ASR/listen and
transcription return `NOT_IMPLEMENTED`, and voice output is not synchronized
with chat presentation state.

The web chat's `presentation-adapter.mjs` declares its supported contract
versions, semantic components, and modalities and checks them before
rendering. A renderer with a smaller feature set uses the contract's text
fallback without mutating the canonical task or content. The web adapter is
the same dependency-free module used by its React view and Node conformance
tests. A second, framework-free text renderer in `presentation_contract.py` consumes the
identical fixture at
`tests/fixtures/presentation-research-v1.json`. This demonstrates that the
contract can be consumed without React/Next.js; the text renderer is a
conformance adapter, not a shipped native or desktop endpoint.
`endpoint_registry.py` now stores owner-bound endpoints, health transitions,
validated advertisement claims, modality/version negotiation, active
selection, revocation, and audit events in the shared SQL database. Its
authenticated `/api/v1/endpoints` routes support registration, heartbeat,
disconnect/reconnect, renegotiation, selection, revocation, and owner-scoped
event history. Unknown claimed capabilities are retained as unsupported;
advertisements do not grant permissions and are not marked operational by
negotiation alone.

Presentation revisions are durable SQL records linked to canonical chat tasks,
requests, conversations, commands, executions, endpoints, compatibility
decisions, and fallback reasons. ChatService writes an idempotent initial
revision. The authenticated presentation recovery route reuses the latest
completed presentation, validates the newly connected endpoint, and persists a
new revision without re-executing the task. Legacy v1.0 endpoints receive an
explicit text adaptation with provenance retained in the text; unsupported
v1.1 components retain the canonical contract and its renderer fallback.
Revisions use optimistic concurrency and runtime events are replayable by
command. Endpoint self-reports still do not prove that a renderer actually
painted or played the content.
The existing Markdown response fields remain for API compatibility and as an
explicit fallback, while persisted chat history, resumed requests, SSE
completion, command results, and the existing `presentation.updated` runtime
event carry the optional contract.

## Verification boundaries

Focused resolver tests cover registered web/workspace intent matching,
schema-checked selection, contract permission enforcement, confirmation
requirements, verified-authentication gating, ranked alternatives,
unsupported and offline outcomes, actual offline workspace search and
presentation, result-link selection, ownership isolation, and runtime-event
ordering/correlation. Tool context tests verify canonical request correlation
survives while tool invocation IDs remain distinct. Browser unit tests cover backend failure reporting and
successful fallback to a real configured search backend. The separate
`tests/test_browser_search_live.py` suite is an opt-in external-service test;
it must be run with `JARVIS_BROWSER_SEARCH_ENABLED=1` and is not a substitute
for a full authenticated command deployment test.

The current registered operations prove public web search, media discovery,
and local workspace search only. A media-playback request is recognized and
returns an explicit unsupported result because no playback capability is
registered. No current execution surface proves page interaction,
authenticated service access, email send, or device control. There is no real
second provider for the public web operations. Provider fallback, remote
runtime continuity, cross-device handoff, and deployment-level availability
remain unverified until a compatible real surface and deployment are configured
and exercised.

## Verification performed

From `platform/`, the focused resolver, command-runtime, durability,
truthfulness, project-intelligence, capability-contract/fabric, ToolRegistry,
and PlanValidator suites passed with **180 passed, 2 skipped**:

```text
python -m pytest tests\test_world_resolver.py tests\test_command_runtime_integration.py tests\test_runtime_durability.py tests\test_runtime_truthfulness.py tests\test_project_intelligence.py tests\test_capability_contract.py tests\test_capability_fabric.py ..\tests\test_tool_registry.py ..\tests\test_plan_validator.py -q -o addopts=''
```

With `JARVIS_BROWSER_SEARCH_ENABLED=1`, the live chat integration test passed
and exercised sourced Avengers discovery, ordinal follow-up to the actual
second result, a non-media web research request, durable command selection,
ordered runtime events, and conversation presentation:

```text
python -m pytest tests\test_world_resolver.py::test_live_chat_executes_and_presents_real_discovery_results -q -o addopts=''
```

The opt-in live test makes real public search requests; it does not establish
provider redundancy, authenticated service interaction, or deployment
independence. The legacy browser API tests currently cannot be collected in
this platform checkout because their fixtures import the absent `api.main`
module. Existing provider-dependent chat tests also remain environment
sensitive; no authorization or provider policy was weakened to make them pass.

Presentation contract verification in this checkout:

* Focused backend regression command, including contract, world resolver,
  command-runtime, durability, and truthfulness tests: **60 passed, 2 skipped**.
* Shared-fixture consumers: Python text renderer assertions passed, and the
  web adapter's Node conformance suite passed **7 tests**. The isolated
  presentation contract suite passed **15 tests**.
* The opt-in live chat scenario performed real Avengers discovery, returned
  observed HTTPS sources with a v1.1 research presentation and observed-at
  provenance, matched the command runtime event payload and persisted chat
  history, then selected the actual second result in the same conversation:
  **1 passed**.
* ESLint on the presentation adapter, web message renderer, and contract
  types completed without errors.

The live command is:

```text
$env:JARVIS_BROWSER_SEARCH_ENABLED='1'
python -m pytest tests\test_world_resolver.py::test_live_chat_executes_and_presents_real_discovery_results -q -o addopts=''
```

Frontend-wide type validation remains blocked by unrelated existing errors in
`src/app/holographic/page.tsx`, `src/features/chat/store.ts` (including stream
status/nullability), and `src/features/voice/realtime/{store,voiceEngine}.ts`.
The command `npx tsc --noEmit` reported those errors.
`npm run build` compiled the optimized bundle but stopped during its TypeScript
phase at the same existing `holographic/page.tsx` error. ESLint over the
broader modified chat API/store files also reports an existing explicit-`any`
in `store.ts`; the focused presentation renderer lint is clean. These failures
were not hidden by weakening the types or changing unrelated behavior.

The web conformance adapter uses Node's built-in test runner because this
frontend package has no configured unit-test script:

```text
node --test frontend\web\src\features\chat\presentation-adapter.test.mjs
```
