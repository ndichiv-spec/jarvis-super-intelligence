import os
import subprocess
import sys
from pathlib import Path


def test_research_engine_package_is_inside_the_checkout():
    import research_engine

    checkout_root = Path(__file__).resolve().parents[1]
    package_path = Path(research_engine.__file__).resolve()

    assert package_path.is_relative_to(checkout_root / "research_engine")


def test_research_engine_exposes_the_existing_registry_and_contract_catalogue():
    from research_engine.capability_contract import build_contracts
    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolRegistry

    registry = build_capability_registry()
    contracts = build_contracts(registry, inventory={})

    assert isinstance(registry, ToolRegistry)
    assert "search_web" in registry.available()
    assert "search_web" in contracts


def test_project_tools_default_the_workspace_to_this_checkout():
    checkout_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("JARVIS_WORKSPACE_ROOT", None)
    environment.pop("JARVIS_PROJECT_ROOT", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from research_engine.project_tools import WORKSPACE_ROOT; print(WORKSPACE_ROOT)",
        ],
        cwd=checkout_root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert Path(result.stdout.strip()).resolve() == checkout_root
