# JARVIS Core Runtime Boundary

## Ownership and request path

The core conversation and execution path stays within the existing runtime:

1. `jarvis_backend/routers/legacy.py::legacy_chat` authenticates the caller,
   takes the owner from the server-side principal, and passes the session,
   message id, and principal to `ChatService`.
2. `jarvis_backend/chat_service.py::ChatService._generate` routes supported
   registered intents through `_world_resolution_reply`. A caller-supplied
   conversation identifier is checked against that owner's session.
3. `_world_resolution_reply` creates or resumes a durable command through
   `jarvis_backend/routers/commands.py::_create_command`.
4. `jarvis_backend/world_resolver.py::resolve_execution_surface` selects only
   a registered tool whose operation mapping, schemas, availability, cost,
   permissions, and endpoint requirements are compatible.
5. `jarvis_brain/orchestrator.py` and `PlanValidator` authorize the plan;
   `research_engine/tool_registry.py::ToolRegistry.invoke` enforces the tool's
   risk, confirmation, and declared permissions at invocation.
6. `routers/commands.py::_execute_command` records the command/execution
   lifecycle, observed result, presentation revision, and ordered correlated
   runtime events through `jarvis_backend/runtime.py`.
7. The validated Presentation Contract is returned by the chat service and
   rendered by the existing web conversation renderer.

The World Resolver does not own registration, permission enforcement,
dispatch, storage, or durable events. The executable registry remains
`ToolRegistry`; capability contracts are metadata for those registered tools,
not a second registry or executable plugin system.

## Manifest and acquisition boundary

`research_engine/capability_contract.py` builds machine-readable manifests
from registered capability contracts. Validation checks stable identifiers,
numeric versions, typed object input/output schemas, supported schema
keywords, risk and approval metadata, dependency declarations, timeout and
cancellation semantics, and provenance/observability requirements. Schema
references and unsupported keywords are rejected rather than resolved or
executed.

Registration validates a manifest against the existing tool and canonical
contract. It rejects unknown tool IDs and mismatched schemas, permissions,
risk, confirmation requirements, provider dependencies, operations, and
other execution-boundary fields. Claimed lifecycle, availability, and health
are not accepted as evidence: registration derives those states from the
server's canonical contract/inventory. This API validates metadata for trusted
in-process adapters; it does not install code, packages, connectors, remote
servers, or credentials. There is no external capability-installation route.

Discovery uses the existing capability catalogue and provider/tool inventory.
It may describe candidates and current configuration, but does not authorize
new external data sharing, paid services, package installation, credentials,
shell execution, or device control. Those remain explicit server/user approval
boundaries.

## Image generation vertical slice

`image.generate` is the current multimodal conversation path:

* The resolver recognizes explicit image-generation requests and selects the
  existing `ImageGenerationTool`. The user request is treated as confirmation
  for that requested image operation; the tool still rejects calls without
  confirmation at the registry boundary.
* The adapter validates prompt length and credential-shaped content, invokes
  the configured OpenAI, Replicate, or Stability HTTP API, applies a bounded
  execution timeout, propagates cancellation, and does not retry paid
  generation implicitly.
* Provider output is checked before a media reference is issued. Base64 image
  bytes are validated and persisted under the private generated-media store;
  provider URLs are restricted, encrypted at rest, and proxied without
  redirects. References are owner-checked for issuance/revocation and expire.
* The execution persists a v1.1 image presentation and revision with request,
  conversation, command, and execution correlation. The existing chat renderer
  renders verified images and provides the contract's text fallback to
  renderers without image support. Invalid provider output is presented as an
  error, never as a completed image.
* Chat `client_message_id` replay returns the prior result rather than charging
  for a second generation.

The direct image API chooses a configured provider if the request omits one.
Provider-status responses distinguish `configured_unverified` from
`not_configured`; capability inventory uses `DEGRADED` for configured but
unverified providers and `NOT_CONFIGURED` when no credential is present. A
credential's presence is not a successful health check, and the configured
adapter is not claimed operational until an actual invocation succeeds. The
resolver and plan-validation gate may select that degraded adapter for an
explicitly requested image operation; the request then establishes success or
failure through the real provider call. No provider result is live-verified by
deterministic fixture tests.

## Compatibility, endpoint, and verification boundaries

Presentation Contract v1.0 remains readable; v1.1 carries task state,
provenance, media references, view state, and correlation. Endpoint registration
and negotiation routes already exist and are owner-bound. Endpoint capability
claims do not grant tool authority. No claim of cross-device continuity is
made without independent clients and restart/reconnect evidence.

The image-provider tests use deterministic HTTP fixtures and temporary media
storage. Live image generation is opt-in and requires a server-side provider
credential (`OPENAI_API_KEY` or `JARVIS_API_KEY_OPENAI`, `REPLICATE_API_KEY`,
or `STABILITY_API_KEY`). A live call can incur provider charges and was not
performed as part of deterministic validation.

External provider discovery beyond the integrations already registered in
JARVIS, arbitrary adapter/package installation, credential onboarding, and
cross-device continuity verification are not implemented by this slice.
