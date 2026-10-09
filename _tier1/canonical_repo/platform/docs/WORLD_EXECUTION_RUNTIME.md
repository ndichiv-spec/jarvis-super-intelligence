# World Execution Runtime

## Current integration

Natural-language requests with a registered intent are resolved inside the
existing conversation and command path. The World Resolver does not own tool
registration, authorization, dispatch, persistence, or runtime events.

| Responsibility | Existing owner |
| --- | --- |
| Capability registration, tool schemas, invocation, permissions, risk policy, and secret scrubbing | `research_engine/tool_registry.py` and `research_engine/capability_tools.py` |
| Capability metadata, operation mappings, intent patterns, evidence requirements, and confirmation scope | `research_engine/capability_contract.py` |
| Matching registered intent metadata, schema compatibility, candidate eligibility/ranking, result selection, and conversation presentation metadata | `platform/jarvis_backend/world_resolver.py` |
| Plan validation, invocation authorization, evidence, and bounded re-planning | `jarvis_brain/orchestrator.py` and `jarvis_brain/plan_validator.py` |
| Authenticated durable command/execution lifecycle and ordered correlated events | `platform/jarvis_backend/routers/commands.py` and `platform/jarvis_backend/runtime.py` |
| Session ownership, conversation persistence, request dispatch, and inline result presentation | `platform/jarvis_backend/chat_service.py` and the existing chat frontend |
| HTTP page retrieval, public search, and text extraction | `platform/jarvis_backend/browser_engine.py` and `research_engine/tool_registry.py::BrowserSearchTool` |

The resolver consumes the existing registry and its contracts. It ranks only
registered providers of the requested operation, checks mapped inputs against
the tool schema, verifies declared evidence paths against the output schema,
requires a declared execution surface and observability, checks inventory
availability, endpoint/network constraints, accepted cost policy, and calls
the existing `ToolRegistry.authorize` policy. Unknown health, cost, and latency
remain unknown; unknown is not reported as healthy or free.

Alternative candidates are passed to the existing bounded Brain re-planning
path. They are not assumed interchangeable: each must register the same
operation and pass the same schema, availability, authorization, and
observability checks. There is currently no second registered provider for
`media.discovery`, so alternate-surface fallback is implemented but has not
been demonstrated for media discovery.

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
creating a command. The durable command and execution identifiers flow into
the existing runtime event store. Events describe resolution, selection,
capability start/completion/failure, observed results, and presentation. Event
payloads use the existing secret scrubber and do not include provider
credentials.

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

## Verification boundaries

Focused resolver tests cover metadata-driven intent matching, schema-checked
selection, authorization filtering, ranked alternatives, unsupported and
offline outcomes, result-link selection, ownership isolation, and runtime-event
ordering/correlation. Browser unit tests cover backend failure reporting and
successful fallback to a real configured search backend. The separate
`tests/test_browser_search_live.py` suite is an opt-in external-service test;
it must be run with `JARVIS_BROWSER_SEARCH_ENABLED=1` and is not a substitute
for a full authenticated command deployment test.

At present, the registered world operation is public media discovery through
`search_web`. No current registered world intent proves page interaction,
authenticated service access, email send, device control, or playback. Provider
fallback, remote runtime continuity, cross-device handoff, and deployment-level
availability remain unverified until a compatible real surface and deployment
are configured and exercised.
