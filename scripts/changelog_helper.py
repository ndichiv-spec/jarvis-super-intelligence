"""Changelog helper for Jarvis.

Provides utilities for validating and generating changelog entries
following the Keep a Changelog format.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path


CHANGELOG_FILE = "CHANGELOG.md"

VALID_TYPES = {
    "Added": "New features",
    "Changed": "Changes in existing functionality",
    "Deprecated": "Soon-to-be removed features",
    "Removed": "Now removed features",
    "Fixed": "Bug fixes",
    "Security": "Vulnerability fixes",
}


def get_current_version(changelog: Path) -> str | None:
    """Get the latest version from the changelog."""
    content = changelog.read_text()
    match = re.search(r"## \[([\d.]+)\]", content)
    return match.group(1) if match else None


def validate_changelog(changelog: Path) -> list[str]:
    """Validate changelog structure."""
    errors = []
    content = changelog.read_text()

    if not content.startswith("# Changelog"):
        errors.append("Must start with '# Changelog'")

    if "Keep a Changelog" not in content:
        errors.append("Missing 'Keep a Changelog' reference")

    if "Semantic Versioning" not in content:
        errors.append("Missing 'Semantic Versioning' reference")

    sections = re.findall(r"### (\w+)", content)
    for section in sections:
        if section not in VALID_TYPES:
            errors.append(f"Unknown section type: '{section}'")

    unreleased = re.search(r"## \[Unreleased\]", content)
    if not unreleased:
        errors.append("Missing '[Unreleased]' section")

    return errors


def add_entry(
    version: str,
    entry_type: str,
    message: str,
    pr_number: int | None = None,
    dry_run: bool = False,
) -> str:
    """Add a changelog entry."""
    if entry_type not in VALID_TYPES:
        valid = ", ".join(VALID_TYPES.keys())
        raise ValueError(f"Invalid type '{entry_type}'. Valid: {valid}")

    today = date.today().isoformat()
    entry = f"- {message}"
    if pr_number:
        entry += f" (#{pr_number})"

    changelog = Path(CHANGELOG_FILE)
    content = changelog.read_text()

    version_header = f"## [{version}] - {today}"
    insert = f"{version_header}\n\n### {entry_type}\n\n{entry}\n\n"

    if "[Unreleased]" in content:
        new_content = content.replace(
            "## [Unreleased]",
            f"## [Unreleased]\n\n{insert}",
            1,
        )
    else:
        header_end = content.index("\n", content.index("\n") + 1)
        new_content = (
            content[:header_end]
            + f"\n\n## [Unreleased]\n\n{insert}"
            + content[header_end:]
        )

    if dry_run:
        return f"[DRY RUN] Would add to {CHANGELOG_FILE}:\n{insert.strip()}"

    changelog.write_text(new_content)
    return f"Added entry to {CHANGELOG_FILE}"


def main():
    parser = argparse.ArgumentParser(description="Changelog utilities")
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate", help="Validate changelog format")

    add_parser = subparsers.add_parser("add", help="Add a changelog entry")
    add_parser.add_argument("version", help="Version (e.g., 0.2.0)")
    add_parser.add_argument("type", choices=list(VALID_TYPES.keys()), help="Entry type")
    add_parser.add_argument("message", help="Description of the change")
    add_parser.add_argument("--pr", type=int, help="PR number")
    add_parser.add_argument("--dry-run", action="store_true", help="Preview only")

    show_parser = subparsers.add_parser("show", help="Show current version")

    args = parser.parse_args()

    if args.command == "validate":
        errors = validate_changelog(Path(CHANGELOG_FILE))
        if errors:
            print("Validation errors:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print(f"Changelog is valid. Latest: {get_current_version(Path(CHANGELOG_FILE))}")

    elif args.command == "add":
        result = add_entry(args.version, args.type, args.message, args.pr, args.dry_run)
        print(result)

    elif args.command == "show":
        version = get_current_version(Path(CHANGELOG_FILE))
        print(f"Latest version in changelog: {version}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
