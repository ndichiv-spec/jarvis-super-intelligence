"""Canonical Capability Contract + domain classification.

Adds machine-readable capability metadata to the EXISTING ToolRegistry
capabilities without introducing a second registry, permission system or
dispatch path.  ``ToolRegistry`` remains the single execution and authorization
boundary; this module is the *catalogue* that tells the Brain what exists,
whether it is available, what it costs and whether it works offline.

The contract per capability::

    id, name, description, domain, version,
    input_schema, output_schema,
    availability, availability_reason, health,
    execution_surface, operations, operation_arguments,
    authentication_required, required_permissions,
    requires_confirmation, risk_level, data_classification,
    network_requirements, endpoint_requirements, latency_ms, quality_score,
    fallbacks, supported_environments, observability,
    supports_streaming, supports_async, supports_offline,
    supports_background_jobs, service_dependencies, provider_dependencies,
    cost_model, timeout, retry_policy, audit_policy

New domains are added by declaring a :class:`DomainPack` and registering
capabilities into it - no Brain change required.
"""
from __future__ import annotationsfrom dataclasses import dataclass, fieldfrom typing import Any, Optionalfrom .models import RiskLevelfrom .tool_registry import ToolRegistryCONTRACT_VERSION = "1.1"

import math
import refrom dataclasses import dataclass, fieldfrom typing import Any, Optionalfrom .models import RiskLevelfrom .tool_registry import ToolRegistryCONTRACT_VERSION = "1.1"

# Operating modes.  A capability declares which modes it can serve so the
# fabric can degrade honestly instead of pretending a cloud path exists.
ONLINE = "online"
DEGRADED = "degraded"
OFFLINE = "offline"
MODES = (ONLINE, DEGRADED, OFFLINE)

# Canonical domains.
DOMAINS = (
    "software_engineering",
    "research",
    "documents",
    "data_analytics",
    "web",
    "geography",
    "communication",
    "infrastructure",
    "ai_ml_development",
    "business_workflow",
    "offline_local",
    "platform",
)

# Per-domain free-text intent hints used for task->capability discovery.
DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "software_engineering": (
        "code", "repo", "repository", "file", "function", "test", "github",
        "diff", "branch", "pull request", "build", "ci", "stub", "todo",
        "placeholder", "refactor", "bug", "stack trace", "traceback"),
    "research": (
        "research", "find out", "latest", "compare", "source", "citation",
        "paper", "evidence", "investigate"),
    "documents": (
        "document", "pdf", "docx", "csv", "xlsx", "spreadsheet", "markdown",
        "extract text", "summarize document"),
    "data_analytics": (
        "database", "postgres", "mongodb", "query", "dataset", "profile",
        "metric", "aggregate", "chart"),
    "web": ("web", "internet", "browse", "url", "website", "online search",
            "http"),
    "geography": ("map", "route", "navigate", "place", "geography", "offline map",
                  "kiwix", "organic maps"),
    "communication": ("email", "calendar", "notify", "message", "voice", "call"),
    "infrastructure": ("docker", "container", "service", "deploy", "restart",
                       "health", "redis", "port", "process"),
    "ai_ml_development": ("model", "training", "checkpoint", "artifact",
                          "kaggle", "hugging face", "huggingface", "nvidia",
                          "evaluate", "promote", "dataset", "gpu", "silverwing",
                          "brain", "lifecycle"),
    "business_workflow": ("workflow", "approval", "invoice", "schedule",
                          "business process"),
    "offline_local": ("offline", "without internet", "local", "degraded",
                      "air-gapped", "no network"),
    "platform": ("capability", "capabilities", "what can you do", "job",
                 "task status", "usage", "audit", "cost"),
}


CAPABILITY_LIFECYCLE_STATES = (
    "discovered",
    "installed",
    "configured",
    "registered",
    "available",
    "authorized",
    "executable",
    "verified",
    "verified_operational",
    "temporarily_unavailable",
    "unsupported",
)


@dataclass
class CapabilityManifest:
    """Validated capability manifest anchored to the existing contract metadata."""

    id: str
    name: str
    description: str
    domain: str
    version: str = CONTRACT_VERSION
    lifecycle_state: str = "registered"
    supported_operations: tuple[str, ...] = ()
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_provider: str | None = None
    provider_dependencies: tuple[str, ...] = ()
    required_services: tuple[str, ...] = ()
    required_hardware: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    approval_policy: str = "user_confirmation"
    risk_level: str = RiskLevel.READ.value
    requires_confirmation: bool = False
    authentication_required: bool | None = None
    availability: str = "available"
    health: str = "healthy"
    data_classification: str = "unspecified"
    network_requirements: str = "not_required"
    endpoint_requirements: tuple[str, ...] = ()
    supported_presentation_formats: tuple[str, ...] = ()
    compatibility_requirements: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    cancellation_semantics: str = "cooperative"
    error_semantics: str = "explicit_failure"
    alternatives: tuple[str, ...] = ()
    observability: str = "canonical_runtime_events"
    provenance_requirements: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "version": self.version,
            "lifecycle_state": self.lifecycle_state,
            "supported_operations": list(self.supported_operations),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "required_provider": self.required_provider,
            "provider_dependencies": list(self.provider_dependencies),
            "required_services": list(self.required_services),
            "required_hardware": list(self.required_hardware),
            "required_permissions": list(self.required_permissions),
            "approval_policy": self.approval_policy,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "authentication_required": self.authentication_required,
            "availability": self.availability,
            "health": self.health,
            "data_classification": self.data_classification,
            "network_requirements": self.network_requirements,
            "endpoint_requirements": list(self.endpoint_requirements),
            "supported_presentation_formats": list(self.supported_presentation_formats),
            "compatibility_requirements": self.compatibility_requirements,
            "timeout_seconds": self.timeout_seconds,
            "cancellation_semantics": self.cancellation_semantics,
            "error_semantics": self.error_semantics,
            "alternatives": list(self.alternatives),
            "observability": self.observability,
            "provenance_requirements": self.provenance_requirements,
        }


_SCHEMA_TYPES = {
    "array", "boolean", "integer", "null", "number", "object", "string",
}
_SCHEMA_KEYWORDS = {
    "$schema", "$id", "$comment", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly", "type", "enum",
    "const", "properties", "required", "additionalProperties",
    "items", "minProperties", "maxProperties",
    "minLength", "maxLength", "pattern", "format", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems", "uniqueItems", "allOf", "anyOf", "oneOf", "not",
}
_SCHEMA_NUMBER_KEYWORDS = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
}
_SCHEMA_INTEGER_KEYWORDS = {
    "minProperties", "maxProperties",
    "minLength", "maxLength", "minItems", "maxItems",
}


