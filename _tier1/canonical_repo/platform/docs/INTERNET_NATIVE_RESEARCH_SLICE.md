# Internet-Native Conversation Research Slice

## Architecture map

The owner-facing path is now conversation-first. `/` redirects to `/chat`,
which mounts the existing `ChatWindow` inside the shared authenticated shell.
On `/chat`, navigation is limited to Assistant, Task Runtime, and
Administration; the broader optional navigation and system/provider panels
remain available on the existing dashboard routes.
The dashboard, holographic page, account settings, and other destinations are
retained as optional routes; none is required to submit this research task.

```text
Owner
  -> web /chat (ChatWindow; POST /api/chat/stream by default)
  -> authenticated legacy chat route (server-side principal and session owner)
  -> ChatService stream_message/send_message
  -> resolve_world_intent("research.compare")
  -> durable command + execution ID, request/conversation correlation
  -> World Resolver selects the registered research.compare capability
  -> BrainOrchestrator + PlanValidator + ToolRegistry authorization
  -> ResearchCompareTool
       -> BrowserSearchTool -> HttpBrowserEngine
            -> DuckDuckGo Lite / Wikipedia search results and snippets
       -> provider-fabric discovery -> two distinct provider consultations
       -> one bounded synthesis call through the first successful provider
  -> observed search artifacts + attributed consultation results
  -> command evidence, lifecycle events, result and presentation revision
  -> persisted assistant message
  -> validated Presentation Contract 1.1 rendered inline by ChatMessageBubble
```

The comparison request uses one identical prompt for two distinct provider IDs;
their responses are retained with provider/model attribution. Only after both
independent calls finish does the first successful provider receive a separate
synthesis prompt containing the observations and each successful response. The
final report labels that synthesis by provider, does not present provider analysis as
verified fact, and includes numbered source links. Provider discovery,
consultation, or synthesis failure produces a partial result, not a fabricated
reply or consensus. One successful `ResearchCompareTool.invoke` makes at most
three provider calls: two concurrent consultations and one synthesis. However,
the shared Brain orchestrator can retry a failed transient capability under its
general retry budget (three retries by default). The end-to-end request therefore
does not yet have a separately enforced aggregate provider-call ceiling.
A repeated
`client_message_id` replays the persisted result rather than repeating those
calls.

Search uses the existing opt-in HTTP search adapter. It returns search-result
snippets and timestamps; this slice does not fetch or verify the linked pages.
Provider prompts explicitly treat snippets and previous model output as
untrusted data. The report states that no image or chart was generated: this
research capability currently returns text and citations, and does not silently
invoke a separately billable image operation.

## Capability status

| Capability | Classification | Evidence and boundary |
|---|---|---|
| Authenticated conversation-to-command execution | IMPLEMENTED; TESTED WITH FIXTURES | Authenticated `/api/chat` path, owner-bound session, durable command/execution IDs, lifecycle events, persisted message and presentation revision are exercised by the conversation integration test. |
| Public web search | IMPLEMENTED; TESTED WITH FIXTURES; UNCONFIGURED in inspected process | Uses the registered `BrowserSearchTool` and existing `HttpBrowserEngine`; `JARVIS_BROWSER_SEARCH_ENABLED=1` is required. The flag was absent from the inspected process environment, and no live search was run. |
| Provider availability and independent consultation | IMPLEMENTED; TESTED WITH FIXTURES; UNCONFIGURED in inspected process | Uses the provider registry/router and `ProviderGateway`, not a hardcoded availability catalog. The first two independent responses must come from different provider IDs. Environment credentials were not used for tests or live calls; no deployment credential store was inspected, so deployment configuration is unknown. |
| Attributed comparative synthesis | IMPLEMENTED; TESTED WITH FIXTURES | One additional bounded call synthesizes actual successful consultant responses. A timeout, provider identity mismatch, or failure remains partial and retains the original attributed responses. |
| Text, citations, and source provenance rendering | IMPLEMENTED; TESTED WITH FIXTURES | Presentation Contract 1.1 validates the response, source references, correlation, task state, and source observation timestamps; the web conversation renderer displays Markdown and source links inline. |
| Generated-image presentation | IMPLEMENTED; TESTED WITH FIXTURES; UNCONFIGURED in inspected process | Existing image-generation/media capability has separate deterministic tests. It is not invoked by this research slice and has not been live-verified. |
| Audio, video, charts, supplied photographs, and arbitrary interactive websites | BLOCKED | These are not result primitives in the current presentation contract/research execution path. The HTTP browser is not a JavaScript browser and does not claim authenticated website actions. |
| Worker restart and deployed persistence | IMPLEMENTED; TESTED WITH FIXTURES; BLOCKED for live verification | Durable command, event, presentation-revision, replay, and recovery code has fixture coverage. No independent deployment, process restart, database restore, or cross-device recovery was tested. |

