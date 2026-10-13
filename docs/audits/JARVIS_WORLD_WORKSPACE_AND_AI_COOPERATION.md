# JARVIS World Workspace and AI Cooperation Audit

**Audit date:** 2026-10-13  
**Scope:** Existing `F:\AI\_tier1\canonical_repo` JARVIS platform checkout.  
**Status:** Runtime capabilities are implemented in bounded slices and have fixture coverage. This checkout is not a deployed, internet-wide autonomous service. No live external call or deployment is claimed by this audit.

## Canonical request and execution path

The owner-facing path is the authenticated conversation, not a capability dashboard:

```text
web /chat -> authenticated chat route -> ChatService
 -> durable command -> World Resolver -> BrainOrchestrator / PlanValidator
 -> ToolRegistry authorization and invocation -> runtime events and persistence
 -> verified Presentation Contract -> conversation renderer
```

The main entry points are `platform/jarvis_backend/routers/legacy.py::legacy_chat`, `platform/jarvis_backend/chat_service.py::ChatService`, `platform/jarvis_backend/routers/commands.py`, `platform/jarvis_backend/world_resolver.py::resolve_execution_surface`, `jarvis_brain/orchestrator.py::BrainOrchestrator`, `jarvis_brain/plan_validator.py::PlanValidator`, and `research_engine/tool_registry.py::ToolRegistry`. The registry is the executable capability authority; the capability contracts and catalogue describe its registered tools and do not install external code or grant permissions.

## Discovery, execution contracts, and external services

Discovery currently resolves operation metadata against registered capabilities, then checks schemas, availability/health, network needs, authentication dependencies, endpoint requirements, cost policy, and caller authorization before selection. Invocation repeats authorization and validates tool arguments. The durable command records the selected capability, results, failures, events, execution and presentation references.

The implemented research path uses the existing opt-in HTTP search adapter and `research.compare`. It returns search snippets and links, then can consult up to two configured providers independently and ask one successful provider to synthesize. Provider/model attribution, partial failures, timeouts, cancellation, and the distinction between model analysis and verified facts are retained. Retrieved pages are not fetched by this path. Website automation, arbitrary API discovery/installation, authentication to arbitrary services, and broad external capability acquisition are not implemented.

Capability manifests validate contracts for trusted, already registered tools. They do not install plugins, packages, MCP servers, credentials, or remote code. Discovered webpage/document text is passed as bounded untrusted data with explicit anti-instruction prompts in the research flow. This is not a general prompt-injection-proof browser or an SSRF-safe arbitrary page-fetch service.

## AI collaboration and data sharing

The runtime reuses the existing provider fabric and gateway rather than maintaining a second provider registry. Collaboration is task-specific: `research.compare` is the current independent parallel consultation plus sequential synthesis slice. Provider discovery/configuration failure and individual provider failure produce partial/error evidence; model agreement is not represented as factual verification.

Research comparison requires `web:read` and `model:consult`. The new regression test verifies the request cannot reach search or a provider if provider-consult authorization is absent. The current chat flow does not yet expose a general per-task privacy-policy selector that classifies arbitrary user context and filters fields per provider. Thus no claim is made that all private data-sharing policies have been implemented. Owners should not submit sensitive material to this research capability until an explicit sharing policy is wired through the runtime.

Provider costs are reported when adapters return usage. Otherwise the runtime uses estimates; there is no enforced vendor-side or pre-call aggregate spend ceiling specific to research comparison. The generic task budget is not a hard pre-call billing limit.

## Task persistence, lifecycle, and recovery

Commands, plans, executions, ordered runtime events, and presentation revisions use the existing persistence/runtime services. Chat message IDs and execution/presentation idempotency keys prevent supported duplicate work. Worker recovery requeues work only when it is known not to have started; work that may have caused side effects is marked `RECOVERY_REQUIRED` for reconciliation. Authorization waits and command status are represented in runtime state.

Deterministic tests cover database-engine reopen, idempotency, event ordering, owner-scoped command/presentation reads, approval denial/approval behavior, and orphan recovery. These tests are not evidence of recovery from a deployed worker restart, database failover, backup restore, or cross-device session revocation.

## Presentation integration

The runtime returns a versioned Presentation Contract carrying task state, components, data references, provenance, permissions, errors, and correlation IDs. The frontend renders supported conversation, research, map, and image content. Unsupported modalities produce an explicit text fallback; the contract does not claim that a website or media player was opened or that playback succeeded. See `platform/jarvis_backend/presentation_contract.py` and `platform/frontend/web/src/features/chat`.

## Identity, owner access, and device controls

Backend routes derive identity from the authenticated server-side principal, enforce owner-scoped records, and reject client-supplied identity as authority. Optional collaborators are not granted access by default; a complete invitation/delegation product model is not established by this World Workspace slice. Endpoint registrations are owner-bound and revocable. The added endpoint regression checks that a revoked endpoint cannot negotiate again. Separate-device enrollment, reauthentication, and independent-client revocation have not been live-verified. Database enforcement uses the project's application persistence boundary; no Supabase RLS policy is claimed as a security boundary here.