def _validate_json_schema(schema: Any, path: str, depth: int = 0) -> None:
    """Validate the local JSON Schema subset used by trusted capability adapters."""
    if depth > 32 or not isinstance(schema, dict):
        raise ValueError(f"{path} must be a valid JSON Schema object")
    unknown = set(schema) - _SCHEMA_KEYWORDS
    if unknown:
        raise ValueError(f"{path} contains unsupported schema keywords")

    schema_type = schema.get("type")
    if "type" in schema:
        types = schema_type if isinstance(schema_type, list) else [schema_type]
        if (
            not types
            or any(not isinstance(item, str) or item not in _SCHEMA_TYPES for item in types)
            or len(types) != len(set(types))
        ):
            raise ValueError(f"{path}.type contains an unsupported type")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or any(
        not isinstance(name, str) or not name for name in properties
    ):
        raise ValueError(f"{path}.properties must map names to schemas")
    for name, child in properties.items():
        _validate_json_schema(child, f"{path}.properties.{name}", depth + 1)

    for key in ("items", "not"):
        if key in schema:
            _validate_json_schema(schema[key], f"{path}.{key}", depth + 1)
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _validate_json_schema(additional, f"{path}.additionalProperties", depth + 1)
    elif "additionalProperties" in schema and not isinstance(additional, bool):
        raise ValueError(f"{path}.additionalProperties must be a schema or boolean")
    for key in ("allOf", "anyOf", "oneOf"):
        alternatives = schema.get(key)
        if alternatives is not None:
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(f"{path}.{key} must contain schemas")
            for child in alternatives:
                _validate_json_schema(child, f"{path}.{key}", depth + 1)

    required = schema.get("required", [])
    if (
        not isinstance(required, list)
        or any(not isinstance(name, str) or not name for name in required)
        or len(required) != len(set(required))
    ):
        raise ValueError(f"{path}.required must contain unique property names")
    for key in ("enum", "examples"):
        if key in schema and (
            not isinstance(schema[key], list)
            or (key == "enum" and not schema[key])
        ):
            raise ValueError(f"{path}.{key} must be a non-empty list")
    for key in ("title", "description", "format", "$schema", "$id", "$comment"):
        if key in schema and not isinstance(schema[key], str):
            raise ValueError(f"{path}.{key} must be a string")
    if "pattern" in schema:
        try:
            re.compile(schema["pattern"])
        except (TypeError, re.error) as exc:
            raise ValueError(f"{path}.pattern is invalid") from exc
    for key in _SCHEMA_INTEGER_KEYWORDS:
        value = schema.get(key)
        if key in schema and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ValueError(f"{path}.{key} must be a non-negative integer")
    for key in _SCHEMA_NUMBER_KEYWORDS:
        value = schema.get(key)
        if key in schema and (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError(f"{path}.{key} must be a finite number")
    for lower, upper in (
        ("minProperties", "maxProperties"),
        ("minLength", "maxLength"),
        ("minItems", "maxItems"),
    ):
        if lower in schema and upper in schema and schema[lower] > schema[upper]:
            raise ValueError(f"{path}.{lower} must not exceed {upper}")
    if "multipleOf" in schema and schema["multipleOf"] <= 0:
        raise ValueError(f"{path}.multipleOf must be greater than zero")
    for lower, upper in (
        ("minimum", "maximum"),
        ("exclusiveMinimum", "exclusiveMaximum"),
    ):
        if lower in schema and upper in schema and schema[lower] > schema[upper]:
            raise ValueError(f"{path}.{lower} must not exceed {upper}")
    for key in ("deprecated", "readOnly", "writeOnly", "uniqueItems"):
        if key in schema and not isinstance(schema[key], bool):
            raise ValueError(f"{path}.{key} must be a boolean")


def validate_capability_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate a manifest without trusting its claimed lifecycle or health."""
    if not isinstance(manifest, dict):
        raise ValueError("capability manifest must be a mapping")
    required = (
        "id", "name", "description", "domain", "version",
        "supported_operations", "input_schema", "output_schema",
        "required_provider", "provider_dependencies", "required_services", "required_hardware",
        "required_permissions", "approval_policy", "risk_level",
        "requires_confirmation", "authentication_required",
        "availability", "health",
        "data_classification", "network_requirements", "endpoint_requirements",
        "supported_presentation_formats", "compatibility_requirements",
        "timeout_seconds", "cancellation_semantics", "error_semantics",
        "alternatives", "observability", "provenance_requirements",
        "lifecycle_state",
    )
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"missing capability manifest fields: {missing}")
    state = str(manifest["lifecycle_state"])
    if state not in CAPABILITY_LIFECYCLE_STATES:
        raise ValueError(f"unsupported lifecycle state: {state}")
    if not all(
        isinstance(manifest.get(key), str) and manifest[key].strip()
        for key in ("id", "name", "description", "version", "domain")
    ):
        raise ValueError("manifest identity fields must be non-empty strings")
    if manifest["id"] != manifest["name"]:
        raise ValueError("manifest id must match its registered capability name")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", manifest["id"]):
        raise ValueError("manifest id is not a stable capability identifier")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", manifest["version"]):
        raise ValueError("manifest version must be numeric major.minor[.patch]")
    if manifest["domain"] not in DOMAINS:
        raise ValueError("unsupported capability domain")
    operations = manifest.get("supported_operations") or ()
    if not isinstance(operations, (list, tuple)) or not operations:
        raise ValueError("capability manifest must declare one or more operations")
    if not all(isinstance(item, str) and item.strip() for item in operations):
        raise ValueError("supported operations must be non-empty strings")
    for key in ("input_schema", "output_schema"):
        _validate_json_schema(manifest.get(key), key)
        if manifest[key].get("type") != "object":
            raise ValueError(f"{key} must describe an object")
    list_fields = (
        "provider_dependencies", "required_services", "required_hardware", "required_permissions",
        "endpoint_requirements", "supported_presentation_formats",
        "alternatives",
    )
    for key in list_fields:
        value = manifest[key]
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"{key} must be a list of non-empty strings")
    if manifest["required_provider"] is not None and not isinstance(
        manifest["required_provider"], str,
    ):
        raise ValueError("required_provider must be a string or null")
    if manifest["approval_policy"] not in {"server_policy", "user_confirmation"}:
        raise ValueError("unsupported capability approval policy")
    if manifest["risk_level"] not in {level.value for level in RiskLevel}:
        raise ValueError("unsupported capability risk level")
    if not isinstance(manifest["requires_confirmation"], bool):
        raise ValueError("requires_confirmation must be boolean")
    if manifest["authentication_required"] not in (None, True, False):
        raise ValueError("authentication_required must be boolean or null")
    if manifest["availability"] not in {
        "AVAILABLE", "DEGRADED", "UNAVAILABLE", "OFFLINE",
        "NOT_CONFIGURED", "UNKNOWN",
    }:
        raise ValueError("unsupported capability availability")
    if manifest["health"] not in {"healthy", "degraded", "unhealthy", "unknown"}:
        raise ValueError("unsupported capability health state")
    for key in ("compatibility_requirements", "provenance_requirements"):
        if not isinstance(manifest[key], dict):
            raise ValueError(f"{key} must be an object")
    timeout = manifest["timeout_seconds"]
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600")
    for key in ("cancellation_semantics", "error_semantics", "observability"):
        if not isinstance(manifest[key], str) or not manifest[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    safe = dict(manifest)
    safe["claimed_lifecycle_state"] = state
    safe["lifecycle_state"] = "discovered"
    safe["required_services"] = list(manifest["required_services"])
    safe["provider_dependencies"] = list(manifest["provider_dependencies"])
    safe["required_hardware"] = list(manifest["required_hardware"])
    safe["required_permissions"] = list(manifest["required_permissions"])
    safe["endpoint_requirements"] = list(manifest["endpoint_requirements"])
    safe["supported_presentation_formats"] = list(
        manifest["supported_presentation_formats"]
    )
    safe["alternatives"] = list(manifest["alternatives"])
    return safe


def _manifest_from_contract(contract: dict[str, Any], lifecycle_state: str = "registered") -> dict[str, Any]:
    """Create a manifest from the canonical capability contract for registries and runtime checks."""
    requested = {
        "id": contract.get("id") or contract.get("name"),
        "name": contract.get("name") or contract.get("id"),
        "description": contract.get("description") or "",
        "domain": contract.get("domain") or "platform",
        "version": contract.get("version") or CONTRACT_VERSION,
        "lifecycle_state": lifecycle_state,
        "supported_operations": list(
            contract.get("operations") or [contract.get("id") or contract.get("name")]
        ),
        "input_schema": contract.get("input_schema") or {},
        "output_schema": contract.get("output_schema") or {},
        "required_provider": (
            contract["provider_dependencies"][0]
            if len(contract.get("provider_dependencies") or ()) == 1 else None
        ),
        "provider_dependencies": list(contract.get("provider_dependencies") or ()),
        "required_services": list(contract.get("service_dependencies") or ()),
        "required_hardware": list(contract.get("hardware_dependencies") or ()),
        "required_permissions": list(contract.get("required_permissions") or ()),
        "approval_policy": "user_confirmation" if contract.get("requires_confirmation") else "server_policy",
        "risk_level": contract.get("risk_level") or RiskLevel.READ.value,
        "requires_confirmation": bool(contract.get("requires_confirmation")),
        "authentication_required": contract.get("authentication_required"),
        "availability": contract.get("availability") or "available",
        "health": contract.get("health") or "healthy",
        "data_classification": contract.get("data_classification") or "unspecified",
        "network_requirements": contract.get("network_requirements") or "not_required",
        "endpoint_requirements": list(contract.get("endpoint_requirements") or ()),
        "supported_presentation_formats": tuple(contract.get("supported_environments") or ()),
        "compatibility_requirements": {
            "supported_environments": list(contract.get("supported_environments") or ()),
        },
        "timeout_seconds": int(contract.get("timeout") or 30),
        "cancellation_semantics": "cooperative" if contract.get("supports_async") else "not_supported",
        "error_semantics": "explicit_tool_result_failure",
        "alternatives": list(contract.get("fallbacks") or ()),
        "observability": contract.get("observability") or "canonical_runtime_events",
        "provenance_requirements": {
            "audit_policy": contract.get("audit_policy") or "record_execution",
            "observability": contract.get("observability") or "canonical_runtime_events",
        },
    }
    return requested


def register_capability_manifest(
    manifest: dict[str, Any],
    registry: Any | None = None,
    *,
    contracts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate metadata for an already trusted tool; never register executable code."""
    validated = validate_capability_manifest(manifest)
    if registry is not None:
        registered = {
            item["name"]: item for item in registry.describe()
        }
        existing = registered.get(validated["id"])
        if existing is None:
            raise ValueError("capability manifest cannot install an unregistered tool")
        if existing.get("parameters") != validated["input_schema"]:
            raise ValueError("capability manifest input schema conflicts with ToolRegistry")
        required_permissions = tuple(
            getattr(registry, "_required_permissions", {}).get(validated["id"], ())
        )
        if set(required_permissions) != set(validated["required_permissions"]):
            raise ValueError("capability manifest permissions conflict with ToolRegistry")
        if existing.get("risk") != validated["risk_level"]:
            raise ValueError("capability manifest risk conflicts with ToolRegistry")
        if existing.get("requires_confirmation") != validated["requires_confirmation"]:
            raise ValueError("capability manifest approval conflicts with ToolRegistry")
        canonical_contracts = contracts or build_contracts(registry, inventory={})
        contract = canonical_contracts.get(validated["id"])
        if contract is None:
            raise ValueError("capability manifest has no canonical contract")
        canonical = validate_capability_manifest(
            _manifest_from_contract(contract),
        )
        contract_fields = (
            "description", "domain", "version", "supported_operations",
            "input_schema", "output_schema", "required_provider",
            "provider_dependencies", "required_services", "required_hardware",
            "required_permissions", "approval_policy", "risk_level",
            "requires_confirmation", "authentication_required",
            "data_classification", "network_requirements",
            "endpoint_requirements", "supported_presentation_formats",
            "compatibility_requirements", "timeout_seconds",
            "cancellation_semantics", "error_semantics", "alternatives",
            "observability", "provenance_requirements",
        )
        for key in contract_fields:
            if validated[key] != canonical[key]:
                raise ValueError(f"capability manifest {key} conflicts with registry contract")
        validated["lifecycle_state"] = "registered"
        validated["registration_verified"] = True
        validated["claimed_availability"] = validated["availability"]
        validated["claimed_health"] = validated["health"]
        validated["availability"] = canonical["availability"]
        validated["health"] = canonical["health"]
    return validated


@dataclass
class CapabilityContract:
    """Machine-readable metadata for one capability."""

    id: str
    name: str
    description: str
    domain: str
    version: str = CONTRACT_VERSION
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    availability: str = "UNKNOWN"
    availability_reason: Optional[str] = None
    health: str = "unknown"
    execution_surface: str = "unknown"
    operations: tuple[str, ...] = ()
    operation_arguments: dict[str, dict[str, Any]] = field(default_factory=dict)
    operation_intents: dict[str, dict[str, Any]] = field(default_factory=dict)
    intent_confirmation_operations: tuple[str, ...] = ()
    operation_output_requirements: dict[str, tuple[str, ...]] = field(default_factory=dict)
    authentication_required: Optional[bool] = None
    required_permissions: tuple[str, ...] = ()
    requires_confirmation: bool = False
    risk_level: str = RiskLevel.READ.value
    data_classification: str = "unspecified"
    network_requirements: str = "unknown"
    endpoint_requirements: tuple[str, ...] = ()
    latency_ms: Optional[float] = None
    quality_score: Optional[float] = None
    fallbacks: tuple[str, ...] = ()
    supported_environments: tuple[str, ...] = ()
    observability: str = "unknown"
    supports_streaming: bool = False
    supports_async: bool = True
    supports_offline: Optional[bool] = None
    supports_background_jobs: bool = False
    service_dependencies: tuple[str, ...] = ()
    provider_dependencies: tuple[str, ...] = ()
    cost_model: str = "unknown"
    timeout: int = 30
    retry_policy: str = "none"
    audit_policy: str = "record_execution"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "description": self.description, "domain": self.domain,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "availability": self.availability,
            "availability_reason": self.availability_reason,
            "health": self.health,
            "execution_surface": self.execution_surface,
            "operations": list(self.operations),
            "operation_arguments": self.operation_arguments,
            "operation_intents": self.operation_intents,
            "intent_confirmation_operations": list(self.intent_confirmation_operations),
            "operation_output_requirements": {
                operation: list(requirements)
                for operation, requirements in self.operation_output_requirements.items()
            },
            "authentication_required": self.authentication_required,
            "required_permissions": list(self.required_permissions),
            "requires_confirmation": self.requires_confirmation,
            "risk_level": self.risk_level,
            "data_classification": self.data_classification,
            "network_requirements": self.network_requirements,
            "endpoint_requirements": list(self.endpoint_requirements),
            "latency_ms": self.latency_ms,
            "quality_score": self.quality_score,
            "fallbacks": list(self.fallbacks),
            "supported_environments": list(self.supported_environments),
            "observability": self.observability,
            "supports_streaming": self.supports_streaming,
            "supports_async": self.supports_async,
            "supports_offline": self.supports_offline,
            "supports_background_jobs": self.supports_background_jobs,
            "service_dependencies": list(self.service_dependencies),
            "provider_dependencies": list(self.provider_dependencies),
            "cost_model": self.cost_model,
            "timeout": self.timeout,
            "retry_policy": self.retry_policy,
            "audit_policy": self.audit_policy,
        }


