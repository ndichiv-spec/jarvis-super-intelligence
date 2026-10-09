from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jarvis_backend.presentation.lifecycle import LifecycleState
from jarvis_backend.presentation.negotiation import negotiate_renderers
from jarvis_backend.presentation.schemas import (
    DataReference,
    PresentationCapabilities,
    PresentationEnvelope,
    PresentationIntent,
    PresentationLifecycle,
    SceneGraph,
)
from jarvis_backend.presentation.service import PresentationService
from jarvis_backend.presentation.validation import (
    UnsafePresentationDataError,
    UnsupportedPresentationVersionError,
)


def test_intent_accepts_semantic_scene_and_real_data_references():
    intent = PresentationIntent.model_validate({
        "id": "presentation-1",
        "session_id": "session-1",
        "sequence": 1,
        "environment": {"id": "world", "type": "geospatial"},
        "mode": "focused",
        "scene": {
            "root": {
                "id": "world",
                "type": "group",
                "children": [{
                    "id": "map",
                    "type": "map",
                    "data": {
                        "source": "device",
                        "resource": "authorized.location",
                        "authorization": "location-permission-1",
                        "freshness": {"required": True, "max_age_ms": 10000},
                    },
                }],
            },
        },
        "interactions": [{
            "id": "map-zoom",
            "type": "zoom",
            "action": {"capability": "geospatial", "action": "zoom"},
            "requires_confirmation": False,
        }],
    })

    assert intent.scene is not None
    assert intent.scene.root.children[0].data is not None
    assert intent.scene.root.children[0].data.resource == "authorized.location"
    assert intent.interactions[0].requires_confirmation is False


def test_contract_rejects_unbacked_visual_nodes_and_ignores_unknown_minor_additions():
    with pytest.raises(ValidationError):
        SceneGraph.model_validate({
            "root": {"id": "map", "type": "map"},
        })

    intent = PresentationIntent.model_validate({
        "id": "presentation-1",
        "session_id": "session-1",
        "sequence": 1,
        "environment": {"id": "world", "type": "geospatial"},
        "executable": "<script>alert(1)</script>",
    })
    assert "executable" not in intent.model_dump()

    with pytest.raises(ValidationError, match="authorization context"):
        DataReference.model_validate({
            "source": "connector",
            "resource": "mail.inbox",
        })


def test_envelope_rejects_unsupported_protocol_major():
    envelope = PresentationEnvelope.model_validate({
        "protocol": "jarvis.presentation",
        "version": "2.0",
        "issuedAt": datetime.now(UTC).isoformat(),
        "source": {"runtime": "jarvis-core", "request_id": "request-1"},
        "security": {"authorizationContext": "opaque-context", "capabilities": []},
        "intent": {
            "id": "presentation-1",
            "session_id": "session-1",
            "sequence": 1,
            "environment": {"id": "conversation", "type": "conversation"},
        },
    })

    with pytest.raises(UnsupportedPresentationVersionError):
        PresentationService().validate(envelope)


def test_envelope_does_not_accept_credentials_as_authorization_context():
    with pytest.raises(ValidationError, match="opaque reference"):
        PresentationEnvelope.model_validate({
            "protocol": "jarvis.presentation",
            "version": "1.0",
            "issuedAt": datetime.now(UTC).isoformat(),
            "source": {"runtime": "jarvis-core", "requestId": "request-1"},
            "security": {"authorizationContext": "Bearer secret-value", "capabilities": []},
            "intent": {
                "id": "presentation-1",
                "sessionId": "session-1",
                "sequence": 1,
                "environment": {"id": "conversation", "type": "conversation"},
            },
        })


def test_core_service_emits_semantic_creation_event_from_validated_intent():
    envelope = PresentationEnvelope.model_validate({
        "protocol": "jarvis.presentation",
        "version": "1.0",
        "issuedAt": datetime.now(UTC).isoformat(),
        "source": {"runtime": "jarvis-core", "requestId": "request-1"},
        "security": {"authorizationContext": "opaque-context", "capabilities": []},
        "intent": {
            "id": "presentation-1",
            "sessionId": "session-1",
            "sequence": 3,
            "environment": {"id": "world", "type": "geospatial"},
            "mode": "focused",
        },
    })

    event = PresentationService().created_event(envelope)

    assert event.type == "created"
    assert event.sequence == 0
    assert event.payload == {"environment": "geospatial", "mode": "focused"}
    assert event.model_dump(mode="json", by_alias=True)["presentationId"] == "presentation-1"


