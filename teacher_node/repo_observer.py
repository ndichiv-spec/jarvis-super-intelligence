"""Repository observer for the Teacher Node (spec §17, §19).

Observes the git repository to extract learning signals from code changes:
  * New test files → potential new lesson or evaluation target.
  * Changed imports → new dependencies or provider integration.
  * File deletions → deprecated patterns or tech debt.
  * Configuration changes → environment or deployment signals.

All observations are sanitized before storage (spec §23).  The observer
never reads or stores file *contents* — only paths, diffs (sanitized), and
metadata.

If `git` is unavailable or the directory is not a git repo, the observer
gracefully reports ``unavailable`` — honesty over fabrication (spec §73).
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .sanitizer import Sanitizer


@dataclass
class RepoChange:
    """A single repository change observed in a sampling cycle."""

    id: str
    sha: str
    file_path: str
    change_type: str  # "added", "modified", "deleted", "renamed"
    category: str     # inferred: "test", "source", "config", "docs", "dependency"
    sanitized_diff: str  # diff with secrets/PII redacted
    tags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class RepoObserver:
    """Observes git repository changes for learning signals (spec §17).

    Parameters
    ----------
    repo_path
        Path to the git repository root.
    sanitizer
        :class:`Sanitizer` to redact secrets from diffs before storage.
    """

    def __init__(
        self,
        repo_path: str,
        sanitizer: Optional[Sanitizer] = None,
    ) -> None:
        self._repo_path = os.path.abspath(repo_path)
        self._sanitizer = sanitizer or Sanitizer()
        self._last_seen_sha: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Git availability
    # ------------------------------------------------------------------ #
    @property
    def is_available(self) -> bool:
        """True iff ``git`` is present AND the repo path is a git repo."""
        if not self._has_git:
            return False
        result = self._run(["rev-parse", "--is-inside-work-tree"])
        return result is not None and result.strip() == "true"

    @property
    def _has_git(self) -> bool:
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True, timeout=5, check=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _run(self, args: list[str], *, timeout: int = 10) -> Optional[str]:
        """Run a git command in the repo path. Returns stdout or None on error."""
        if not self._has_git:
            return None
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            return result.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

    # ------------------------------------------------------------------ #
    # Sampling
    # ------------------------------------------------------------------ #
    @property
    def current_sha(self) -> Optional[str]:
        """Return the current HEAD commit SHA, or None if unavailable."""
        return self._run(["rev-parse", "HEAD"])

    def get_changes_since(
        self,
        since_sha: Optional[str] = None,
        max_files: int = 50,
    ) -> list[RepoChange]:
        """Return changes since ``since_sha`` (or since last observation).

        Returns sanitized RepoChange records — file paths and diffs with
        secrets redacted.
        """
        since_sha = since_sha or self._last_seen_sha
        self._last_seen_sha = self.current_sha

        if since_sha is None:
            # No prior state — get the full diff of the working tree vs HEAD.
            diff_output = self._run(["diff", "HEAD", "--", "."]) or ""
        else:
            diff_output = self._run(["diff", since_sha, "HEAD", "--", "."]) or ""

        if not diff_output:
            return []

        changes = self._parse_diff(diff_output)
        # Update last seen.
        self._last_seen_sha = self.current_sha
        return changes[:max_files]

    def _parse_diff(self, diff_output: str) -> list[RepoChange]:
        """Parse ``git diff`` output into RepoChange records (sanitized)."""
        changes: list[RepoChange] = []
        # git diff format: diff --git a/path b/path
        #                  new file mode ...
        #                  index ...
        #                  --- a/path
        #                  +++ b/path
        #                  @@ ... @@
        #                  +content / -content
        current_path = ""
        current_change_type = "modified"
        current_diff_lines: list[str] = []

        for line in diff_output.splitlines():
            if line.startswith("diff --git"):
                # Save previous file.
                if current_path:
                    changes.append(self._make_change(
                        current_path, current_change_type, "\n".join(current_diff_lines)
                    ))
                # Parse new file.
                parts = line.split()
                if len(parts) >= 4:
                    current_path = parts[3].lstrip("b/") if len(parts) > 3 else ""
                current_change_type = "modified"
                current_diff_lines = []
            elif line.startswith("new file"):
                current_change_type = "added"
            elif line.startswith("deleted file"):
                current_change_type = "deleted"
            elif line.startswith("rename from"):
                current_change_type = "renamed"
            elif line.startswith("---") or line.startswith("+++"):
                continue  # path line
            elif line.startswith("@@") or line.startswith("index"):
                continue
            else:
                if line.startswith("+") or line.startswith("-"):
                    current_diff_lines.append(line)

        # Don't forget the last file.
        if current_path:
            changes.append(self._make_change(
                current_path, current_change_type, "\n".join(current_diff_lines)
            ))

        return changes

    def _make_change(self, path: str, change_type: str, raw_diff: str) -> RepoChange:
        """Create a sanitized RepoChange from raw diff data."""
        sanitized_diff = self._sanitizer.sanitize(raw_diff)
        category = self._categorize(path)
        tags = self._tags_for(path, category, change_type)
        return RepoChange(
            id=str(uuid.uuid4()),
            sha=self._last_seen_sha or "unknown",
            file_path=path,
            change_type=change_type,
            category=category,
            sanitized_diff=sanitized_diff,
            tags=tags,
        )

    @staticmethod
    def _categorize(path: str) -> str:
        """Infer file category from path."""
        lower = path.lower()
        ext = os.path.splitext(lower)[1]
        if ext in (".py", ".kt", ".java", ".js", ".ts", ".go", ".rs"):
            if "/test" in lower or lower.endswith("_test.py") or lower.endswith("test.kt"):
                return "test"
            if "/src/" in lower or "/main/" in lower:
                return "source"
            return "source"
        if ext in (".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".env") or lower.endswith(".env"):
            return "config"
        if ext in (".md", ".rst", ".txt"):
            return "docs"
        if ext in (".lock", ".csproj", ".sln") or lower in ("requirements.txt", "pyproject.toml"):
            return "dependency"
        return "other"

    @staticmethod
    def _tags_for(path: str, category: str, change_type: str) -> list[str]:
        tags = [category, change_type]
        lower = path.lower()
        if "identity" in lower:
            tags.append("identity")
        if "provider" in lower or "providers" in lower:
            tags.append("provider")
        if "teacher" in lower or "learning" in lower:
            tags.append("teacher")
        if "test" in lower:
            tags.append("test")
        if change_type == "added":
            tags.append("new-file")
        if change_type == "deleted":
            tags.append("removed")
        return tags

    # ------------------------------------------------------------------ #
    # Knowledge integration
    # ------------------------------------------------------------------ #
    def observe_to_knowledge(self, knowledge: Any, *, since_sha: Optional[str] = None) -> int:
        """Record all new changes into the knowledge store. Returns count."""
        changes = self.get_changes_since(since_sha)
        for change in changes:
            knowledge.add(
                category="repo",
                key=f"repo_change_{change.id}",
                value={
                    "file_path": change.file_path,
                    "change_type": change.change_type,
                    "category": change.category,
                    "tags": change.tags,
                    "sanitized_diff_length": len(change.sanitized_diff),
                },
                confidence=1.0,
                tags=["repo", change.category, change.change_type] + change.tags,
                source_ref="repo_observer",
            )
        return len(changes)