@dataclass
class DomainPack:
    """A named group of capabilities. Adding a domain = adding a pack."""

    domain: str
    title: str
    description: str
    capability_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain, "title": self.title,
            "description": self.description,
            "capabilities": list(self.capability_ids),
        }


# --------------------------------------------------------------------------- #
# Declarative metadata for every existing capability.
# domain, offline, streaming, background, cost, timeout, retry, services, perms
# --------------------------------------------------------------------------- #
_META: dict[str, dict[str, Any]] = {
    "image.generate": dict(
        domain="communication",
        supports_offline=False,
        cost_model="provider",
        timeout=120,
        retry_policy="none",
        execution_surface="configured_image_provider",
        operations=("image.generate",),
        operation_arguments={
            "image.generate": {"prompt": "$query"},
        },
        operation_intents={
            "image.generate": {
                "semantic_type": "image.generate",
                "result_renderer": "generated_image",
                "match_patterns": [
                    r"\b(?:generate|create|draw|make)\b",
                    r"\b(?:image|picture|illustration|photo)\b",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?"
                    r"(?:please\s+)?(?:generate|create|draw|make)\s+"
                    r"(?:me\s+)?(?:an?\s+)?"
                    r"(?:image|picture|illustration|photo)\s+"
                    r"(?:of\s+)?(?P<subject>.+?)[?.!,]*\s*$"
                ),
                "query_template": "{subject}",
                "result_caveat": (
                    "Generated media is an AI-created result, not a photograph "
                    "or a verified depiction of a real scene."
                ),
                "empty_result_message": (
                    "The configured image provider did not return a stored image."
                ),
                "plan_summary": "Generate and securely store the requested image.",
                "step_summary": "Call the configured image provider and validate its stored output.",
                "completion_condition_type": "answer_generated",
                "completion_expected": "validated stored image reference",
                "result_count_path": "media_refs",
            },
        },
        intent_confirmation_operations=("image.generate",),
        operation_output_requirements={"image.generate": ("result",)},
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        },
        network_requirements="required",
        data_classification="user_supplied_prompt",
        provider_dependencies=("openai", "replicate", "stability"),
        supported_environments=("conversation", "image"),
        observability="canonical_runtime_events",
        approval_policy="explicit_user_request",
    ),
    # -- software engineering -------------------------------------------------
    "project.inspect": dict(domain="software_engineering", supports_offline=True,
                            cost_model="local_io", timeout=60),
    "project.search": dict(
        domain="software_engineering",
        supports_offline=True,
        cost_model="local_io",
        timeout=60,
        execution_surface="core_workspace",
        operations=("workspace.search",),
        operation_arguments={
            "workspace.search": {"query": "$query", "max_results": 40},
        },
        operation_intents={
            "workspace.search": {
                "semantic_type": "workspace.search",
                "result_renderer": "workspace_matches",
                "result_count_path": "match_count",
                "match_patterns": [
                    r"\b(?:search|find)\b",
                    r"\b(?:this|the|my)\s+(?:jarvis\s+)?(?:project|workspace|repository|repo)\b",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?"
                    r"(?:search|find)\s+(?:this|the|my)\s+"
                    r"(?:jarvis\s+)?(?:project|workspace|repository|repo)\s+"
                    r"for\s+(?P<subject>.+?)[?.!,]*\s*$"
                ),
                "query_template": "{subject}",
                "plan_summary": "Search the configured JARVIS workspace for the requested text.",
                "step_summary": "Search the authorized workspace and report observed matches.",
                "completion_condition_type": "answer_generated",
                "completion_expected": "workspace search result observed",
                "empty_result_message": "The workspace search returned no readable result.",
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "artifacts": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["result", "artifacts"],
        },
        network_requirements="not_required",
        data_classification="workspace",
        supported_environments=("core_workspace", "conversation"),
        observability="canonical_runtime_events",
        required_permissions=("project:read",),
    ),
    "project.test_status": dict(domain="software_engineering",
                                supports_offline=True, cost_model="local_io",
                                timeout=30),
    "files.read": dict(domain="software_engineering", supports_offline=True,
                       cost_model="local_io", timeout=30),
    "files.search": dict(domain="software_engineering", supports_offline=True,
                         cost_model="local_io", timeout=60),
    "github.inspect": dict(domain="software_engineering",
                           service_dependencies=("github_api",),
                           required_permissions=("github:read",), timeout=25),
    "github.search": dict(domain="software_engineering",
                          service_dependencies=("github_api",),
                          required_permissions=("github:read",), timeout=25),
    # -- research / web ------------------------------------------------------
    "research.compare": dict(
        domain="research",
        execution_surface="http_browser_engine+provider_fabric",
        operations=("research.compare",),
        operation_arguments={
            "research.compare": {"query": "$query"},
        },
        operation_intents={
            "research.compare": {
                "semantic_type": "research.compare",
                "match_patterns": [
                    r"\bresearch\b",
                    r"\b(?:consult|ask)\b",
                    r"\bindependently\b",
                    r"\bcompare\b",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?(?:please\s+)?"
                    r"research\s+(?P<subject>.+?)\s*,?\s+"
                    r"(?:consult|ask)\s+(?:the\s+)?(?:configured\s+)?"
                    r"(?:ai\s+systems|models|providers)\s+independently"
                    r".*$"
                ),
                "query_template": "{subject}",
                "result_caveat": (
                    "Search snippets are discovery observations, not verified page "
                    "contents. Provider analyses are attributed opinions, not facts."
                ),
                "empty_result_message": (
                    "No valid public search sources were observed; no consultation "
                    "or report is claimed."
                ),
                "plan_summary": (
                    "Research the public topic and compare independent configured AI consultations."
                ),
                "step_summary": (
                    "Search public sources, consult distinct healthy providers, "
                    "synthesize their attributed conclusions, and present the comparison."
                ),
                "completion_condition_type": "answer_generated",
                "completion_expected": (
                    "observed public sources, two distinct provider responses, "
                    "and a comparison synthesis, or an explicitly partial result"
                ),
                "result_renderer": "research_report",
                "result_count_path": "artifacts",
            },
        },
        intent_confirmation_operations=("research.compare",),
        operation_output_requirements={
            "research.compare": ("artifacts.url", "artifacts.title"),
        },
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2, "maxLength": 500},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "artifacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "snippet": {"type": "string"},
                            "retrieved_at": {"type": "string"},
                            "provider": {"type": "string"},
                        },
                        "required": ["title", "url", "snippet"],
                    },
                },
            },
            "required": ["result", "artifacts"],
        },
        network_requirements="required",
        data_classification="public_research_query_and_search_snippets",
        provider_dependencies=("provider_fabric",),
        service_dependencies=("browser",),
        required_permissions=("web:read", "model:consult"),
        supported_environments=("conversation", "web"),
        observability="canonical_runtime_events",
        approval_policy="explicit_user_request",
        risk_level=RiskLevel.NETWORK.value,
        cost_model="provider",
        timeout=150,
        retry_policy="none",
        audit_policy="record_execution",
    ),
    "search_web": dict(
        domain="web",
        execution_surface="http_browser_engine",
        operations=("web.search", "media.discovery"),
        operation_arguments={
            "media.discovery": {
                "query": "$query",
                "max_results": 8,
                "extract": False,
            },
            "web.search": {
                "query": "$query",
                "max_results": 8,
                "extract": False,
            },
        },
        operation_intents={
            "media.discovery": {
                "semantic_type": "media.discovery",
                "match_patterns": [
                    r"\b(?:watch|stream|find|search|where\s+can\s+i\s+watch|where\s+to\s+watch)\b",
                    r"\b(?:movies?|films?|series|tv\s+shows?|where\s+can\s+i\s+watch|where\s+to\s+watch)\b",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?"
                    r"(?:(?:i\s+)?(?:want|would\s+like)\s+to\s+)?"
                    r"(?:where\s+can\s+i\s+watch|where\s+to\s+watch|"
                    r"watch|stream|find|search)\s+"
                    r"(?P<subject>.+?)\s*"
                    r"(?:movies?|films?|series|tv\s+shows?|streaming|"
                    r"legally|online|to\s+watch)?\s*[?.!,]*\s*$"
                ),
                "query_template": (
                    "{subject} movies official streaming availability where to watch"
                ),
                "result_caveat": (
                    "These listings are not verified as official or current and do "
                    "not confirm licensing, subscription access, or regional playback. "
                    "Prefer an official provider result and authenticate there if required. "
                    "Discovery is supported by this execution surface; playback is not "
                    "currently supported here. I have not started playback."
                ),
                "empty_result_message": (
                    "I could not confirm where this title is available. This execution "
                    "surface supports discovery only, not playback; I have not started "
                    "playback."
                ),
                "plan_summary": "Search the selected source for media viewing information.",
                "step_summary": "Retrieve current viewing information from this source.",
                "completion_expected": "public HTTPS source with a title observed",
                "completion_condition_type": "source_observed",
                "selectable_results": True,
            },
            "web.search": {
                "semantic_type": "web.search",
                "result_renderer": "public_links",
                "match_patterns": [
                    r"\b(?:research|search|find|look\s+up)\b",
                    r"\b(?:web|internet|online|sources?|latest|current|today)\b",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?"
                    r"(?:research|search(?:\s+the\s+web|\s+online)?|"
                    r"look\s+up|find)\s+(?P<subject>.+?)"
                    r"(?:\s+(?:on\s+the\s+web|online|with\s+sources))?"
                    r"[?.!,]*\s*$"
                ),
                "query_template": "{subject}",
                "result_caveat": (
                    "These are observed public search results, not independently "
                    "verified claims or authenticated service actions."
                ),
                "empty_result_message": "The public web search returned no usable sources.",
                "plan_summary": "Search the public web for the requested information.",
                "step_summary": "Retrieve public search results from an authorized source.",
                "completion_expected": "public HTTPS source observed",
                "completion_condition_type": "source_observed",
                "selectable_results": True,
            },
            "media.playback": {
                "semantic_type": "media.playback",
                "result_renderer": "unsupported",
                "match_patterns": [
                    r"\b(?:play|start)\b",
                    r"\b(?:video|movie|film|episode|stream)\b",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?"
                    r"(?:(?:i\s+)?(?:want|would\s+like)\s+to\s+)?"
                    r"(?:play|start)\s+(?P<subject>.+?)[?.!,]*\s*$"
                ),
                "query_template": "{subject}",
                "empty_result_message": (
                    "No authorized media playback capability is registered. "
                    "I have not started playback."
                ),
                "plan_summary": "Check for an authorized media playback capability.",
                "step_summary": "Do not claim playback unless an authorized player exists.",
            },
        },
        operation_output_requirements={
            "media.discovery": ("artifacts.url", "artifacts.title"),
        },
        intent_confirmation_operations=("media.discovery", "web.search"),
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "artifacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                        "required": ["url", "title"],
                    },
                },
            },
            "required": ["result", "artifacts"],
        },
        network_requirements="required",
        data_classification="public",
        supported_environments=("web", "conversation"),
        service_dependencies=("browser",),
        required_permissions=("web:read",),
        observability="canonical_runtime_events",
        cost_model="unknown",
        timeout=30,
        retry_policy="backoff_1",
    ),
    "knowledge_retrieve": dict(domain="research", supports_offline=True,
                               cost_model="local_index", timeout=20),
    "static_search": dict(domain="research", supports_offline=True,
                          cost_model="local_index", timeout=20),
    "model_consult": dict(domain="research",
                          service_dependencies=("provider_gateway",),
                          required_permissions=("model:consult",),
                          cost_model="llm_tokens", timeout=120,
                          retry_policy="backoff_2"),
    # -- memory --------------------------------------------------------------
    "memory_recall": dict(domain="platform", supports_offline=True,
                          cost_model="local_io", timeout=15),
    "memory_store": dict(domain="platform", supports_offline=True,
                         risk_level=RiskLevel.WRITE.value,
                         cost_model="local_io", timeout=15,
                         audit_policy="record_write"),
    # -- execution / sandbox -------------------------------------------------
    "sandbox_run": dict(domain="software_engineering",
                        risk_level=RiskLevel.EXEC.value,
                        cost_model="local_compute", timeout=60,
                        retry_policy="none", audit_policy="record_execution",
                        required_permissions=("sandbox:execute",)),
    # -- platform status -----------------------------------------------------
    "provider.status": dict(domain="platform", supports_offline=True,
                            cost_model="probe", timeout=60),
    "model.status": dict(domain="ai_ml_development", supports_offline=True,
                         cost_model="db_read", timeout=30),
    "job.status": dict(domain="platform", supports_offline=True,
                       cost_model="db_read", timeout=20),
    "artifact.inspect": dict(domain="ai_ml_development", supports_offline=True,
                             cost_model="db_read", timeout=20),
    "docker.status": dict(domain="infrastructure",
                          risk_level=RiskLevel.EXEC.value,
                          service_dependencies=("docker_daemon",), timeout=20),
    # -- cloud hardware fabric ----------------------------------------------
    "cloud.status": dict(domain="infrastructure", supports_offline=True,
                         cost_model="probe", timeout=120),
    "cloud.resources": dict(domain="infrastructure", supports_offline=True,
                            cost_model="probe", timeout=120),
    "cloud.execution_mode": dict(domain="platform", supports_offline=True,
                                 cost_model="probe", timeout=60),
    "compute.select": dict(domain="infrastructure", supports_offline=True,
                           cost_model="local_compute", timeout=60),
    # -- compute capability family (Phase 9 §3) -------------------------------
    "compute.discover": dict(domain="ai_ml_development", supports_offline=False,
                             cost_model="probe", timeout=120),
    "compute.verify": dict(domain="infrastructure", supports_offline=True,
                           cost_model="probe", timeout=60),
    "compute.inference": dict(domain="ai_ml_development",
                              service_dependencies=("nvidia_api",
                                                    "provider_gateway"),
                              cost_model="llm_tokens", timeout=120),
    "compute.training": dict(domain="ai_ml_development",
                             service_dependencies=("kaggle_api",
                                                   "huggingface_api"),
                             risk_level=RiskLevel.EXEC.value,
                             cost_model="provider", timeout=600,
                             retry_policy="none",
                             audit_policy="record_execution",
                             required_permissions=("compute:train",)),
    "compute.evaluation": dict(domain="ai_ml_development", supports_offline=True,
                               cost_model="local_compute", timeout=120),
    "compute.embedding": dict(domain="ai_ml_development",
                              service_dependencies=("nvidia_api",
                                                    "provider_gateway"),
                              cost_model="llm_tokens", timeout=120),
    "compute.artifact_upload": dict(domain="ai_ml_development",
                                    service_dependencies=("huggingface_api",),
                                    risk_level=RiskLevel.WRITE.value,
                                    cost_model="provider", timeout=300,
                                    retry_policy="none",
                                    audit_policy="record_write",
                                    required_permissions=("compute:artifact_upload",)),
    "compute.artifact_download": dict(domain="ai_ml_development",
                                      service_dependencies=("huggingface_api",),
                                      cost_model="provider", timeout=300,
                                      retry_policy="backoff_1"),
    "compute.job_submit": dict(domain="infrastructure",
                               risk_level=RiskLevel.EXEC.value,
                               cost_model="local_compute", timeout=120,
                               audit_policy="record_execution",
                               required_permissions=("compute:submit",)),
    "compute.job_status": dict(domain="infrastructure", supports_offline=True,
                              cost_model="db_read", timeout=20),
    "compute.job_cancel": dict(domain="infrastructure",
                              risk_level=RiskLevel.EXEC.value,
                              cost_model="local_compute", timeout=60,
                              audit_policy="record_execution",
                              required_permissions=("compute:cancel",)),
    "compute.resource_health": dict(domain="infrastructure", supports_offline=True,
                                    cost_model="probe", timeout=60),
    # -- remote execution host ----------------------------------------------
    "remote.compute.status": dict(domain="infrastructure", supports_offline=True,
                                  cost_model="probe", timeout=60),
    "remote.compute.health": dict(domain="infrastructure", supports_offline=True,
                                  cost_model="probe", timeout=60),
    "remote.compute.resources": dict(domain="infrastructure",
                                     supports_offline=True, cost_model="probe",
                                     timeout=90),
    "remote.compute.verify": dict(domain="infrastructure",
                                  supports_offline=True, cost_model="probe",
                                  timeout=60),
    "docker.remote.status": dict(domain="infrastructure",
                                 supports_offline=True, cost_model="probe",
                                 timeout=60),
    "docker.remote.images": dict(domain="infrastructure",
                                 supports_offline=True, cost_model="probe",
                                 timeout=60),
    "docker.remote.containers": dict(domain="infrastructure",
                                     supports_offline=True, cost_model="probe",
                                     timeout=60),
    "docker.remote.logs": dict(domain="infrastructure", supports_offline=True,
                               cost_model="probe", timeout=60),
    "docker.remote.health": dict(domain="infrastructure",
                                 supports_offline=True, cost_model="probe",
                                 timeout=60),
    # -- capability discovery ------------------------------------------------
    "capability.discover": dict(domain="platform", supports_offline=True,
                                cost_model="local_compute", timeout=30),
    "capability.catalogue": dict(domain="platform", supports_offline=True,
                                 cost_model="local_compute", timeout=60),
    # -- data analytics -------------------------------------------------------
    # Read-only analytics capabilities all enforce the same default trio
    # (discover + read + analyze). These values are the ENFORCED set on the
    # tool classes in research_engine.data_tools; a drift test asserts the two
    # never diverge, so discovery can never under-declare a requirement.
    "data.sources": dict(domain="data_analytics", supports_offline=True,
                         cost_model="probe", timeout=90,
                         required_permissions=("data:discover", "data:read",
                                               "data:analyze")),
    "data.schema": dict(domain="data_analytics", supports_offline=True,
                        cost_model="db_read", timeout=60,
                        required_permissions=("data:discover", "data:read",
                                              "data:analyze")),
    "data.preview": dict(domain="data_analytics", supports_offline=True,
                         cost_model="db_read", timeout=40,
                         required_permissions=("data:discover", "data:read",
                                               "data:analyze")),
    "data.query": dict(domain="data_analytics", supports_offline=True,
                       cost_model="db_read", timeout=40, retry_policy="none",
                       required_permissions=("data:discover", "data:read",
                                             "data:analyze")),
    "data.aggregate": dict(domain="data_analytics", supports_offline=True,
                           cost_model="db_read", timeout=60,
                           required_permissions=("data:discover", "data:read",
                                                 "data:analyze")),
    "data.profile": dict(domain="data_analytics", supports_offline=True,
                         cost_model="local_compute", timeout=120,
                         required_permissions=("data:discover", "data:read",
                                               "data:analyze")),
    "data.compare": dict(domain="data_analytics", supports_offline=True,
                         cost_model="local_compute", timeout=120,
                         required_permissions=("data:discover", "data:read",
                                               "data:analyze")),
    "data.sql_explain": dict(domain="data_analytics", supports_offline=True,
                             cost_model="db_read", timeout=40,
                             required_permissions=("data:discover", "data:read",
                                                   "data:analyze")),
    # These capabilities had no _META entry, so build_contracts() defaulted them
    # to domain="platform" and they were invisible to domain-filtered
    # discovery. required_permissions MUST mirror the enforced values on the
    # tool classes in research_engine.data_tools (a drift check asserts this).
    "data.analyze": dict(domain="data_analytics", supports_offline=True,
                         cost_model="provider", timeout=120,
                         required_permissions=("data:discover", "data:read",
                                               "data:analyze"),
                         retry_policy="none"),
    "data.export": dict(domain="data_analytics", supports_offline=True,
                        cost_model="local_compute", timeout=120,
                        required_permissions=("data:discover", "data:read",
                                              "data:export"),
                        retry_policy="none"),
    "data.visualize": dict(domain="data_analytics", supports_offline=True,
                           cost_model="local_compute", timeout=120,
                           required_permissions=("data:discover", "data:read",
                                                 "data:export"),
                           retry_policy="none"),
    "data.ingest": dict(domain="data_analytics", supports_offline=True,
                        cost_model="local_compute", timeout=180,
                        required_permissions=("data:read", "data:write"),
                        retry_policy="none"),
    # -- documents ------------------------------------------------------------
    "documents.inspect": dict(domain="documents", supports_offline=True,
                              cost_model="local_io", timeout=60),
    "documents.extract_text": dict(domain="documents", supports_offline=True,
                                   cost_model="local_io", timeout=60),
    "documents.search": dict(domain="documents", supports_offline=True,
                             cost_model="local_io", timeout=60),
    "documents.chunk": dict(domain="documents", supports_offline=True,
                            cost_model="local_io", timeout=60),
    "documents.validate": dict(domain="documents", supports_offline=True,
                               cost_model="local_io", timeout=60),
    "documents.compare": dict(domain="documents", supports_offline=True,
                              cost_model="local_compute", timeout=120),
    "documents.metadata": dict(domain="documents", supports_offline=True,
                               cost_model="local_io", timeout=30),
    # Also previously missing, defaulting to domain="platform". NOTE: the
    # document tools declare no required_permissions (that domain is gated by
    # risk policy only), so the contract must not invent requirements the
    # registry does not enforce.
    "documents.convert": dict(domain="documents", supports_offline=True,
                              cost_model="local_io", timeout=90),
    "documents.generate": dict(domain="documents", supports_offline=True,
                               cost_model="provider", timeout=120,
                               retry_policy="none"),
    "documents.ingest": dict(domain="documents", supports_offline=True,
                             cost_model="local_io", timeout=180,
                             retry_policy="none"),
    "documents.summarize": dict(domain="documents", supports_offline=True,
                                cost_model="provider", timeout=120,
                                retry_policy="none"),
    # -- geography ------------------------------------------------------------
    # All geography tools are fully offline (pure computation or local files).
    # Coordinates, distance and bearing use local math only.
    # Map data inspection requires JARVIS_GEOGRAPHY_MAP_ROOT to be configured.
    # Offline search requires KIWIX_CORPUS_PATH with a real ZIM archive.
    "geography.coordinates": dict(
        domain="geography",
        supports_offline=True,
        cost_model="local_compute",
        timeout=30,
        execution_surface="local_compute",
        operations=("geography.coordinates.map",),
        operation_arguments={
            "geography.coordinates.map": {"input": "$query"},
        },
        operation_intents={
            "geography.coordinates.map": {
                "semantic_type": "geography.point_map",
                "result_renderer": "geospatial_point_map",
                "match_patterns": [
                    r"\b(?:map|show|plot)\b",
                    r"(?:-?\d{1,2}(?:\.\d+)?\s*[, ]\s*-?\d{1,3}(?:\.\d+)?|coordinates?)",
                ],
                "subject_pattern": (
                    r"^\s*(?:(?:jarvis)[,:]?\s*)?(?:please\s+)?"
                    r"(?:map|show|plot)\s+(?:these\s+)?"
                    r"(?:coordinates?\s*:?\s*)?"
                    r"(?P<subject>-?\d{1,2}(?:\.\d+)?"
                    r"\s*[, ]\s*-?\d{1,3}(?:\.\d+)?)"
                    r"\s*[?.!,]*\s*$"
                ),
                "query_template": "{subject}",
                "result_caveat": (
                    "The map uses coordinates explicitly provided in this "
                    "conversation; it is not a live device location."
                ),
                "empty_result_message": (
                    "The supplied coordinates could not be validated."
                ),
                "plan_summary": (
                    "Validate the user-provided coordinates and prepare a map view."
                ),
                "step_summary": (
                    "Parse and range-check the user-provided coordinate pair."
                ),
            },
        },
    ),
    "geography.distance": dict(domain="geography", supports_offline=True,
                               cost_model="local_compute", timeout=30),
    "geography.bearing": dict(domain="geography", supports_offline=True,
                              cost_model="local_compute", timeout=30),
    "geography.area": dict(domain="geography", supports_offline=True,
                           cost_model="local_compute", timeout=30),
    "geography.location_info": dict(domain="geography", supports_offline=True,
                                    cost_model="local_compute", timeout=30),
    "geography.offline_search": dict(domain="geography", supports_offline=True,
                                    cost_model="local_io", timeout=30,
                                    required_permissions=("geography:read",
                                                          "geography:search")),
    # Map data and place search require local configuration - reported UNAVAILABLE
    # when JARVIS_GEOGRAPHY_MAP_ROOT is not set or when no map files exist.
    "geography.geocode": dict(domain="geography", supports_offline=False,
                            cost_model="none", timeout=30),
    "geography.reverse_geocode": dict(domain="geography", supports_offline=False,
                                     cost_model="none", timeout=30),
    "geography.route": dict(domain="geography", supports_offline=False,
                            cost_model="none", timeout=60),
    "geography.place_search": dict(domain="geography", supports_offline=False,
                                  cost_model="none", timeout=30),
    # Map data inspection requires configured map root.
    "geography.map_data.inspect": dict(domain="geography", supports_offline=True,
                                       cost_model="local_io", timeout=60),
    "geography.map_data.search": dict(domain="geography", supports_offline=True,
                                     cost_model="local_io", timeout=60),
    # Organic Maps requires explicit installation - not available by default.
    "geography.organic_maps": dict(domain="geography", supports_offline=False,
                                  cost_model="none", timeout=30),
    # -- AI / ML development -------------------------------------------------
    "brain.status": dict(domain="ai_ml_development", supports_offline=True,
                         cost_model="filesystem", timeout=60),
    "brain.artifacts": dict(domain="ai_ml_development", supports_offline=True,
                            cost_model="filesystem", timeout=60),
    "brain.lifecycle": dict(domain="ai_ml_development", supports_offline=True,
                            cost_model="filesystem", timeout=60),
    "silverwing.status": dict(domain="offline_local", supports_offline=True,
                              cost_model="probe", timeout=30),
    "silverwing.artifacts": dict(domain="offline_local",
                                 supports_offline=True,
                                 cost_model="filesystem", timeout=60),
    "silverwing.lifecycle": dict(domain="offline_local",
                                 supports_offline=True,
                                 cost_model="filesystem", timeout=60),
    "kaggle.status": dict(domain="ai_ml_development",
                          service_dependencies=("kaggle_api",), timeout=60),
    "kaggle.jobs": dict(domain="ai_ml_development",
                        service_dependencies=("kaggle_api",), timeout=60),
    "huggingface.status": dict(domain="ai_ml_development",
                               service_dependencies=("huggingface_api",),
                               timeout=40),
    "huggingface.artifacts": dict(domain="ai_ml_development",
                                  service_dependencies=("huggingface_api",),
                                  timeout=40),
    "nvidia.models": dict(domain="ai_ml_development",
                          service_dependencies=("nvidia_api",), timeout=60),
    "nvidia.inference": dict(domain="ai_ml_development",
                             service_dependencies=("nvidia_api",),
                             cost_model="llm_tokens", timeout=120),
    "nvidia.deployment": dict(domain="ai_ml_development",
                              service_dependencies=("nvidia_api",), timeout=60),
    "training.status": dict(domain="ai_ml_development",
                            service_dependencies=("kaggle_api",
                                                  "huggingface_api"),
                            timeout=90),
    "fabric.pipeline": dict(domain="ai_ml_development", supports_offline=True,
                            cost_model="probe", timeout=180),
    "fabric.integrations": dict(domain="ai_ml_development",
                                supports_offline=True, cost_model="probe",
                                timeout=180),
    "development.status": dict(domain="ai_ml_development",
                               supports_offline=True, cost_model="probe",
                               timeout=180),
    "development.next_action": dict(domain="ai_ml_development",
                                    supports_offline=True,
                                    cost_model="probe", timeout=180),
    "development.verify": dict(domain="ai_ml_development",
                               supports_offline=True, cost_model="probe",
                               timeout=180),
}