No capability in this matrix is LIVE VERIFIED. The process environment check
found the web-search gate and common provider/image API-key variables absent;
this does not establish the state of external secret stores or a deployment.
No production readiness or public availability claim is made.

## Security, cost, and persistence

- The chat route supplies the authenticated server principal; the command,
  conversation, events, and presentation revision remain owner-scoped.
- Research requires both `web:read` and `model:consult`. The explicitly
  requested research intent is the confirmation boundary for this read-only
  network operation; it does not authorize website writes, purchases, or
  communications.
- Tool arguments are validated by the registered schema and tool registry.
  Provider credentials remain in the server-side provider fabric and are not
  included in prompts or presentation payloads.
- Search-result URLs are restricted to public HTTPS sources. Private and
  loopback IP literals are filtered before presentation. This research path
  does not dereference result URLs, so it is not evidence that arbitrary browser
  navigation or DNS-rebinding SSRF is safe.
- Consultant calls are bounded to 25 seconds at the gateway and 30 seconds at
  the task boundary; provider discovery is bounded to 10 seconds. The two
  independent calls are the only concurrent provider calls in one tool
  invocation. Cancellation is propagated to the async gateway operation and
  provider calls have no adapter-level retry. The generic orchestrator can,
  however, retry a failed transient capability; aggregate retries are not
  bounded specifically for this operation.
- Provider routing prioritizes the existing low-cost model class. Provider
  reported USD cost is recorded when every attempted call supplies it;
  otherwise task-budget accounting estimates $0.01 per attempted provider call.
  This estimate is not vendor billing, and there is no verified provider-side
  spending cap in this checkout.
- Request ID, conversation ID, command ID, and execution ID are carried into
  durable events and the presentation. Idempotent replay is fixture-tested.
  Actual worker restart and database backup/restore remain unverified.

The first test invocation used the platform test fixture's default tracked
SQLite path. Its autouse fixture removed and recreated
`platform/tests/_test_jarvis.db`, changing it from 344,064 to 606,208 bytes.
That database is preserved in its current working-tree state; subsequent
platform test runs used unique temporary database paths. No manual database
restore, checkout, or cleanup was run.

## Verification evidence

The final focused backend run, from `platform`, used an isolated
`JARVIS_TEST_DB_PATH` and completed:

```text
pytest -q tests/test_research_compare_runtime.py \
  tests/test_presentation_contract.py tests/test_world_resolver.py \
  tests/test_command_runtime_integration.py tests/test_runtime_durability.py
60 passed, 2 skipped
```

The budget tests, from the canonical repository root:

```text
pytest -q tests/test_task_budget.py
12 passed
```

The web frontend was type-checked, its existing presentation-adapter tests
passed (10 tests), and `next build` completed with `/chat` included in the
generated routes (46 static pages). Next.js emitted workspace-root inference
and stale Browserslist-data warnings. After simplifying the `/chat` navigation,
the changed sidebar passed ESLint and the frontend type-check; a fresh
production build also completed with `/chat` and 46 static pages.

From `platform/frontend/web`, the commands were:

```powershell
node .\node_modules\typescript\bin\tsc --noEmit -p tsconfig.json
node --test src/features/chat/presentation-adapter.test.mjs
node .\node_modules\next\dist\bin\next build
```

The final assistant-navigation checks were:

```powershell
npm exec eslint -- src/components/layout/sidebar.tsx
npm exec tsc -- --noEmit
npm exec next build
```

A local `agent-browser` smoke opened `http://127.0.0.1:3101`; the root
redirected to `/chat`, and the rendered shell showed the conversation composer
with only Assistant, Task Runtime, and Administration navigation. The backend
was not running (`Backend API unavailable`), so no message was submitted and
this is not evidence of an end-to-end live conversation.

