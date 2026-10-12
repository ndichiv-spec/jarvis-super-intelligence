"""Router registration tests for the canonical backend application."""


def test_core_routers_are_registered_on_the_application(client):
    paths = set(client.get("/openapi.json").json()["paths"])

    assert "/api/v1/health/status" in paths
    assert "/api/v1/system/status" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/metrics" in paths
