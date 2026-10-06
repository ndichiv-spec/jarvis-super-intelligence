from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_URL = "https://github.com/ndichiv-spec/jarvis-cloud"
REPO_CLONE_URL = f"{REPO_URL}.git"
REPO_API_URL = "https://api.github.com/repos/ndichiv-spec/jarvis-cloud"


@dataclass(slots=True)
class RepoProbe:
    reachable: bool
    status_code: int | None
    message: str
    private_or_missing: bool = False


@dataclass(slots=True)
class WorkspaceProbe:
    path: str
    is_git_repo: bool
    current_branch: str | None
    origin_url: str | None
    origin_matches_target: bool
    message: str


@dataclass(slots=True)
class EnvironmentReport:
    repo_url: str
    git_available: bool
    git_path: str | None
    git_version: str | None
    token_present: bool
    repo_probe: RepoProbe
    suggested_clone_dir: str
    workspace_probe: WorkspaceProbe


def detect_git() -> tuple[bool, str | None, str | None]:
    git_path = shutil.which("git")
    if git_path is None:
        for candidate in (
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Users\Administrator\AppData\Local\Programs\Git\cmd\git.exe",
        ):
            if Path(candidate).exists():
                git_path = candidate
                break
    if git_path is None:
        return False, None, None

    try:
        result = subprocess.run(
            [git_path, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True, git_path, None

    return True, git_path, result.stdout.strip() or None


def github_token() -> str | None:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = str(os.environ.get(name, "")).strip()
        if value:
            return value
    return None


def normalize_remote_url(url: str | None) -> str | None:
    if url is None:
        return None
    normalized = url.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized


def run_git_command(
    git_path: str,
    args: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [git_path, *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
    )


def git_stdout(
    git_path: str,
    args: list[str],
    cwd: Path | None = None,
) -> str | None:
    result = run_git_command(git_path, args, cwd=cwd)
    if result.returncode != 0:
        return None
    stdout = result.stdout.strip()
    return stdout or None


def ensure_git_path(git_path: str | None = None) -> str:
    if git_path:
        return git_path
    git_available, resolved_git_path, _ = detect_git()
    if not git_available or resolved_git_path is None:
        raise RuntimeError("Git is not available. Install Git before connecting the workspace.")
    return resolved_git_path


def probe_workspace(
    workspace_dir: Path,
    git_path: str | None = None,
    remote_name: str = "origin",
    target_remote_url: str = REPO_CLONE_URL,
) -> WorkspaceProbe:
    resolved_workspace = workspace_dir.expanduser().resolve()
    if not resolved_workspace.exists():
        return WorkspaceProbe(
            path=str(resolved_workspace),
            is_git_repo=False,
            current_branch=None,
            origin_url=None,
            origin_matches_target=False,
            message="Workspace directory does not exist yet.",
        )

    git_available, detected_git_path, _ = detect_git()
    if git_path is None:
        git_path = detected_git_path

    if not git_available or git_path is None:
        return WorkspaceProbe(
            path=str(resolved_workspace),
            is_git_repo=False,
            current_branch=None,
            origin_url=None,
            origin_matches_target=False,
            message="Git is not installed, so workspace status cannot be inspected.",
        )

    repo_check = run_git_command(git_path, ["rev-parse", "--is-inside-work-tree"], cwd=resolved_workspace)
    if repo_check.returncode != 0 or repo_check.stdout.strip().lower() != "true":
        return WorkspaceProbe(
            path=str(resolved_workspace),
            is_git_repo=False,
            current_branch=None,
            origin_url=None,
            origin_matches_target=False,
            message="Workspace is not a Git repository yet.",
        )

    current_branch = git_stdout(git_path, ["branch", "--show-current"], cwd=resolved_workspace)
    origin_url = git_stdout(git_path, ["remote", "get-url", remote_name], cwd=resolved_workspace)
    origin_matches_target = normalize_remote_url(origin_url) == normalize_remote_url(target_remote_url)

    if origin_url is None:
        message = f"Workspace is a Git repository, but remote '{remote_name}' is not configured."
    elif origin_matches_target:
        message = f"Workspace is connected to {target_remote_url} through remote '{remote_name}'."
    else:
        message = f"Workspace remote '{remote_name}' points to a different repository."

    return WorkspaceProbe(
        path=str(resolved_workspace),
        is_git_repo=True,
        current_branch=current_branch,
        origin_url=origin_url,
        origin_matches_target=origin_matches_target,
        message=message,
    )


def probe_repo(url: str = REPO_API_URL, token: str | None = None) -> RepoProbe:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "jarvis-pycharm-connector",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            full_name = str(payload.get("full_name", "")).strip()
            visibility = str(payload.get("visibility", "")).strip()
            message = full_name or "Repository metadata loaded successfully."
            if visibility:
                message = f"{message} ({visibility})"
            return RepoProbe(reachable=True, status_code=response.status, message=message)
    except HTTPError as exc:
        status_code = getattr(exc, "code", None)
        if status_code == 404:
            return RepoProbe(
                reachable=False,
                status_code=status_code,
                message="GitHub returned 404. The repo is private, renamed, missing, or your token lacks access.",
                private_or_missing=True,
            )
        body = exc.read().decode("utf-8", errors="ignore").strip()
        detail = body or str(exc.reason)
        return RepoProbe(
            reachable=False,
            status_code=status_code,
            message=f"GitHub returned HTTP {status_code}: {detail}",
        )
    except URLError as exc:
        return RepoProbe(
            reachable=False,
            status_code=None,
            message=f"Network error while contacting GitHub: {exc.reason}",
        )


def build_report(
    clone_dir: Path,
    workspace_dir: Path | None = None,
    remote_name: str = "origin",
) -> EnvironmentReport:
    git_available, git_path, git_version = detect_git()
    token = github_token()
    repo_probe = probe_repo(token=token)
    workspace_probe = probe_workspace(
        workspace_dir or Path.cwd(),
        git_path=git_path,
        remote_name=remote_name,
    )
    return EnvironmentReport(
        repo_url=REPO_URL,
        git_available=git_available,
        git_path=git_path,
        git_version=git_version,
        token_present=bool(token),
        repo_probe=repo_probe,
        suggested_clone_dir=str(clone_dir),
        workspace_probe=workspace_probe,
    )


def render_report(report: EnvironmentReport) -> str:
    repo_status = "reachable" if report.repo_probe.reachable else "not confirmed"
    lines = [
        "JARVIS GitHub Connector",
        f"Repo: {report.repo_url}",
        f"Git: {'ready' if report.git_available else 'missing'}",
        f"Git path: {report.git_path or 'not found'}",
        f"Git version: {report.git_version or 'unknown'}",
        f"GitHub token: {'present' if report.token_present else 'missing'}",
        f"Repo probe: {repo_status}",
        f"Repo message: {report.repo_probe.message}",
        f"Workspace path: {report.workspace_probe.path}",
        f"Workspace git repo: {'yes' if report.workspace_probe.is_git_repo else 'no'}",
        f"Workspace branch: {report.workspace_probe.current_branch or 'not available'}",
        f"Workspace origin: {report.workspace_probe.origin_url or 'not configured'}",
        f"Workspace status: {report.workspace_probe.message}",
        f"Suggested clone dir: {report.suggested_clone_dir}",
        "",
        "PyCharm steps:",
        "1. Install Git and confirm PyCharm can see it in Settings > Version Control > Git.",
        "2. In PyCharm, open Settings > Version Control > GitHub and sign in with the GitHub account that can access this repo.",
        "3. Use a Personal Access Token if the repo is private. A token with repo access is the safest default.",
        "4. Run `python digital_clock.py --connect-current` to turn this workspace into a Git repo and attach the GitHub remote.",
        "5. Run `python digital_clock.py --connect-current --fetch` after credentials are configured to verify remote access.",
        f"6. Or clone {REPO_CLONE_URL} into {report.suggested_clone_dir} and open that folder in PyCharm.",
    ]

    if not report.git_available:
        lines.append("7. Git is not installed or not on PATH, so PyCharm cannot complete the GitHub workflow yet.")
    if report.repo_probe.private_or_missing and not report.token_present:
        lines.append("8. The repo appears private or unavailable without authentication. Add GITHUB_TOKEN or sign in inside PyCharm first.")

    return "\n".join(lines)


def clone_repo(target_dir: Path) -> int:
    git_available, git_path, _ = detect_git()
    if not git_available or git_path is None:
        print("Git is not available. Install Git before cloning.", file=sys.stderr)
        return 2

    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"Target directory is not empty: {target_dir}", file=sys.stderr)
        return 3

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [git_path, "clone", REPO_CLONE_URL, str(target_dir)],
            check=False,
            text=True,
        )
    except OSError as exc:
        print(f"Failed to launch git: {exc}", file=sys.stderr)
        return 4
    return int(result.returncode)


def initialize_workspace_repo(workspace_dir: Path, git_path: str) -> str:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    initial_result = run_git_command(git_path, ["init", "-b", "main"], cwd=workspace_dir)
    if initial_result.returncode == 0:
        return "Initialized the current workspace as a Git repository on branch main."

    fallback_result = run_git_command(git_path, ["init"], cwd=workspace_dir)
    if fallback_result.returncode != 0:
        detail = fallback_result.stderr.strip() or fallback_result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"Git init failed: {detail}")

    rename_result = run_git_command(git_path, ["branch", "-M", "main"], cwd=workspace_dir)
    if rename_result.returncode != 0:
        detail = rename_result.stderr.strip() or rename_result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"Git branch rename failed: {detail}")

    return "Initialized the current workspace as a Git repository and renamed the default branch to main."


