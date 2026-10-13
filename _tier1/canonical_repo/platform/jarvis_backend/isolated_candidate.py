"""Prepare and evaluate code candidates without changing the active checkout."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

_SNAPSHOT_ROOTS = (
    "platform",
    "research_engine",
    "jarvis_brain",
    "infrastructure",
    "providers",
    "brain_runtime",
    "model_lifecycle",
    "backend",
    "tests",
    "src",
)
_SNAPSHOT_FILES = ("jarvis_runtime.py", "pytest.ini", "pyproject.toml", "conftest.py")
_IGNORED_DIRECTORIES = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
    "node_modules", "venv", ".next", "frontend", "jarvis_data", "jarvis_uploads",
    "models", "training", "checkpoints", "notebooks", "silverwing-backend",
}
_IGNORED_FILES = {
    ".env", ".env.local", "credentials.json", "service-account.json",
}
_PROTECTED_FILES = {
    ".env",
    "platform/jarvis_backend/core.py",
    "platform/jarvis_backend/db.py",
    "platform/jarvis_backend/main.py",
    "platform/jarvis_backend/isolated_candidate.py",
    "platform/jarvis_backend/routers/improvements.py",
    "platform/infrastructure/promotion_gate.py",
    "platform/infrastructure/provider_registry.py",
    "platform/infrastructure/artifact_registry.py",
    "platform/infrastructure/audit_events.py",
    "research_engine/tool_registry.py",
    "jarvis_brain/plan_validator.py",
}
_PROTECTED_PREFIXES = (
    "providers/",
    "platform/providers/",
    "identity/",
    "platform/identity/",
)
_SECRET_VALUE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|"
    r"nvapi-[A-Za-z0-9_-]{20,})\b"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"
)
_SECRET_OUTPUT = (
    _SECRET_ASSIGNMENT,
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{16,}"),
    _SECRET_VALUE,
)
_CANDIDATE_ID = re.compile(r"^candidate-[a-f0-9]{12}-[a-f0-9]{8}$")
_MAX_CHANGED_FILES = 5
_MAX_FILE_BYTES = 200_000
_MAX_TOTAL_BYTES = 500_000
_MAX_TEST_TARGETS = 5
_MAX_TEST_SECONDS = 180
_MAX_OUTPUT_CHARS = 20_000


class IsolatedCandidateRunner:
    """Create a versioned candidate and run fixed pytest invocations on a copy.

    This isolates candidate files and test databases from the active checkout.
    It is not an OS-level sandbox; candidate tests still run with this process's
    operating-system permissions and must only be used for trusted project code.
    """

    def __init__(
        self,
        project_root: Path,
        artifact_root: Path,
        timeout_seconds: int = 120,
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.artifact_root = Path(artifact_root).resolve()
        if not self.project_root.is_dir():
            raise ValueError("project_root must be an existing directory")
        if not 1 <= timeout_seconds <= _MAX_TEST_SECONDS:
            raise ValueError(f"timeout_seconds must be between 1 and {_MAX_TEST_SECONDS}")
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        owner_id: str,
        problem: str,
        evidence: str,
        proposed_change: str,
        file_changes: dict[str, str],
        test_targets: list[str],
    ) -> dict[str, Any]:
        """Reproduce a test failure, evaluate proposed source changes, and persist evidence."""
        self._validate_request(
            owner_id, problem, evidence, proposed_change, file_changes, test_targets,
        )
        normalized = {
            self._normalize_relative_path(name): content
            for name, content in file_changes.items()
        }
        patch_digest = hashlib.sha256()
        for name, content in sorted(normalized.items()):
            patch_digest.update(name.encode("utf-8"))
            patch_digest.update(b"\0")
            patch_digest.update(content.encode("utf-8"))
            patch_digest.update(b"\0")
        candidate_id = f"candidate-{patch_digest.hexdigest()[:12]}-{uuid.uuid4().hex[:8]}"
        owner_key = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:24]
        candidate_dir = self.artifact_root / owner_key / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        with tempfile.TemporaryDirectory(prefix="jarvis-candidate-workspace-") as workspace_dir:
            workspace = Path(workspace_dir)
            self._snapshot_project(workspace)

            original_contents: dict[str, str] = {}
            for relative in normalized:
                source = self.project_root / Path(relative)
                original_contents[relative] = source.read_text(encoding="utf-8")
            diff = self._build_diff(original_contents, normalized)
            with tempfile.TemporaryDirectory(prefix="jarvis-candidate-tests-") as temp_dir:
                db_dir = Path(temp_dir)
                baseline = self._run_tests(
                    workspace,
                    test_targets,
                    db_dir / "baseline.sqlite",
                    db_dir / "baseline.xml",
                )
                for relative, content in normalized.items():
                    destination = workspace / Path(relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(content, encoding="utf-8", newline="")
                candidate = self._run_tests(
                    workspace,
                    test_targets,
                    db_dir / "candidate.sqlite",
                    db_dir / "candidate.xml",
                )

            baseline_failed = (baseline["failed_tests"] or 0) > 0
            candidate_passed = candidate["exit_code"] == 0
            timed_out = baseline["timed_out"] or candidate["timed_out"]
            if timed_out:
                status = "evaluation_timed_out"
            elif baseline["failed_tests"] is None or baseline["error_tests"] is None:
                status = "baseline_evaluation_error"
            elif baseline["error_tests"] > 0:
                status = "baseline_evaluation_error"
            elif not baseline_failed:
                status = "baseline_failure_not_reproduced"
            elif candidate["error_tests"] is None or candidate["error_tests"] > 0:
                status = "candidate_evaluation_error"
            elif candidate_failed := not candidate_passed:
                status = "candidate_failed"
            elif baseline_failed and candidate_passed:
                status = "ready_for_owner_review"
            else:
                status = "candidate_failed"

        candidate_files = candidate_dir / "files"
        for relative, content in normalized.items():
            destination = candidate_files / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="")

        report = {
            "candidate_id": candidate_id,
            "candidate_version": patch_digest.hexdigest(),
            "owner_ref": owner_key,
            "created_at": datetime.now(UTC).isoformat(),
            "problem": problem.strip(),
            "failure_evidence": evidence.strip(),
            "proposed_change": proposed_change.strip(),
            "changed_files": sorted(normalized),
            "diff": self._redact_output(diff)[:_MAX_OUTPUT_CHARS],
            "tests": {
                "targets": test_targets,
                "baseline": baseline,
                "candidate": candidate,
                "reproducible_failure": baseline_failed,
                "candidate_passed": candidate_passed,
            },
            "status": status,
            "promotion": {
                "recommendation": (
                    "owner_review_required"
                    if status == "ready_for_owner_review"
                    else "do_not_promote"
                ),
                "approval_required": True,
                "automatic_promotion": False,
                "production_changed": False,
                "rollback_plan": (
                    "No production change was made; discard this candidate artifact "
                    "to return to the unchanged active version."
                ),
            },
            "execution_boundary": {
                "workspace": "isolated filesystem copy",
                "os_sandbox": False,
                "network_isolation": False,
                "active_checkout_modified": False,
            },
            "artifact_path": str(candidate_dir),
        }
        self._write_json(candidate_dir / "report.json", report)
        return report

    def load_report(self, owner_id: str, candidate_id: str) -> dict[str, Any] | None:
        """Load a report only from the authenticated owner's candidate directory."""
        if not _CANDIDATE_ID.fullmatch(candidate_id):
            return None
        owner_key = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:24]
        report_path = self.artifact_root / owner_key / candidate_id / "report.json"
        if not report_path.is_file():
            return None
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("owner_ref") != owner_key or report.get("candidate_id") != candidate_id:
            return None
        return report

    def _validate_request(
        self,
        owner_id: str,
        problem: str,
        evidence: str,
        proposed_change: str,
        file_changes: dict[str, str],
        test_targets: list[str],
    ) -> None:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id is required")
        for name, value, limit in (
            ("problem", problem, 2_000),
            ("evidence", evidence, 8_000),
            ("proposed_change", proposed_change, 2_000),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(f"{name} must be non-empty and at most {limit} characters")
            if _SECRET_VALUE.search(value) or _SECRET_ASSIGNMENT.search(value):
                raise ValueError(f"{name} must not contain credential-shaped values")
        if not isinstance(file_changes, dict) or not 1 <= len(file_changes) <= _MAX_CHANGED_FILES:
            raise ValueError(f"file_changes must contain 1 to {_MAX_CHANGED_FILES} files")
        total_size = 0
        for relative, content in file_changes.items():
            normalized = self._normalize_relative_path(relative)
            self._validate_source_target(normalized)
            if not isinstance(content, str):
                raise ValueError(f"candidate content for {relative} must be text")
            encoded = content.encode("utf-8")
            total_size += len(encoded)
            if len(encoded) > _MAX_FILE_BYTES:
                raise ValueError(f"candidate file {relative} exceeds {_MAX_FILE_BYTES} bytes")
            if _SECRET_VALUE.search(content) or _SECRET_ASSIGNMENT.search(content):
                raise ValueError(f"candidate file {relative} contains a credential-shaped value")
        if total_size > _MAX_TOTAL_BYTES:
            raise ValueError(f"candidate changes exceed {_MAX_TOTAL_BYTES} bytes")
        if not isinstance(test_targets, list) or not 1 <= len(test_targets) <= _MAX_TEST_TARGETS:
            raise ValueError(f"test_targets must contain 1 to {_MAX_TEST_TARGETS} test files")
        for target in test_targets:
            self._validate_test_target(target)

    @staticmethod
    def _normalize_relative_path(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("file paths must be non-empty strings")
        candidate = value.replace("\\", "/")
        path = PurePosixPath(candidate)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"path must be relative and cannot traverse directories: {value}")
        if ":" in candidate or "\x00" in candidate:
            raise ValueError(f"invalid candidate path: {value}")
        return path.as_posix()

    def _validate_source_target(self, relative: str) -> None:
        path = PurePosixPath(relative)
        lowered = relative.casefold()
        if path.suffix != ".py" or "tests" in {part.casefold() for part in path.parts}:
            raise ValueError("candidate changes are limited to existing Python source files")
        if lowered in _PROTECTED_FILES or any(
            lowered.startswith(prefix) for prefix in _PROTECTED_PREFIXES
        ):
            raise ValueError(f"candidate changes to protected code are not allowed: {relative}")
        allowed_roots = {
            "platform", "research_engine", "jarvis_brain", "infrastructure",
            "brain_runtime", "model_lifecycle", "backend", "src",
        }
        if not path.parts or path.parts[0] not in allowed_roots:
            raise ValueError(f"candidate path is outside supported source roots: {relative}")
        source = self.project_root.joinpath(*path.parts)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"candidate target must be an existing regular source file: {relative}")
        if not source.resolve(strict=True).is_relative_to(self.project_root):
            raise ValueError(f"candidate target escapes the project root: {relative}")
        self._reject_symlink_components(source, relative)

    def _validate_test_target(self, target: str) -> None:
        relative = self._normalize_relative_path(target)
        path = PurePosixPath(relative)
        parts = tuple(part.casefold() for part in path.parts)
        supported_tests_root = (
            parts[0] == "tests"
            or (len(parts) > 1 and parts[0] == "platform" and parts[1] == "tests")
        )
        if path.suffix != ".py" or not supported_tests_root:
            raise ValueError("tests must be existing Python files under a tests directory")
        source = self.project_root.joinpath(*path.parts)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"test target does not exist as a regular file: {target}")
        if not source.resolve(strict=True).is_relative_to(self.project_root):
            raise ValueError(f"test target escapes the project root: {target}")
        self._reject_symlink_components(source, target)

    def _reject_symlink_components(self, source: Path, relative: str) -> None:
        current = source
        while current != self.project_root:
            if current.is_symlink():
                raise ValueError(f"path cannot traverse symbolic links: {relative}")
            current = current.parent

    def _snapshot_project(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        for name in _SNAPSHOT_ROOTS:
            source = self.project_root / name
            if source.is_dir() and not source.is_symlink():
                self._copy_tree(source, workspace / name)
        for name in _SNAPSHOT_FILES:
            source = self.project_root / name
            if source.is_file() and not source.is_symlink():
                shutil.copy2(source, workspace / name)

    @classmethod
    def _copy_tree(cls, source: Path, destination: Path) -> None:
        for current, directories, files in os.walk(source, topdown=True, followlinks=False):
            current_path = Path(current)
            relative = current_path.relative_to(source)
            target_dir = destination / relative
            target_dir.mkdir(parents=True, exist_ok=True)
            directories[:] = [
                name for name in directories
                if name not in _IGNORED_DIRECTORIES
                and not (current_path / name).is_symlink()
            ]
            for name in files:
                item = current_path / name
                lowered_name = name.casefold()
                if (
                    item.is_symlink()
                    or lowered_name in _IGNORED_FILES
                    or lowered_name.startswith(".env.")
                    or item.suffix.casefold() in {
                        ".db", ".sqlite", ".sqlite3", ".pyc", ".pem", ".p12",
                    }
                ):
                    continue
                target = target_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    def _run_tests(
        self,
        workspace: Path,
        test_targets: list[str],
        database_path: Path,
        junit_path: Path,
    ) -> dict[str, Any]:
        env = {
            key: value for key, value in os.environ.items()
            if not re.search(r"(?:API.?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)", key, re.I)
        }
        env.update({
            "JARVIS_TEST_DB_PATH": str(database_path),
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "JARVIS_TEST_MODE": "1",
            "JARVIS_BROWSER_SEARCH_ENABLED": "0",
            "JARVIS_LIVE_IMAGE_OPT_IN": "0",
            "JARVIS_LIVE_RESEARCH_OPT_IN": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        command = [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            f"--junitxml={junit_path}",
            *test_targets,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
            output = self._redact_output(
                (completed.stdout or "") + (completed.stderr or ""),
            )
            test_counts = self._read_junit_counts(junit_path)
            return {
                "exit_code": completed.returncode,
                "passed": completed.returncode == 0,
                "timed_out": False,
                "output": output[-_MAX_OUTPUT_CHARS:],
                **test_counts,
            }
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            output = self._redact_output(stdout + stderr)
            return {
                "exit_code": None,
                "passed": False,
                "timed_out": True,
                "output": output[-_MAX_OUTPUT_CHARS:],
                "failed_tests": None,
                "error_tests": None,
            }

    @staticmethod
    def _read_junit_counts(path: Path) -> dict[str, int | None]:
        if not path.is_file():
            return {"failed_tests": None, "error_tests": None}
        root = ElementTree.parse(path).getroot()
        test_cases = root.iter("testcase")
        failures = 0
        errors = 0
        for test_case in test_cases:
            failures += test_case.find("failure") is not None
            errors += test_case.find("error") is not None
        return {"failed_tests": failures, "error_tests": errors}

    @staticmethod
    def _redact_output(output: str) -> str:
        for pattern in _SECRET_OUTPUT:
            output = pattern.sub("[REDACTED]", output)
        return output

    @staticmethod
    def _build_diff(before: dict[str, str], after: dict[str, str]) -> str:
        chunks = []
        for name in sorted(before):
            chunks.extend(difflib.unified_diff(
                before[name].splitlines(keepends=True),
                after[name].splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            ))
        return "".join(chunks)

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)


__all__ = ["IsolatedCandidateRunner"]
