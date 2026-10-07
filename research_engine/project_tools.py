"""Project-intelligence tools (read-only) for the JARVIS workspace.

These are ordinary :class:`~research_engine.tool_registry.Tool` implementations
registered into the existing ``ToolRegistry``.  They add NO new registry, NO new
permission system and NO new secret scrubber: authorization, risk levels and
``scrub_secrets()`` all come from the existing tool fabric.

Security boundary
-----------------
* Every path is confined to :data:`WORKSPACE_ROOT` (``F:\\AI``).  Traversal
  (``../``), absolute escapes and symlink escapes are rejected.
* Secret-bearing files are never read: ``.env``, ``*.pem``, ``*.key``,
  ``credentials*``, ``*secret*``, ``*token*`` and friends are excluded by name.
* Only credential *existence* metadata (``configured: true/false``) is ever
  reported - never a value.
* The tools never execute shell commands.  ``project.test_status`` only reads
  already-persisted pytest artifacts, or reports truthfully that tests have not
  been run.
"""
from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import RiskLevel, ToolResult
from .tool_registry import Tool, ToolContext, scrub_secrets

# --------------------------------------------------------------------------- #
# Boundaries
# --------------------------------------------------------------------------- #
WORKSPACE_ROOT = Path(os.environ.get("JARVIS_WORKSPACE_ROOT", r"F:\AI")).resolve()

# The JARVIS repository itself.  The workspace is the AUTHORIZATION boundary;
# the project root is what we actually analyze.  Auto-detected so the map is
# generated from the real layout rather than hard-coded.
def _detect_project_root() -> Path:
    env = os.environ.get("JARVIS_PROJECT_ROOT", "").strip()
    if env:
        candidate = Path(env)
        if candidate.exists():
            return candidate.resolve()
    # Prefer a directory that looks like the JARVIS repo.
    for child in sorted(WORKSPACE_ROOT.iterdir() if WORKSPACE_ROOT.is_dir() else []):
        if not child.is_dir():
            continue
        if (child / "jarvis_backend").is_dir() or (child / "jarvis_api.py").exists():
            return child.resolve()
    return WORKSPACE_ROOT


PROJECT_ROOT = _detect_project_root()

# Directories that are never walked: huge, generated, or third-party.
PRUNE_DIRS = {
    ".git", "node_modules", ".next", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".idea",
    "site-packages", ".pytest_cache", "coverage", ".coverage", "target",
    ".gradle", "vendor", ".tox", "egg-info", "kaggle_output", "jarvis_data",
    ".jarvis", ".poolside", ".sw_cache", ".kimchi",
}

# Filenames / suffixes that must never be read or emitted.
SECRET_FILE_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development", "credentials",
    "credentials.json", "secrets.json", "secret.json", "id_rsa", "id_ed25519",
    ".netrc", ".npmrc", ".pypirc", "service-account.json",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".crt"}
SECRET_SUBSTRINGS = ("secret", "credential", "apikey", "api_key", "token",
                     "password", "passwd", "private_key")

TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".md", ".txt", ".sql", ".sh", ".ps1",
    ".html", ".css", ".scss", ".go", ".rs", ".java", ".rb", ".php", ".c",
    ".cpp", ".h", ".hpp", ".cs", ".kt", ".swift", ".dart", ".lua", ".r",
}

# Evidence is bounded so the pack can never blow up model context.
MAX_FILE_BYTES = 200_000
MAX_SEARCH_RESULTS = 50
MAX_SNIPPET_CHARS = 400
MAX_MAP_ENTRIES = 40

# Files that are the most important structural anchors; always kept in the map
# even when the per-category cap is reached, so the highest-signal evidence
# (e.g. the API entrypoint) is never crowded out by alphabetical ordering.
_MAP_PRIORITY_FILES = (
    "jarvis_api.py",
    "tool_registry.py",
    "model_registry.py",
    "provider_registry.py",
    "artifact_registry.py",
    "job_registry.py",
    "observability.py",
)


def _sanitize(text: str) -> str:
    """Strip control characters so the payload is always valid JSON.

    Source files legitimately contain tabs/newlines and stray control bytes; a
    raw control char inside a JSON string would make the whole tool result
    unparseable for the caller.
    """
    return "".join(
        ch for ch in text
        if ch in "\t\n\r" or 0x20 <= ord(ch) < 0x7F or ord(ch) > 0x9F
    )

