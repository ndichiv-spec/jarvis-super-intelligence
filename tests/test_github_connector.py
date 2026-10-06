from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

import digital_clock


def require_git() -> str:
    git_available, git_path, _ = digital_clock.detect_git()
    if not git_available or git_path is None:
        pytest.skip("Git is not available in the test environment.")
    return git_path


def run_git(git_path: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [git_path, *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result


def test_probe_workspace_reports_non_repo(tmp_path: Path) -> None:
    git_path = require_git()

    probe = digital_clock.probe_workspace(tmp_path, git_path=git_path)

    assert probe.is_git_repo is False
    assert probe.origin_url is None
    assert probe.current_branch is None
    assert "not a Git repository" in probe.message


def test_connect_workspace_initializes_repo_and_sets_origin(tmp_path: Path) -> None:
    git_path = require_git()

    actions = digital_clock.connect_workspace(tmp_path, git_path=git_path)
    probe = digital_clock.probe_workspace(tmp_path, git_path=git_path)

    assert any("Initialized the current workspace as a Git repository" in action for action in actions)
    assert any("Configured remote 'origin'" in action for action in actions)
    assert probe.is_git_repo is True
    assert probe.current_branch == "main"
    assert probe.origin_url == digital_clock.REPO_CLONE_URL
    assert probe.origin_matches_target is True


def test_connect_workspace_updates_existing_origin(tmp_path: Path) -> None:
    git_path = require_git()
    run_git(git_path, ["init", "-b", "main"], cwd=tmp_path)
    run_git(git_path, ["remote", "add", "origin", "https://github.com/example/other.git"], cwd=tmp_path)

    actions = digital_clock.connect_workspace(tmp_path, git_path=git_path)
    probe = digital_clock.probe_workspace(tmp_path, git_path=git_path)

    assert any("Updated remote 'origin'" in action for action in actions)
    assert probe.origin_url == digital_clock.REPO_CLONE_URL
    assert probe.origin_matches_target is True


def test_build_report_includes_workspace_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        digital_clock,
        "probe_repo",
        lambda url=digital_clock.REPO_API_URL, token=None: digital_clock.RepoProbe(
            reachable=True,
            status_code=200,
            message="ok",
        ),
    )

    report = digital_clock.build_report(tmp_path / "clone-target", workspace_dir=tmp_path)

    assert report.workspace_probe.path == str(tmp_path.resolve())
    assert report.repo_probe.reachable is True
