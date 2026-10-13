from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_backend.isolated_candidate import IsolatedCandidateRunner


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "calculator.py").write_text(
        "def add(left, right):\n    return left - right\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    return root


def _run(root: Path, artifacts: Path, new_source: str) -> dict:
    runner = IsolatedCandidateRunner(root, artifacts, timeout_seconds=120)
    return runner.run(
        owner_id="creator-1",
        problem="Addition regression fails.",
        evidence="Reproduction: tests/test_calculator.py::test_add expected 5, got -1.",
        proposed_change="Use addition instead of subtraction.",
        file_changes={"src/calculator.py": new_source},
        test_targets=["tests/test_calculator.py"],
    )


def test_failing_test_is_reproduced_and_fixed_in_persisted_candidate(tmp_path):
    root = _project(tmp_path)
    report = _run(
        root,
        tmp_path / "artifacts",
        "def add(left, right):\n    return left + right\n",
    )

    assert report["tests"]["baseline"]["passed"] is False
    assert report["tests"]["candidate"]["passed"] is True
    assert report["tests"]["reproducible_failure"] is True
    assert report["status"] == "ready_for_owner_review"
    assert report["promotion"]["approval_required"] is True
    assert report["promotion"]["automatic_promotion"] is False
    assert report["promotion"]["production_changed"] is False
    assert report["execution_boundary"]["os_sandbox"] is False
    assert (root / "src" / "calculator.py").read_text(encoding="utf-8").endswith(
        "return left - right\n"
    )

    runner = IsolatedCandidateRunner(root, tmp_path / "artifacts", timeout_seconds=120)
    assert runner.load_report("creator-1", report["candidate_id"]) == report
    assert runner.load_report("another-owner", report["candidate_id"]) is None
    candidate_copy = Path(report["artifact_path"]) / "files" / "src" / "calculator.py"
    assert candidate_copy.read_text(encoding="utf-8").endswith("return left + right\n")
    assert (Path(report["artifact_path"]) / "report.json").is_file()


def test_candidate_is_not_recommended_when_failure_was_not_reproduced(tmp_path):
    root = _project(tmp_path)
    (root / "src" / "calculator.py").write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )

    report = _run(
        root,
        tmp_path / "artifacts",
        "def add(left, right):\n    return left + right\n",
    )

    assert report["tests"]["baseline"]["passed"] is True
    assert report["tests"]["candidate"]["passed"] is True
    assert report["status"] == "baseline_failure_not_reproduced"
    assert report["promotion"]["recommendation"] == "do_not_promote"


@pytest.mark.parametrize(
    "changes",
    [
        {"tests/test_calculator.py": "def test_nothing():\n    pass\n"},
        {"platform/jarvis_backend/core.py": "def unsafe():\n    pass\n"},
        {"src/../../outside.py": "def unsafe():\n    pass\n"},
        {"src/calculator.py": "API_KEY = 'sk-" + "a" * 24 + "'\n"},
    ],
)
def test_unsafe_candidate_changes_are_rejected(tmp_path, changes):
    root = _project(tmp_path)
    runner = IsolatedCandidateRunner(root, tmp_path / "artifacts", timeout_seconds=120)

    with pytest.raises(ValueError):
        runner.run(
            owner_id="creator-1",
            problem="A reproduced issue.",
            evidence="A test failed.",
            proposed_change="Change source safely.",
            file_changes=changes,
            test_targets=["tests/test_calculator.py"],
        )


def test_credential_shaped_evidence_is_rejected(tmp_path):
    root = _project(tmp_path)
    runner = IsolatedCandidateRunner(root, tmp_path / "artifacts", timeout_seconds=20)

    with pytest.raises(ValueError, match="credential-shaped"):
        runner.run(
            owner_id="creator-1",
            problem="A reproduced issue.",
            evidence="token=private-value",
            proposed_change="Change the calculation.",
            file_changes={"src/calculator.py": "def add(a, b): return a + b\n"},
            test_targets=["tests/test_calculator.py"],
        )


def test_candidate_test_selector_must_be_existing_test_file(tmp_path):
    root = _project(tmp_path)
    runner = IsolatedCandidateRunner(root, tmp_path / "artifacts", timeout_seconds=20)

    with pytest.raises(ValueError, match="does not exist"):
        runner.run(
            owner_id="creator-1",
            problem="A reproduced issue.",
            evidence="A test failed.",
            proposed_change="Change source safely.",
            file_changes={"src/calculator.py": "def add(a, b):\n    return a + b\n"},
            test_targets=["tests/test_missing.py"],
        )


def test_code_candidate_api_requires_admin_authentication(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from jarvis_backend.core import get_current_user
    from jarvis_backend.main import app

    monkeypatch.setenv("JARVIS_CANDIDATE_ROOT", str(tmp_path / "artifacts"))
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "regular-user",
        "email": "user@example.invalid",
        "roles": ["user"],
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/improvements/code-candidates",
                json={
                    "problem": "Failure.",
                    "evidence": "A test failed.",
                    "proposed_change": "Fix the regression.",
                    "file_changes": {"src/calculator.py": "def add(a, b): return a + b\n"},
                    "test_targets": ["tests/test_calculator.py"],
                },
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_authenticated_admin_can_submit_and_read_owner_scoped_candidate(
    tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient

    from jarvis_backend.core import get_current_user
    from jarvis_backend.main import app
    from jarvis_backend.routers import improvements

    root = _project(tmp_path)
    runner = IsolatedCandidateRunner(root, tmp_path / "artifacts", timeout_seconds=120)
    monkeypatch.setattr(improvements, "_candidate_runner", lambda: runner)
    monkeypatch.setattr(improvements, "_audit_system_action", lambda **kwargs: None)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "creator-1",
        "email": "creator@example.invalid",
        "roles": ["admin"],
    }
    payload = {
        "problem": "Addition regression fails.",
        "evidence": "The selected pytest target reproduces the failure.",
        "proposed_change": "Use addition instead of subtraction.",
        "file_changes": {
            "src/calculator.py": "def add(left, right):\n    return left + right\n",
        },
        "test_targets": ["tests/test_calculator.py"],
    }
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/improvements/code-candidates", json=payload,
            )
            assert created.status_code == 200, created.text
            candidate_id = created.json()["candidate_id"]
            fetched = client.get(
                f"/api/v1/improvements/code-candidates/{candidate_id}",
            )
            assert fetched.status_code == 200
            assert fetched.json()["tests"]["baseline"]["passed"] is False
            assert fetched.json()["tests"]["candidate"]["passed"] is True

            app.dependency_overrides[get_current_user] = lambda: {
                "id": "different-admin",
                "email": "other@example.invalid",
                "roles": ["admin"],
            }
            hidden = client.get(
                f"/api/v1/improvements/code-candidates/{candidate_id}",
            )
            assert hidden.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
