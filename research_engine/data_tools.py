"""JARVIS Data Analytics Capability Domain.

Real, bounded, read-only analytics over PostgreSQL, MongoDB and local
structured files. Every capability is an ordinary
:class:`~research_engine.tool_registry.Tool`, inheriting the existing
authorization, risk policy and ``scrub_secrets()`` boundary.

Reused, not duplicated:
  * ``jarvis_backend.db.get_engine`` - the canonical SQLAlchemy engine
  * ``research_engine.document_tools`` - CSV/JSON/XLSX parsing
  * ``infrastructure.artifact_registry`` - persistent output provenance
  * the existing provider fabric for AI analysis

No SQL parser dependency (sqlglot/sqlparse absent), so this module implements
a **conservative allowlist validator**. It refuses anything it cannot prove is
read-only rather than pretending arbitrary SQL is safe.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import RiskLevel, ToolResult
from .project_tools import _fail, _ok, _sanitize
from .tool_registry import Tool, ToolContext

VERSION = "data_analytics/1.0"

# Hard resource limits - this host has ~8 GB RAM and must not be overrun.
MAX_ROWS = 5_000
MAX_COLUMNS = 200
MAX_RESPONSE_BYTES = 2_000_000
MAX_SCAN_ROWS = 1_000_000
QUERY_TIMEOUT_S = 20
MAX_PROFILE_ROWS = 200_000
MAX_AGGREGATE_GROUPS = 1_000

# Permissions
DATA_DISCOVER = "data:discover"
DATA_READ = "data:read"
DATA_ANALYZE = "data:analyze"
DATA_EXPORT = "data:export"
DATA_WRITE = "data:write"

DEFAULT_PERMISSIONS = (DATA_DISCOVER, DATA_READ, DATA_ANALYZE)

_MONGO_URL_VARS = ("MONGODB_URL", "MONGODB_URI", "MONGO_URL",
                   "MONGODB_CONNECTION_STRING")
_mongo_client: Any = None


# --------------------------------------------------------------------------- #
# Conservative SQL validation (no parser dependency available)
# --------------------------------------------------------------------------- #
# Only these statement heads may execute. Anything else is refused.
_ALLOWED_HEADS = ("select", "with", "table", "values")
# Recursive CTE + data-modifying CTE heads are never allowed.
_FORBIDDEN_HEAD = re.compile(
    r"^\s*(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"replace|merge|copy|vacuum|reindex|cluster|comment|do|call|execute|"
    r"prepare|deallocate|listen|notify|discard|reset|reassign|refresh|"
    r"security\s+label|import\s+foreign)", re.I)
# Dangerous anywhere in the statement.
_FORBIDDEN_ANYWHERE = re.compile(
    r"(;.*\S)"              # multiple statements
    r"|\bpg_read_file\b|\bpg_ls_dir\b|\bpg_stat_file\b"
    r"|\blo_import\b|\blo_export\b|\bcopy\b"
    r"|\bdblink\b|\bdblink_exec\b"
    r"|\bset\b\s+\w"
    r"|\bxp_cmdshell\b|\bsp_executesql\b"
    r"|\bcreate\b|\balter\b|\bdrop\b|\bgrant\b|\brevoke\b"
    r"|\btruncate\b|\bdelete\b|\bupdate\b|\binsert\b"
    r"|information_schema\.pg_(shadow|catalog)"
    r"|\bcurrent_setting\b|\bset_config\b"
    # SELECT ... INTO creates a table (DDL through a SELECT head), and
    # FOR SHARE / FOR UPDATE take row locks (a write side effect).
    r"|\binto\b|\bfor\s+(share|update|no\s+key\s+update|key\s+share)\b",
    re.I | re.S)
_IDENT_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SqlRejected(ValueError):
    """Raised when SQL cannot be proven read-only."""


# --------------------------------------------------------------------------- #
# Relation (table) authorization - explicit ALLOWLIST, default DENY
# --------------------------------------------------------------------------- #
# The SQL validator above proves a statement is *read-only*; it says nothing
# about *which relations* it may read. Without this layer a single
# ``SELECT * FROM jarvis_kv`` would return live refresh tokens, user records
# and the role/permission catalogue, because the application credential has
# broad read access to ``public``.
#
# Design: allowlist, never denylist. Anything not named here is denied, so a
# table added to the database tomorrow is denied until it is deliberately
# approved. Operators may extend it with JARVIS_DATA_ALLOWED_TABLES.
ANALYTICS_SCHEMA = "public"

# Relations approved for read-only analytics. These are JARVIS's own
# operational/telemetry tables. Application identity and security stores
# (jarvis_kv -> users/roles/permissions/refresh_tokens/sessions/agents) are
# deliberately ABSENT and must never be added.
ALLOWED_RELATIONS: frozenset[str] = frozenset({
    "public.artifacts",
    "public.audit_events",
    "public.jobs",
    "public.models",
    "public.providers",
    "public.usage_costs",
})

# Schemas that may never be queried through analytics, whatever the table.
DENIED_SCHEMAS: frozenset[str] = frozenset({
    "pg_catalog", "information_schema", "pg_toast",
})


class RelationNotAuthorized(SqlRejected):
    """Raised when a statement references a relation outside the allowlist.

    Subclasses :class:`SqlRejected` so existing callers that already catch
    ``SqlRejected`` keep working, while callers that care can distinguish an
    authorization refusal from a syntax refusal.
    """


def allowed_relations() -> frozenset[str]:
    """The effective allowlist, including operator-approved additions."""
    extra = (os.environ.get("JARVIS_DATA_ALLOWED_TABLES") or "").strip()
    if not extra:
        return ALLOWED_RELATIONS
    approved = set(ALLOWED_RELATIONS)
    for item in extra.replace(";", ",").split(","):
        name = item.strip().strip('"').lower()
        if not name:
            continue
        if "." not in name:
            name = f"{ANALYTICS_SCHEMA}.{name}"
        # An operator extension may never reach a denied schema.
        if name.split(".", 1)[0] in DENIED_SCHEMAS:
            continue
        approved.add(name)
    return frozenset(approved)


# Tokenizer: yields (kind, value, was_quoted).
#   kind: "word" | "quoted" | "punct" | "string" | "number"
_TOKEN_RE = re.compile(
    r"""
      (?P<string>'(?:[^']|'')*')
    | (?P<quoted>"(?:[^"]|"")*")
    | (?P<number>\d+(?:\.\d+)?)
    | (?P<word>[A-Za-z_\$][A-Za-z0-9_\$]*)
    | (?P<punct>\(|\)|,|\.|\*|;|[^\sA-Za-z0-9_\$])
    """,
    re.X,
)


def _tokenize(sql: str) -> list[tuple[str, str, bool]]:
    tokens: list[tuple[str, str, bool]] = []
    for m in _TOKEN_RE.finditer(sql):
        kind = m.lastgroup or "punct"
        raw = m.group()
        if kind == "quoted":
            tokens.append(("quoted", raw[1:-1].replace('""', '"').lower(), True))
        elif kind == "word":
            tokens.append(("word", raw.lower(), False))
        elif kind == "string":
            tokens.append(("string", raw, False))
        elif kind == "number":
            tokens.append(("number", raw, False))
        else:
            tokens.append(("punct", raw, False))
    return tokens


def _cte_names(tokens: list[tuple[str, str, bool]]) -> set[str]:
    """Names bound by a leading WITH clause (these are not relations)."""
    names: set[str] = set()
    for i, (kind, value, _) in enumerate(tokens):
        if kind != "word" or value != "with":
            continue
        j = i + 1
        if j < len(tokens) and tokens[j][1] == "recursive":
            j += 1
        # Walk the comma-separated CTE list: name [ (cols) ] AS ( ... )
        while j < len(tokens):
            nk, nv, _ = tokens[j]
            if nk in {"word", "quoted"} and nv not in {"recursive"}:
                names.add(nv)
                j += 1
                if j < len(tokens) and tokens[j][1] == "(":   # optional column list
                    depth = 0
                    while j < len(tokens):
                        depth += tokens[j][1] in {"(", ")"}
                        j += 1
                        if depth == 0:
                            break
                if j < len(tokens) and tokens[j][1] == "as":
                    j += 1
            if j < len(tokens) and tokens[j][1] == ",":
                j += 1
                continue
            break
    return names


def extract_relations(sql: str) -> list[str]:
    """Return every relation reference in ``sql`` as ``schema.name``.

    Handles schema qualification, aliases, JOINs, subqueries, CTEs, quoted and
    mixed-case identifiers. Raises :class:`SqlRejected` if a relation position
    cannot be parsed with certainty, so the caller fails closed.
    """
    tokens = _tokenize(sql)
    ctes = _cte_names(tokens)
    relations: list[str] = []
    for i, (kind, value, _) in enumerate(tokens):
        if kind != "word" or value not in {"from", "join"}:
            continue
        j = i + 1
        while j < len(tokens) and tokens[j][1] in {",", "lateral", "only"}:
            j += 1
        if j >= len(tokens):
            raise SqlRejected("unparseable relation reference")
        nk, nv, _ = tokens[j]
        if nk == "punct" and nv == "(":
            # Subquery / parenthesized join - its inner relations are found by
            # the same global scan, so nothing to authorize here.
            continue
        if nk == "punct" or nk == "string" or nk == "number":
            raise SqlRejected("unparseable relation reference")
        # A function call in relation position is never approved.
        if j + 1 < len(tokens) and tokens[j + 1][1] == "(":
            raise SqlRejected("set-returning functions are not authorized here")
        parts = [nv]
        j += 1
        while j + 1 < len(tokens) and tokens[j][1] == "." \
                and tokens[j + 1][0] in {"word", "quoted"}:
            parts.append(tokens[j + 1][1])
            j += 2
        if len(parts) == 1:
            # Unqualified: resolve against the analytics schema, unless it is a
            # locally defined CTE.
            if parts[0] in ctes:
                continue
            relations.append(f"{ANALYTICS_SCHEMA}.{parts[0]}")
        elif len(parts) == 2:
            if parts[0] in ctes:
                continue
            relations.append(f"{parts[0]}.{parts[1]}")
        else:
            # database.schema.table - cross-database reference is refused.
            raise SqlRejected("cross-database references are not authorized")
    return relations


def authorize_relations(sql: str) -> list[str]:
    """Validate every relation in ``sql`` against the allowlist.

    Returns the authorized relation list. Raises :class:`RelationNotAuthorized`
    naming only the offending relation - never schema internals or credentials.
    """
    relations = extract_relations(sql)
    allowed = allowed_relations()
    for rel in relations:
        schema = rel.split(".", 1)[0]
        if schema in DENIED_SCHEMAS:
            raise RelationNotAuthorized(
                f"relation is not authorized for analytics: {rel}")
        if rel not in allowed:
            raise RelationNotAuthorized(
                f"relation is not authorized for analytics: {rel}")
    return relations


def validate_analytics_sql(sql: str) -> tuple[str, list[str]]:
    """Full analytics gate: SQL safety, then relation authorization.

    Returns ``(normalised_sql, authorized_relations)``.
    """
    statement = validate_readonly_sql(sql)
    relations = authorize_relations(statement)
    return statement, relations


def validate_readonly_sql(sql: str) -> str:
    """Return the normalised SQL, or raise :class:`SqlRejected`.

    Conservative by design: a single leading SELECT/WITH, no statement
    separators, no DDL/DML, no filesystem or server-side execution functions.
    """
    if not sql or not sql.strip():
        raise SqlRejected("empty statement")
    text = sql.strip().rstrip(";").strip()
    if not text:
        raise SqlRejected("empty statement")
    if ";" in text:
        raise SqlRejected("multiple statements are not permitted")
    if "--" in text or "/*" in text:
        raise SqlRejected("SQL comments are not permitted")
    if "\x00" in text:
        raise SqlRejected("illegal character in statement")
    lowered = text.lower()
    head = re.match(r"[a-z_]+", lowered)
    if not head or head.group(0) not in _ALLOWED_HEADS:
        raise SqlRejected(
            f"only read-only SELECT/WITH statements are permitted; got "
            f"{head.group(0).upper() if head else 'unknown'!r}")
    bad = _FORBIDDEN_ANYWHERE.search(text)
    if bad:
        raise SqlRejected(f"forbidden construct: {bad.group(0).strip()[:40]!r}")
    # A leading WITH must still be a SELECT, never an INSERT/UPDATE/DELETE CTE.
    if lowered.startswith("with"):
        tail = re.sub(r"\brecursive\b", "", lowered, count=1)
        for cte_head in ("insert", "update", "delete"):
            if re.search(rf"\)\s*{cte_head}\b|\bas\s*\({cte_head}\b", tail):
                raise SqlRejected(
                    f"data-modifying CTE ({cte_head}) is not permitted")
        if not re.search(r"\bselect\b", tail):
            raise SqlRejected("WITH statement does not contain a SELECT")
    return text


def _check_ident(name: str, kind: str = "identifier") -> str:
    if not name or not _IDENT_OK.match(str(name)):
        raise SqlRejected(f"invalid {kind}: {name!r}")
    return str(name)


def query_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def _engine():
    from jarvis_backend.db import get_engine

    return get_engine()


def _sql_source() -> dict[str, Any]:
    """Real SQL source state from the existing engine factory."""
    out: dict[str, Any] = {"kind": "sql", "driver": None, "available": False,
                           "error": None}
    try:
        engine = _engine()
        url = str(engine.url)
        out["driver"] = engine.dialect.name
        out["server"] = engine.dialect.server_name \
            if hasattr(engine.dialect, "server_name") else None
        # Never return credentials: only the host/db portion.
        out["database"] = getattr(engine.url, "database", None)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        out["available"] = True
        out["state_chain"] = {"configured": True, "authenticated": True,
                              "reachable": True, "healthy": True,
                              "resource_verified": True}
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["state_chain"] = {"configured": True, "reachable": False}
    return out


def _mongo_client_instance():
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    url = ""
    for var in _MONGO_URL_VARS:
        url = (os.environ.get(var) or "").strip()
        if url:
            break
    if not url:
        url = "mongodb://127.0.0.1:27017"
    try:
        _mongo_client = MongoClient(url, serverSelectionTimeoutMS=2500,
                                    connectTimeoutMS=2500)
    except Exception:  # noqa: BLE001
        _mongo_client = None
    return _mongo_client


def _mongo_source() -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "mongodb", "available": False,
                           "error": None, "databases": []}
    client = _mongo_client_instance()
    if client is None:
        out["error"] = "pymongo is not installed"
        return out
    try:
        names = client.list_database_names()
        out["databases"] = [n for n in names if n not in {"admin", "local",
                                                          "config"}]
        out["available"] = True
        out["state_chain"] = {"configured": True, "authenticated": True,
                              "reachable": True, "healthy": True,
                              "resource_verified": True}
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["state_chain"] = {"configured": True, "reachable": False}
    return out


def _local_source() -> dict[str, Any]:
    """Local structured files, parsed by the EXISTING documents domain."""
    from .document_tools import dep_available, detect_format

    return {
        "kind": "local_files",
        "available": True,
        "formats": {ext: True for ext in (".csv", ".json", ".xlsx", ".tsv")},
        "parsers": {
            "csv": "research_engine.document_tools (stdlib csv)",
            "json": "research_engine.document_tools (stdlib json)",
            "xlsx": "research_engine.document_tools (openpyxl)"
            if dep_available("xlsx") else None,
        },
        "offline_capable": True,
    }


# --------------------------------------------------------------------------- #
# Execution helpers
# --------------------------------------------------------------------------- #
class QueryTimeout(RuntimeError):
    """Raised when PostgreSQL terminated a statement via statement_timeout."""


def _is_timeout(exc: BaseException) -> bool:
    """True when the driver error is a server-side statement timeout."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return ("statement timeout" in text or "canceling statement" in text
            or "query timeout" in text or "57014" in text)


