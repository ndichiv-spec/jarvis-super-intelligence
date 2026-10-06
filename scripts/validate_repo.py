"""Repository structure validation and consistency checks."""

import argparse
import sys
from pathlib import Path


EXCLUDE_DIRS = {"__pycache__", ".venv", "venv", ".git", ".benchmarks",
                 "node_modules", ".idea", ".vscode", "logs", "coverage_html",
                 "uploads", "data"}

REQUIRED_DIRS = [
    "core",
    "infrastructure",
    "performance",
    "tests",
    "docs",
    "deployment",
    "frontend",
    "automation",
]

IGNORE_NO_INIT = {"drive_engine", "marketplace", "models", "monitoring",
                   "logs", "data", "uploads", "frontend", "automation"}

REQUIRED_FILES = [
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "MAINTAINERS.md",
    "SECURITY.md",
    "LICENSE",
    "pyproject.toml",
    "pytest.ini",
    ".coveragerc",
    ".editorconfig",
    ".pre-commit-config.yaml",
    ".gitignore",
    ".env.example",
]

DOCS_DIRS = [
    "docs/adr",
    "docs/guides",
]

INFRA_DIRS = [
    "infrastructure/config",
    "infrastructure/vault",
    "infrastructure/logsys",
    "infrastructure/health",
    "infrastructure/startup",
    "infrastructure/observability",
    "infrastructure/security",
    "infrastructure/resilience",
    "infrastructure/errors",
    "infrastructure/sandbox",
    "infrastructure/deploy",
    "infrastructure/knowledge",
    "infrastructure/plugins",
]

CI_FILES = [
    ".github/workflows/ci-cd.yml",
    ".github/workflows/deploy.yml",
    ".github/workflows/release.yml",
    ".github/workflows/codeql-analysis.yml",
    ".github/workflows/labeler.yml",
    ".github/dependabot.yml",
    ".github/CODEOWNERS",
]


def check_paths(paths: list[str], root: Path, label: str) -> list[str]:
    errors = []
    for p in paths:
        full = root / p
        if not full.exists():
            errors.append(f"Missing {label}: {p}")
    return errors


def check_init_files(root: Path) -> list[str]:
    errors = []
    for py_dir in root.iterdir():
        if py_dir.name in IGNORE_NO_INIT or py_dir.name.startswith(".") or py_dir.name in EXCLUDE_DIRS:
            continue
        if not py_dir.is_dir():
            continue
        py_files = list(py_dir.rglob("*.py"))
        has_init = any(f.name == "__init__.py" for f in py_dir.rglob("__init__.py")) or (py_dir / "__init__.py").exists()
        if py_files and not has_init:
            errors.append(f"Missing __init__.py in {py_dir}")
    return errors


def check_gitignore_entries(root: Path) -> list[str]:
    errors = []
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        for entry in [".env", "__pycache__", "*.pyc", ".venv", "venv", "logs/", "coverage/"]:
            if entry not in content:
                errors.append(f"Missing .gitignore entry: {entry}")
    return errors


def validate(root: Path) -> int:
    errors = []
    errors += check_paths(REQUIRED_DIRS, root, "directory")
    errors += check_paths(REQUIRED_FILES, root, "file")
    errors += check_paths(DOCS_DIRS, root, "docs directory")
    errors += check_paths(CI_FILES, root, "CI file")
    errors += check_init_files(root)
    errors += check_gitignore_entries(root)

    if errors:
        print(f"Repository validation failed ({len(errors)} issues):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("Repository structure is valid.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Validate repository structure")
    parser.add_argument("--root", default=".", help="Repository root directory")
    args = parser.parse_args()
    sys.exit(validate(Path(args.root).resolve()))


if __name__ == "__main__":
    main()
