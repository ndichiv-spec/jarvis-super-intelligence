"""Version management utility for Jarvis.

Updates the canonical version in pyproject.toml and syncs
version references in config files.
"""

import argparse
import re
import sys
from pathlib import Path


VERSION_FILES = {
    "pyproject.toml": [
        (r'^version = ".*"', 'version = "{version}"'),
    ],
    "infrastructure/config/settings.py": [
        (r'app_version: str = ".*"', 'app_version: str = "{version}"'),
    ],
    "core/config/settings.py": [
        (r'version: str = ".*"', 'version: str = "{version}"'),
    ],
}


def read_version(project_file: Path) -> str | None:
    """Read the current version from pyproject.toml."""
    content = project_file.read_text()
    match = re.search(r'^version = "(.*)"', content, re.MULTILINE)
    return match.group(1) if match else None


def write_version(version: str, dry_run: bool = False) -> list[str]:
    """Write version to all configured files."""
    updated = []
    for filepath, patterns in VERSION_FILES.items():
        path = Path(filepath)
        if not path.exists():
            updated.append(f"SKIP (not found): {filepath}")
            continue

        content = path.read_text()
        for pattern, template in patterns:
            new_content = re.sub(
                pattern, template.format(version=version), content, flags=re.MULTILINE
            )
            if new_content != content:
                if not dry_run:
                    path.write_text(new_content)
                updated.append(f"UPDATE: {filepath}")
            else:
                updated.append(f"NO CHANGE: {filepath}")

    return updated


def validate_semver(version: str) -> bool:
    """Validate semantic version format."""
    pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$'
    return bool(re.match(pattern, version))


def main():
    parser = argparse.ArgumentParser(description="Update project version")
    parser.add_argument("version", nargs="?", help="New version (e.g., 0.2.0)")
    parser.add_argument("--show", action="store_true", help="Show current version")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    project_file = Path("pyproject.toml")
    current = read_version(project_file)

    if args.show:
        print(f"Current version: {current}")
        return

    if not args.version:
        print(f"Current version: {current}")
        parser.print_help()
        sys.exit(1)

    if not validate_semver(args.version):
        print(f"Error: '{args.version}' is not a valid semver string (e.g., 0.2.0)")
        sys.exit(1)

    results = write_version(args.version, dry_run=args.dry_run)
    for r in results:
        print(r)

    if not args.dry_run:
        print(f"Version updated: {current} -> {args.version}")
    else:
        print(f"[DRY RUN] Would update: {current} -> {args.version}")


if __name__ == "__main__":
    main()
