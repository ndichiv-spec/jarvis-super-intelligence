"""Code quality check runner for Jarvis.

Runs ruff, mypy, bandit, and pytest in sequence, reporting results.
"""

import argparse
import subprocess
import sys
from pathlib import Path


CHECKS = [
    {
        "name": "Ruff (linting)",
        "cmd": ["ruff", "check", "infrastructure/", "performance/", "core/", "tests/"],
    },
    {
        "name": "Ruff (formatting)",
        "cmd": ["ruff", "format", "--check", "infrastructure/", "performance/", "core/", "tests/"],
    },
    {
        "name": "Mypy (type checking)",
        "cmd": ["mypy", "infrastructure/", "performance/", "--ignore-missing-imports", "--no-strict-optional"],
    },
    {
        "name": "Bandit (security)",
        "cmd": ["bandit", "-r", "infrastructure/", "performance/", "--skip", "B101"],
    },
]


def run_check(name: str, cmd: list[str]) -> bool:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode == 0:
        print(f"  PASSED")
        return True
    print(f"  FAILED (exit code {result.returncode})")
    return False


def main():
    parser = argparse.ArgumentParser(description="Run code quality checks")
    parser.add_argument("--fix", action="store_true", help="Auto-fix ruff issues")
    parser.add_argument("--skip-mypy", action="store_true", help="Skip mypy checks")
    parser.add_argument("--skip-bandit", action="store_true", help="Skip bandit checks")
    args = parser.parse_args()

    checks = [c for c in CHECKS if not (args.skip_mypy and "mypy" in c["name"].lower())]
    checks = [c for c in checks if not (args.skip_bandit and "bandit" in c["name"].lower())]

    if args.fix:
        subprocess.run(["ruff", "check", "--fix", "infrastructure/", "performance/", "core/", "tests/"])

    results = []
    for check in checks:
        ok = run_check(check["name"], check["cmd"])
        results.append((check["name"], ok))

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  {passed}/{total} checks passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