An additional attempt to run local/metadata URL-blocking cases from
`tests/test_browser_api.py` was blocked during fixture setup by
`ModuleNotFoundError: No module named 'api'`; that legacy test module imports
an `api.main` package not present on the platform test path. The attempted
command was:

```powershell
pytest -q tests/test_browser_api.py -k 'navigate_blocks_localhost or navigate_blocks_metadata'
```

This run is not counted as security test evidence. The research-specific
presentation tests do verify that a loopback URL is not returned as a public
citation.

No provider, web-search, image-generation, deployment, HTTPS, or independent
client test was run live. The fixtures above do not incur provider charges.

## Remaining work and next milestone

The next useful milestone is an isolated staging run: configure the web-search
gate and two owner-approved, low-cost provider credentials server-side, set an
explicit pre-call spend and attempt ceilings, then obtain approval for one
research request (up to three provider calls per tool invocation). Verify
actual source observation timestamps and provider
attribution, cancellation, idempotent replay, owner isolation, and recovery
after a worker restart from a separate client.

Further work should add cost-limit preflight enforcement using vendor pricing,
fetch-and-verify source pages through an SSRF-hardened egress adapter, and only
then extend the validated presentation contract for actual chart/image/audio/
video outputs. Until that work and live evidence exist, the slice is
fixture-verified rather than production-ready.

## Controlled live-staging preflight — 2026-10-10

**Decision: BLOCKED before external calls.** This checkout is a local Windows
development workspace, not an identified staging deployment. No staging
hostname, staging credentials, owner-approved staging identity, or separate
approval for a potentially billable live test was supplied. No external search,
AI provider, deployment, DNS, HTTPS endpoint, secret store, database, or Redis
service was contacted. Live provider approval is therefore still required.

### Preflight findings

| Area | Observed result |
|---|---|
| Git/worktree | Branch `main`, two commits ahead of `origin/main`; substantial pre-existing modified and untracked work remains. Nothing was reset, cleaned, committed, or reverted. |
| Deployment target | No staging target or hostname is configured in the inspected checkout. A production Compose template and runbook exist, but the production `.env` file is absent; Docker is not installed. Deployment credential state and external secret-store state are unknown. |
| Local processes | PostgreSQL 17 is listening on local port 5432 and Redis on 6379. Neither service was contacted. No listener was found on backend ports 8000/8001 or frontend ports 3000/3101; local `/health/live` and `/health/ready` probes on 8000 and 8001 were unavailable. |
| Search | `JARVIS_BROWSER_SEARCH_ENABLED` is unset in the inspected process. The adapter uses DuckDuckGo Lite with Wikipedia fallback; search results are snippets. Linked result pages are not fetched by this research path. No live search was run. |
| Providers | The inspected process had no OpenAI, Google, NVIDIA, Hugging Face, or AWS credential variables set. No local or remote secret manager was inspected. Provider readiness outside this process, including any deployed configuration, is unknown. The production Compose template does not currently wire research-provider credentials into the API service. |
| Request/cost bound | Runtime code sets a five-minute task time budget and an estimated `$1.00` task cost budget. The Brain orchestrator accounts for tool cost after the tool returns; the task budget is not an enforceable pre-call provider spend ceiling. Provider-reported cost may be missing or non-authoritative. No vendor billing records were available. |
| Database safety | Test execution below used a unique temporary SQLite path, not the tracked test database. The tracked working copy was only read for hashes, schemas, and row counts; neither it nor its baseline was overwritten. |

Before any live request, the staging operator must provision an HTTPS staging
target and a dedicated owner account; enable `JARVIS_BROWSER_SEARCH_ENABLED=1`
on the backend; and inject at least two distinct, approved provider credentials
server-side (for example `OPENAI_API_KEY`/`JARVIS_OPENAI_API_KEY` and
`GOOGLE_API_KEY`/`JARVIS_GOOGLE_API_KEY`, or an equivalent supported pair).
The current production Compose template needs a reviewed server-side secret
injection path for those research providers. Select approved low-cost models
and provider priority, establish a hard request/cost ceiling that is checked
before each external call, and separately approve one request. Without those
controls, stop before search or provider invocation.

### Commands and tests run

