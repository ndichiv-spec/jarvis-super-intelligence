# Legacy test-suite retirement record

The canonical application is the FastAPI service in `jarvis_backend`; its
supported entrypoint is `jarvis_api:app`. The following checked-in tests
targeted modules that are absent from the canonical source tree and absent
from the reachable repository history. They could not exercise implemented
behavior here. They have been removed rather than replaced with placeholder
modules or unconditional passing tests:

## Original collection import blockers

Every reported import was traced through tracked source, callers, and reachable
Git history. No compatibility-only module was added.

| Reported import | Root cause and disposition |
|---|---|
| `core.advanced_page_transactions` | Imported only by the retired `tests/test_advanced_page_transactions.py`; no implementation exists in the tracked history. The prototype test was removed. |
| `config.settings` | Imported by the retired `tests/test_engine.py`. The maintained configuration module is `infrastructure.config.settings`; the legacy test targeted a separate absent engine package and was removed. |
| `core.enhanced_browsing_engine` | Stale prototype import in the legacy browsing/search tests. Supported browsing and search behavior is implemented by `jarvis_backend.routers.browser` and `jarvis_backend.routers.search`; tests now target those maintained surfaces. |
| `digital_clock` | The implementation is `frontend.digital_clock`, not a top-level module. `tests/test_github_connector.py` now imports the existing frontend package module. |
| `api.routers` | Legacy package path; the mounted API routers live under `jarvis_backend.routers`. Wiring tests now inspect the canonical FastAPI application and its routers. |
| `core.metrics` (both test locations) | Stale imports in `tests/test_metrics.py` and `tests/test_metrics_direct.py`. The maintained metrics implementation is `infrastructure.observability.metrics`; both tests now target it. |
| `web_server` | Obsolete server module name. The supported application is exported by `jarvis_api:app` and `jarvis_backend.main`; observation tests now use the in-process canonical app. |
| `api.router_registry` | Legacy router discovery path. Tests now verify the routers actually mounted by the canonical backend instead of importing a nonexistent registry. |
| `core.agents` | Imported by the retired prototype orchestration suite. Maintained agents live in `jarvis_backend.agents` and `jarvis_backend.routers.agents`; focused tests cover these supported components. |
| `core.quantum_computing` | Imported only by the retired Tier 6 prototype test. No implementation or mounted capability exists in the tracked history; the unsupported feature is not advertised as part of the backend. |
| `core.tier8_integration` | The old dashboard and prototype tests depended on an absent subsystem. Their imports, initialization, and unbacked routes were removed; the retired test records the unsupported surface. |
| `core.tier9_integration` | Same retirement decision as Tier 8: no implementation or backend route existed. Dashboard imports and prototype tests were removed rather than replaced with a stub. |

The `core.*`, top-level `api.*`, and `web_server` paths were never present as
implementations in the reachable history. The names `digital_clock`,
`metrics`, and the backend routers were moved/maintained under their current
packages and their callers were updated. Collection succeeds from the project
root using the configured `testpaths`; running pytest with the repository path
as an explicit argument also collects unrelated root-level experiment files
and is not the documented suite command.

The import-only prototype assertions in `tests/test_memory.py` were replaced
with checks against the maintained cognitive-memory routes. Those tests now
exercise `/api/v1/cognitive/memory/stats` and verify its authentication
requirement; the obsolete `/api/v1/memory/sessions` route is not advertised.
The chat memory-injection tests use the existing seeded test administrator
fixture rather than depending on a missing `auth_user` fixture.