def configure_remote(
    workspace_dir: Path,
    git_path: str,
    remote_name: str,
    remote_url: str,
) -> str:
    existing_url = git_stdout(git_path, ["remote", "get-url", remote_name], cwd=workspace_dir)
    if existing_url is not None:
        if normalize_remote_url(existing_url) == normalize_remote_url(remote_url):
            return f"Remote '{remote_name}' already points to {existing_url}."

        update_result = run_git_command(
            git_path,
            ["remote", "set-url", remote_name, remote_url],
            cwd=workspace_dir,
        )
        if update_result.returncode != 0:
            detail = update_result.stderr.strip() or update_result.stdout.strip() or "unknown git error"
            raise RuntimeError(f"Failed to update remote '{remote_name}': {detail}")
        return f"Updated remote '{remote_name}' from {existing_url} to {remote_url}."

    add_result = run_git_command(
        git_path,
        ["remote", "add", remote_name, remote_url],
        cwd=workspace_dir,
    )
    if add_result.returncode != 0:
        detail = add_result.stderr.strip() or add_result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"Failed to add remote '{remote_name}': {detail}")
    return f"Configured remote '{remote_name}' -> {remote_url}."


def fetch_remote(workspace_dir: Path, git_path: str, remote_name: str) -> str:
    fetch_result = run_git_command(git_path, ["fetch", remote_name], cwd=workspace_dir)
    if fetch_result.returncode != 0:
        detail = fetch_result.stderr.strip() or fetch_result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"Git fetch failed for remote '{remote_name}': {detail}")
    return f"Fetched from remote '{remote_name}'."


