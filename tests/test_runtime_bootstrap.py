import subprocess
import sys

from jarvis_runtime import (
    PROJECT_ROOT,
    SILVERWING_BACKEND_ROOT,
    WORKSPACE_ROOT,
    ensure_import_paths,
)


def test_runtime_paths_are_registered():
    ensure_import_paths()
    assert str(PROJECT_ROOT) in sys.path
    assert str(WORKSPACE_ROOT) in sys.path
    assert str(SILVERWING_BACKEND_ROOT) in sys.path


def test_entrypoints_share_application():
    import jarvis_api
    import start_jarvis
    import unified_jarvis_api

    assert start_jarvis.app is jarvis_api.app
    assert unified_jarvis_api.app is jarvis_api.app


def test_silverwing_subapp_loads_from_its_backend_root():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import jarvis_backend.main as jarvis_main; "
                "import sys; "
                "assert jarvis_main._silverwing_error is None; "
                "assert jarvis_main._silverwing_app is not None; "
                "print(Path(sys.modules['main'].__file__).resolve())"
            ),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert str((SILVERWING_BACKEND_ROOT / "main.py").resolve()) in result.stdout


def test_usage_serializes_all_token_counts():
    from providers.base import ProviderResponse, Usage

    usage = Usage(prompt_tokens=3, completion_tokens=2)
    assert usage.to_dict() == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    response = ProviderResponse(provider="test", model="test", usage=usage)
    assert response.to_dict()["usage"] == usage.to_dict()
