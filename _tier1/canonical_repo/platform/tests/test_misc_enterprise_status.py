def test_tier4_status_does_not_claim_unconfigured_enterprise_features_are_available(client):
    response = client.get("/api/v1/tier4/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "tier": 4,
        "features_enabled": False,
        "capabilities": {},
        "reason": "No enterprise control plane is configured for this deployment.",
    }


def test_sso_test_reports_missing_provider_validation(client):
    response = client.post("/api/v1/enterprise/sso/test", json={"provider": "example-idp"})

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_monitoring_health_does_not_report_healthy_when_metrics_are_unavailable(monkeypatch):
    import asyncio

    from jarvis_backend.routers import monitoring

    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {"available": False, "reason": "Host metrics collection is unavailable."},
    )
    report = asyncio.run(monitoring.health_report())

    assert report["status"] == "unavailable"
    assert report["health_score"] is None
    assert report["checks"] == []


def test_monitoring_health_score_uses_weighted_resource_pressure(monkeypatch):
    import asyncio

    from jarvis_backend.routers import monitoring

    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {
            "available": True,
            "cpu_percent": 50,
            "memory": {"percent": 25},
            "disk": 75,
        },
    )
    report = asyncio.run(monitoring.health_report())

    assert report["health_score"] == 55
    assert report["status"] == "degraded"


def test_monitoring_unimplemented_automation_endpoints_do_not_claim_success(client):
    assert client.get("/api/v1/monitoring/optimization-report").status_code == 501
    assert client.post("/api/v1/monitoring/optimize").status_code == 501
    assert client.get("/api/v1/monitoring/recovery-history").status_code == 501
    assert client.post("/api/v1/monitoring/trigger-recovery").status_code == 501


def test_monitoring_health_endpoint_reflects_unavailable_metrics(monkeypatch):
    import asyncio

    from jarvis_backend.routers import monitoring

    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {"available": False, "reason": "Host metrics collection is unavailable."},
    )
    response = asyncio.run(monitoring.monitoring_health())

    assert response["status"] == "unavailable"
    assert response["health_score"] is None


def test_monitoring_diagnostics_does_not_claim_unavailable_host_is_healthy(monkeypatch):
    import asyncio

    from jarvis_backend.routers import monitoring

    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {"available": False, "reason": "Host metrics collection is unavailable."},
    )
    response = asyncio.run(monitoring.system_diagnostics())

    assert response["healthy"] is False


def test_monitoring_websocket_publishes_actual_metric_snapshots(client, monkeypatch):
    from jarvis_backend import websocket
    from jarvis_backend.routers import monitoring

    monkeypatch.setattr(websocket, "_MONITORING_PUSH_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(
        monitoring,
        "_sample",
        lambda: {
            "available": True,
            "cpu_percent": 23,
            "memory": {"percent": 45, "available": 1000},
            "disk": 60,
            "processes": 17,
        },
    )
    with client.websocket_connect("/ws/monitoring") as stream:
        event = stream.receive_json()

    assert event["type"] == "monitoring_update"
    assert event["data"]["metrics"]["cpu_percent"] == 23