# Markers that indicate unfinished / placeholder work.
PLACEHOLDER_PATTERNS = [
    r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bHACK\b",
    r"\bNotImplementedError\b", r"\braise\s+NotImplemented\b",
    r"\bplaceholder\b", r"\bstub\b", r"\bmock\b", r"\bsimulation\b",
    r"\bsimulated\b", r"\bdummy\b", r"\bfake\b", r"\bhardcoded\b",
    r"\bcoming soon\b", r"\bnot implemented\b", r"\bWIP\b",
]
_PLACEHOLDER_RE = re.compile("|".join(PLACEHOLDER_PATTERNS), re.IGNORECASE)

# Short-lived cache for the structural map.  The map is derived from the file
# tree, which does not change between chat turns; caching keeps the tool fast
# enough to run inline.  ``project.search`` always reads live file contents.
_MAP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_MAP_CACHE_TTL_S = 60.0


# --------------------------------------------------------------------------- #
# Path safety
# --------------------------------------------------------------------------- #
def _is_secret_name(name: str) -> bool:
    low = name.lower()
    if low in SECRET_FILE_NAMES or low.startswith(".env"):
        return True
    if any(low.endswith(sfx) for sfx in SECRET_SUFFIXES):
        return True
    stem = low.rsplit(".", 1)[0]
    return any(sub in stem for sub in SECRET_SUBSTRINGS)


def safe_path(candidate: str | os.PathLike[str], root: Path | None = None) -> Path:
    """Resolve ``candidate`` inside the workspace or raise ``ValueError``.

    Rejects ``..`` traversal, absolute escapes and symlink escapes.
    """
    base = (root or WORKSPACE_ROOT).resolve()
    raw = str(candidate)
    if not raw or raw.strip() in {".", "./"}:
        return base
    if "\x00" in raw:
        raise ValueError("invalid path")
    target = Path(raw)
    resolved = (base / target).resolve() if not target.is_absolute() else target.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(
            f"path escapes the authorized workspace root: {raw!r}"
        ) from None
    return resolved


def _walk(root: Path, *, limit_files: int = 20000) -> Iterable[Path]:
    """Yield non-secret files under ``root``, pruning heavy directories.

    Metadata only - this never reads file contents, so it stays fast.
    """
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in PRUNE_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            if _is_secret_name(fn):
                continue
            p = Path(dirpath) / fn
            if p.suffix.lower() not in TEXT_SUFFIXES:
                continue
            seen += 1
            if seen > limit_files:
                return
            yield p


def _rel(path: Path) -> str:
    """Path relative to the AUTHORIZATION boundary (workspace root)."""
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT))
    except ValueError:
        return str(path)


def _proj_rel(path: Path) -> str:
    """Path relative to the analyzed PROJECT root (POSIX separators).

    Category globs are written project-relative (``jarvis_backend/**``), so the
    map must match against this form, while all emitted evidence stays
    workspace-relative for unambiguous citation.
    """
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
        except ValueError:
            return str(path)


