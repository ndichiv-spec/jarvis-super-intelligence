"""JARVIS backend wiring.

Builds the single main FastAPI application that serves every JARVIS
/api/v1 endpoint AND integrates the Silverwing AI backend as a mounted
sub-application, so one process on one port (8000) powers the whole system.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi.responses import JSONResponse

from jarvis_runtime import SILVERWING_BACKEND_ROOT

from . import websocket
from .core import (
    DATA_DIR,
    _read_secret_setting,
    admin_email,
    ai_service,
    app,
    is_production,
    start_backend,
)
from .observability import install_observability
from .runtime_status import router as runtime_status_router, build_canonical_runtime_status
from .mcp_runtime import router as mcp_runtime_router, mount_mcp
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
    endpoints,
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
    platform_identity,
    provider_status,
    rbac,
    research,
    sandbox,
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
        mcp_runtime_router,
        improvements.router,
        auth.router,
        endpoints.router,
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
        global_knowledge.router,
        automation.router,
        browser.router,
        search.router,
        codegen.router,
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
        verification.router,
        commands.router,
        websocket.router,
    ):
        app.include_router(r)


# ---- Root / status / silverwing info ------------------------------------- #
@app.get("/api/v1/status")
@app.get("/api/status")
async def unified_status():
    runtime = await build_canonical_runtime_status(probe=False)
    return {
        "status": runtime["status"],
        "alive": runtime["alive"],
        "service_readiness": runtime["service_readiness"],
        "name": "JARVIS Unified System",
        "version": "3.0.0",
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

    @app.on_event("startup")
    async def _silverwing_startup():
        try:
            await _silverwing_app.router.startup()
        except Exception as _e:  # noqa: BLE001
            logging.warning("Silverwing startup error: %s", _e)

    @app.on_event("shutdown")
    async def _silverwing_shutdown():
        try:
            await _silverwing_app.router.shutdown()
        except Exception as _e:  # noqa: BLE001
            logging.warning("Silverwing shutdown error: %s", _e)


def integrate_mcp() -> None:
    mount_mcp(app)


@app.on_event("startup")
async def _jarvis_startup():
    if is_production():
        signing_key = _read_secret_setting("JARVIS_SECRET_KEY")
        admin_password = _read_secret_setting("JARVIS_ADMIN_PASSWORD")
        database_url = os.environ.get("DATABASE_URL")
        if not database_url and os.environ.get("DATABASE_URL_FILE"):
            from .db import database_url as resolve_database_url

            database_url = resolve_database_url()
        if not signing_key or len(signing_key) < 32:
            raise RuntimeError("Production requires JARVIS_SECRET_KEY with at least 32 characters.")
        if not admin_password or len(admin_password) < 16:
            raise RuntimeError("Production requires JARVIS_ADMIN_PASSWORD with at least 16 characters.")
        if not database_url or not database_url.startswith(("postgresql://", "postgresql+")):
            raise RuntimeError("Production requires DATABASE_URL pointing to PostgreSQL.")
        if not os.environ.get("JARVIS_CORS_ORIGINS"):
            raise RuntimeError("Production requires explicit JARVIS_CORS_ORIGINS.")
        admin_email()

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

    start_backend()
    logger.info("JARVIS backend started. data_dir=%s ai_enabled=%s",
                DATA_DIR, ai_service.enabled)


def build_app():
    install_observability(app)
    setup_routers()
    integrate_silverwing()
    integrate_mcp()
    return app


# Build eagerly so `python -m jarvis_backend.main:app` and imports work.
build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
