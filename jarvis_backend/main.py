"""JARVIS backend wiring.

Builds the single main FastAPI application that serves every JARVIS
/api/v1 endpoint AND integrates the Silverwing AI backend as a mounted
sub-application, so one process on one port (8000) powers the whole system.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

if os.environ.get("JARVIS_TEST_MODE") != "1":
    load_dotenv()

from .secret_config import load_file_secrets

load_file_secrets()

from fastapi.responses import JSONResponse

from jarvis_runtime import SILVERWING_BACKEND_ROOT

from . import websocket
from .core import DATA_DIR, ai_service, app, start_backend
from .observability import install_observability
from .runtime_status import router as runtime_status_router, build_canonical_runtime_status
from .routers import (
    agents,
    ai,
    auth,
    automation,
    billing,
    browser,
    challenges,
    codegen,
    commands,
    connectors,
    control_plane,
    curriculum,
    developer,
    experiments,
    extensions,
    global_knowledge,
    geography,
    health,
    improvements,
    knowledge,
    legacy,
    media,
    memory,
    misc,
    models,
    monitoring,
    multimodal,
    notifications,
    openai_compat,
    platform_identity,
    provider_status,
    rbac,
    research,
    sandbox,
    bio_growth,
    search,
    stark,
    system,
    verification,
    voice,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis")

SILVERWING_BACKEND = SILVERWING_BACKEND_ROOT

# ---- Integrate the Silverwing backend ------------------------------------ #
# Make Silverwing's sibling modules importable, then mount its app object as a
# sub-application so all of its /api/* + WebSocket routes are served here.
_silverwing_app = None
_silverwing_error = None
try:  # pragma: no cover - defensive integration
    import main as silverwing_main  # type: ignore

    _silverwing_app = silverwing_main.app
except Exception as _sw_err:  # noqa: BLE001
    _silverwing_error = str(_sw_err)
    logging.warning("Silverwing backend could not be integrated: %s", _sw_err)


def setup_routers() -> None:
    # Identity layer (OIDC login, sessions, RBAC, Provider Connection Center).
    try:
        from identity import configure_oidc_providers
        from identity import router as identity_router
        from providers.secrets import get_secret_manager
        secrets = get_secret_manager()
        configure_oidc_providers(secrets)
        app.include_router(identity_router)
        logger.info("Identity router integrated (OIDC + Provider Connection Center).")
    except Exception as exc:  # noqa: BLE001 — identity layer is optional
        logger.warning("External identity router not integrated: %s", exc)

    # Include our JARVIS identity router (Google OAuth, email/password)
    from .routers import identity as identity_router_internal
    app.include_router(identity_router_internal.router)
    logger.info("JARVIS identity router integrated (email/password + Google OAuth).")

    for r in (
        health.router,
        openai_compat.router,
        improvements.router,
        auth.router,
        control_plane.router,
        ai.router,
        stark.router,
        agents.router,
        monitoring.router,
        system.router,
        platform_identity.router,
        knowledge.router,
        memory.router,
        multimodal.router,
        media.router,
        voice.router,
        rbac.router,
        research.router,
        sandbox.router,
        bio_growth.router,
        global_knowledge.router,
        automation.router,
        browser.router,
        search.router,
        codegen.router,
        commands.router,
        billing.router,
        runtime_status_router,  # MUST be before misc.router to avoid {subsystem} catching /runtime/status
        misc.router,
        legacy.router,
        connectors.router,
        extensions.router,
        provider_status.router,
        developer.router,
        experiments.router,
        curriculum.router,
        challenges.router,
        models.router,
        geography.router,
        notifications.router,
        verification.router,
        websocket.router,
    ):
        app.include_router(r)


# ---- Root / status / silverwing info ------------------------------------- #
@app.get("/api/v1/status")
@app.get("/api/status")
async def unified_status():
    # Live-verify providers so /api/v1/status reflects real availability
    # (AVAILABLE) rather than the "configured, pass probe=true" DEGRADED state.
    # The fast summary surface (/api/v1/system/status) stays probe-free.
    runtime = await build_canonical_runtime_status(probe=True)
    return {
        "status": runtime["status"],
        "name": "JARVIS Unified System",
        **health.deployment_metadata(),
        "runtime": runtime,
        "silverwing": {
            "integrated": _silverwing_app is not None,
            "error": _silverwing_error,
            "mount": "/silverwing" if _silverwing_app is not None else None,
        },
    }


@app.get("/api/runtime/status")
async def runtime_status_alias():
    return await build_canonical_runtime_status(probe=False)


@app.get("/silverwing/health")
async def silverwing_health():
    return JSONResponse({
        "status": "integrated" if _silverwing_app is not None else "unavailable",
        "silverwing_backend": "mounted" if _silverwing_app is not None else "error",
        "error": _silverwing_error,
    })


def integrate_silverwing() -> None:
    if _silverwing_app is None:
        return
    app.mount("/silverwing", _silverwing_app, name="silverwing")

    # The previous implementation called ``_silverwing_app.router.startup()`` /
    # ``.shutdown()`` here. ``_silverwing_app`` is a FastAPI sub-application and
    # its ``router`` attribute is an ``APIRouter`` -- which exposes NO
    # ``startup``/``shutdown`` methods. Every boot therefore emitted
    # ``Silverwing startup error: 'APIRouter' object has no attribute 'startup'``
    # (and never initialised the sub-app here).
    #
    # Starlette runs a *mounted* sub-application's own lifespan handlers
    # (``silverwing-backend/main.py`` declares its own ``@app.on_event``)
    # automatically during the parent app's lifespan startup, so the manual
    # hook was both invalid and redundant. The mount above is sufficient; the
    # sub-app's own ``/silverwing/health`` route already returns ``integrated``
    # once mounted.


def integrate_mcp() -> None:
    """Mount the MCP (Model Context Protocol) HTTP transport at /mcp.

    This exposes JARVIS tools (browser, github, postgresql) to any MCP-compatible
    client — matching the integration pattern used by OpenAI Codex and Anthropic
    Claude Code.  Clients can connect via SSE/Streamable HTTP transport.
    """
    try:
        from .mcp_server import get_mcp_http_app
        mcp_app = get_mcp_http_app()
        if mcp_app is not None:
            app.mount("/mcp", mcp_app, name="mcp")
            logger.info("MCP transport integrated at /mcp (Model Context Protocol).")
        else:
            logger.info("MCP SDK not installed; MCP endpoint not mounted.")
    except Exception as _mcp_err:  # noqa: BLE001 — MCP is optional
        logging.warning("MCP integration error: %s", _mcp_err)


def integrate_a2a() -> None:
    """Mount the A2A (Agent2Agent) protocol endpoints on the FastAPI app.

    Exposes JARVIS capabilities as A2A agents at /a2a (JSON-RPC 2.0) and
    /.well-known/agent-card.json (agent card metadata).  This is an additive
    integration — no new process, no new port, no new database.
    """
    try:
        from .a2a_server import mount_a2a_routes
        mounted = mount_a2a_routes(app)
        if mounted:
            logger.info("A2A protocol server integrated at /a2a and /.well-known/agent-card.json.")
        else:
            logger.info("A2A SDK not installed; A2A endpoints not mounted (graceful degradation).")
    except Exception as _a2a_err:  # noqa: BLE001 — A2A is optional
        logging.warning("A2A integration error: %s", _a2a_err)


@app.on_event("startup")
async def _jarvis_startup():
    # Initialise the Phase 6 provider fabric (OpenAI, NVIDIA NIM, Google, etc.)
    # so all adapters are registered and health-cached before the first request.
    try:
        from providers.bootstrap import bootstrap_fabric  # type: ignore[import-not-found]

        bootstrap_fabric()
        logger.info("Phase 6 provider fabric initialised at startup.")
    except ImportError:
        logger.info("Phase 6 provider fabric not available — skipping initialisation.")
    except Exception as _fabric_err:  # noqa: BLE001 — never block startup on fabric
        logger.warning("Phase 6 fabric initialisation error: %s", _fabric_err)

    # Register all JARVIS capabilities with the orchestration layer so that
    # the capability runtime, event fabric, and persistence are live.
    try:
        from jarvis_backend.capabilities import register_all_capabilities

        register_all_capabilities()
        logger.info("JARVIS capability runtime initialised (15 capabilities).")
    except Exception as _cap_err:  # noqa: BLE001 — never block startup on capabilities
        logger.warning("Capability runtime initialisation error: %s", _cap_err)

    start_backend()
    logger.info("JARVIS backend started. data_dir=%s ai_enabled=%s",
                DATA_DIR, ai_service.enabled)

    try:
        from .bio_growth_worker import start_bio_growth_worker

        await start_bio_growth_worker()
    except Exception as _worker_err:  # noqa: BLE001 — optional background service
        logger.exception("Bio-Growth worker could not start: %s", _worker_err)

    try:
        from .mcp_client import start_mcp_clients

        mcp_results = await start_mcp_clients()
        if mcp_results:
            logger.info(
                "Configured MCP services connected: %d/%d",
                sum(mcp_results.values()),
                len(mcp_results),
            )
        else:
            logger.info("No external MCP services configured.")
    except Exception as _mcp_client_err:  # noqa: BLE001 — external services are optional
        logger.warning(
            "Configured MCP services could not be initialized: %s",
            type(_mcp_client_err).__name__,
        )

    # Start the gRPC server (Phase 19: typed internal service mesh)
    # on port 50051 alongside the FastAPI REST server on 8000.
    try:
        from .grpc_server import start_grpc_server
        grpc_port = await start_grpc_server(
            host=os.environ.get("GRPC_HOST", "0.0.0.0"),
            port=int(os.environ.get("GRPC_PORT", "50051")),
        )
        logger.info("JARVIS gRPC service mesh started on port %d", grpc_port)
    except Exception as _grpc_err:  # noqa: BLE001 — gRPC is optional
        logging.warning("gRPC server failed to start: %s", _grpc_err)


@app.on_event("shutdown")
async def _jarvis_shutdown():
    from .bio_growth_worker import stop_bio_growth_worker

    await stop_bio_growth_worker()
    from .mcp_client import stop_mcp_clients

    await stop_mcp_clients()


def build_app():
    install_observability(app)
    setup_routers()
    integrate_silverwing()
    integrate_mcp()
    integrate_a2a()
    return app


# Build eagerly so `uvicorn jarvis_backend.main:app` and imports work.
build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
