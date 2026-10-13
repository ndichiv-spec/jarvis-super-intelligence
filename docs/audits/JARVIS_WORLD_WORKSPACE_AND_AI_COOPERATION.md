# JARVIS World Workspace and AI cooperation

## Scope and product boundary

The World Workspace is an owner-facing way to submit work to JARVIS's
existing runtime. It is not a second intelligence engine, task database, or
authorization authority. A conversational turn remains a conversational turn;
submitting a durable task is an explicit separate action. Selecting an
environment in the frontend does not authorize or dispatch a task.

JARVIS is not yet a general internet-wide autonomous agent. It can use only
capabilities that are present in the existing registries, have an executable
implementation, satisfy authorization and policy checks, and are available
to the runtime. Discovery of a website or a provider does not by itself grant
permission to invoke it or establish that an external action succeeded.

## Canonical request-to-execution path

The durable command path is the authoritative route for planned work:

`authenticated owner → POST /api/v1/commands → routers/commands.py → AgentExecutor → existing capability discovery/tool registry → task execution → durable command/task state and events → GET /api/v1/commands/{command_id}`

- `jarvis_backend/routers/commands.py` accepts a natural-language `goal`,
  optional `conversation_id`, idempotency `request_id`, capability constraints,
  and autonomy mode. Its create route scopes records to the authenticated
  principal and returns the persisted command record.
- `jarvis_backend/execution_fabric.py` owns the `Task` lifecycle, graph
  construction, capability discovery, execution, authorization gates,
  checkpoints, and resume. It delegates discovery/registry construction to
  `research_engine.capability_contract` and
  `research_engine.capability_tools`.
- `jarvis_backend/celery_tasks.py` and
  `jarvis_backend/celery_app.py` provide the production worker enqueue/recovery
  path. Command lease recovery and task checkpoints are existing mechanisms;
  workers must report recovered, failed, blocked, or pending work honestly.
- `jarvis_backend/db.py` and `jarvis_backend/core.py::Store` persist command
  and task state. `jarvis_backend/runtime_events.py` persists the owner/session
  event stream. Runtime events supplement task state; they are not a replacement
  for the durable command record.
- `GET /api/v1/commands` lists only records owned by the caller.
  `GET /api/v1/commands/{command_id}` is also owner-scoped and returns 404 for
  an unknown or non-owned record.
- `POST /api/v1/commands/{command_id}/authorization` approves or rejects
  pending work. When multiple graph nodes await authorization, approval is
  scoped to an outstanding node ID. Rejection cancels that command. There is
  no separate approval-revocation endpoint; approval is not rollback of an
  action already performed.

Ordinary chat follows a separate existing path:
`jarvis_backend/routers/ai.py` → `jarvis_backend/chat_service.py` →
`jarvis_backend/gateway.py::ProviderGateway`. Chat may use registered
conversation capabilities, while durable multi-step command work uses the
execution-fabric graph. The workspace must not silently turn an ordinary chat
message into an external action.

## Discovery and capability execution

The execution-fabric discovery interface and tool registry are the canonical
discovery/execution mechanism for durable commands. The in-process
`jarvis_backend/capability.py::CapabilityRegistry` and
`Orchestrator`, populated by `jarvis_backend/capabilities/__init__.py`,
serve registered capabilities used by chat and other API paths. Provider
routing is owned by `ProviderGateway` and existing provider adapters. These
are distinct layers in the current architecture; they must not be represented
as one already-unified, live-verified registry.

Important limitation: `research_engine` is imported from the sibling
`F:\\AI\\research_engine` workspace and is not included in this checkout.
Consequently a clean clone does not yet establish that command discovery and
tool registry construction are self-contained. Do not add an empty substitute
or claim the full tool catalog is available until the dependency is packaged
and tested from a clean environment.

The request planner should use official APIs or supported connectors when
available, and should treat browsing, browser actions and arbitrary external
services as untrusted. Retrieval is evidence, not task completion. A website
visit is not authentication, an API response is not a verified transaction,
and model agreement is not independent proof. Record only provenance and
execution evidence actually returned by the selected capability.

## AI cooperation and privacy

`ProviderGateway` and provider adapters are the canonical model boundary;
the model/provider registries describe or route existing integrations.
`jarvis_backend/routers/agents.py` has collaboration endpoints, but they are
not evidence of a general multi-model consensus/verification system.

