"""Development environment setup script for Jarvis.

Verifies Python version, installs dependencies, configures pre-commit hooks,
and validates the repository structure.
"""

import subprocess
import sys
from pathlib import Path


REQUIRED_PYTHON = (3, 12)


def check_python():
    major, minor = sys.version_info[:2]
    if (major, minor) < REQUIRED_PYTHON:
        print(f"Error: Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required, found {major}.{minor}")
        sys.exit(1)
    print(f"Python {major}.{minor}.{sys.version_info[2]} OK")


def run(cmd: list[str], cwd: Path | None = None) -> bool:
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode == 0


def main():
    root = Path(__file__).parent.parent

    print("=" * 60)
    print("  Jarvis Development Setup")
    print("=" * 60)

    print("\n[1/5] Checking Python version...")
    check_python()

    print("\n[2/5] Installing dependencies...")
    reqs = root / "requirements.txt"
    if reqs.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(reqs)])
    else:
        print("  WARNING: requirements.txt not found")

    dev_reqs = root / "requirements-dev.txt"
    if dev_reqs.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(dev_reqs)])

    print("\n[3/5] Installing pre-commit hooks...")
    if run(["pre-commit", "install"], cwd=root):
        run(["pre-commit", "install", "--hook-type", "commit-msg"], cwd=root)

    print("\n[4/5] Validating repository structure...")
    run([sys.executable, "scripts/validate_repo.py"], cwd=root)

    print("\n[5/5] Running initial linting...")
    run(["ruff", "check", "infrastructure/", "performance/", "core/", "tests/"], cwd=root)

    print("\n" + "=" * 60)
    print("  Setup complete! Run 'make test' to verify.")
    print("=" * 60)


if __name__ == "__main__":
    main()