def _apply_guards(conn, dialect: str) -> dict[str, Any]:
    """Apply the strongest read-only + timeout guards the dialect supports.

    PostgreSQL gets genuine SERVER-side enforcement (``statement_timeout``
    aborts the running statement; ``transaction_read_only`` refuses writes at
    the engine). Both are set with ``SET LOCAL`` so they cannot leak onto the
    pooled session, and both are read back so the reported values are measured.

    SQLite (used by the default/local JARVIS database) has no server-side
    statement timeout. It does support ``PRAGMA query_only``, which is applied
    as the read-only backstop, and the missing timeout is reported as
    ``None``/``False`` rather than being claimed as enforced.
    """
    guards: dict[str, Any] = {
        "dialect": dialect,
        "read_only_enforced": False,
        "read_only_by": None,
        "statement_timeout_s": None,
        "timeout_enforced_by": None,
        "timeout_enforced": False,
    }
    if dialect == "postgresql":
        conn.exec_driver_sql(
            f"SET LOCAL statement_timeout = {int(QUERY_TIMEOUT_S * 1000)}")
        conn.exec_driver_sql("SET LOCAL transaction_read_only = on")
        ro = str(conn.exec_driver_sql(
            "SHOW transaction_read_only").scalar()).lower()
        to_ms = str(conn.exec_driver_sql(
            "SHOW statement_timeout").scalar()).strip()
        guards.update(
            read_only_enforced=ro in {"on", "true"},
            read_only_by="postgresql SET LOCAL transaction_read_only",
            statement_timeout_s=QUERY_TIMEOUT_S,
            timeout_enforced_by="postgresql SET LOCAL statement_timeout",
            timeout_enforced=to_ms not in {"0", ""},
        )
    elif dialect == "sqlite":
        conn.exec_driver_sql("PRAGMA query_only = ON")
        guards.update(
            read_only_enforced=bool(conn.exec_driver_sql(
                "PRAGMA query_only").scalar()),
            read_only_by="sqlite PRAGMA query_only",
            statement_timeout_s=None,
            timeout_enforced_by=None,
            timeout_enforced=False,
        )
    else:
        guards["read_only_by"] = f"none (unsupported dialect: {dialect})"
    return guards