def test_envelope_rejects_excessive_nested_payloads():
    nested: dict[str, object] = {"leaf": "value"}
    for index in range(14):
        nested = {f"level{index}": nested}
    envelope = PresentationEnvelope.model_validate({
        "protocol": "jarvis.presentation",
        "version": "1.0",
        "issuedAt": datetime.now(UTC).isoformat(),
        "source": {"runtime": "jarvis-core", "request_id": "request-1"},
        "security": {"authorizationContext": "opaque-context", "capabilities": []},
        "intent": {
            "id": "presentation-1",
            "session_id": "session-1",
            "sequence": 1,
            "environment": {"id": "conversation", "type": "conversation", "state": nested},
        },
    })

    with pytest.raises(UnsafePresentationDataError):
        PresentationService().validate(envelope)


def test_renderer_negotiation_uses_advertised_surface_and_reports_truthful_fallback():
    result = negotiate_renderers(PresentationCapabilities.model_validate({
        "client_id": "installation-42",
        "surfaces": ["web"],
        "environments": ["geospatial"],
        "primitives": ["map", "marker", "avatar"],
        "media": ["image"],
        "spatial": ["globe"],
        "input": ["text", "voice"],
        "output": ["text", "image"],
    }))

    assert {renderer.type for renderer in result.renderers} == {
        "map.renderer", "image.renderer", "avatar.renderer",
    }
    assert result.fallbacks[0].requested == "globe"
    assert result.fallbacks[0].selected == "map.renderer"
    map_renderer = next(renderer for renderer in result.renderers if renderer.type == "map.renderer")
    assert map_renderer.supported_primitives == ["map", "marker"]
    assert result.fallbacks[0].available == ["map", "marker"]


def test_lifecycle_enforces_resume_and_terminal_transitions():
    service = PresentationService()
    suspended = service.transition(
        PresentationLifecycle(state="active"),
        LifecycleState.SUSPENDED,
    )
    resumed = service.transition(suspended, LifecycleState.RESUMED)

    assert resumed.state == "resumed"
    with pytest.raises(ValueError, match="Invalid presentation lifecycle transition"):
        service.transition(
            PresentationLifecycle(state="closed"),
            LifecycleState.ACTIVE,
        )


@pytest.mark.asyncio
async def test_presentation_contract_api_requires_auth_and_negotiates_real_client_capabilities(
    test_client,
    auth_headers,
):
    unauthorized = await test_client.get("/api/v1/presentation/contract")
    assert unauthorized.status_code in {401, 403}

    contract = await test_client.get(
        "/api/v1/presentation/contract",
        headers=auth_headers,
    )
    assert contract.status_code == 200
    assert contract.json()["protocol"] == "jarvis.presentation"
    assert contract.json()["version"] == "1.0"

    negotiated = await test_client.post(
        "/api/v1/presentation/negotiate",
        headers=auth_headers,
        json={
            "clientId": "web-installation-1",
            "surfaces": ["web"],
            "environments": ["geospatial"],
            "primitives": ["map", "marker", "avatar"],
            "media": ["image"],
            "spatial": [],
            "input": ["text", "voice"],
            "output": ["text", "image", "voice"],
        },
    )
    assert negotiated.status_code == 200
    assert negotiated.json()["clientId"] == "web-installation-1"
    assert "map.renderer" in {item["type"] for item in negotiated.json()["renderers"]}

    preference_response = await test_client.put(
        "/api/v1/presentation/preferences",
        headers=auth_headers,
        json={"density": "technical", "avatarPreference": "hidden"},
    )
    assert preference_response.status_code == 200
    assert preference_response.json()["density"] == "technical"
    assert preference_response.json()["avatarPreference"] == "hidden"