# Capabilities that stream tokens back rather than returning a single result.
_STREAMING = frozenset({"nvidia.inference", "compute.inference", "model_consult", "search_web"})

# Capabilities that can be promoted to a durable background Job.
_BACKGROUND = frozenset({"project.test_status", "sandbox_run", "kaggle.jobs",
                         "training.status", "development.verify",
                         "fabric.integrations", "development.status",
                         "compute.training", "compute.job_submit",
                         "compute.artifact_upload"})

_DOMAIN_PACKS: tuple[DomainPack, ...] = (
    DomainPack("software_engineering", "Software Engineering",
               "Repository inspection, code search, file access, GitHub and "
               "sandboxed execution.", ()),
    DomainPack("research", "Research",
               "Knowledge retrieval, static corpora and model-assisted "
               "synthesis with provenance.", ()),
    DomainPack("web", "Web",
               "Network-backed search and browsing (requires connectivity).", ()),
    DomainPack("documents", "Documents",
               "PDF/DOCX/CSV/XLSX inspection and extraction.", ()),
    DomainPack("data_analytics", "Data / Analytics",
               "PostgreSQL, MongoDB and dataset inspection and querying.", ()),
    DomainPack("geography", "Geography / Navigation",
               "Maps, routing and offline geographic knowledge (Kiwix, "
               "Organic Maps).", ()),
    DomainPack("communication", "Communication",
               "Controlled email, calendar, notification and voice actions.", ()),
    DomainPack("infrastructure", "Infrastructure",
               "Docker, services and deployment health.", ()),
    DomainPack("ai_ml_development", "AI / ML Development",
               "Kaggle training, Hugging Face artifacts, NVIDIA inference and "
               "the Brain/Silverwing lifecycle.", ()),
    DomainPack("business_workflow", "Business Workflows",
               "Approval and business process automation.", ()),
    DomainPack("offline_local", "Offline / Local",
               "Capabilities that keep working without internet access.",
               ()),
    DomainPack("platform", "Platform",
               "Capability discovery, jobs, usage and audit.", ()),
)