def _run_sql(sql: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Execute validated read-only SQL with hard row/size/time limits.

    Every statement runs inside an explicit transaction that applies the
    read-only and timeout guards the backend actually supports (see
    :func:`_apply_guards`) using transaction-local scoping, so nothing leaks to
    any other operation. On PostgreSQL this includes real server-side
    termination via ``statement_timeout``; on backends without it the result
    says so instead of implying enforcement that did not happen.

    On timeout the transaction is rolled back so the pooled connection is
    returned clean and remains usable.
    """
    statement, relations = validate_analytics_sql(sql)
    engine = _engine()
    dialect = engine.dialect.name
    started = time.monotonic()
    conn = engine.connect()
    try:
        transaction = conn.begin()
        try:
            guards = _apply_guards(conn, dialect)
            # Row cap applied server-side.
            limited = statement
            if not re.match(r"^\s*limit\b", limited, re.I) and \
                    not re.search(r"\blimit\s+\d+\s*$", limited, re.I):
                limited = f"SELECT * FROM ({statement}) AS _jarvis_bounded " \
                          f"LIMIT {MAX_ROWS}"
            result = conn.exec_driver_sql(
                limited, params or {}) if params else conn.exec_driver_sql(limited)
            columns = list(result.keys())
            if len(columns) > MAX_COLUMNS:
                raise ValueError(
                    f"result has {len(columns)} columns, exceeding the "
                    f"{MAX_COLUMNS} column limit")
            rows = [dict(zip(columns, r)) for r in result.fetchmany(MAX_ROWS)]
            transaction.commit()
        except Exception as exc:  # noqa: BLE001
            try:
                transaction.rollback()
            except Exception:  # noqa: BLE001
                pass
            if _is_timeout(exc):
                raise QueryTimeout(
                    f"query exceeded the {QUERY_TIMEOUT_S}s analytics limit and "
                    f"was terminated by the database") from None
            raise
    finally:
        # Returning a connection with an open transaction would poison the pool.
        try:
            if conn.in_transaction():
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        # SQLite's PRAGMA query_only is CONNECTION-scoped, not
        # transaction-local, so it must be explicitly cleared or the pooled
        # connection would hand the next caller a read-only database.
        if dialect == "sqlite":
            try:
                conn.exec_driver_sql("PRAGMA query_only = OFF")
            except Exception:  # noqa: BLE001
                pass
        conn.close()
    elapsed = (time.monotonic() - started) * 1000
    payload = json.dumps(rows, default=str)
    truncated = len(payload) > MAX_RESPONSE_BYTES
    if truncated:
        keep = max(1, int(MAX_RESPONSE_BYTES / max(1, len(payload) / max(1, len(rows)))))
        rows = rows[:keep]
    return {
        "columns": columns, "rows": rows, "row_count": len(rows),
        "row_limit": MAX_ROWS, "truncated": truncated,
        "elapsed_ms": round(elapsed, 2), "query_hash": query_hash(statement),
        "statement_hash": query_hash(statement), "relations": relations,
        "dialect": dialect,
        "statement_timeout_s": guards["statement_timeout_s"],
        "timeout_enforced": guards["timeout_enforced"],
        "timeout_enforced_by": guards["timeout_enforced_by"],
        "read_only_enforced": guards["read_only_enforced"],
        "read_only_by": guards["read_only_by"],
    }


def _jsonable(value: Any) -> Any:
    """Coerce to a JSON-safe scalar WITHOUT stringifying numbers.

    numpy scalars (int64/float64) are not Python ``int``/``float``, so a naive
    isinstance check would silently turn every statistic into a string.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        return value
    # numpy / pandas scalars expose .item()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary {len(bytes(value))} bytes>"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "tolist"):  # numpy array
        return [_jsonable(v) for v in value.tolist()]
    return str(value)


# --------------------------------------------------------------------------- #
# Local dataframe loading (bounded)
# --------------------------------------------------------------------------- #
def _load_frame(path_str: str, max_rows: int = MAX_PROFILE_ROWS):
    """Load a local structured file into a bounded pandas DataFrame.

    Reuses the documents domain for parsing. Raises on traversal/oversize.
    """
    import pandas as pd

    from .document_tools import detect_format, resolve_document

    path = resolve_document(path_str or "")
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {path.name}")
    if path.stat().st_size > 200 * 1024 * 1024:
        raise ValueError("file exceeds the 200 MB local analytics limit")
    fmt = detect_format(path)
    if fmt == "csv":
        frame = pd.read_csv(path, nrows=max_rows, sep="\t"
                            if path.suffix.lower() == ".tsv" else ",")
    elif fmt == "json":
        frame = pd.read_json(path)
        frame = frame.head(max_rows)
    elif fmt == "xlsx":
        frame = pd.read_excel(path, nrows=max_rows)
    else:
        raise ValueError(f"unsupported local format for analytics: {fmt}")
    if len(frame.columns) > MAX_COLUMNS:
        frame = frame.iloc[:, :MAX_COLUMNS]
    return frame, fmt, path


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
class _DataTool(Tool):
    risk: RiskLevel = RiskLevel.READ
    required_permissions: tuple[str, ...] = DEFAULT_PERMISSIONS
    schema = {"type": "object", "properties": {}, "required": []}

    def _provenance(self, ctx: ToolContext, source: str, **extra: Any) -> dict:
        base = {"source": source, "capability_version": VERSION,
                "request_id": ctx.request_id, "user_id": ctx.user_id,
                "timestamp": time.time()}
        base.update(extra)
        return base


class DataSourcesTool(_DataTool):
    name = "data.sources"
    description = ("Discover available data sources (PostgreSQL via the existing "
                   "engine, MongoDB, and local structured files) with real "
                   "connection state. Never returns passwords, connection "
                   "strings or tokens.")
    schema = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            sources = {
                "sql": _sql_source(),
                "mongodb": _mongo_source(),
                "local_files": _local_source(),
            }
            # Defence in depth: strip anything credential-shaped.
            blob = json.dumps(sources, default=str)
            for marker in ("://", "password", "PASSWORD"):
                if marker in blob:
                    sources = {"error": "withheld: credential-shaped metadata",
                               "fields": [marker]}
                    break
            return _ok(self.name, ctx, started, {
                "sources": sources,
                "available": [k for k, v in sources.items()
                              if isinstance(v, dict) and v.get("available")],
                "provenance": self._provenance(ctx, "capability_inventory"),
            }, {"available": len([k for k, v in sources.items()
                                  if isinstance(v, dict)
                                  and v.get("available")])})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DataSchemaTool(_DataTool):
    name = "data.schema"
    description = ("Inspect authorized database structure: PostgreSQL "
                   "schemas/tables/columns/types/indexes, or MongoDB "
                   "databases/collections with safe sample metadata. Never "
                   "returns credentials.")
    schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string",
                       "enum": ["sql", "mongodb"], "description": "Default sql."},
            "schema": {"type": "string",
                       "description": "Optional authorized schema name."},
            "include_indexes": {"type": "boolean"},
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            kind = (args.get("source") or "sql").lower()
            if kind == "mongodb":
                data = self._mongo_schema(ctx)
            else:
                data = self._sql_schema(args, ctx)
            return _ok(self.name, ctx, started, data)
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")

    def _sql_schema(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Describe ONLY allowlisted relations.

        Schema discovery is an authorization surface, not a free pass: the same
        allowlist that gates ``data.query`` gates metadata, so a caller cannot
        learn that ``jarvis_kv``/``users``/``refresh_tokens`` exist by asking for
        the schema instead of the rows. Unallowlisted relations are reported as
        a count only - never by name.
        """
        from sqlalchemy import text as sa_text

        allow = allowed_relations()
        allowed_schemas = {r.split(".", 1)[0] for r in allow}
        engine = _engine()
        dialect = engine.dialect.name
        with engine.connect() as conn:
            if dialect == "sqlite":
                # SQLite has no information_schema; introspect its catalogue and
                # report relations under the analytics schema name so the same
                # allowlist governs both backends.
                rel_rows = conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type IN "
                    "('table','view') AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name").fetchall()
                present = {f"{ANALYTICS_SCHEMA}.{r[0]}" for r in rel_rows}
            else:
                rel_rows = conn.execute(sa_text(
                    "SELECT table_schema, table_name "
                    "FROM information_schema.tables "
                    "WHERE table_type IN ('BASE TABLE','VIEW') "
                    "ORDER BY table_schema, table_name")).fetchall()
                present = {f"{r[0]}.{r[1]}" for r in rel_rows}
            # Restrict BEFORE any further metadata is read.
            authorized = sorted(present & allow)
            withheld = len(present - allow)

            wanted = args.get("schema")
            if wanted:
                _check_ident(wanted, "schema name")
                if wanted in DENIED_SCHEMAS or wanted not in allowed_schemas:
                    raise SqlRejected(f"schema not authorized for analytics: {wanted}")

            if dialect == "sqlite":
                col_rows: list[tuple[str, str, str, str, str]] = []
                for rel in authorized:
                    tname = rel.split(".", 1)[1]
                    for c in conn.exec_driver_sql(
                            f'PRAGMA table_info("{tname}")').fetchall():
                        col_rows.append((ANALYTICS_SCHEMA, tname, c[1],
                                         c[2], "YES" if not c[3] else "NO"))
                columns = col_rows
            else:
                columns = conn.execute(sa_text(
                    "SELECT table_schema, table_name, column_name, data_type, "
                    "is_nullable FROM information_schema.columns "
                    "ORDER BY table_schema, table_name, ordinal_position")
                    ).fetchall()
            indexes: list[dict[str, Any]] = []
            if args.get("include_indexes", True):
                try:
                    if dialect == "sqlite":
                        index_rows = [
                            (ANALYTICS_SCHEMA, rel.split(".", 1)[1],
                             f"idx_{i[1]}")
                            for rel in authorized
                            for i in conn.exec_driver_sql(
                                f'PRAGMA index_list("{rel.split(".", 1)[1]}")'
                            ).fetchall()]
                    else:
                        index_rows = [
                            (r[0], r[1], r[2])
                            for r in conn.execute(sa_text(
                                "SELECT schemaname, tablename, indexname "
                                "FROM pg_indexes WHERE schemaname = ANY(:s)"),
                                {"s": list(allowed_schemas)}).fetchall()]
                    indexes = [{"schema": s, "table": t, "index": i}
                               for s, t, i in index_rows
                               if f"{s}.{t}" in allow]
                except Exception:  # noqa: BLE001
                    indexes = []
        tables: dict[str, Any] = {}
        for s, t, c, d, n in columns:
            rel = f"{s}.{t}"
            if rel not in allow:
                continue
            if wanted and s != wanted:
                continue
            tables.setdefault(rel, []).append(
                {"name": c, "type": d, "nullable": n == "YES"})
        authorized = [k for k in authorized if k in tables]
        return {
            "source": "sql", "driver": dialect,
            "schemas": sorted({r.split(".", 1)[0] for r in authorized}),
            "table_count": len(tables),
            "tables": {k: v for k, v in list(tables.items())[:300]},
            "indexes": indexes[:200],
            "authorization": {
                "mode": "allowlist", "default": "DENY",
                "withheld_relation_count": withheld,
                "note": ("relations outside the analytics allowlist are neither "
                         "listed nor described"),
            },
            "provenance": self._provenance(ctx, "information_schema"),
        }

    def _mongo_schema(self, ctx: ToolContext) -> dict[str, Any]:
        client = _mongo_client_instance()
        if client is None:
            return {"source": "mongodb", "available": False,
                    "reason": "pymongo not installed"}
        out: dict[str, Any] = {"source": "mongodb", "available": True,
                               "databases": {}}
        for db_name in client.list_database_names():
            if db_name in {"admin", "local", "config"}:
                continue
            db = client[db_name]
            colls: dict[str, Any] = {}
            for cname in db.list_collection_names()[:100]:
                try:
                    stats = db.command("collstats", cname)
                    sample = list(db[cname].find({}, limit=1))
                    colls[cname] = {
                        "documents": stats.get("count"),
                        "storage_bytes": stats.get("storageSize"),
                        "indexes": sorted((stats.get("indexSizes") or {}).keys()),
                        "sample_keys": sorted(sample[0].keys())[:40]
                        if sample else [],
                    }
                except Exception as exc:  # noqa: BLE001
                    colls[cname] = {"error": f"{type(exc).__name__}"}
            out["databases"][db_name] = colls
        out["provenance"] = self._provenance(ctx, "mongodb_introspection")
        return out


class DataPreviewTool(_DataTool):
    name = "data.preview"
    description = ("Preview bounded records from a SQL table, a MongoDB "
                   "collection or a local file, with hard row/column/byte/time "
                   "limits. No unbounded SELECT *.")
    schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string",
                       "enum": ["sql", "mongodb", "file"]},
            "table": {"type": "string"},
            "schema": {"type": "string"},
            "database": {"type": "string"},
            "collection": {"type": "string"},
            "path": {"type": "string"},
            "rows": {"type": "integer", "description": "Default 50, max 5000."},
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            kind = (args.get("source") or "").lower()
            if kind == "file":
                return _ok(self.name, ctx, started, self._file_preview(args, ctx))
            if kind == "mongodb":
                return _ok(self.name, ctx, started, self._mongo_preview(args, ctx))
            table = args.get("table")
            if not table:
                return _fail(self.name, ctx, started, "table is required")
            schema_name = args.get("schema")
            limit = min(int(args.get("rows") or 50), MAX_ROWS)
            qualified = (f"{_check_ident(schema_name, 'schema')}."
                         f"{_check_ident(table, 'table')}") if schema_name \
                else _check_ident(table, "table")
            data = _run_sql(f"SELECT * FROM {qualified} LIMIT {int(limit)}")
            data["source"] = "sql"
            data["object"] = qualified
            data["provenance"] = self._provenance(
                ctx, "sql", query_hash=data["query_hash"],
                row_limit=int(limit), sampling="LIMIT")
            return _ok(self.name, ctx, started, data,
                       {"rows": data["row_count"]})
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")

    def _file_preview(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        frame, fmt, path = _load_frame(args.get("path") or "",
                                       max_rows=MAX_PROFILE_ROWS)
        rows = min(int(args.get("rows") or 50), MAX_ROWS)
        head = frame.head(rows)
        return {
            "source": "file", "format": fmt, "object": path.name,
            "columns": [str(c) for c in head.columns][:MAX_COLUMNS],
            "rows": json.loads(head.to_json(orient="records",
                                            date_format="iso")),
            "row_count": len(head), "truncated": len(frame) > rows,
            "provenance": self._provenance(
                ctx, "local_file", filename=path.name,
                file_sha_pending=True, sampling=f"head({rows})"),
        }

    def _mongo_preview(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        client = _mongo_client_instance()
        if client is None:
            return {"source": "mongodb", "available": False,
                    "reason": "pymongo not installed"}
        database = _check_ident(args.get("database") or "", "database")
        collection = _check_ident(args.get("collection") or "", "collection")
        if not database or not collection:
            raise SqlRejected("database and collection are required")
        limit = min(int(args.get("rows") or 50), MAX_ROWS)
        docs = list(client[database][collection].find({}, limit=limit))
        return {
            "source": "mongodb", "object": f"{database}.{collection}",
            "rows": [{k: _jsonable(v) for k, v in list(d.items())[:MAX_COLUMNS]}
                     for d in docs],
            "row_count": len(docs), "row_limit": limit,
            "provenance": self._provenance(ctx, "mongodb",
                                            sampling=f"limit({limit})"),
        }


class DataQueryTool(_DataTool):
    name = "data.query"
    description = ("Execute an authorized READ-ONLY analytical SQL query. "
                   "Statements are validated by a conservative allowlist "
                   "(SELECT/WITH only); DDL, DML, multiple statements, "
                   "filesystem and server-side execution functions are "
                   "rejected. Row, column, size and time limits are enforced.")
    schema = {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "A single SELECT/WITH."},
            "params": {"type": "object",
                       "description": "Bound parameters; never interpolated."},
        },
        "required": ["sql"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            sql = args.get("sql") or ""
            params = args.get("params") or None
            data = _run_sql(sql, params if isinstance(params, dict) else None)
            data["source"] = "sql"
            data["provenance"] = self._provenance(
                ctx, "sql", query_hash=data["query_hash"],
                row_limit=MAX_ROWS, sampling="server_side_limit")
            return _ok(self.name, ctx, started, data,
                       {"rows": data["row_count"]})
        except QueryTimeout as exc:
            return _ok(self.name, ctx, started, {
                "status": "TIMEOUT", "rows": [], "row_count": 0,
                "statement_timeout_s": QUERY_TIMEOUT_S,
                "terminated_by": "postgresql statement_timeout",
                "reason": str(exc), "read_only_enforced": True,
            }, {"status": "TIMEOUT"})
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DataAggregateTool(_DataTool):
    name = "data.aggregate"
    description = ("Run safe analytical aggregation (count/sum/avg/min/max, "
                   "grouping, percentages, time-series) using database-side "
                   "GROUP BY so large datasets are never loaded into RAM.")
    schema = {
        "type": "object",
        "properties": {
            "table": {"type": "string"},
            "schema": {"type": "string"},
            "group_by": {"type": "array", "items": {"type": "string"}},
            "metrics": {
                "type": "array", "items": {"type": "string"},
                "description": "e.g. ['count', 'sum:amount', 'avg:amount', "
                               "'min:ts', 'max:ts', 'distinct:user']"},
            "where": {"type": "string",
                      "description": "Optional read-only WHERE fragment."},
            "having": {"type": "string"},
        },
        "required": ["table", "group_by", "metrics"],
    }
    # ``count`` needs no column; every other aggregate requires one.
    _AGG = re.compile(r"^(count|sum|avg|mean|min|max|median|stddev|variance|"
                      r"distinct|percentile)(?:\s*:\s*([A-Za-z_][\w.]*))?$", re.I)

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            schema_name = args.get("schema")
            table = _check_ident(args.get("table") or "", "table")
            qualified = (f"{_check_ident(schema_name, 'schema')}.{table}"
                         if schema_name else table)
            groups = list(args.get("group_by") or [])
            if len(groups) > 20:
                raise SqlRejected("too many group_by columns")
            group_sql = ", ".join(_check_ident(g, "group column") for g in groups)
            selects: list[str] = []
            for metric in args.get("metrics") or []:
                m = self._AGG.match(str(metric).strip())
                if not m:
                    raise SqlRejected(f"unsupported metric: {metric!r}")
                fn = m.group(1).lower()
                col = m.group(2)
                if fn == "count":
                    selects.append("COUNT(*) AS count")
                    continue
                if not col:
                    raise SqlRejected(
                        f"metric {fn!r} requires a column, e.g. '{fn}:amount'")
                col = _check_ident(col, "column")
                if fn == "distinct":
                    selects.append(f"COUNT(DISTINCT {col}) AS distinct_{col}")
                elif fn == "mean":
                    selects.append(f"AVG({col}) AS avg_{col}")
                elif fn == "median":
                    selects.append(f"PERCENTILE_CONT(0.5) WITHIN GROUP "
                                   f"(ORDER BY {col}) AS median_{col}")
                elif fn == "percentile":
                    selects.append(f"PERCENTILE_CONT(0.5) WITHIN GROUP "
                                   f"(ORDER BY {col}) AS p50_{col}")
                else:
                    selects.append(f"{fn.upper()}({col}) AS {fn}_{col}")
            if not selects:
                raise SqlRejected("at least one metric is required")
            where = str(args.get("where") or "").strip()
            if where:
                # The whole statement is re-validated below, so a malicious
                # fragment cannot smuggle DDL through.
                if re.search(r"[;]|--|/\*", where):
                    raise SqlRejected("illegal characters in where clause")
            sql = (f"SELECT {group_sql + ', ' if group_sql else ''}"
                   f"{', '.join(selects)} FROM {qualified}")
            if where:
                sql += f" WHERE {where}"
            if group_sql:
                sql += f" GROUP BY {group_sql}"
            having = str(args.get("having") or "").strip()
            if having:
                if re.search(r"[;]|--|/\*", having):
                    raise SqlRejected("illegal characters in having clause")
                sql += f" HAVING {having}"
            data = _run_sql(sql)
            data["source"] = "sql"
            data["object"] = qualified
            data["aggregation"] = "database_side"
            data["provenance"] = self._provenance(
                ctx, "sql", query_hash=data["query_hash"],
                row_limit=MAX_AGGREGATE_GROUPS)
            return _ok(self.name, ctx, started, data,
                       {"rows": data["row_count"]})
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DataProfileTool(_DataTool):
    name = "data.profile"
    description = ("Generate a real data profile: row count, null rates, "
                   "distinct counts, min/max and numeric statistics for a local "
                   "structured file or a bounded SQL table. Large inputs are "
                   "sampled and the sampling is reported.")
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local file."},
            "table": {"type": "string", "description": "SQL table."},
            "schema": {"type": "string"},
            "max_rows": {"type": "integer"},
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            if args.get("path"):
                frame, fmt, path = _load_frame(args["path"],
                                                MAX_PROFILE_ROWS)
                data = self._profile_frame(frame, ctx, f"file:{path.name}",
                                           max_rows=MAX_PROFILE_ROWS)
                data["format"] = fmt
            elif args.get("table"):
                table = _check_ident(args["table"], "table")
                qualified = (f"{_check_ident(args['schema'], 'schema')}.{table}"
                             if args.get("schema") else table)
                data = self._profile_sql(qualified, ctx)
            else:
                return _fail(self.name, ctx, started,
                             "either path or table is required")
            return _ok(self.name, ctx, started, data)
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")

    def _profile_frame(self, frame, ctx: ToolContext, source: str,
                       max_rows: int) -> dict[str, Any]:
        import numpy as np

        total = int(len(frame))
        sampled = total > max_rows
        work = frame.head(max_rows)
        columns: dict[str, Any] = {}
        for name in work.columns[:MAX_COLUMNS]:
            series = work[name]
            entry: dict[str, Any] = {
                "dtype": str(series.dtype),
                "null_count": int(series.isna().sum()),
                "null_rate": round(float(series.isna().mean()), 4),
                "distinct_count": int(series.nunique(dropna=True)),
            }
            if pd_is_numeric(series):
                values = series.dropna()
                if len(values):
                    entry.update({
                        "min": _jsonable(values.min()),
                        "max": _jsonable(values.max()),
                        "mean": round(float(values.mean()), 6),
                        "std": round(float(values.std()) if len(values) > 1
                                     else 0.0, 6),
                    })
            columns[str(name)] = entry
        dupes = int(work.duplicated().sum())
        return {
            "source": source, "row_count": total, "row_count_profiled":
                int(len(work)), "sampled": sampled,
            "sampling_note": (f"profiled the first {max_rows} of {total} rows"
                              if sampled else "entire dataset profiled"),
            "column_count": int(len(work.columns)),
            "duplicate_rows": dupes,
            "memory_bytes": int(work.memory_usage(deep=True).sum()),
            "columns": columns,
            "provenance": self._provenance(
                ctx, source, sampled=sampled, row_limit=max_rows),
        }

    def _profile_sql(self, qualified: str, ctx: ToolContext) -> dict[str, Any]:
        from sqlalchemy import text as sa_text

        engine = _engine()
        with engine.connect() as conn:
            count = conn.execute(sa_text(
                f"SELECT COUNT(*) FROM {qualified}")).scalar()
            cols = conn.execute(sa_text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = "
                "split_part(:q, '.', 2) ORDER BY ordinal_position"),
                {"q": qualified}).fetchall()
        return {
            "source": f"sql:{qualified}",
            "row_count": int(count or 0),
            "row_count_method": "database_side_count",
            "sampled": False,
            "column_count": len(cols),
            "columns": {c[0]: {"type": c[1], "nullable": c[2] == "YES"}
                        for c in cols[:MAX_COLUMNS]},
            "note": ("Column-level statistics require a bounded scan; use "
                     "data.aggregate for numeric summaries on large tables."),
            "provenance": self._provenance(ctx, f"sql:{qualified}"),
        }


def pd_is_numeric(series) -> bool:
    from pandas.api import types as pdt

    return bool(pdt.is_numeric_dtype(series) and not pdt.is_bool_dtype(series))


class DataAnalyzeTool(_DataTool):
    name = "data.analyze"
    description = ("Analyze bounded data through the EXISTING provider/model "
                   "fabric. Returns PROVIDER_UNAVAILABLE when no healthy "
                   "provider exists - never produces deterministic text "
                   "pretending to be AI analysis.")
    risk: RiskLevel = RiskLevel.NETWORK
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "sql": {"type": "string"},
            "question": {"type": "string"},
            "max_rows": {"type": "integer"},
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            question = args.get("question") or "Analyze this dataset."
            sample: dict[str, Any]
            if args.get("sql"):
                sample = _run_sql(args["sql"])
            elif args.get("path"):
                frame, fmt, path = _load_frame(args["path"], 2000)
                head = frame.head(min(int(args.get("max_rows") or 50), 200))
                sample = {"columns": [str(c) for c in head.columns],
                          "rows": json.loads(head.to_json(orient="records",
                                                          date_format="iso")),
                          "row_count": len(head), "source": f"file:{path.name}"}
            else:
                return _fail(self.name, ctx, started,
                             "either sql or path is required")

            payload = json.dumps(sample.get("rows") or [], default=str)[:20000]
            from .capability_tools import live_provider_status

            providers = live_provider_status()
            usable = [p for p, m in providers.items()
                      if not p.startswith("_") and m.get("available")]
            verified = [p for p in usable
                        if (providers[p] or {}).get("inference_verified")]
            candidates = verified or usable
            if not candidates:
                return _ok(self.name, ctx, started, {
                    "status": "PROVIDER_UNAVAILABLE",
                    "reason": "No healthy AI provider is available; no "
                               "analysis was produced.",
                    "analysis": None,
                }, {"available": False})

            from jarvis_backend.gateway import provider_gateway
            from .document_tools import _default_model

            errors: list[str] = []
            for provider_id in candidates:
                model = f"{provider_id}:{_default_model(provider_id, providers)}"
                try:
                    result = await provider_gateway.chat([{
                        "role": "user",
                        "content": (f"{question}\n\nDATA (JSON, "
                                    f"{sample.get('row_count')} rows, columns: "
                                    f"{sample.get('columns')}):\n{payload}")}],
                        model=model, system=None, timeout=120)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{provider_id}: {type(exc).__name__}: {exc}")
                    continue
                text = (result.get("content") or "").strip()
                if not text:
                    errors.append(f"{provider_id}: empty analysis")
                    continue
                return _ok(self.name, ctx, started, {
                    "status": "COMPLETED",
                    "analysis": text,
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "usage": result.get("usage"),
                    "latency_ms": result.get("latency_ms"),
                    "sample_rows_sent": sample.get("row_count"),
                    "source": sample.get("source"),
                    "provenance": self._provenance(
                        ctx, str(sample.get("source")),
                        query_hash=sample.get("query_hash"),
                        provider=result.get("provider"),
                        model=result.get("model"), ai_generated=True),
                }, {"rows": sample.get("row_count")})

            return _ok(self.name, ctx, started, {
                "status": "PROVIDER_UNAVAILABLE",
                "reason": "; ".join(errors[:3]),
                "analysis": None,
            }, {"available": False})
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DataCompareTool(_DataTool):
    name = "data.compare"
    description = ("Compare two local structured files or two bounded SQL "
                   "queries: schema differences, row counts, numeric column "
                   "means and per-key differences. Deterministic.")
    schema = {
        "type": "object",
        "properties": {
            "left": {"type": "string"}, "right": {"type": "string"},
            "left_sql": {"type": "string"}, "right_sql": {"type": "string"},
            "key": {"type": "string",
                    "description": "Optional key column for key-level diff."},
        },
        "required": [],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            if args.get("left") and args.get("right"):
                lf, lfmt, lpath = _load_frame(args["left"], 100_000)
                rf, rfmt, rpath = _load_frame(args["right"], 100_000)
            elif args.get("left_sql") and args.get("right_sql"):
                lf = pd_from_records(_run_sql(args["left_sql"]))
                rf = pd_from_records(_run_sql(args["right_sql"]))
                lfmt = rfmt = "sql"
                lpath = rpath = Path("query")
            else:
                return _fail(self.name, ctx, started,
                             "left/right paths or left_sql/right_sql required")
            lcols, rcols = set(map(str, lf.columns)), set(map(str, rf.columns))
            numeric: dict[str, Any] = {}
            for col in sorted(lcols & rcols):
                if pd_is_numeric(lf[col]) and pd_is_numeric(rf[col]):
                    lv, rv = lf[col].dropna(), rf[col].dropna()
                    if len(lv) and len(rv):
                        numeric[col] = {
                            "left_mean": round(float(lv.mean()), 6),
                            "right_mean": round(float(rv.mean()), 6),
                            "mean_delta": round(float(rv.mean() - lv.mean()), 6),
                        }
            result: dict[str, Any] = {
                "left": {"file": lpath.name, "format": lfmt,
                         "rows": int(len(lf)), "columns": sorted(lcols)},
                "right": {"file": rpath.name, "format": rfmt,
                          "rows": int(len(rf)), "columns": sorted(rcols)},
                "row_count_delta": int(len(rf) - len(lf)),
                "only_in_left": sorted(lcols - rcols),
                "only_in_right": sorted(rcols - lcols),
                "shared_columns": sorted(lcols & rcols),
                "numeric_comparison": numeric,
            }
            key = args.get("key")
            if key and key in lcols & rcols:
                kl, kr = set(lf[key].astype(str)), set(rf[key].astype(str))
                result["key_diff"] = {
                    "key_column": key,
                    "only_in_left": sorted(kl - kr)[:500],
                    "only_in_right": sorted(kr - kl)[:500],
                    "truncated": len(kl - kr) > 500 or len(kr - kl) > 500,
                }
            result["provenance"] = self._provenance(
                ctx, "comparison", left=str(lpath.name), right=str(rpath.name))
            return _ok(self.name, ctx, started, result)
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def pd_from_records(payload: dict[str, Any]):
    import pandas as pd

    return pd.DataFrame(payload.get("rows") or [],
                        columns=payload.get("columns") or None)


class DataExportTool(_DataTool):
    name = "data.export"
    description = ("Export an authorized bounded result to CSV, JSON, XLSX or "
                   "Parquet. Persistent outputs are registered in the existing "
                   "ArtifactRegistry with provenance.")
    risk: RiskLevel = RiskLevel.WRITE
    required_permissions: tuple[str, ...] = (DATA_DISCOVER, DATA_READ,
                                              DATA_EXPORT)
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local source file."},
            "sql": {"type": "string"},
            "output": {"type": "string"},
            "format": {"type": "string", "enum": ["csv", "json", "xlsx",
                                                  "parquet"]},
            "register_artifact": {"type": "boolean"},
        },
        "required": ["output", "format"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            fmt = (args.get("format") or "").lower()
            if args.get("sql"):
                frame = pd_from_records(_run_sql(args["sql"]))
                source = "sql"
            elif args.get("path"):
                frame, f, path = _load_frame(args["path"], MAX_PROFILE_ROWS)
                source = f"file:{path.name}"
            else:
                return _fail(self.name, ctx, started,
                             "either sql or path is required")
            from .document_tools import resolve_document

            out = resolve_document(args.get("output") or "")
            out.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "csv":
                frame.to_csv(out, index=False)
            elif fmt == "json":
                frame.to_json(out, orient="records", date_format="iso")
            elif fmt == "xlsx":
                frame.to_excel(out, index=False)
            elif fmt == "parquet":
                frame.to_parquet(out, index=False)
            else:
                return _fail(self.name, ctx, started,
                             f"unsupported export format: {fmt}")
            artifact = None
            if args.get("register_artifact", True):
                artifact = _register_output(out, fmt, ctx, source, int(len(frame)))
            return _ok(self.name, ctx, started, {
                "output": str(out), "format": fmt, "rows": int(len(frame)),
                "bytes_written": out.stat().st_size, "source": source,
                "artifact": artifact,
                "artifact_registry": "unavailable" if artifact is None
                else "registered",
            }, {"rows": int(len(frame))})
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _register_output(path: Path, fmt: str, ctx: ToolContext, source: str,
                     rows: int) -> Optional[dict[str, Any]]:
    try:
        import hashlib as _h

        from infrastructure.artifact_registry import (
            ArtifactInfo,
            get_artifact_registry,
        )
        digest = _h.sha256(path.read_bytes()).hexdigest()
        info = ArtifactInfo(
            artifact_id=f"data-{digest[:16]}",
            name=path.name,
            artifact_type="data_export",
            uri=str(path),
            size_bytes=path.stat().st_size,
            checksum=digest,
            metadata={"format": fmt, "source": source, "rows": rows,
                      "producing_capability": "data.export",
                      "capability_version": VERSION,
                      "request_id": ctx.request_id, "user_id": ctx.user_id},
        )
        return get_artifact_registry().register(info).to_dict()
    except Exception:  # noqa: BLE001
        return None


class DataVisualizeTool(_DataTool):
    name = "data.visualize"
    description = ("Render a real chart (line, bar, scatter, histogram) from "
                   "bounded data with matplotlib and persist it as a PNG, "
                   "registered in the ArtifactRegistry. Fabricates nothing.")
    risk: RiskLevel = RiskLevel.WRITE
    required_permissions: tuple[str, ...] = (DATA_DISCOVER, DATA_READ,
                                              DATA_EXPORT)
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"}, "sql": {"type": "string"},
            "chart": {"type": "string",
                      "enum": ["line", "bar", "scatter", "histogram"]},
            "x": {"type": "string"}, "y": {"type": "string"},
            "title": {"type": "string"},
            "output": {"type": "string"},
        },
        "required": ["chart", "output"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            args = args or {}
            if args.get("sql"):
                frame = pd_from_records(_run_sql(args["sql"]))
                source = "sql"
            elif args.get("path"):
                frame, f, path = _load_frame(args["path"], 50_000)
                source = f"file:{path.name}"
            else:
                return _fail(self.name, ctx, started,
                             "either sql or path is required")
            kind = (args.get("chart") or "bar").lower()
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            from .document_tools import resolve_document

            out = resolve_document(args.get("output") or "")
            out.parent.mkdir(parents=True, exist_ok=True)
            fig, ax = plt.subplots(figsize=(8, 5))
            x_col, y_col = args.get("x"), args.get("y")
            if kind == "histogram":
                col = x_col or str(frame.columns[0])
                ax.hist(frame[col].dropna(), bins=30)
                ax.set_xlabel(col)
            else:
                if not x_col:
                    return _fail(self.name, ctx, started, "x is required")
                if x_col not in frame.columns:
                    return _fail(self.name, ctx, started,
                                 f"column not present: {x_col}")
                if kind == "scatter":
                    if not y_col:
                        return _fail(self.name, ctx, started, "y is required")
                    ax.scatter(frame[x_col], frame[y_col], alpha=0.6)
                    ax.set_ylabel(y_col)
                else:
                    if y_col and y_col in frame.columns:
                        ax.plot(frame[x_col], frame[y_col], marker="o")
                        ax.set_ylabel(y_col)
                    else:
                        counts = frame[x_col].value_counts().head(30)
                        if kind == "bar":
                            ax.bar([str(i) for i in counts.index], counts.values)
                        else:
                            ax.plot(range(len(counts)), counts.values, marker="o")
                    ax.set_xticks(range(len(counts)))
                    ax.set_xticklabels([str(i) for i in counts.index],
                                       rotation=45, ha="right", fontsize=7)
                ax.set_xlabel(x_col)
            ax.set_title(str(args.get("title") or f"{kind} chart"))
            fig.tight_layout()
            fig.savefig(out, dpi=110)
            plt.close(fig)
            artifact = _register_output(out, "png", ctx, source, int(len(frame)))
            return _ok(self.name, ctx, started, {
                "chart": kind, "output": str(out),
                "bytes_written": out.stat().st_size, "source": source,
                "rows_plotted": int(len(frame)),
                "artifact": artifact,
                "artifact_registry": "unavailable" if artifact is None
                else "registered",
            }, {"rows": int(len(frame))})
        except SqlRejected as exc:
            return _fail(self.name, ctx, started, f"SQL rejected: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


class DataExplainTool(_DataTool):
    name = "data.sql_explain"
    description = ("Validate and EXPLAIN a read-only SQL statement WITHOUT "
                   "executing its body. Refuses anything the conservative "
                   "validator cannot prove is read-only.")
    schema = {
        "type": "object",
        "properties": {"sql": {"type": "string"},
                       "run_explain": {"type": "boolean"}},
        "required": ["sql"],
    }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            sql = (args or {}).get("sql") or ""
            statement, relations = validate_analytics_sql(sql)
            out: dict[str, Any] = {
                "valid": True, "read_only": True,
                "query_hash": query_hash(statement),
                "statement_preview": statement[:500],
                "relations": relations,
                "executed": False,
                "note": ("Validation only. Use data.query to run a read-only "
                         "statement."),
            }
            if (args or {}).get("run_explain", True):
                try:
                    from sqlalchemy import text as sa_text

                    engine = _engine()
                    dialect = engine.dialect.name
                    conn = engine.connect()
                    try:
                        txn = conn.begin()
                        try:
                            # Same guards as data.query, so EXPLAIN cannot be a
                            # way to execute unbounded work.
                            guards = _apply_guards(conn, dialect)
                            conn.execute(sa_text("EXPLAIN " + statement))
                            txn.commit()
                        except Exception:
                            try:
                                txn.rollback()
                            except Exception:  # noqa: BLE001
                                pass
                            raise
                    finally:
                        try:
                            if conn.in_transaction():
                                conn.rollback()
                        except Exception:  # noqa: BLE001
                            pass
                        # Connection-scoped on SQLite: must be cleared.
                        if dialect == "sqlite":
                            try:
                                conn.exec_driver_sql("PRAGMA query_only = OFF")
                            except Exception:  # noqa: BLE001
                                pass
                        conn.close()
                    out["plan_available"] = True
                    out["explain_executed"] = True
                    out["executed"] = False
                    out["read_only_enforced"] = guards["read_only_enforced"]
                    out["read_only_by"] = guards["read_only_by"]
                    out["timeout_enforced"] = guards["timeout_enforced"]
                    out["statement_timeout_s"] = guards["statement_timeout_s"]
                except Exception as exc:  # noqa: BLE001
                    out["plan_available"] = False
                    if _is_timeout(exc):
                        out["status"] = "TIMEOUT"
                        out["statement_timeout_s"] = QUERY_TIMEOUT_S
                    out["explain_note"] = f"{type(exc).__name__}: {exc}"
            out["provenance"] = self._provenance(ctx, "sql_validator",
                                                query_hash=out["query_hash"])
            return _ok(self.name, ctx, started, out)
        except SqlRejected as exc:
            return _ok(self.name, ctx, started, {
                "valid": False, "read_only": False, "executed": False,
                "reason": str(exc), "query_hash": query_hash(sql or ""),
            }, {"valid": False})
        except Exception as exc:  # noqa: BLE001
            return _fail(self.name, ctx, started, f"{type(exc).__name__}: {exc}")


def _dep_state(module_name: str) -> str:
    """Truthfully probe an optional dependency."""
    try:
        module = __import__(module_name)
    except Exception:  # noqa: BLE001
        return "UNAVAILABLE"
    version = getattr(module, "__version__", None)
    return "AVAILABLE" if version is not None or module else "AVAILABLE"


def _probe_dependencies() -> dict[str, Any]:
    """Real import probes - never hardcoded availability claims."""
    deps: dict[str, Any] = {}
    for mod in ("sqlalchemy", "psycopg2", "pymongo", "pandas", "numpy",
                "matplotlib", "pyarrow", "openpyxl"):
        state = _dep_state(mod)
        entry: dict[str, Any] = {"state": state}
        if state == "AVAILABLE":
            try:
                entry["version"] = getattr(__import__(mod), "__version__", "unknown")
            except Exception:  # noqa: BLE001
                entry["version"] = "unknown"
        else:
            entry["reason"] = f"{mod} is not importable in this environment"
        deps[mod] = entry
    for mod in ("sqlglot", "sqlparse"):
        state = _dep_state(mod)
        deps[f"{mod}_parser"] = {
            "state": state,
            "reason": (None if state == "AVAILABLE" else
                       f"{mod} is not installed; a conservative allowlist "
                       f"validator is used instead of pretending arbitrary SQL "
                       f"is safe."),
        }
    # Stable, pre-existing status keys. A real SQL parser is deliberately NOT
    # claimed: the validator is a conservative allowlist, and discovery callers
    # rely on these keys to decide whether parsing is trustworthy.
    deps["sql_parser"] = any(
        deps[f"{m}_parser"]["state"] == "AVAILABLE" for m in ("sqlglot", "sqlparse"))
    deps["sql_parser_note"] = (
        "no third-party SQL parser is installed; SQL is validated by a "
        "conservative allowlist validator plus a deny-by-default relation "
        "allowlist, so arbitrary SQL is never assumed safe."
    )
    deps["relation_authorization"] = {
        "mode": "allowlist", "default": "DENY",
        "allowed": sorted(ALLOWED_RELATIONS),
        "denied_schemas": sorted(DENIED_SCHEMAS),
    }
    return deps


def _capability_availability() -> dict[str, Any]:
    """Per-capability availability derived from REAL probes, not assumptions.

    One unavailable dependency never takes down the domain: PostgreSQL being
    down leaves local-file analytics AVAILABLE, and a missing plotting library
    only marks data.visualize UNAVAILABLE with a truthful reason.
    """
    sql = _sql_source()
    mongo = _mongo_source()
    local = _local_source()
    deps = _probe_dependencies()
    provider_ok, provider_reason, provider_detail = _provider_health()

    def dep(name: str) -> bool:
        return deps.get(name, {}).get("state") == "AVAILABLE"

    offline = "AVAILABLE"           # deterministic local analytics always work
    sql_state = "AVAILABLE" if sql.get("available") else (
        "NOT_CONFIGURED" if not sql.get("driver") else "UNAVAILABLE")
    mongo_state = "AVAILABLE" if mongo.get("available") else (
        "NOT_CONFIGURED" if "MONGODB" not in
        " ".join(f"{k}={v}" for k, v in os.environ.items()
                 if k in _MONGO_URL_VARS) else "UNAVAILABLE")

    def entry(state: str, reason: str | None = None) -> dict[str, Any]:
        return {"availability": state, "reason": reason}

    # A reachable local file is a real data source: a dead database must not
    # make discovery itself report as broken.
    any_source = bool(sql.get("available") or mongo.get("available")
                      or local.get("available"))
    return {
        "data.sources": entry("AVAILABLE" if any_source else "UNAVAILABLE",
                              None if any_source else
                              "no data source is currently reachable"),
        "data.schema": entry(sql_state, sql.get("error")),
        "data.preview": entry(sql_state, sql.get("error")),
        "data.query": entry(sql_state, sql.get("error")),
        "data.aggregate": entry(sql_state, sql.get("error")),
        "data.sql_explain": entry(sql_state, sql.get("error")),
        "data.profile": entry(offline if dep("pandas") else "UNAVAILABLE",
                              None if dep("pandas") else "pandas is not installed"),
        "data.compare": entry(offline if dep("pandas") else "UNAVAILABLE",
                              None if dep("pandas") else "pandas is not installed"),
        "data.analyze": entry("AVAILABLE" if provider_ok else "NOT_CONFIGURED",
                              None if provider_ok else provider_reason),
        "data.export": entry("AVAILABLE" if dep("pandas") else "UNAVAILABLE",
                             None if dep("pandas") else "pandas is not installed"),
        "data.export.parquet": entry("AVAILABLE" if dep("pyarrow") else "UNAVAILABLE",
                                     None if dep("pyarrow") else
                                     "pyarrow is not installed; parquet export is "
                                     "unavailable, other formats still work"),
        "data.visualize": entry("AVAILABLE" if dep("matplotlib") else "UNAVAILABLE",
                                None if dep("matplotlib") else
                                "matplotlib is not installed; charts are not "
                                "fabricated without a real plotting backend"),
        "mongodb_state": mongo_state,
        "local_files": local,
        "providers": provider_detail,
    }


def _provider_health() -> tuple[bool, str | None, dict[str, Any]]:
    """Single live provider health probe -> (available, reason, per-provider)."""
    detail = _provider_status_detail()
    if "_error" in detail:
        return False, f"provider fabric unavailable: {detail['_error']}", detail
    if not detail:
        return False, "no provider is registered in the control center", detail
    ready = sorted(pid for pid, st in detail.items()
                   if isinstance(st, dict) and st.get("available"))
    if ready:
        return True, None, detail
    states = sorted({st.get("state") for st in detail.values()
                     if isinstance(st, dict) and st.get("state")})
    return False, ("no provider reports an available model; observed states: "
                   + (", ".join(states) if states else "unknown")), detail


def _provider_available() -> tuple[bool, str | None]:
    """Use the EXISTING provider health fabric - never a bespoke check.

    Reuses ``research_engine.capability_tools.live_provider_status()``, which is
    the same live ``ProviderControlCenter`` probe behind ``provider.status``.
    Constructing a gateway object is deliberately NOT treated as availability:
    an importable interface says nothing about whether a model can answer.
    """
    ok, reason, _ = _provider_health()
    return ok, reason


def _provider_status_detail() -> dict[str, Any]:
    """Per-provider availability for the truthful status report."""
    try:
        from research_engine.capability_tools import live_provider_status

        return live_provider_status()
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}


def data_capability_status() -> dict[str, Any]:
    """Truthful dependency + source report for the data domain."""
    return {
        "version": VERSION,
        "sql": _sql_source(),
        "mongodb": _mongo_source(),
        "local_files": _local_source(),
        "dependencies": _probe_dependencies(),
        "capability_availability": _capability_availability(),
        "relation_authorization": {
            "mode": "allowlist",
            "default": "DENY",
            "allowed": sorted(allowed_relations()),
            "denied_schemas": sorted(DENIED_SCHEMAS),
        },
        "limits": {
            "max_rows": MAX_ROWS, "max_columns": MAX_COLUMNS,
            "max_response_bytes": MAX_RESPONSE_BYTES,
            "max_profile_rows": MAX_PROFILE_ROWS,
            "max_aggregate_groups": MAX_AGGREGATE_GROUPS,
            "query_timeout_s": QUERY_TIMEOUT_S,
            "query_timeout_enforced_by": "postgresql SET LOCAL statement_timeout",
            "server_side_timeout_available": _sql_source().get("driver")
            == "postgresql",
            "note": ("statement_timeout is a PostgreSQL server feature. On the "
                     "SQLite fallback the read-only backstop is PRAGMA "
                     "query_only and NO server-side query timeout exists; "
                     "queries are bounded by row/size limits only."),
        },
        "permissions": {
            "discover": DATA_DISCOVER, "read": DATA_READ,
            "analyze": DATA_ANALYZE, "export": DATA_EXPORT,
            "write": DATA_WRITE,
            "default": list(DEFAULT_PERMISSIONS),
            "enforced_by": "research_engine.tool_registry.ToolRegistry.authorize",
            "note": ("DATA_WRITE is never granted by a data capability in this "
                     "domain; ingestion/mutation is not implemented."),
        },
    }


DATA_TOOLS = (
    DataSourcesTool, DataSchemaTool, DataPreviewTool, DataQueryTool,
    DataAggregateTool, DataProfileTool, DataAnalyzeTool, DataCompareTool,
    DataExportTool, DataVisualizeTool, DataExplainTool,
)


__all__ = [
    "DataSourcesTool", "DataSchemaTool", "DataPreviewTool", "DataQueryTool",
    "DataAggregateTool", "DataProfileTool", "DataAnalyzeTool",
    "DataCompareTool", "DataExportTool", "DataVisualizeTool",
    "DataExplainTool", "DATA_TOOLS", "data_capability_status",
    "validate_readonly_sql", "validate_analytics_sql", "SqlRejected",
    "RelationNotAuthorized", "QueryTimeout",
    "authorize_relations", "extract_relations", "allowed_relations",
    "ALLOWED_RELATIONS", "DENIED_SCHEMAS", "ANALYTICS_SCHEMA",
    "query_hash",
    "DATA_DISCOVER", "DATA_READ", "DATA_ANALYZE", "DATA_EXPORT", "DATA_WRITE",
    "VERSION",
]
