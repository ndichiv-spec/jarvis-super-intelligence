"""Authorization regressions for user-scoped control-plane data."""
from types import SimpleNamespace


def test_job_list_is_scoped_to_authenticated_user(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import control_plane

    calls = []
    registry = SimpleNamespace(
        list_jobs=lambda **kwargs: calls.append(kwargs) or [],
    )
    monkeypatch.setattr(control_plane, "get_job_registry", lambda: registry)

    response = client.get("/api/v2/control/jobs", headers=auth_headers)

    assert response.status_code == 200
    assert calls[0]["user_id"] == "testuser"


def test_job_list_rejects_another_users_filter(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import control_plane

    monkeypatch.setattr(
        control_plane,
        "get_job_registry",
        lambda: SimpleNamespace(list_jobs=lambda **_: []),
    )

    response = client.get(
        "/api/v2/control/jobs",
        params={"user_id": "another-user"},
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_job_details_are_hidden_from_another_user(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import control_plane

    job = SimpleNamespace(
        job_id="job-owned-by-other",
        user_id="another-user",
    )
    monkeypatch.setattr(
        control_plane,
        "get_job_registry",
        lambda: SimpleNamespace(get=lambda _job_id: job),
    )

    response = client.get(
        "/api/v2/control/jobs/job-owned-by-other",
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_cost_and_budget_queries_reject_another_users_id(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import control_plane

    monkeypatch.setattr(
        control_plane,
        "get_usage_accountant",
        lambda: SimpleNamespace(list_records=lambda **_: []),
    )

    costs = client.get(
        "/api/v2/control/costs",
        params={"user_id": "another-user"},
        headers=auth_headers,
    )
    budget = client.get(
        "/api/v2/control/costs/budget/another-user",
        headers=auth_headers,
    )

    assert costs.status_code == 403
    assert budget.status_code == 403


def test_provider_usage_is_scoped_to_authenticated_user(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import control_plane

    calls = []
    accountant = SimpleNamespace(
        get_usage_by_provider=lambda **kwargs: calls.append(kwargs) or {},
    )
    monkeypatch.setattr(control_plane, "get_usage_accountant", lambda: accountant)

    response = client.get(
        "/api/v2/control/costs/usage-by-provider",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert calls[0]["user_id"] == "testuser"


def test_audit_count_rejects_another_users_filter(client, auth_headers, monkeypatch):
    from jarvis_backend.routers import control_plane

    monkeypatch.setattr(
        control_plane,
        "get_audit_service",
        lambda: SimpleNamespace(count_events=lambda **_: 0),
    )

    response = client.get(
        "/api/v2/control/audit/count",
        params={"user_id": "another-user"},
        headers=auth_headers,
    )

    assert response.status_code == 403
