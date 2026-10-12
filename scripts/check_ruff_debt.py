"""Fail if changed Python files add Ruff findings relative to a base revision."""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pyproject.toml"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result


def changed_python_files(base: str, committed: bool) -> list[str]:
    diff_args = ["diff", "--name-only", "--diff-filter=ACMR"]
    diff_args.append(f"{base}...HEAD" if committed else base)
    diff_args.extend(["--", "*.py"])
    paths = set(git(*diff_args).stdout.decode().splitlines())
    if not committed:
        untracked = git("ls-files", "--others", "--exclude-standard", "--", "*.py")
        paths.update(untracked.stdout.decode().splitlines())
    return sorted(path for path in paths if path)


def changed_line_numbers(before: bytes, after: bytes) -> set[int]:
    """Return 1-based current-file lines that differ from the base revision."""
    before_lines = before.decode("utf-8", errors="replace").splitlines()
    after_lines = after.decode("utf-8", errors="replace").splitlines()
    unchanged: set[int] = set()
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    for block in matcher.get_matching_blocks():
        unchanged.update(range(block.b + 1, block.b + block.size + 1))
    return set(range(1, len(after_lines) + 1)) - unchanged


def ruff_findings(source: bytes, path: str) -> list[dict[str, object]]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format",
            "json",
            "--config",
            str(CONFIG),
            "--stdin-filename",
            path,
            "-",
        ],
        cwd=ROOT,
        input=source,
        capture_output=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return json.loads(result.stdout)


def base_source(base: str, path: str) -> bytes:
    result = git("show", f"{base}:{path}", check=False)
    return result.stdout if result.returncode == 0 else b""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base commit or ref to compare against")
    parser.add_argument(
        "--committed",
        action="store_true",
        help="Compare committed changes using the merge base with --base",
    )
    args = parser.parse_args()

    offenders: list[tuple[str, int, int]] = []
    for path in changed_python_files(args.base, args.committed):
        current_path = ROOT / path
        if not current_path.is_file():
            continue
        before_source = base_source(args.base, path)
        current_source = current_path.read_bytes()
        before = ruff_findings(before_source, path)
        after = ruff_findings(current_source, path)
        before_counts = Counter(item.get("code") for item in before)
        after_counts = Counter(item.get("code") for item in after)
        increases = {
            code: count - before_counts[code]
            for code, count in after_counts.items()
            if count > before_counts[code]
        }

        if any(item.get("code") == "invalid-syntax" for item in before):
            changed = changed_line_numbers(before_source, current_source)
            parse_error_increases = Counter(
                item.get("code")
                for item in after
                if item.get("location", {}).get("row") in changed
            )
            if parse_error_increases:
                offenders.append((path, ", ".join(sorted(parse_error_increases)), sum(parse_error_increases.values())))
        elif increases:
            description = ", ".join(
                f"{code} +{count}" for code, count in sorted(increases.items())
            )
            offenders.append((path, description, sum(increases.values())))

    if offenders:
        for path, rules, count in offenders:
            print(f"{path}: {count} additional Ruff finding(s): {rules}.")
        return 1

    print("Changed Python files do not increase their Ruff finding counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
