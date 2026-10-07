"""Canonical Capability Contract + domain classification.

Adds machine-readable capability metadata to the EXISTING ToolRegistry
capabilities without introducing a second registry, permission system or
dispatch path.  ``ToolRegistry`` remains the single execution and authorization
boundary; this module is the *catalogue* that tells the Brain what exists,
whether it is available, what it costs and whether it works offline.

The contract per capability::

    id, name, description, domain, version,
    input_schema, output_schema,
    availability, availability_reason,
    authentication_required, required_permissions,
    risk_level, supports_streaming, supports_async, supports_offline,
    supports_background_jobs, service_dependencies, provider_dependencies,
    cost_model, timeout, retry_policy, audit_policy

New domains are added by declaring a :class:`DomainPack` and registering
capabilities into it - no Brain change required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import RiskLevel
from .tool_registry import ToolRegistry

CONTRACT_VERSION = "1.0"

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


@dataclass
class CapabilityContract:
    """Machine-readable metadata for one capability."""

    id: str
    name: str
    description: str
    domain: str
    version: str = CONTRACT_VERSION
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object"})
    availability: str = "UNKNOWN"
    availability_reason: Optional[str] = None
    authentication_required: bool = True
    required_permissions: tuple[str, ...] = ()
    risk_level: str = RiskLevel.READ.value
    supports_streaming: bool = False
    supports_async: bool = True
    supports_offline: bool = False
    supports_background_jobs: bool = False
    service_dependencies: tuple[str, ...] = ()
    provider_dependencies: tuple[str, ...] = ()
    cost_model: str = "none"
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
            "authentication_required": self.authentication_required,
            "required_permissions": list(self.required_permissions),
            "risk_level": self.risk_level,
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
    # -- software engineering -------------------------------------------------
    "project.inspect": dict(domain="software_engineering", supports_offline=True,
                            cost_model="local_io", timeout=60),
    "project.search": dict(domain="software_engineering", supports_offline=True,
                           cost_model="local_io", timeout=60),
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
    "search_web": dict(domain="web", service_dependencies=("browser",),
                       required_permissions=("web:read",), timeout=30,
                       retry_policy="backoff_1"),
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
    "geography.coordinates": dict(domain="geography", supports_offline=True,
                                    cost_model="local_compute", timeout=30),
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
            authentication_required=True,
            required_permissions=tuple(meta.get("required_permissions", ())),
            risk_level=risk,
            supports_streaming=name in _STREAMING,
            supports_async=True,
            supports_offline=bool(meta.get("supports_offline", False)),
            supports_background_jobs=name in _BACKGROUND,
            service_dependencies=tuple(meta.get("service_dependencies", ())),
            provider_dependencies=tuple(meta.get("provider_dependencies", ())),
            cost_model=meta.get("cost_model", "none"),
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


def discover_capabilities(
    task: str,
    *,
    mode: str = ONLINE,
    contracts: dict[str, Any] | None = None,
    include_unavailable: bool = False,
    max_results: int = 25,
) -> dict[str, Any]:
    """Answer "what capabilities are available for this task?".

    Filters by domain relevance, operating mode, availability, risk and
    dependencies.  Never invents a capability that is not registered.
    """
    if contracts is None:
        from .capability_tools import build_capability_registry

        contracts = build_contracts(build_capability_registry())
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")

    haystack = (task or "").lower()
    scores: list[tuple[int, str, dict[str, Any]]] = []
    for name, c in contracts.items():
        if not include_unavailable and c["availability"] != "AVAILABLE":
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
    "CapabilityContract", "DomainPack", "build_contracts", "domain_packs",
    "discover_capabilities", "capability_catalogue", "CONTRACT_VERSION",
    "DOMAINS", "MODES", "ONLINE", "DEGRADED", "OFFLINE", "DOMAIN_HINTS",
]
