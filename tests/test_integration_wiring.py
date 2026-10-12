"""Integration checks for supported router composition."""


def test_health_system_and_metrics_routers_share_the_canonical_app(client):
    paths = set(client.get("/openapi.json").json()["paths"])

    assert "/api/v1/health/status" in paths
    assert "/api/v1/system/status" in paths
    assert "/api/v1/metrics" in paths
