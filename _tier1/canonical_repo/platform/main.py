"""Compatibility CLI for the older repository entry-points.

The historical configuration uses ``main.py`` with a small CLI to read a file or
launch the canonical API application using uvicorn.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

_REPOSITORY_ROOT = Path(__file__).resolve().parent


def _slice_content(content: str, start_line: int, line_count: int) -> str:
    lines = content.splitlines()
    start_index = max(0, start_line - 1)
    end_index = start_index + max(0, line_count)
    return "\n".join(lines[start_index:end_index])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JARVIS compatibility CLI")
    subparsers = parser.add_subparsers(dest="command")

    read = subparsers.add_parser("read", help="Read a file from the repo")
    read.add_argument("path")
    read.add_argument("--lines", type=int, default=20)
    read.add_argument("--start", type=int, default=1)

    launch = subparsers.add_parser("launch", help="Launch the API server")
    launch.add_argument("--host", default="127.0.0.1")
    launch.add_argument("--port", type=int, default=8000)
    return parser


def read_file(args: argparse.Namespace) -> int:
    target = Path(args.path).resolve()
    if not target.is_relative_to(_REPOSITORY_ROOT):
        print("Path must be inside the platform repository.", flush=True)
        return 1
    if not target.is_file():
        print(f"File not found: {args.path}", flush=True)
        return 1
    content = target.read_text(encoding="utf-8")
    print(_slice_content(content, args.start, args.lines), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "read":
        return read_file(args)
    if args.command == "launch":
        uvicorn.run("jarvis_backend.main:app", host=args.host, port=args.port)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