def _read_bounded(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def _scrub_payload(obj: Any) -> Any:
    """Recursively scrub secret-shaped substrings from string values.

    This runs BEFORE the payload is serialised to JSON.  The registry's
    ``scrub_secrets`` regexes use ``\\s*``, which can match across the newlines
    and indentation *of the JSON structure itself* and corrupt it.  Scrubbing
    the values first means the registry pass finds nothing left to match, so the
    result stays valid JSON while remaining secret-free.
    """
    if isinstance(obj, str):
        scrubbed, _ = scrub_secrets(obj)
        return scrubbed
    if isinstance(obj, dict):
        return {
            scrub_secrets(str(k))[0]: _scrub_payload(v)  # type: ignore[misc]
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub_payload(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_scrub_payload(v) for v in obj)
    return obj


def _ok(name: str, ctx: ToolContext, started: float, payload: Any,
        metrics: Optional[dict] = None) -> ToolResult:
    safe = _scrub_payload(payload)
    body = json.dumps(safe, indent=2, default=str)
    # Registry-level scrub still runs (defence in depth); verify we did not
    # corrupt the JSON structure, and fall back to a minimal safe payload.
    scrubbed, redacted = scrub_secrets(body)
    try:
        json.loads(scrubbed)
    except json.JSONDecodeError:
        scrubbed = json.dumps(
            {"error": "result withheld: failed integrity check after scrubbing"},
            indent=2,
        )
        redacted = True
    return ToolResult(
        tool_id=ctx.request_id, name=name, success=True, result=scrubbed,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        metrics=metrics or {}, redacted_secrets=redacted,
    )


def _fail(name: str, ctx: ToolContext, started: float, error: str) -> ToolResult:
    scrubbed, redacted = scrub_secrets(error)
    return ToolResult(
        tool_id=ctx.request_id, name=name, success=False, error=scrubbed,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        redacted_secrets=redacted,
    )


# --------------------------------------------------------------------------- #
# Symbol extraction (best effort, syntax-based)
# --------------------------------------------------------------------------- #
def _python_symbols(source: str) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            prefix = "class " if isinstance(node, ast.ClassDef) else "def "
            out.append(f"{prefix}{node.name} (L{node.lineno})")
    return out[:MAX_MAP_ENTRIES]


def _js_symbols(source: str) -> list[str]:
    out: list[str] = []
    pattern = re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?"
        r"(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    )
    for m in pattern.finditer(source):
        out.append(f"{m.group(1)} (L{source[:m.start()].count(chr(10)) + 1})")
        if len(out) >= MAX_MAP_ENTRIES:
            break
    return out


def _symbols_for(path: Path, source: str) -> list[str]:
    if path.suffix == ".py":
        return _python_symbols(source)
    if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        return _js_symbols(source)
    return []


# --------------------------------------------------------------------------- #
# Project map
# --------------------------------------------------------------------------- #
# Category -> (marker paths/globs, description).  Detection is by ACTUAL files
# on disk, never hard-coded claims about today's architecture.
_MAP_CATEGORIES: dict[str, dict[str, Any]] = {
    "BACKEND": {"globs": ["jarvis_backend/**/*.py", "jarvis_api.py", "backend/**/*.py"],
                "detect": ("router", "api", "service", "endpoint")},
    "FRONTEND": {"globs": ["frontend/**/*.tsx", "frontend/**/*.ts", "frontend/**/package.json"],
                 "detect": ("component", "page", "ui", "frontend")},
    "PROVIDERS": {"globs": ["providers/**/*.py", "**/providers/**/*.py"],
                  "detect": ("provider", "adapter", "registry")},
    "MODELS": {"globs": ["**/model_registry.py", "models/**/*.py", "**/model_lifecycle*/**"],
               "detect": ("model",)},
    "DATABASE": {"globs": ["**/migrations/**", "**/schema*.py", "**/*db*.py", "**/alembic*"],
                 "detect": ("database", "db", "postgres", "sql")},
    "CACHE": {"globs": ["**/cache*.py", "**/redis*.py"], "detect": ("cache", "redis")},
    "AUTH": {"globs": ["**/auth*.py", "**/security*.py"], "detect": ("auth", "login", "token")},
    "TOOLS": {"globs": ["**/tool_registry.py", "**/tools/**/*.py"],
              "workspace_globs": ["research_engine/**/*.py"],
              "detect": ("tool",)},
    "CAPABILITIES": {"globs": ["**/capabilit*.py", "**/plugins/**/*.py"],
                     "detect": ("capability", "plugin")},
    "KNOWLEDGE": {"globs": ["**/knowledge*/**", "**/rag*/**", "**/memory*/**"],
                  "detect": ("knowledge", "rag", "retriev", "memory")},
    "TASKS": {"globs": ["**/task*.py", "**/job*.py", "**/scheduler*.py"],
              "detect": ("task", "job", "queue")},
    "AGENTS": {"globs": ["**/agent*.py", "**/orchestrat*.py"],
               "detect": ("agent", "orchestrat")},
    "TRAINING": {"globs": ["training/**", "**/train*.py", "**/finetune*", "kaggle*/**"],
                 "detect": ("train", "finetune", "lora")},
    "ARTIFACTS": {"globs": ["**/artifact*.py", "jarvis_data/**", "kaggle_output/**"],
                  "detect": ("artifact",)},
    "DEPLOYMENT": {"globs": ["**/docker-compose*.yml", "**/Dockerfile*", "deployment/**",
                             "infrastructure/deploy/**"],
                   "detect": ("deploy", "docker", "compose")},
    "TESTS": {"globs": ["tests/**/*.py", "**/test_*.py", "**/conftest.py"],
              "detect": ("test",)},
    "DOCUMENTATION": {"globs": ["docs/**", "**/*.md", "README*"],
                      "detect": ("doc", "readme", "guide")},
    "INTEGRATIONS": {"globs": ["**/integrations/**", "**/connectors/**", "**/webhook*/**"],
                     "detect": ("integration", "connector", "webhook")},
}


def _iter_scope_files(scope: Path, limit: int = 4000) -> list[Path]:
    """Enumerate project files once, pruning heavy directories.

    Category globs are then matched against this bounded list instead of each
    glob re-walking the tree (which made the map take ~48s on the real repo).
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(scope):
        dirnames[:] = [
            d for d in dirnames
            if d not in PRUNE_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            if _is_secret_name(fn):
                continue
            p = Path(dirpath) / fn
            if p.suffix.lower() not in TEXT_SUFFIXES:
                continue
            out.append(p)
            if len(out) >= limit:
                return out
    return out


def _cached_project_map(scope: Path) -> dict[str, Any]:
    key = str(scope)
    now = time.monotonic()
    hit = _MAP_CACHE.get(key)
    if hit and (now - hit[0]) < _MAP_CACHE_TTL_S:
        return hit[1]
    built = _build_project_map(scope)
    _MAP_CACHE[key] = (now, built)
    return built


def _build_project_map(scope: Path) -> dict[str, Any]:
    """Generate the structured project map from ACTUAL files on disk.

    ``scope`` is the project root being analyzed (auto-detected by default), so
    every glob is relative to the real repository layout rather than assuming the
    project sits at the workspace root.
    """
    out: dict[str, Any] = {}
    # Enumerate the tree ONCE (pruned), then match every category's globs
    # against that list.  Avoids re-walking the filesystem per category.
    all_files = _iter_scope_files(scope)
    # (project-relative, workspace-relative) pairs.
    rel_files = [(_proj_rel(f), _rel(f)) for f in all_files]

    # A few subsystems legitimately live in the workspace but outside the repo
    # (e.g. the shared research_engine tool fabric).  Enumerate those once,
    # still confined to the authorized workspace root.
    ws_extra: list[tuple[str, str]] = []
    if any(spec.get("workspace_globs") for spec in _MAP_CATEGORIES.values()):
        for f in _iter_scope_files(WORKSPACE_ROOT, limit=40000):
            ws_rel = _rel(f).replace("\\", "/")
            if ws_rel.startswith(f"{PROJECT_ROOT.name}/"):
                continue  # already covered by the project scan
            ws_extra.append((ws_rel, _rel(f)))

    for category, spec in _MAP_CATEGORIES.items():
        dirs: list[str] = []
        matched: list[str] = []
        for pattern in spec["globs"]:
            if any(part in PRUNE_DIRS for part in pattern.split("/")):
                continue
            for proj_rel, ws_rel in rel_files:
                if _glob_match(proj_rel, pattern) and ws_rel not in matched:
                    matched.append(ws_rel)
        for pattern in spec.get("workspace_globs") or []:
            if any(part in PRUNE_DIRS for part in pattern.split("/")):
                continue
            for ws_rel_norm, ws_rel in ws_extra:
                if _glob_match(ws_rel_norm, pattern) and ws_rel not in matched:
                    matched.append(ws_rel)

        # Keep the highest-signal anchors (API entrypoint, registries) ahead of
        # the alphabetical tail so the cap never hides the important evidence.
        anchors = [f for f in matched
                   if Path(f).name in _MAP_PRIORITY_FILES]
        rest = sorted(f for f in matched if f not in anchors)
        files = (anchors + rest)[:MAX_MAP_ENTRIES]

        for f in files:
            parent = str(Path(f).parent)
            if parent not in dirs and parent not in {".", ""}:
                dirs.append(parent)
        out[category] = {
            "present": bool(files or dirs),
            "key_files": files,
            "key_dirs": sorted(dirs)[:MAX_MAP_ENTRIES],
            "file_count": len(matched),
        }
    return out


def _glob_match(rel_path: str, pattern: str) -> bool:
    """Match a workspace-relative POSIX path against a glob pattern.

    ``fnmatch`` treats ``*`` as matching ``/`` too, which would make
    ``jarvis_backend/*.py`` match nested routers.  We therefore anchor the
    pattern at the start and require ``**`` for multi-segment matches.
    """
    p = rel_path.replace("\\", "/")
    pat = pattern.replace("\\", "/")
    if "**/" in pat:
        head, tail = pat.split("**/", 1)
        if not p.startswith(head):
            return False
        rest = p[len(head):]
        return fnmatch.fnmatch(rest, tail) or fnmatch.fnmatch(
            rest, "*/" + tail
        ) or tail in rest.split("/")
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return p.startswith(prefix + "/") or p == prefix
    return fnmatch.fnmatch(p, pat)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
class _ProjectToolBase(Tool):
    risk: RiskLevel = RiskLevel.READ
    requires_confirmation: bool = False

    def _root(self, args: dict[str, Any]) -> Path:
        """Resolve the scope: default to the JARVIS project root, confined to
        the workspace.  An explicit ``path`` is still validated against the
        workspace boundary."""
        args = args or {}
        scope = (args.get("path") or "").strip()
        if not scope or scope in {".", "./"}:
            return safe_path(str(PROJECT_ROOT))
        return safe_path(scope)

    def _fail(self, ctx: ToolContext, started: float, exc: Exception) -> ToolResult:
        return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class ProjectInspectTool(_ProjectToolBase):
    """Bounded structural overview of the JARVIS workspace."""

    name = "project.inspect"
    description = (
        "Inspect the real JARVIS project on disk. Returns a bounded structural map "
        "(backend, frontend, providers, models, database, cache, auth, tools, "
        "capabilities, knowledge, tasks, agents, training, artifacts, deployment, "
        "tests, docs, integrations), key files, entrypoints, routers, registries, "
        "configuration sources and placeholder/TODO markers. Read-only."
    )
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional workspace-relative subdirectory to scope the inspection.",
            },
            "include_placeholders": {
                "type": "boolean",
                "description": "Include TODO/FIXME/stub/simulated markers (default true).",
            },
            "max_placeholders": {
                "type": "integer",
                "description": "Cap on placeholder findings returned (default 40).",
            },
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            root = self._root(args)
            if not root.exists():
                return _fail(self.name, ctx, started, f"path does not exist: {_rel(root)}")
            if not root.is_dir():
                root = root.parent

            include_ph = (args or {}).get("include_placeholders", True)
            max_ph = int((args or {}).get("max_placeholders") or 40)

            project_map = _cached_project_map(root)

            # Entrypoints + routers + registries, discovered by name/pattern.
            entrypoints: list[str] = []
            routers: list[str] = []
            registries: list[str] = []
            config_sources: list[str] = []
            tests: list[str] = []
            py_files = 0
            ts_files = 0
            placeholders: list[dict[str, Any]] = []

            for path in _walk(root):
                rel = _rel(path)
                low = rel.lower()
                if path.suffix == ".py":
                    py_files += 1
                elif path.suffix in {".ts", ".tsx"}:
                    ts_files += 1
                if low.endswith(("jarvis_api.py", "main.py", "app.py", "__main__.py")):
                    entrypoints.append(rel)
                if "router" in low or "routes" in low:
                    routers.append(rel)
                if "registry" in low:
                    registries.append(rel)
                if low.endswith((".env.example", "config.py", "settings.py",
                                 "pyproject.toml", "package.json", "requirements.txt")):
                    config_sources.append(rel)
                if low.startswith("tests/") or "/test_" in low or low.endswith("test_*.py"):
                    tests.append(rel)

            # Placeholder scan is bounded to the primary source trees so the tool
            # stays fast enough to run inside a chat turn.
            ph_roots = [p for p in (root / "jarvis_backend", root / "providers",
                                    root / "jarvis_backend" / "routers")
                        if p.is_dir()]
            ph_suffixes = {".py", ".ts", ".tsx"}
            if include_ph:
                for ph_root in ph_roots:
                    if len(placeholders) >= max_ph:
                        break
                    for dirpath, dirnames, filenames in os.walk(ph_root):
                        dirnames[:] = [d for d in dirnames
                                       if d not in PRUNE_DIRS and not d.startswith(".")]
                        for fn in filenames:
                            if len(placeholders) >= max_ph:
                                break
                            if _is_secret_name(fn) or Path(fn).suffix not in ph_suffixes:
                                continue
                            source = _read_bounded(Path(dirpath) / fn)
                            if not source:
                                continue
                            rel = _rel(Path(dirpath) / fn)
                            for lineno, line in enumerate(source.splitlines(), 1):
                                if _PLACEHOLDER_RE.search(line):
                                    snippet = _sanitize(line.strip())
                                    if len(snippet) > MAX_SNIPPET_CHARS:
                                        snippet = snippet[:MAX_SNIPPET_CHARS] + "..."
                                    placeholders.append({
                                        "file": rel, "line": lineno, "text": snippet,
                                        "in_test": "test" in rel.lower(),
                                    })
                                    if len(placeholders) >= max_ph:
                                        break

            def _cap(items: list[str]) -> list[str]:
                return sorted(set(items))[:MAX_MAP_ENTRIES]

            # Credential presence metadata only - never values.
            credential_presence: dict[str, dict[str, Any]] = {}
            for env_name in (
                "OPENAI_API_KEY", "NVIDIA_API_KEY", "GOOGLE_API_KEY",
                "ANTHROPIC_API_KEY", "HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN",
                "GROQ_API_KEY", "DEEPSEEK_API_KEY", "GITHUB_TOKEN",
                "DATABASE_URL", "REDIS_URL", "MONGODB_URL",
            ):
                value = os.environ.get(env_name)
                credential_presence[env_name] = {
                    "configured": bool(value and value.strip()),
                }

            payload = {
                "workspace_root": str(WORKSPACE_ROOT),
                "inspected_path": _rel(root),
                "project_map": project_map,
                "entrypoints": _cap(entrypoints),
                "routers": _cap(routers),
                "registries": _cap(registries),
                "configuration_sources": _cap(config_sources),
                "test_files_count": len(set(tests)),
                "test_files_sample": _cap(tests)[:20],
                "file_counts": {"python": py_files, "typescript": ts_files},
                "placeholder_markers": placeholders,
                "placeholder_note": (
                    "Markers in *_test_* files are usually harmless; production gaps "
                    "are entries with in_test=false."
                ),
                "credential_presence": credential_presence,
                "credential_note": "Presence only. Values are never returned.",
            }
            return _ok(self.name, ctx, started, payload, {
                "files_scanned": py_files + ts_files,
                "placeholders": len(placeholders),
            })
        except Exception as exc:  # noqa: BLE001
            return self._fail(ctx, started, exc)


class ProjectSearchTool(_ProjectToolBase):
    """Bounded, workspace-confined code search."""

    name = "project.search"
    description = (
        "Search the real JARVIS project for a literal pattern. Returns file, line "
        "number, a short snippet and the enclosing symbol when detectable. "
        "Workspace-confined and read-only."
    )
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Literal substring to find."},
            "path": {"type": "string", "description": "Optional workspace-relative scope."},
            "file_types": {
                "type": "array", "items": {"type": "string"},
                "description": "Optional extensions, e.g. ['.py', '.tsx'].",
            },
            "max_results": {"type": "integer", "description": "Cap on matches (default 40)."},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            query = (args.get("query") or "").strip()
            if not query:
                return _fail(self.name, ctx, started, "query is required")
            root = self._root(args)
            if not root.exists():
                return _fail(self.name, ctx, started, f"path does not exist: {_rel(root)}")
            max_results = min(int(args.get("max_results") or 40), MAX_SEARCH_RESULTS)
            wanted = {
                t if t.startswith(".") else f".{t}"
                for t in (args.get("file_types") or [])
            }

            matches: list[dict[str, Any]] = []
            truncated = False
            for path in _walk(root):
                if wanted and path.suffix.lower() not in wanted:
                    continue
                source = _read_bounded(path)
                if not source or query not in source:
                    continue
                rel = _rel(path)
                symbols = _symbols_for(path, source)
                for lineno, line in enumerate(source.splitlines(), 1):
                    if query in line:
                        if len(matches) >= max_results:
                            truncated = True
                            break
                        snippet = _sanitize(line.strip())
                        if len(snippet) > MAX_SNIPPET_CHARS:
                            snippet = snippet[:MAX_SNIPPET_CHARS] + "..."
                        symbol = ""
                        for s in symbols:  # last symbol at or above this line
                            try:
                                sl = int(re.search(r"\(L(\d+)\)", s).group(1))
                            except (AttributeError, ValueError):
                                continue
                            if sl <= lineno:
                                symbol = s
                        matches.append({
                            "file": rel, "line": lineno, "text": snippet,
                            "symbol": symbol,
                        })
                if truncated:
                    break

            payload = {
                "query": query,
                "scope": _rel(root),
                "match_count": len(matches),
                "truncated": truncated,
                "matches": matches,
            }
            return _ok(self.name, ctx, started, payload, {"matches": len(matches)})
        except ValueError as exc:
            return _fail(self.name, ctx, started, f"path rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._fail(ctx, started, exc)


class ProjectTestStatusTool(_ProjectToolBase):
    """Report the real test status WITHOUT executing anything.

    Reuses the existing pytest cache/last-run artifacts when present.  If they
    are absent it returns a truthful "not run" result - it never invents counts
    and never shells out.
    """

    name = "project.test_status"
    description = (
        "Report the current project test status using existing pytest artifacts. "
        "Returns passed/failed/skipped/error counts and failing test names when a "
        "recent run is recorded; otherwise reports truthfully that tests have not "
        "been run. Never executes tests and never returns invented metrics."
    )
    schema = {
        "type": "object",
        "properties": {
            "refresh": {
                "type": "boolean",
                "description": "Reserved. Tests are never executed by this tool.",
            }
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            pytest_cache = WORKSPACE_ROOT / ".pytest_cache"
            lastfailed = pytest_cache / "v" / "cache" / "lastfailed"
            nodeids = pytest_cache / "v" / "cache" / "nodeids"

            if not lastfailed.exists() and not nodeids.exists():
                payload = {
                    "status": "NOT_RUN",
                    "source": str(lastfailed),
                    "passed": None, "failed": None, "skipped": None,
                    "errors": None, "duration_s": None,
                    "failing_tests": [],
                    "explanation": (
                        "No pytest run artifacts were found. The test suite has not "
                        "been run in this workspace, so no pass/fail metrics can be "
                        "reported. Nothing is inferred."
                    ),
                }
                return _ok(self.name, ctx, started, payload, {"status": "NOT_RUN"})

            failing: list[str] = []
            if lastfailed.exists():
                try:
                    failing = list(json.loads(_read_bounded(lastfailed) or "{}").keys())
                except (json.JSONDecodeError, ValueError):
                    failing = []

            collected = 0
            if nodeids.exists():
                try:
                    collected = len(json.loads(_read_bounded(nodeids) or "[]"))
                except (json.JSONDecodeError, ValueError):
                    collected = 0

            payload = {
                "status": "RECORDED",
                "source": str(pytest_cache),
                "collected_last_run": collected,
                "failed": len(failing) or None,
                "failing_tests": sorted(failing)[:MAX_SEARCH_RESULTS],
                "skipped": None,
                "passed": None,
                "duration_s": None,
                "explanation": (
                    "Derived from the existing .pytest_cache last-run artifacts. "
                    "Counts not present in those artifacts are reported as null "
                    "rather than estimated."
                ),
            }
            return _ok(self.name, ctx, started, payload, {
                "collected": collected, "failing": len(failing),
            })
        except Exception as exc:  # noqa: BLE001
            return self._fail(ctx, started, exc)


__all__ = [
    "ProjectInspectTool",
    "ProjectSearchTool",
    "ProjectTestStatusTool",
    "WORKSPACE_ROOT",
    "safe_path",
]
