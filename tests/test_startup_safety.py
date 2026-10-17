"""Phase 5 regression guard for `start_jarvis.py` startup safety.

These tests NEVER execute `start_jarvis.py` (it is not authorized to run in
this sandbox — Phase 5) and NEVER print, commit, or log a token value. They
assert the four hardening properties that close the BACKEND-1/BACKEND-2/Phase-5
risk surface:

  * sensitive credential files are git-ignored (cannot be committed);
  * `start_jarvis.py` never echoes a bearer token value (static check);
  * the token-file helper persists `0600` permissions on POSIX;
  * the launcher's `chdir` is guarded so importing it (e.g. from CI) cannot
    raise when the git-ignored operational checkout is absent.

The token-persistence helper is loaded by AST-execution of its function body so
the test does **not** run the launcher's top-level side effects.
"""
from __future__ import annotations

import ast
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT / "start_jarvis.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


def _git_ignored(relpath: str) -> bool:
    """True if `relpath` (under repo root) is git-ignored."""
    proc = subprocess.run(
        ["git", "check-ignore", str(ROOT / relpath)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


# --------------------------------------------------------------------------- #
# 1. Credential files can never be committed.
# --------------------------------------------------------------------------- #
SENSITIVE_FILES = [
    "_token.txt",        # admin bearer token written by start_jarvis.py (Phase 5)
    ".env",              # live env / provider credentials
    ".env.bak",
    ".mcp.json",         # MCP server config (may carry keys)
    "dev_secret.pem",    # stand-in for *.pem private keys
    "_scratch.txt",      # any root-level /_*.txt scratch file
]


def test_sensitive_files_are_gitignored():
    not_ignored = [p for p in SENSITIVE_FILES if not _git_ignored(p)]
    assert not not_ignored, f"these sensitive files are NOT git-ignored: {not_ignored}"


def test_env_example_is_the_only_tracked_env_sample():
    # The canonical env sample must be tracked (so consumers have a template),
    # and must NOT itself be ignored.
    assert not _git_ignored(".env.example")
    assert ".env.example" in {p.name for p in ROOT.glob("**/.env.example")}


# --------------------------------------------------------------------------- #
# 2. start_jarvis.py never echoes a token value.
# --------------------------------------------------------------------------- #
def test_start_jarvis_does_not_echo_token():
    # No wholesale print of the token variable.
    assert "print(token)" not in SOURCE
    # No literal bearer/JWT/credential assignments in the launcher source.
    for forbidden in ("Bearer ", "jwt = ", "password = '"):
        assert forbidden not in SOURCE, f"forbidden literal present: {forbidden!r}"


def test_start_jarvis_has_no_hardcoded_live_secret():
    # P1-1 closed over (no Admin#Jarvis1). The seed password must be the
    # documented dev-only test value, never a production credential.
    assert "Admin#Jarvis1" not in SOURCE
    assert "test-password-for-testing" in SOURCE


# --------------------------------------------------------------------------- #
# 3. Token-file helper writes 0600 (POSIX) and round-trips content.
# --------------------------------------------------------------------------- #
def _load_write_token_file():
    """Compile just the `_write_token_file` function from start_jarvis.py."""
    tree = ast.parse(SOURCE)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_write_token_file":
            mod = ast.Module(body=[node], type_ignores=[])
            code = compile(mod, str(SOURCE_PATH), "exec")
            # Seed the module-level imports the function relies on (os, stat).
            namespace: dict = {"__name__": "__test__", "os": os, "stat": stat}
            exec(code, namespace)  # noqa: S102 — function-isolated
            return namespace["_write_token_file"]
    raise AssertionError("_write_token_file not found in start_jarvis.py")


def test_token_file_permissions_and_content(tmp_path):
    write = _load_write_token_file()
    token_path = tmp_path / "_run_token.txt"
    sample = "header.payload.signature"  # structural stand-in, not a real token
    write(str(token_path), sample)

    # Content round-trips exactly.
    assert token_path.read_text(encoding="utf-8") == sample

    if os.name == "posix":
        mode = stat.S_IMODE(os.stat(token_path).st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
        # No group/other access.
        assert not (mode & 0o077), f"group/other bits set: {oct(mode & 0o077)}"
    # On Windows (this sandbox) POSIX mode bits are not enforced by the OS;
    # the helper still issues os.chmod best-effort. We assert the source uses
    # the 0600 hardening unconditionally (covered by the static test below).


def test_start_jarvis_uses_0600_hardening():
    assert "0o600" in SOURCE
    assert "_write_token_file" in SOURCE
    assert "os.chmod" in SOURCE


def test_start_jarvis_chdir_is_guarded():
    # Importing the launcher must not raise when REPO_ROOT (the git-ignored
    # operational checkout) is absent — clean-clone import safety.
    assert "os.path.isdir(REPO_ROOT)" in SOURCE
