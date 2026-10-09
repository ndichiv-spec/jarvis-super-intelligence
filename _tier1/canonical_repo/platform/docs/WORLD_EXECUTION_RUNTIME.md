# World Execution Runtime

## Current integration

Natural-language requests with a registered intent are resolved inside the
existing conversation and command path. The World Resolver does not own tool
registration, authorization, dispatch, persistence, or runtime events.

| Responsibility | Existing owner |
| --- | --- |
| Capability registration, tool schemas, invocation, permissions, risk policy, and secret scrubbing | `research_engine/tool_registry.py` and `research_engine/capability_tools.py` |
| Capability metadata, operation mappings, intent patterns, evidence requirements, and confirmation scope | `research_engine/capability_contract.py` |
| Plan validation, invocation authorization, evidence, and bounded re-planning | `jarvis_brain/orchestrator.py` and `jarvis_brain/plan_validator.py` |
| Authenticated durable command/execution lifecycle and ordered correlated events | `platform/jarvis_backend/routers/commands.py` and `platform/jarvis_backend/runtime.py` |
| HTTP page retrieval, public search, and text extraction | `platform/jarvis_backend/browser_engine.py` and `research_engine/tool_registry.py::BrowserSearchTool` |

registered providers of the requested operation, checks mapped inputs against
the tool schema, verifies declared evidence paths against the output schema,
requires a declared execution surface and observability, checks inventory
availability, endpoint/network constraints, accepted cost policy, and calls

Alternative candidates are passed to the existing bounded Brain re-planning
path. They are not assumed interchangeable: each must register the same
operation and pass the same schema, availability, authorization, and

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

successful fallback to a real configured search backend. The separate
`tests/test_browser_search_live.py` suite is an opt-in external-service test;
it must be run with `JARVIS_BROWSER_SEARCH_ENABLED=1` and is not a substitute
for a full authenticated command deployment test.

