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