def build_contracts(registry: ToolRegistry | None = None,
                    inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the canonical contract for every registered capability."""
    if registry is None:
        from .capability_tools import build_capability_registry

        registry = build_capability_registry()
    if inventory is None:
        from .capability_tools import capability_inventory

        try:
            inventory = capability_inventory()
        except Exception:  # noqa: BLE001
            inventory = {}

    contracts: dict[str, Any] = {}
    for described in registry.describe():
        name = described["name"]
        meta = _META.get(name, {})
        inv = inventory.get(name) or {}
        availability = inv.get("state") or "UNKNOWN"
        reason = (inv.get("reason") or inv.get("detail")
                  or inv.get("source") or None)
        risk = described.get("risk") or RiskLevel.READ.value
        contract = CapabilityContract(
            id=name,
            name=name,
            description=described.get("description", ""),
            domain=meta.get("domain", "platform"),
            input_schema=described.get("parameters")
            or {"type": "object", "properties": {}},
            availability=availability,
            availability_reason=reason,
            health=inv.get("health", "unknown"),
            execution_surface=meta.get("execution_surface", "unknown"),
            operations=tuple(meta.get("operations", ())),
            operation_arguments=meta.get("operation_arguments", {}),
            operation_intents=meta.get("operation_intents", {}),
            intent_confirmation_operations=tuple(
                meta.get("intent_confirmation_operations", ())
            ),
            operation_output_requirements=meta.get(
                "operation_output_requirements", {},
            ),
            output_schema=meta.get("output_schema", {}),
            authentication_required=meta.get("authentication_required"),
            required_permissions=tuple(dict.fromkeys((
                *meta.get("required_permissions", ()),
                *described.get("required_permissions", ()),
            ))),
            requires_confirmation=bool(described.get("requires_confirmation", False)),
            risk_level=risk,
            data_classification=meta.get("data_classification", "unspecified"),
            network_requirements=meta.get("network_requirements", "unknown"),
            endpoint_requirements=tuple(meta.get("endpoint_requirements", ())),
            latency_ms=meta.get("latency_ms"),
            quality_score=meta.get("quality_score"),
            fallbacks=tuple(meta.get("fallbacks", ())),
            supported_environments=tuple(meta.get("supported_environments", ())),
            observability=meta.get("observability", "unknown"),
            supports_streaming=name in _STREAMING,
            supports_async=True,
            supports_offline=meta.get("supports_offline"),
            supports_background_jobs=name in _BACKGROUND,
            service_dependencies=tuple(meta.get("service_dependencies", ())),
            provider_dependencies=tuple(meta.get("provider_dependencies", ())),
            cost_model=meta.get("cost_model", "unknown"),
            timeout=int(meta.get("timeout", 30)),
            retry_policy=meta.get("retry_policy", "none"),
            audit_policy=meta.get("audit_policy", "record_execution"),
        )
        contracts[name] = contract.to_dict()
    return contracts


def domain_packs(contracts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Group contracts into domain packs, generated from real registrations."""
    if contracts is None:
        from .capability_tools import build_capability_registry

        contracts = build_contracts(build_capability_registry())
    grouped: dict[str, list[str]] = {}
    for name, c in contracts.items():
        grouped.setdefault(c["domain"], []).append(name)
    out: list[dict[str, Any]] = []
    for pack in _DOMAIN_PACKS:
        names = sorted(grouped.get(pack.domain, []))
        out.append({
            "domain": pack.domain, "title": pack.title,
            "description": pack.description,
            "capabilities": names,
            "implemented": len(names),
            "operational": sum(
                1 for n in names
                if contracts[n]["availability"] == "AVAILABLE"),
        })
        grouped.pop(pack.domain, None)
    for domain, names in sorted(grouped.items()):
        out.append({
            "domain": domain, "title": domain.replace("_", " ").title(),
            "description": "Auto-classified domain.",
            "capabilities": sorted(names),
            "implemented": len(names),
            "operational": sum(
                1 for n in names
                if contracts[n]["availability"] == "AVAILABLE"),
        })
    return out


def build_capability_manifest(
    capability_name: str,
    *,
    lifecycle_state: str = "registered",
    contracts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a validated lifecycle manifest for a registered capability."""
    from .capability_tools import build_capability_registry

    registry = build_capability_registry()
    if contracts is None:
        contracts = build_contracts(registry)
    contract = contracts.get(capability_name)
    if contract is None:
        raise KeyError(f"unknown capability {capability_name!r}")
    manifest = _manifest_from_contract(contract, lifecycle_state)
    return register_capability_manifest(manifest, registry, contracts=contracts)


def discover_capabilities(
    task: str,
    *,
    mode: str = ONLINE,
    contracts: dict[str, Any] | None = None,
    include_unavailable: bool = False,
    max_results: int = 25,
) -> dict[str, Any]:
    """Discover registered matching capabilities, including degraded candidates.

    Filters by domain relevance, operating mode, risk and dependencies.
    Degraded candidates remain visible with their truthful availability state;
    unavailable capabilities are omitted unless explicitly requested.
    Never invents a capability that is not registered.
    """
    if contracts is None:
        from .capability_tools import build_capability_registry

        contracts = build_contracts(build_capability_registry())
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")

    haystack = (task or "").lower()
    scores: list[tuple[int, str, dict[str, Any]]] = []
    for name, c in contracts.items():
        if not include_unavailable and c["availability"] not in {
            "AVAILABLE", "DEGRADED",
        }:
            continue
        if mode == OFFLINE and not c["supports_offline"]:
            continue
        if mode == DEGRADED and not c["supports_offline"] and c["domain"] == "web":
            continue
        score = 0
        for hint in DOMAIN_HINTS.get(c["domain"], ()):
            if hint in haystack:
                score += 3
        for token in haystack.replace("/", " ").replace("-", " ").split():
            if len(token) > 3 and token in name:
                score += 2
            if len(token) > 3 and token in c["description"].lower():
                score += 1
        if score == 0:
            continue
        # Prefer offline-capable, low-risk, available capabilities.
        score += 1 if c["supports_offline"] else 0
        score += 1 if c["risk_level"] == RiskLevel.READ.value else 0
        scores.append((score, name, c))

    scores.sort(key=lambda t: (-t[0], t[1]))
    chosen = scores[:max_results]
    return {
        "task": task,
        "mode": mode,
        "total_registered": len(contracts),
        "matched": len(chosen),
        "capabilities": [
            {"name": n, "domain": c["domain"], "risk": c["risk_level"],
             "availability": c["availability"], "offline": c["supports_offline"],
             "streaming": c["supports_streaming"],
             "cost_model": c["cost_model"], "score": s}
            for s, n, c in chosen
        ],
    }


def capability_catalogue() -> dict[str, Any]:
    """Full catalogue: contracts + domain packs + mode coverage."""
    from .capability_tools import build_capability_registry, capability_inventory

    registry = build_capability_registry()
    try:
        inventory = capability_inventory()
    except Exception:  # noqa: BLE001
        inventory = {}
    contracts = build_contracts(registry, inventory)
    packs = domain_packs(contracts)
    return {
        "contract_version": CONTRACT_VERSION,
        "capability_count": len(contracts),
        "contracts": contracts,
        "domains": packs,
        "mode_coverage": {
            mode: sorted(n for n, c in contracts.items()
                         if c["supports_offline"] or mode != OFFLINE)
            for mode in MODES
        },
        "domain_coverage": {
            "implemented": sorted(p["domain"] for p in packs
                                 if p["implemented"] > 0),
            "declared_but_empty": sorted(p["domain"] for p in packs
                                         if p["implemented"] == 0),
        },
    }


__all__ = [
    "CapabilityContract", "CapabilityManifest", "DomainPack",
    "build_contracts", "build_capability_manifest",
    "validate_capability_manifest", "register_capability_manifest",
    "domain_packs", "discover_capabilities", "capability_catalogue",
    "CONTRACT_VERSION", "CAPABILITY_LIFECYCLE_STATES",
    "DOMAINS", "MODES", "ONLINE", "DEGRADED", "OFFLINE", "DOMAIN_HINTS",
]
