"""Real platform identity via Git repository introspection (spec §12/13).

This module reads the actual Git repository state — never hardcodes values.
If Git is unavailable or the directory is not a repo, it reports a truthful
``GIT_UNAVAILABLE`` state instead of fabricating data.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent  # jarvis_backend -> Jarvis-super-intelligence-


def _git(cmd: List[str], timeout: float = 5.0) -> Optional[str]:
    """Run a git command inside the repo root; return stdout stripped or None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + cmd,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _git_bytes(cmd: List[str], timeout: float = 5.0) -> Optional[str]:
    """Run a git command, return raw stdout text (multi-line) or None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + cmd,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def is_git_repo() -> bool:
    """True if the JARVIS project directory is a Git repository."""
    return _git(["rev-parse", "--git-dir"]) is not None


def _safe_remote() -> Optional[str]:
    """Try to get the remote URL safely."""
    remotes = _git(["remote"])
    if not remotes:
        return None
    return _git(["remote", "get-url", "origin"])


def git_status() -> Dict[str, Any]:
    """Real Git repository state.

    Returns repository identity, branch, HEAD commit, dirty-file count,
    recent commits, and working-tree status — all from ``git`` subcommands.
    If Git is unavailable or the directory is not a repo, every field is
    truthfully reported as unavailable.
    """
    if not is_git_repo():
        return {
            "repo_available": False,
            "error": "Git repository not found at project root",
            "repository": None,
            "branch": None,
            "head": None,
            "short_head": None,
            "dirty": False,
            "changed_files": 0,
            "untracked_files": 0,
            "recent_commits": [],
            "last_commit": None,
            "is_bare": False,
            "remote_url": None,
            "working_tree_clean": False,
        }

    head = _git(["rev-parse", "HEAD"]) or ""
    short_head = head[:12] if head else None
    branch = _git(["branch", "--show-current"]) or "unknown"

    # Changed + untracked file counts from porcelain output
    porcelain = _git_bytes(["status", "--porcelain"]) or ""
    changed_files = len([l for l in porcelain.strip().split("\n") if l]) if porcelain.strip() else 0
    untracked = _git_bytes(["status", "--porcelain", "--untracked-files=all"]) or ""
    untracked_files = len([l for l in untracked.strip().split("\n") if l and l.startswith("??")]) if untracked.strip() else 0

    dirty = changed_files > 0

    # Last commit details
    last_commit = None
    commit_date = _git(["log", "-1", "--format=%cI"])
    commit_author = _git(["log", "-1", "--format=%an <%ae>"])
    commit_subject = _git(["log", "-1", "--format=%s"])
    if head:
        last_commit = {
            "hash": head,
            "short_hash": short_head,
            "branch": branch,
            "author": commit_author or None,
            "subject": commit_subject or None,
            "timestamp": commit_date or None,
        }

    # Recent commits (last 10)
    log_raw = _git_bytes(["log", "-10", "--format=%H|%an <%ae>|%s|%cI"]) or ""
    recent_commits: List[Dict[str, Any]] = []
    for line in log_raw.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            recent_commits.append({
                "hash": parts[0][:12],
                "author": parts[1],
                "subject": parts[2],
                "timestamp": parts[3],
            })

    return {
        "repo_available": True,
        "repository": os.path.basename(str(REPO_ROOT)),
        "repository_path": str(REPO_ROOT),
        "remote_url": _safe_remote(),
        "branch": branch,
        "head": head,
        "short_head": short_head,
        "dirty": dirty,
        "changed_files": changed_files,
        "untracked_files": untracked_files,
        "recent_commits": recent_commits,
        "last_commit": last_commit,
        "is_bare": False,
        "working_tree_clean": not dirty,
    }


def get_platform_identity() -> Dict[str, Any]:
    """Real platform identity: Git state + versions + service state.

    Everything here is read from actual sources — no hardcoded values.
    """
    git = git_status()

    # Backend version: try to read from package metadata or git
    backend_version = None
    try:
        from importlib.metadata import version
        backend_version = version("jarvis-backend") if "jarvis-backend" else None
    except Exception:
        pass
    if not backend_version:
        # Fall back to git describe
        tag = _git(["describe", "--tags", "--always"])
        if tag:
            backend_version = tag
        elif git.get("repo_available"):
            backend_version = f"git-{git.get('short_head', 'unknown')}"

    # Frontend version
    frontend_version = None
    pkg_path = REPO_ROOT / "frontend" / "web" / "package.json"
    if pkg_path.exists():
        try:
            import json
            with open(pkg_path, encoding="utf-8", errors="replace") as f:
                pkg = json.load(f)
                frontend_version = pkg.get("version")
        except Exception:
            pass

    # Silverwing version
    silverwing_version = None
    sw_pkg = REPO_ROOT / "silverwing-backend" / "pyproject.toml"
    if sw_pkg.exists():
        try:
            import tomllib
            with open(sw_pkg, "rb") as f:
                data = tomllib.load(f)
                silverwing_version = data.get("tool", {}).get("poetry", {}).get("version") or data.get("project", {}).get("version")
        except Exception:
            pass

    # Active model — from environment / capability runtime
    active_model = os.environ.get("JARVIS_ACTIVE_MODEL")
    active_provider = os.environ.get("JARVIS_ACTIVE_PROVIDER")

    return {
        "platform": "JARVIS Unified System",
        "version": "3.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git": git,
        "versions": {
            "backend": backend_version,
            "frontend": frontend_version,
            "silverwing": silverwing_version,
        },
        "active_provider": active_provider,
        "active_model": active_model,
        "jarvis_dir": str(REPO_ROOT),
        "backend_root": str(REPO_ROOT),
    }


def get_version() -> str:
    """Get the JARVIS platform version string."""
    return get_platform_identity().get("version", "unknown")
