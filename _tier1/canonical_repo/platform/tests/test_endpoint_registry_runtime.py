from __future__ import annotations

import pytest

from jarvis_backend.endpoint_registry import EndpointRegistry


def test_endpoint_registration_is_owner_bound_and_reusable_across_instances():
    first_registry = EndpointRegistry()
    endpoint = first_registry.register_endpoint(
        user_id="endpoint-owner",
        capabilities=["presentation.text", "admin.shell"],
        supported_modalities=["text", "image"],
        presentation_contract_versions=["1.1", "1.0"],
        metadata={"viewport": {"width": 1280, "height": 720}},
    )
    second_registry = EndpointRegistry()

    assert endpoint["status"] == "registered"
    assert endpoint["validated_capabilities"] == ["presentation.text"]
    assert endpoint["unsupported_capabilities"] == ["admin.shell"]
    assert second_registry.get_endpoint(
        endpoint["endpoint_id"], "endpoint-owner"
    )["metadata"]["viewport"]["width"] == 1280
    assert second_registry.list_endpoints("another-owner") == []
    with pytest.raises(PermissionError):
        second_registry.get_endpoint(endpoint["endpoint_id"], "another-owner")


def test_endpoint_renegotiates_and_reconnects_without_gaining_authority():
    registry = EndpointRegistry()
    endpoint = registry.register_endpoint(
        user_id="endpoint-owner",
        capabilities=["presentation.text", "unknown.execute"],
        supported_modalities=["text", "map"],
        presentation_contract_versions=["1.1"],
    )
    endpoint_id = endpoint["endpoint_id"]
    result = registry.negotiate_capabilities(
        user_id="endpoint-owner",
        endpoint_id=endpoint_id,
        advertised_capabilities=["presentation.text", "admin.shell"],
        supported_modalities=["text"],
        presentation_contract_versions=["1.0", "1.1"],
    )

    assert result["negotiated_contract_version"] == "1.1"
    assert result["negotiated_capabilities"] == ["presentation.text"]
    assert result["unsupported_capabilities"] == ["admin.shell"]
    assert result["authorization_granted"] is False
    assert result["verified_operational"] is False
    registry.heartbeat(
        user_id="endpoint-owner", endpoint_id=endpoint_id,
        status="disconnected",
    )
    reconnected = registry.negotiate_capabilities(
        user_id="endpoint-owner", endpoint_id=endpoint_id,
    )
    assert reconnected["status"] == "connected"
    assert registry.select_endpoint(
        user_id="endpoint-owner", endpoint_id=endpoint_id,
    )["is_active"] is True


def test_revocation_is_terminal_and_endpoint_transitions_are_audited():
    registry = EndpointRegistry()
    endpoint = registry.register_endpoint(user_id="endpoint-owner")
    endpoint_id = endpoint["endpoint_id"]
    registry.revoke_endpoint(
        user_id="endpoint-owner", endpoint_id=endpoint_id,
    )

    with pytest.raises(PermissionError, match="revoked"):
        registry.heartbeat(
            user_id="endpoint-owner", endpoint_id=endpoint_id,
            status="connected",
        )
    with pytest.raises(PermissionError, match="revoked"):
        registry.negotiate_capabilities(
            user_id="endpoint-owner", endpoint_id=endpoint_id,
        )
    assert {
        event["event_type"] for event in registry.list_audit_events(
            user_id="endpoint-owner", endpoint_id=endpoint_id,
        )
    } >= {"endpoint.registered", "endpoint.revoked"}


def test_endpoint_api_requires_auth_and_rejects_owner_override(client, auth_headers):
    unauthenticated = client.get("/api/v1/endpoints")
    assert unauthenticated.status_code == 401

    response = client.post(
        "/api/v1/endpoints/register",
        headers=auth_headers,
        json={"owner_id": "somebody-else"},
    )
    assert response.status_code == 403


def test_endpoint_api_reconnect_and_revoke_are_authenticated(client, auth_headers):
    created = client.post(
        "/api/v1/endpoints/register",
        headers=auth_headers,
        json={
            "name": "web renderer",
            "capabilities": ["presentation.text", "admin.shell"],
            "supported_modalities": ["text"],
            "presentation_contract_versions": ["1.1"],
        },
    )
    assert created.status_code == 200, created.text
    endpoint_id = created.json()["endpoint"]["endpoint_id"]

    negotiated = client.post(
        f"/api/v1/endpoints/{endpoint_id}/negotiate",
        headers=auth_headers,
        json={},
    )
    assert negotiated.status_code == 200, negotiated.text
    disconnected = client.post(
        f"/api/v1/endpoints/{endpoint_id}/disconnect",
        headers=auth_headers,
    )
    assert disconnected.json()["endpoint"]["status"] == "disconnected"
    reconnected = client.post(
        f"/api/v1/endpoints/{endpoint_id}/negotiate",
        headers=auth_headers,
        json={},
    )
    assert reconnected.json()["negotiation"]["status"] == "connected"
    revoked = client.post(
        f"/api/v1/endpoints/{endpoint_id}/revoke",
        headers=auth_headers,
    )
    assert revoked.json()["endpoint"]["status"] == "revoked"
    assert client.post(
        f"/api/v1/endpoints/{endpoint_id}/negotiate",
        headers=auth_headers,
        json={},
    ).status_code == 403
    assert client.get(
        f"/api/v1/endpoints/{endpoint_id}/events",
        headers=auth_headers,
    ).status_code == 200


def test_endpoint_requires_supported_versions_and_non_spoofed_ids():
    registry = EndpointRegistry()
    with pytest.raises(ValueError, match="version"):
        registry.register_endpoint(
            user_id="endpoint-owner",
            presentation_contract_versions=["99.0"],
        )
    with pytest.raises(ValueError, match="UUID"):
        registry.register_endpoint(
            user_id="endpoint-owner", endpoint_id="not-a-uuid",
        )
