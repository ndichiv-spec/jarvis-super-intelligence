import pytest

from jarvis_backend.capability import Capability, CapabilityRegistry, ExecutionResult
from jarvis_backend.presentation.registry import (
    PresentationRegistry,
    register_builtin_capability_bindings,
)
from jarvis_backend.presentation.resolver import PresentationResolver
from jarvis_backend.presentation.schemas import (
    EnvironmentBinding,
    PresentationCapabilities,
    PresentationCapabilityBinding,
    VisualizationBinding,
    VisualizationDataRequirement,
)


class GeographyCapability(Capability):
    name = "geography.analysis"
    category = "geography"

    async def execute(self, request, context=None):
        return ExecutionResult(capability=self.name, success=True, data={"region": "real"})


class BrainCapabilityStub(GeographyCapability):
    name = "brain"
    category = "brain"


def _registry():
    capabilities = CapabilityRegistry()
    capabilities.register(GeographyCapability(), {"description": "Geographic analysis"})
    capabilities.register_output_contract(
        "geography.analysis",
        [{"id": "geography.analysis.result", "type": "structured_data"}],
    )
    registry = PresentationRegistry(capabilities)
    registry.register_capability_binding(
        "geography.analysis",
        PresentationCapabilityBinding(
            environments=[
                EnvironmentBinding(
                    environment="geospatial",
                    suitability="primary",
                    priority=100,
                ),
            ],
            visualizations=[
                VisualizationBinding(
                    type="map",
                    input_types=["structured_data"],
                    data_requirements=[
                        VisualizationDataRequirement(output_type="structured_data"),
                    ],
                ),
            ],
            modalities=["visual", "text"],
        ),
    )
    return registry


def test_builtin_bindings_extend_existing_registered_capabilities():
    capabilities = CapabilityRegistry()
    capabilities.register(BrainCapabilityStub(), {"description": "Reasoning"})

    register_builtin_capability_bindings(capabilities)

    metadata = capabilities.get_metadata("brain")
    assert metadata["outputs"][0]["type"] == "text"
    assert metadata["presentation"]["environments"][0]["environment"] == "conversation"
    definition = PresentationRegistry(capabilities).definitions()[0]
    assert definition.id == "brain"
    assert definition.operational_status == "unavailable"


def test_builtin_bindings_allow_capabilities_to_share_environment_definitions():
    capabilities = CapabilityRegistry()
    capabilities.register(BrainCapabilityStub(), {"description": "Reasoning"})

    class ConversationStub(GeographyCapability):
        name = "conversation"
        category = "conversation"

    capabilities.register(ConversationStub(), {"description": "Conversation"})
    register_builtin_capability_bindings(capabilities)

    assert capabilities.get_metadata("brain")["presentation"]["environments"][0]["environment"] == "conversation"
    assert capabilities.get_metadata("conversation")["presentation"]["environments"][0]["environment"] == "conversation"


@pytest.mark.asyncio
async def test_resolver_selects_only_registered_supported_renderers_and_real_output_types():
    registry = _registry()
    resolver = PresentationResolver(registry=registry)
    client = PresentationCapabilities.model_validate({
        "clientId": "web-client",
        "platform": "web",
        "surfaces": ["web"],
        "environments": ["geospatial"],
        "primitives": ["map", "marker"],
    })

    result = await resolver.resolve(
        "geography.analysis",
        ["structured_data"],
        client,
        request="Show me a map",
    )

    assert result.selected is not None
    assert result.selected.type == "map"
    assert result.selected.renderer == "map.renderer"
    assert result.selected.environment == "geospatial"
    assert result.selected.score.client_support == 100

    no_data = await resolver.resolve(
        "geography.analysis",
        [],
        client,
    )
    assert no_data.selected is None
    assert "No matching real capability outputs" in no_data.reasons[0]


@pytest.mark.asyncio
async def test_resolver_reports_unavailable_when_client_has_no_approved_map_renderer():
    registry = _registry()
    resolver = PresentationResolver(registry=registry)
    client = PresentationCapabilities.model_validate({
        "clientId": "text-only",
        "platform": "web",
        "surfaces": ["web"],
        "environments": ["geospatial"],
        "primitives": ["text"],
        "renderers": ["text.renderer"],
    })

    result = await resolver.resolve(
        "geography.analysis",
        ["structured_data"],
        client,
    )

    assert result.selected is None
    assert len(result.unavailable) == 1
    assert result.unavailable[0].renderer is None
    assert "No approved renderer" in result.unavailable[0].reason


def test_capability_binding_is_validated_and_stored_by_existing_registry():
    registry = _registry()
    capability = registry.capabilities.get("geography.analysis")
    assert capability is not None
    assert registry.capabilities.get_metadata("geography.analysis")["presentation"]
    assert registry.definitions()[0].id == "geography.analysis"

    with pytest.raises(ValueError, match="No approved renderer"):
        registry.register_capability_binding(
            "geography.analysis",
            PresentationCapabilityBinding(
                visualizations=[VisualizationBinding(type="diagram")],
            ),
        )

    with pytest.raises(KeyError, match="Unknown capability"):
        registry.register_capability_binding(
            "unknown.capability",
            PresentationCapabilityBinding(),
        )


@pytest.mark.asyncio
async def test_authenticated_discovery_and_client_registration_endpoints(
    test_client,
    auth_headers,
):
    assert (await test_client.get("/api/v1/presentation/capabilities")).status_code in {401, 403}

    capabilities = await test_client.get(
        "/api/v1/presentation/capabilities",
        headers=auth_headers,
    )
    renderers = await test_client.get(
        "/api/v1/presentation/renderers",
        headers=auth_headers,
    )
    environments = await test_client.get(
        "/api/v1/presentation/environments",
        headers=auth_headers,
    )
    assert capabilities.status_code == renderers.status_code == environments.status_code == 200
    assert "map.renderer" in {item["type"] for item in renderers.json()["renderers"]}

    registration = await test_client.post(
        "/api/v1/presentation/clients/register",
        headers=auth_headers,
        json={
            "clientId": "web-client",
            "runtimeVersion": "1.0",
            "platform": "web",
            "surfaces": ["web"],
            "renderers": ["text.renderer"],
            "environments": ["conversation"],
            "primitives": ["text"],
            "input": ["text"],
            "output": ["text"],
        },
    )
    assert registration.status_code == 200
    assert registration.json()["accepted"] is True
    assert registration.json()["clientId"] == "web-client"
    assert "text.renderer" in {
        renderer["type"]
        for renderer in registration.json()["runtimeCapabilities"]["renderers"]
    }
