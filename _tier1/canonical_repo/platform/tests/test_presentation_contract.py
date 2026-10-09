import json
import time
import uuid
from pathlib import Path

import pytest

from jarvis_backend.presentation_contract import (
    CONTRACT_VERSION,
    PresentationContractError,
    build_conversation_presentation,
    build_execution_presentation,
    build_image_presentation,
    render_presentation_text,
    validate_presentation_contract,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "presentation-research-v1.json"


@pytest.fixture
def representative_contract():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_shared_research_contract_is_valid_and_rendered_by_text_renderer(
    representative_contract,
):
    assert representative_contract["contract_version"] == CONTRACT_VERSION
    rendered = render_presentation_text(
        representative_contract,
        authorized_data_refs={"execution:fixture-execution:artifact:0"},
    )
    assert "I found one observed source." in rendered
    assert "Example research source" in rendered
    assert "https://example.org/research" in rendered


def test_legacy_v1_0_contract_remains_valid(representative_contract):
    legacy = json.loads(json.dumps(representative_contract))
    legacy["contract_version"] = "1.0"
    for field in (
        "task_state", "source_provenance", "media_refs",
        "user_preferences", "view_state",
    ):
        legacy.pop(field)
    requirements = legacy["renderer_requirements"]
    requirements["contract_version"] = "1.0"
    requirements.pop("supported_contract_versions")
    requirements.pop("required_modalities")

    validated = validate_presentation_contract(
        legacy,
        authorized_data_refs={"execution:fixture-execution:artifact:0"},
    )
    assert validated["contract_version"] == "1.0"


def test_text_renderer_honors_semantic_content_hierarchy(representative_contract):
    representative_contract["components"].reverse()
    representative_contract["renderer_requirements"]["required_components"].reverse()
    rendered = render_presentation_text(
        representative_contract,
        authorized_data_refs={"execution:fixture-execution:artifact:0"},
    )

    assert rendered.index("I found one observed source.") < rendered.index(
        "Observed sources"
    )


def test_contract_rejects_unknown_version_and_unauthorized_reference(
    representative_contract,
):
    unknown_version = dict(representative_contract, contract_version="99.0")
    with pytest.raises(PresentationContractError, match="version"):
        validate_presentation_contract(
            unknown_version,
            authorized_data_refs={"execution:fixture-execution:artifact:0"},
        )

    with pytest.raises(PresentationContractError, match="unauthorized"):
        validate_presentation_contract(
            representative_contract,
            authorized_data_refs={"execution:other-owner:artifact:0"},
        )


def test_contract_rejects_tampered_source_provenance(representative_contract):
    representative_contract["source_provenance"][0]["observed_at"] = "not-a-time"
    with pytest.raises(PresentationContractError, match="timestamp"):
        validate_presentation_contract(
            representative_contract,
            authorized_data_refs={"execution:fixture-execution:artifact:0"},
        )


def test_media_reference_is_rejected_without_authorized_media_service(
    representative_contract,
):
    representative_contract["media_refs"] = [{
        "id": "media:generated-image",
        "content_type": "image/png",
        "width": 1024,
        "height": 1024,
        "alt_text": "Generated output",
        "provenance": "generated",
    }]
    with pytest.raises(PresentationContractError, match="media service"):
        validate_presentation_contract(
            representative_contract,
            authorized_data_refs={"execution:fixture-execution:artifact:0"},
        )


def test_image_presentation_requires_signed_local_media_and_preserves_correlation():
    asset_id = str(uuid.uuid4())
    expires_at = int(time.time()) + 600
    image = {
        "media_ref": asset_id,
        "url": (
            f"/api/v1/media/{asset_id}?expires={expires_at}&"
            f"signature={'a' * 64}"
        ),
        "expires_at": expires_at,
        "content_type": "image/png",
        "prompt": "A blue fox",
        "provider": "openai",
        "model": "dall-e-3",
        "width": 1024,
        "height": 1024,
    }

    contract = build_image_presentation(
        [image],
        request_id="request-1",
        session_id="conversation-1",
        command_id="command-1",
        execution_id="execution-1",
    )

    assert contract["contract_version"] == "1.1"
    assert contract["data_refs"] == [{
        "id": asset_id,
        "kind": "generated_media",
    }]
    assert contract["correlation"] == {
        "request_id": "request-1",
        "session_id": "conversation-1",
        "conversation_id": "conversation-1",
        "command_id": "command-1",
        "execution_id": "execution-1",
    }

    with pytest.raises(PresentationContractError, match="invalid media reference"):
        build_image_presentation([{
            **image,
            "url": "https://attacker.invalid/image.png",
        }])


def test_interaction_contract_cannot_grant_execution_or_widen_permissions(
    representative_contract,
):
    invalid = json.loads(json.dumps(representative_contract))
    invalid["interactions"][0]["required_permissions"] = ["admin"]
    with pytest.raises(PresentationContractError, match="unsupported interaction"):
        validate_presentation_contract(
            invalid,
            authorized_data_refs={"execution:fixture-execution:artifact:0"},
        )

    invalid["interactions"] = [{
        "id": "send-email",
        "type": "send_email",
        "data_ref": "execution:fixture-execution:artifact:0",
        "required_permissions": ["email:send"],
        "user_gesture_required": True,
    }]
    with pytest.raises(PresentationContractError, match="unsupported interaction"):
        validate_presentation_contract(
            invalid,
            authorized_data_refs={"execution:fixture-execution:artifact:0"},
        )


def test_execution_presentation_uses_observed_sources_and_request_correlation():
    contract = build_execution_presentation(
        operation="web.search",
        success=True,
        message="Observed one source.",
        artifacts=[{
            "title": "Observed article",
            "url": "https://example.org/article",
            "snippet": "Evidence from the executed search.",
        }],
        tool_result="{}",
        request_id="request-1",
        session_id="session-1",
        conversation_id="session-1",
        command_id="command-1",
        execution_id="execution-1",
    )

    source_list = next(
        component for component in contract["components"]
        if component["type"] == "research.source_list"
    )
    assert source_list["items"][0]["title"] == "Observed article"
    assert contract["correlation"] == {
        "request_id": "request-1",
        "session_id": "session-1",
        "conversation_id": "session-1",
        "command_id": "command-1",
        "execution_id": "execution-1",
    }
    assert contract["interactions"][0]["required_permissions"] == ["web:read"]


def test_map_presentation_uses_only_validated_user_provided_coordinates():
    contract = build_execution_presentation(
        operation="geography.coordinates.map",
        success=True,
        message="The coordinates were validated.",
        artifacts=[],
        tool_result=json.dumps({
            "result_available": True,
            "latitude": 47.6062,
            "longitude": -122.3321,
            "units": {
                "latitude": "degrees_north",
                "longitude": "degrees_east",
            },
        }),
        request_id="request-map",
        session_id="session-map",
        conversation_id="session-map",
        command_id="command-map",
        execution_id="execution-map",
    )

    component = next(
        component for component in contract["components"]
        if component["type"] == "geospatial.point_map"
    )
    point = component["items"][0]
    assert point["latitude"] == 47.6062
    assert point["longitude"] == -122.3321
    assert point["location_type"] == "user_provided"
    assert contract["modalities"] == ["text", "map"]
    assert contract["renderer_requirements"]["required_modalities"] == [
        "text", "map",
    ]
    assert contract["source_provenance"][0]["source_type"] == (
        "user_provided_coordinates"
    )
    assert "not a live device location" in contract["task_state"]["message"]
    rendered = render_presentation_text(
        contract,
        authorized_data_refs={"execution:execution-map:coordinate"},
    )
    assert "47.60620, -122.33210" in rendered
    assert "not live device location" in rendered


def test_map_presentation_rejects_invalid_or_unavailable_coordinate_output():
    contract = build_execution_presentation(
        operation="geography.coordinates.map",
        success=True,
        message="No coordinate result was returned.",
        artifacts=[],
        tool_result=json.dumps({
            "result_available": True,
            "latitude": 95,
            "longitude": 190,
        }),
        request_id="request-map",
        session_id="session-map",
        conversation_id="session-map",
        command_id="command-map",
        execution_id="execution-map",
    )

    assert all(
        component["type"] != "geospatial.point_map"
        for component in contract["components"]
    )
    assert contract["modalities"] == ["text"]
    assert "no valid coordinate pair" in contract["errors"][0].lower()


def test_unsupported_modality_falls_back_to_observed_text():
    contract = build_execution_presentation(
        operation="media.playback",
        success=False,
        message="Playback is unsupported.",
        artifacts=[],
        tool_result="",
        request_id="request-1",
        session_id="session-1",
        conversation_id="session-1",
        command_id="command-1",
        execution_id="execution-1",
        requested_modality="video",
    )

    assert contract["modalities"] == ["text"]
    assert "video presentation is unavailable" in contract["fallback"]["text"]
    assert contract["errors"] == ["Unsupported requested modality: video."]


@pytest.mark.parametrize("modality", ["image", "audio", "map", "video", "3d"])
def test_unavailable_modalities_are_explicit_and_never_fabricated(modality):
    contract = build_execution_presentation(
        operation="web.search",
        success=True,
        message="Observed a text result.",
        artifacts=[],
        tool_result="{}",
        request_id="request-1",
        session_id="session-1",
        conversation_id="session-1",
        command_id="command-1",
        execution_id="execution-1",
        requested_modality=modality,
    )

    assert contract["modalities"] == ["text"]
    assert contract["task_state"]["status"] == "completed"
    assert contract["fallback"]["text"].endswith(
        f"{modality} presentation is unavailable; showing text instead."
    )
    assert contract["media_refs"] == []
    assert f"Unsupported requested modality: {modality}." in contract["errors"]


def test_conversation_builder_persists_correlation_and_accessibility():
    contract = build_conversation_presentation(
        "A normal response.",
        request_id="request-2",
        session_id="session-2",
        conversation_id="session-2",
    )

    assert contract["correlation"]["request_id"] == "request-2"
    assert contract["correlation"]["session_id"] == "session-2"
    assert contract["accessibility"]["reading_order"] == ["response"]
