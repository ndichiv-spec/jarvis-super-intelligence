from __future__ import annotations

from jarvis_backend import core, main


def test_main_exports_the_core_application_singleton():
    assert main.app is core.app
    assert main.app.title == "JARVIS Unified System"


def test_main_registers_core_api_routes():
    paths = set(main.app.openapi()["paths"])
    assert "/api/v1/health/status" in paths
    assert "/api/v1/integrations/providers" in paths
    assert "/api/v1/presentation/contract" in paths
    assert "/api/v1/presentation/negotiate" in paths
    assert "/api/v1/presentation/preferences" in paths
    assert "/api/v1/presentation/state/{session_id}" in paths
