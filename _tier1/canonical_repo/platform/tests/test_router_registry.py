from jarvis_backend.main import app


def test_critical_routers_are_registered_on_canonical_application():
    paths = app.openapi()["paths"]

    assert "/api/v1/health/status" in paths
    assert "/api/v1/ai/process" in paths
    assert "/api/v1/auth/login" in paths


def test_registered_openapi_paths_are_absolute_and_unique():
    paths = list(app.openapi()["paths"])

    assert paths
    assert all(path.startswith("/") for path in paths)
    assert len(paths) == len(set(paths))
