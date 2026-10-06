"""Tests for the canonical Capability Contract + domain classification.

Verifies: contract completeness, domain classification, discovery relevance,
mode (online/degraded/offline) filtering, honesty of availability, and that
nothing duplicates or bypasses the existing ToolRegistry.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from research_engine import capability_contract as cc  # noqa: E402
from research_engine.models import RiskLevel  # noqa: E402

REQUIRED_FIELDS = (
    "id", "name", "description", "domain", "version", "input_schema",
    "output_schema", "availability", "authentication_required",
    "required_permissions", "risk_level", "supports_streaming",
    "supports_async", "supports_offline", "supports_background_jobs",
    "service_dependencies", "provider_dependencies", "cost_model", "timeout",
    "retry_policy", "audit_policy",
)


@pytest.fixture(scope="module")
def contracts():
    return cc.build_contracts()


@pytest.fixture(scope="module")
def catalogue():
    return cc.capability_catalogue()


# --------------------------------------------------------------------------- #
# Contract completeness
# --------------------------------------------------------------------------- #
def test_contract_has_all_canonical_fields(contracts) -> None:
    for name, c in contracts.items():
        for field in REQUIRED_FIELDS:
            assert field in c, f"{name} missing contract field {field}"


def test_contract_id_matches_registry_name(contracts) -> None:
    for name, c in contracts.items():
        assert c["id"] == name
        assert c["name"] == name


def test_every_contract_input_schema_is_object(contracts) -> None:
    for name, c in contracts.items():
        assert isinstance(c["input_schema"], dict), f"{name} input schema"
        assert c["input_schema"].get("type") == "object", \
            f"{name} input schema must be a JSON object schema"


def test_risk_level_is_valid(contracts) -> None:
    valid = {r.value for r in RiskLevel}
    for name, c in contracts.items():
        assert c["risk_level"] in valid, f"{name} risk {c['risk_level']!r}"


def test_every_contract_has_a_domain(contracts) -> None:
    for name, c in contracts.items():
        assert c["domain"] in cc.DOMAINS, \
            f"{name} has unknown domain {c['domain']!r}"


def test_no_capability_has_unknown_availability(contracts) -> None:
    """Discovery filters on availability; UNKNOWN would hide capabilities."""
    unknown = [n for n, c in contracts.items() if c["availability"] == "UNKNOWN"]
    assert not unknown, f"capabilities without a real availability: {unknown}"


def test_contract_count_matches_registry(contracts) -> None:
    from research_engine.capability_tools import build_capability_registry

    assert len(contracts) == len(build_capability_registry().available())


# --------------------------------------------------------------------------- #
# Domain packs
# --------------------------------------------------------------------------- #
def test_domain_packs_generated_from_real_registrations(catalogue) -> None:
    total = sum(d["implemented"] for d in catalogue["domains"])
    assert total == catalogue["capability_count"]


def test_every_capability_lands_in_exactly_one_domain(catalogue, contracts) -> None:
    seen: list[str] = []
    for pack in catalogue["domains"]:
        seen.extend(pack["capabilities"])
    assert sorted(seen) == sorted(contracts)


def test_empty_domains_are_reported_not_hidden(catalogue) -> None:
    empty = catalogue["domain_coverage"]["declared_but_empty"]
    assert isinstance(empty, list)
    for domain in empty:
        pack = next(d for d in catalogue["domains"] if d["domain"] == domain)
        assert pack["implemented"] == 0


def test_implemented_domains_are_real(contracts) -> None:
    by_domain: dict[str, int] = {}
    for c in contracts.values():
        by_domain[c["domain"]] = by_domain.get(c["domain"], 0) + 1
    assert by_domain.get("software_engineering", 0) >= 5
    assert by_domain.get("ai_ml_development", 0) >= 5


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_discovery_finds_project_capabilities_for_project_task() -> None:
    r = cc.discover_capabilities(
        "find unfinished functionality in the JARVIS project")
    names = [c["name"] for c in r["capabilities"]]
    assert "project.inspect" in names
    assert "project.search" in names


def test_discovery_prefers_low_risk_and_offline(contracts) -> None:
    r = cc.discover_capabilities("inspect the project structure")
    top = r["capabilities"][0]
    assert top["risk"] == RiskLevel.READ.value
    assert top["offline"] is True


def test_offline_mode_excludes_network_capabilities() -> None:
    r = cc.discover_capabilities("inspect a github repository", mode="offline")
    names = [c["name"] for c in r["capabilities"]]
    assert "github.inspect" not in names, \
        "network capability must not be offered offline"
    assert "files.read" in names, "offline mode must still offer local tools"


def test_online_mode_can_offer_network_capabilities() -> None:
    r = cc.discover_capabilities(
        "search the web for NVIDIA documentation", mode="online")
    assert r["capabilities"], "online mode should match web capabilities"


def test_discovery_never_invents_capabilities(contracts) -> None:
    r = cc.discover_capabilities("do absolutely anything at all",  # noqa: F841
                                 include_unavailable=True)
    for c in r["capabilities"]:
        assert c["name"] in contracts, f"invented capability {c['name']}"


def test_discovery_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        cc.discover_capabilities("anything", mode="telepathy")


def test_discovery_respects_max_results() -> None:
    r = cc.discover_capabilities("project code file test", max_results=3)
    assert len(r["capabilities"]) <= 3


# --------------------------------------------------------------------------- #
# Single-registry guarantee
# --------------------------------------------------------------------------- #
def test_contract_does_not_create_a_second_registry() -> None:
    src = (ROOT / "research_engine" / "capability_contract.py")
    if not src.is_file():
        src = Path(r"F:\AI\research_engine\capability_contract.py")
    text = src.read_text(encoding="utf-8")
    # It reads from ToolRegistry; it must not define a competing dispatch path.
    assert "class ToolRegistry" not in text
    assert "def authorize" not in text
    assert "subprocess" not in text
    assert "os.system" not in text


def test_discover_capability_is_registered_read_only() -> None:
    from research_engine.capability_tools import build_capability_registry

    by_name = {d["name"]: d for d in build_capability_registry().describe()}
    for cap in ("capability.discover", "capability.catalogue"):
        assert cap in by_name
        assert by_name[cap]["risk"] == RiskLevel.READ.value
        assert by_name[cap]["parameters"].get("type") == "object"


def test_discover_capability_executes() -> None:
    import asyncio
    import json

    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    res = asyncio.run(build_capability_registry().invoke(
        "capability.discover", {"task": "inspect the jarvis project"},
        ToolContext(request_id="d", user_id="u")))
    assert res.success is True
    data = json.loads(res.result)
    assert data["capabilities"]


def test_mode_coverage_reported(catalogue) -> None:
    coverage = catalogue["mode_coverage"]
    assert set(coverage) == set(cc.MODES)
    assert coverage["offline"], "offline mode must list real offline capabilities"