The preflight inspected the branch/worktree and diff with
`git branch --show-current`, `git status --short --branch`, and
`git diff --stat`. PowerShell inspected listening ports/process names, checked
the presence (not values) of deployment/provider environment variables and
local `.env` paths, and probed only `http://127.0.0.1:8000/health/live`,
`http://127.0.0.1:8000/health/ready`,
`http://127.0.0.1:8001/health/live`, and
`http://127.0.0.1:8001/health/ready`. Docker availability check returned
`docker=not-installed`. No secret values were printed.

Database comparison used Python 3.13.4 to obtain the tracked baseline through
`git show HEAD:_tier1/canonical_repo/platform/tests/_test_jarvis.db`, write only
that baseline to a temporary file, and open both databases with SQLite
`mode=ro`. It inspected file hashes/sizes, table names, schemas, and per-table
row counts only; row contents were not read.

The only tests run for this preflight were fixture-backed tests from
`platform`, with `JARVIS_TEST_DB_PATH` set to a unique temporary file and
removed after the run:

```powershell
pytest -q tests/test_research_compare_runtime.py tests/test_presentation_contract.py tests/test_runtime_durability.py
```

Result: **36 passed in 34.23s**. Search and provider calls in these tests are
fixtures/mocks; this is not live evidence. No other test, build, or deployment
command was run in this preflight.

### Tracked test database reconciliation recommendation

The modified `platform/tests/_test_jarvis.db` is 606,208 bytes (SHA-256
`9ed4a6c3f904e72f2b12629b69c302da1fcd1ae3af1f06dd76c953f832c2a593`).
The `HEAD` baseline is 344,064 bytes (SHA-256
`f1b15bccf463ff9d89606617f45a6fbcfa81116cb2a5cb76eac919fa9bb67ee9`).
The modified copy contains two additional tables, `audit_events` and
`usage_costs`; five runtime tables have unchanged schemas but higher row
counts: event sequences 1→8, events 1→80, executions 0→9, plan steps 0→4,
and plans 0→5. No data rows were inspected.

Preserve both files unchanged. Before any reconciliation, make separately
protected copies, confirm the intended data/schema from the owning operator,
and merge/export only explicitly identified records into a fresh isolated
database. Do not restore the tracked baseline over the modified copy. For
future test runs, keep using a unique temporary `JARVIS_TEST_DB_PATH`; the
platform test fixture otherwise defaults to this tracked path.

### Capability status for this preflight

| Capability | IMPLEMENTED | FIXTURE-TESTED | LIVE-VERIFIED | UNCONFIGURED | BLOCKED | NOT-TESTED |
|---|---|---|---|---|---|---|
| Authenticated `/chat` research command and inline presentation | Yes | Yes | No | — | Yes: no staging target/owner identity | Live auth, rendering, persistence |
| Public search and source snippets | Yes | Yes | No | Yes: process gate absent; deployment unknown | Yes: no target/approval | Live invocation; linked pages not fetched |
| Two-provider comparison and synthesis | Yes | Yes | No | Yes: no provider environment credentials; secret-store state unknown | Yes: no injected staging credentials/approval | Real provider identities, responses, cost records |
| Pre-call external-spend ceiling | No | No | No | Yes | Yes: no enforceable ceiling | Vendor billing/cost reconciliation |
| Owner isolation, URL/network protection, cancellation, replay | Partial | Yes, narrow fixture coverage | No | — | Yes: no authorized staging identities | Cross-owner HTTP denial, URL bypass/DNS rebinding, live cancellation/replay |
| Persistence and worker-restart recovery | Yes | Yes, isolated fixture persistence/reopen | No | Deployment database target unknown | Yes: no worker/database restart target | Actual worker restart/restore |
| HTTPS, deployment authentication, log secrecy | Implemented in deployment configuration/code | Limited deterministic coverage | No | Yes: no target/domain/secrets | Yes | HTTPS/auth end-to-end, operational logs |
| Multimodal presentation beyond research text/citations | Partial | Narrow image/voice fixtures exist | No | Provider configuration unknown | Yes for this request | Do not claim dynamic multimodal completion |

There were **0 external search calls, 0 provider calls, 0 synthesis calls, and
0 live cost records** in this preflight. The actual external cost incurred was
`$0`. This is not evidence of a successful live request. The smallest next
milestone is to provision an isolated HTTPS staging target, wire two approved
server-side provider secrets, add a pre-call spending limit and attempt limit,
then obtain explicit approval for one authenticated research request.
