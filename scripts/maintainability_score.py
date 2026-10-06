"""Maintainability scoring for Jarvis codebase.

Calculates cyclomatic complexity, maintainability index, and
dependency metrics using radon and manual analysis.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


TARGET_DIRS = [
    "infrastructure",
    "performance",
    "core",
]

THRESHOLDS = {
    "complexity_a": 10,
    "complexity_b": 20,
    "complexity_c": 30,
    "maintainability_green": 80,
    "maintainability_yellow": 60,
    "file_lines_max": 500,
}


def score_complexity() -> dict[str, Any]:
    """Score cyclomatic complexity of Python files."""
    results = {"files": [], "total_complexity": 0, "file_count": 0}

    try:
        from radon.complexity import cc_visit
        from radon.visitors import ComplexityVisitor
    except ImportError:
        results["error"] = "radon not installed (pip install radon)"
        return results

    for target in TARGET_DIRS:
        base = Path(target)
        if not base.exists():
            continue

        for py_file in base.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue

            try:
                code = py_file.read_text(encoding="utf-8")
                visitor = ComplexityVisitor.from_code(code)
                avg = visitor.average_complexity if hasattr(visitor, 'average_complexity') else 0
                results["files"].append({
                    "file": str(py_file),
                    "complexity": round(avg, 2),
                    "functions": len(visitor.functions) if hasattr(visitor, 'functions') else 0,
                })
                results["total_complexity"] += avg
                results["file_count"] += 1
            except Exception:
                pass

    if results["file_count"] > 0:
        results["average_complexity"] = round(
            results["total_complexity"] / results["file_count"], 2
        )

    return results


def score_maintainability() -> dict[str, Any]:
    """Score maintainability index of Python files."""
    results = {"files": [], "total_mi": 0, "file_count": 0}

    try:
        from radon.metrics import mi_visit, mi_rank
    except ImportError:
        results["error"] = "radon not installed (pip install radon)"
        return results

    for target in TARGET_DIRS:
        base = Path(target)
        if not base.exists():
            continue

        for py_file in base.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue

            try:
                code = py_file.read_text(encoding="utf-8")
                mi = mi_visit(code, multi=False)
                rank = mi_rank(mi)
                results["files"].append({
                    "file": str(py_file),
                    "mi": round(mi, 2),
                    "rank": rank,
                })
                results["total_mi"] += mi
                results["file_count"] += 1
            except Exception:
                pass

    if results["file_count"] > 0:
        results["average_mi"] = round(
            results["total_mi"] / results["file_count"], 2
        )

    return results


def count_large_files(max_lines: int = 500) -> list[dict[str, Any]]:
    """Find files exceeding the line count threshold."""
    large = []
    for target in TARGET_DIRS:
        base = Path(target)
        if not base.exists():
            continue
        for py_file in base.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            try:
                lines = len(py_file.read_text(encoding="utf-8").splitlines())
                if lines > max_lines:
                    large.append({"file": str(py_file), "lines": lines})
            except Exception:
                pass
    return sorted(large, key=lambda x: x["lines"], reverse=True)


def generate_report() -> dict[str, Any]:
    """Generate a comprehensive maintainability report."""
    print("Analyzing code complexity...")
    complexity = score_complexity()

    print("Analyzing maintainability index...")
    maintainability = score_maintainability()

    print("Finding large files...")
    large_files = count_large_files(THRESHOLDS["file_lines_max"])

    report = {
        "thresholds": THRESHOLDS,
        "complexity": complexity,
        "maintainability": maintainability,
        "large_files": {
            "count": len(large_files),
            "threshold_lines": THRESHOLDS["file_lines_max"],
            "files": large_files,
        },
    }

    return report


def print_report(report: dict[str, Any]) -> None:
    """Print a human-readable report."""
    print("\n" + "=" * 60)
    print("  MAINTAINABILITY REPORT")
    print("=" * 60)

    c = report.get("complexity", {})
    if "error" not in c and c.get("file_count", 0) > 0:
        print(f"\n  Cyclomatic Complexity:")
        print(f"    Average: {c.get('average_complexity', 'N/A')}")
        print(f"    Files analyzed: {c.get('file_count', 0)}")

    m = report.get("maintainability", {})
    if "error" not in m and m.get("file_count", 0) > 0:
        print(f"\n  Maintainability Index:")
        print(f"    Average MI: {m.get('average_mi', 'N/A')}")
        for rank, label in [(80, "Green (high)"), (60, "Yellow (medium)"), (0, "Red (low)")]:
            count = sum(1 for f in m.get("files", []) if f["mi"] >= rank if rank < 80 or f["mi"] >= 80)
            print(f"    {label}: {count} files")

    lf = report.get("large_files", {})
    if lf.get("files"):
        print(f"\n  Large Files (>{lf.get('threshold_lines', 500)} lines):")
        for f in lf["files"][:10]:
            print(f"    {f['file']}: {f['lines']} lines")
        if len(lf["files"]) > 10:
            print(f"    ... and {len(lf['files']) - 10} more")


def main():
    parser = argparse.ArgumentParser(description="Calculate maintainability scores")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    report = generate_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)

    c = report.get("complexity", {})
    if c.get("average_complexity", 0) > THRESHOLDS["complexity_b"]:
        print(f"\n  WARNING: Average complexity exceeds threshold ({THRESHOLDS['complexity_b']})")
        sys.exit(1)


if __name__ == "__main__":
    main()