## Deployment and Supabase integration

`platform/deployment/production/docker-compose.prod.yml` provides a portless internal API/data network behind Caddy HTTPS, server-side secret files, resource limits, health checks, PostgreSQL, Redis, and persistent artifact volumes. The API now supports optional OpenAI and Google research keys through mounted Docker-secret files, and public search remains disabled unless `JARVIS_BROWSER_SEARCH_ENABLED=1` is explicitly configured. `SecretManager` reads `*_FILE` credentials without returning secret paths from its secret inventory. This is deployment configuration only: the deployment runbook is not evidence of a deployed service. No staging hostname, Docker host, provider credentials, or deployment authorization was available in the inspected checkout, so no deployment was performed.

Supabase is not a configured canonical persistence or authorization service in this slice. The existing runtime/database, identity, provider-secret, endpoint, storage, and audit boundaries remain authoritative. A future Supabase adapter must integrate with those authorities rather than add a second identity or task engine.

## Security controls and known limits

- Capability dispatch checks declared permissions and confirmation policy in the existing registry; plans are validated before invocation.
- External service credentials remain server-side in the provider secret boundary and are excluded from model-visible capability results.
- User/session/command/presentation/media reads are owner-scoped in backend routes.
- Public citation links are limited to HTTPS URLs that pass the current URL checks; search result links are not fetched by `research.compare`.
- Search and provider work are bounded by adapter/task timeouts and cancellation. Aggregate provider spend/retry limits are not a hard billing control.
- No general sandbox for arbitrary discovered code or downloaded browser/tool adapters is provided by this path.
- Production TLS, HTTPS authentication, external service credentials, and data recovery are not live-verified in this workspace.

## Acceptance evidence map

| Requested behavior | Existing evidence / boundary |
|---|---|
| Natural request routes without dashboard selection | `platform/tests/test_research_compare_runtime.py::test_authenticated_conversation_executes_and_presents_research_compare` exercises `/api/chat` through the canonical command path. |
| Relevant capability discovered and invoked | Same integration test verifies selected `research.compare`, fixture search, two model consultations, and synthesis. These are controlled fixtures, not live external calls. |
| Truthful provenance and errors | Research comparison tests cover provider attribution, partial failures, failed discovery, timeouts, cancellation, and observed source metadata. |
| Multi-model consultation | Fixture integration test verifies independent responses and synthesis; no real providers are live-verified. |
| Unauthorized provider data sharing is blocked | `test_compare_does_not_share_request_with_provider_without_consent` asserts missing `model:consult` denies before search/provider calls. This proves the declared permission gate, not general privacy classification. |
| Protected actions require authorization | Command approval-gate tests and tool-registry confirmation tests cover protected execution; external email sending is not demonstrated by this research slice. |
| Revoked device/endpoint loses access | Endpoint registry/API tests cover revocation; the added regression verifies post-revocation negotiation is denied. Cross-device production sessions remain unverified. |
| Supported persistence/recovery | `platform/tests/test_runtime_durability.py` covers engine reopen and worker orphan classification. No production restart/restore was performed. |
| Appropriate output and graceful fallback | `platform/tests/test_presentation_contract.py` covers research, map, image references, validation, and unsupported-modality text fallbacks; frontend adapter tests cover supported client rendering. |
| Deployment integration | Compose and runbook exist, but research secrets are not wired and no environment was deployed. This acceptance criterion is not complete. |

## Verification record and next milestone

The inherited platform verification report records deterministic focused test/build runs and explicitly distinguishes them from live provider/deployment checks (`platform/docs/PRODUCTION_VERIFICATION.md`, `platform/docs/INTERNET_NATIVE_RESEARCH_SLICE.md`). For this audit update, `py_compile` passed for the modified Python source and regression tests, and a direct secret-file smoke check passed without printing the secret. `git diff --check` passed. The focused pytest regressions could not be run: PyCharm interpreter setup created `platform/.venv`, then requirements installation failed because the pinned `ray==2.40.0` is unavailable for the detected Python 3.13 environment, leaving no `pytest` module installed. The generated virtual environment is ignored by Git; no requirements or lockfile were changed. Re-run the focused tests in the supported project Python environment before treating the new assertions as passing.

The next production milestone is a dedicated HTTPS staging environment with owner identity, approved search/provider secret injection, explicit per-request call and spend limits, database/volume backup and restore evidence, and separate-client authorization/revocation checks. Only then can a real end-to-end request be labeled live-verified. Until those conditions are met, JARVIS should be described as a locally fixture-tested runtime with bounded configured integrations, not as an internet-wide autonomous workspace.