def connect_workspace(
    workspace_dir: Path,
    remote_url: str = REPO_CLONE_URL,
    remote_name: str = "origin",
    fetch: bool = False,
    git_path: str | None = None,
) -> list[str]:
    resolved_workspace = workspace_dir.expanduser().resolve()
    resolved_git_path = ensure_git_path(git_path)

    actions: list[str] = []
    workspace_probe = probe_workspace(
        resolved_workspace,
        git_path=resolved_git_path,
        remote_name=remote_name,
        target_remote_url=remote_url,
    )
    if not workspace_probe.is_git_repo:
        actions.append(initialize_workspace_repo(resolved_workspace, resolved_git_path))

    actions.append(
        configure_remote(
            resolved_workspace,
            resolved_git_path,
            remote_name=remote_name,
            remote_url=remote_url,
        )
    )

    if fetch:
        actions.append(fetch_remote(resolved_workspace, resolved_git_path, remote_name))

    return actions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check and connect the current JARVIS workspace to the jarvis-cloud repository."
    )
    parser.add_argument(
        "--clone-dir",
        default=str(Path.cwd() / "jarvis-cloud"),
        help="Target directory for a clone attempt.",
    )
    parser.add_argument(
        "--workspace-dir",
        default=str(Path.cwd()),
        help="Existing workspace to inspect or connect to GitHub.",
    )
    parser.add_argument(
        "--clone",
        action="store_true",
        help="Attempt to clone the jarvis-cloud repository after printing the readiness report.",
    )
    parser.add_argument(
        "--connect-current",
        action="store_true",
        help="Initialize the workspace as a Git repo if needed and attach the GitHub remote.",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch from the configured GitHub remote after connecting the workspace.",
    )
    parser.add_argument(
        "--remote-name",
        default="origin",
        help="Remote name to use for the GitHub repository.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the environment report as JSON.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.fetch and not args.connect_current:
        parser.error("--fetch requires --connect-current")

    clone_dir = Path(args.clone_dir).expanduser().resolve()
    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    actions: list[str] = []

    if args.connect_current:
        try:
            actions = connect_workspace(
                workspace_dir,
                remote_name=args.remote_name,
                fetch=args.fetch,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 5

    report = build_report(
        clone_dir,
        workspace_dir=workspace_dir,
        remote_name=args.remote_name,
    )

    if args.json:
        payload: dict[str, object] = {"report": asdict(report)}
        if actions:
            payload["actions"] = actions
        print(json.dumps(payload, indent=2))
    else:
        print(render_report(report))
        if actions:
            print()
            print("Workspace actions:")
            for action in actions:
                print(f"- {action}")
        print()
        print(
            textwrap.dedent(
                """
                Notes:
                - This helper can initialize Git and wire the workspace remote, but GitHub authentication still depends on your token or PyCharm sign-in.
                - If the repo stays at HTTP 404, verify the repository name, visibility, and your account access.
                - Use --connect-current to attach the current project before you try to fetch or push.
                """
            ).strip()
        )

    if not args.clone:
        return 0

    exit_code = clone_repo(clone_dir)
    if exit_code == 0:
        print(f"Clone completed: {clone_dir}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