The runtime may use parallel or sequential collaborators only where the
existing task/capability path has an explicit implementation, providers are
available, the incremental cost/latency is justified, and privacy policy
permits the specific data transfer. External model providers are service
principals, not owners. They must not receive unrelated conversation history,
credentials, authorization state, or files. Provider errors and unavailable
status must remain visible rather than falling back to fabricated results.

At audit time there is no verified live-provider collaboration run or
configured credential evidence. Deterministic provider tests prove local
contracts only; they do not establish live inference.

## Authorization, untrusted content, and consequential operations

Production owner identity is the configured JARVIS principal. Existing
`jarvis_backend/core.py` authentication and permission checks apply before the
command route. Command records and authorization decisions are scoped by the
server-side principal, not a client-supplied user or owner ID. Optional
collaborators must receive explicit invitations and per-resource permissions;
the current deployment remains owner-only rather than exposing a generalized
delegated-user product.

Command graph nodes that need approval use the existing
`AWAITING_AUTHORIZATION` contract. The UI can approve only pending node IDs
from the owner-scoped server response. Approval controls must not be rendered
for completed or unrelated nodes, and an approval error must not be presented
as successful dispatch. Cancellation cannot undo a completed external effect.
High-impact actions such as sending communications, deleting or publishing
content, or making purchases require explicit owner approval unless a
narrowly scoped policy explicitly grants the action.

Retrieved pages, documents, prompts and tool results are untrusted data. They
cannot change system authorization, grant themselves access, reveal secrets,
or suppress required review. Browser/network access must retain existing
domain policy, SSRF protections, sandbox isolation, deadlines, resource
limits, and audit handling. Upload and code-execution capabilities must
enforce content/size restrictions and execution isolation. This report does
not certify every connector against those requirements.

## Durable state, failure, and presentation

The current command lifecycle includes planning, queued/executing,
authorization-waiting and terminal outcomes, with task checkpoints and worker
lease recovery. Runtime events provide progress/resumption data, while
command/task records are the authority for current execution state. Idempotent
request IDs must be stable across client retries and cannot be reused with a
different task payload. A worker restart must not convert unfinished work to
success. Failure, cancellation, blocked authorization, partial completion and
verification outcomes must remain distinct in the client presentation.

`jarvis_backend/presentation/planner.py`, `resolver.py`, `registry.py`, and
`router.py` define an existing adaptive presentation system. It can choose a
supported structured presentation from available evidence, but it does not
make absent browser automation, media playback, mapping, or artifact rendering
capabilities exist. When a specialized renderer is unavailable, return a
clear, accessible conversational/status representation and preserve truthful
provenance.

Artifacts and durable records use existing JARVIS persistence and storage
boundaries. Do not store private prompts or output copies in browser local
storage just to preserve task display. Fetch owner-scoped history from the
authenticated API; minimize retained content according to configured privacy
policy.

## Integration evidence and remaining acceptance gates

Existing coverage includes command API ownership, idempotency, approvals,
leases/recovery, capability-fabric behavior, chat capability execution,
presentation, migration/persistence, and Celery runtime tests. These cover
components, not the complete end-to-end path from a natural-language owner
request through an authorized real external capability and verified useful
result.

The broader acceptance criterion remains unmet until all of the following
are verified in the appropriate environment:

- The workspace request UI creates a durable command through the authenticated
  canonical API while ordinary chat remains unchanged.
- Command planning discovers and invokes a real, authorized capability
  through the existing tool/capability registry, with truthful provenance
  and errors.
- A capability is exercised end to end with actual external access and
  permission, not only a mocked tool.
- Any AI collaboration has an explicit data-sharing decision and is tested
  with appropriate available providers; private context is not disclosed to
  unauthorized collaborators.
- Authorization blocks consequential work until the owner approves the
  pending action. Revoked sessions/devices lose access.
- A supported worker restart recovers task state without duplicate
  consequential actions or false completion.
- The selected output presentation is rendered and degrades accessibly when
  a specialized renderer is absent.

No Supabase project, external provider credentials, live deployment, DNS
domain, or host were available for this implementation. Supabase remains a
database-provider option via the existing persistence layer, not an
intelligence or authorization authority. Public deployment and internet-wide
capability are not claimed.