| Retired test file | Unavailable prototype surface | Maintained coverage or disposition |
|---|---|---|
| `tests/test_advanced_page_transactions.py` | Advanced page transactions, training, optimization, monitoring, and security classes under `core.*` | Browser authorization and session ownership are covered by `tests/test_browser_api.py`; platform security is covered by the auth, system, and connector suites. |
| `tests/test_engine.py` | Standalone `core.engine` mission engine and its `services` package | The running backend and runtime contract are covered by `tests/test_runtime_status.py`, `tests/test_runtime_bootstrap.py`, and API tests. |
| `tests/test_suite.py` | `core.agents.advanced_agent_orchestration` and top-level legacy auth/rate-limiter/monitoring modules | Current authentication, rate-limit, observability, and agent lifecycle suites remain under `tests/` and `tests/infrastructure/`. |
| `tests/test_tier6_integration.py` | Unimplemented quantum, photonic, DNA, and other Tier 6 integrations | Not advertised or wired into the canonical backend. No compatibility stubs were added. |
| `tests/test_tier8.py` | Unimplemented Tier 8 marketplace/governance/productivity integrations | Not advertised or wired into the canonical backend. |
| `tests/test_tier9.py` | Unimplemented Tier 9 neuromorphic/photonic/biological integrations | Not advertised or wired into the canonical backend. |
| `tests/test_advanced_rag.py` | Legacy `core.advanced_rag` implementation absent from this repository | Current permission-aware knowledge retrieval is tested in `tests/test_rag_integration.py`; no legacy RAG HTTP API is claimed. |
| `tests/test_enhanced_capabilities.py` | Prototype AI, streaming, and vector modules under `core.*`; checks swallowed import/network failures and did not assert results | No corresponding API routes are mounted by the canonical backend. Supported health, search, and runtime routes are exercised in the in-process API suites; prototype marketplace/mobile imports remain a separate migration item. |
| `tests/test_capabilities.py` | Obsolete tier-based `core.capabilities`, `core.tier1_integration`, `core.tier2_integration`, architecture, and domain-mapper APIs; these modules are absent from the reachable source trees and have no canonical callers | Current capability contracts and registration are covered by `tests/test_capability_contract.py`, `tests/test_capability_fabric.py`, and the maintained `jarvis_backend` capability suites. |
| `tests/test_config.py` | Its `core.config`, `core.logging`, `core.error_tracker`, and `core.database` imports targeted an absent legacy package | Configuration assertions now use `infrastructure.config.settings`; logging, error tracking, and database behavior are covered by `tests/infrastructure/test_logsys.py`, `tests/infrastructure/test_errors.py`, and the persistence suites. |
| `tests/test_env_bootstrap.py` | Imported an untracked `_env` module from the parent workspace `F:\\AI` and asserted that workspace-specific defaults were present. The module is absent from this repository's reachable source history. | Removed the cross-checkout tests rather than making canonical test results depend on or modifying the neighboring workspace. The canonical runtime bootstrap remains covered by `tests/test_runtime_bootstrap.py`; admin production-configuration guards are covered by `tests/test_security_regression.py`. |
| `tests/test_tier11.py` | Imported absent `core.universal_interface`, `core.production_monitoring`, and `core.neuro_symbolic` prototypes. No corresponding backend implementation or mounted route exists in this checkout. | Removed the unsupported Python backend suite. This does not remove the separate experimental frontend coordination source. |
| Legacy tests in `tests/test_integration.py` | Imported absent `core.orchestrator` and `core.error_handling`; PostgreSQL/Redis probes used broad exception catches and had no declared disposable-service fixture. | Retained only authenticated agent-collaboration and mounted health-route tests. Database migrations and persistence behavior remain covered by the maintained database suites. |
| Import assertions in `tests/test_speech.py` | Expected absent `core.speech*`, `core.voice_interface`, `core.voice_gateway`, and `core.audio_engine` packages. | Replaced with a contract test for the canonical `/api/v1/voice/status` endpoint. Voice execution and provider-unavailable behavior remain covered by `tests/test_voice_runtime_boundary.py`, `tests/test_openai_compat.py`, and `tests/test_reliability_remediation.py`. |

The old Tier 8 and Tier 9 dashboard imports, initialization calls, and
unbacked HTTP routes were removed from `frontend/dashboard/main_dashboard.py`.
The dashboard no longer fails at import/startup because of those missing
modules, and it no longer advertises those unsupported endpoints.

`tests/test_api.py`, `tests/test_browsing_api.py`, `tests/test_page.py`,
`tests/test_observation.py`, `tests/test_router_registry.py`,
`tests/test_integration_wiring.py`, `tests/test_metrics.py`, and
`tests/test_metrics_direct.py` now exercise the canonical FastAPI app or its
maintained observability implementation. They do not import an unrelated
workspace or issue requests at module import time.

The old `_whatsapp_check.py` assertion was also removed from
`tests/test_search_navigation.py`: it pointed outside this checkout to a
workspace scratch script that is neither tracked nor part of the product.
Maintained navigation tests now use the canonical synchronous in-process
client, the `/api/v1/search/` route, and the endpoint's SSRF rejection for
unsupported protocols.
