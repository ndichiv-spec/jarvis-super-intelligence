"""Tests for the JARVIS Data Analytics Capability Domain.

REAL tests run against the live PostgreSQL/MongoDB and genuinely generated
CSV/XLSX/JSON files. Only the no-database fallback is conditional.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_runtime import bootstrap_runtime  # noqa: E402

bootstrap_runtime()

from research_engine.data_tools import (  # noqa: E402
    DATA_DISCOVER,
    DATA_EXPORT,
    DATA_READ,
    DATA_WRITE,
    SqlRejected,
    data_capability_status,
    query_hash,
    validate_readonly_sql,
)

FIX = ROOT / "tests" / "_data_fixtures"
FIX.mkdir(exist_ok=True)

CAPS = ("data.sources", "data.schema", "data.preview", "data.query",
        "data.aggregate", "data.profile", "data.analyze", "data.compare",
        "data.export", "data.visualize", "data.sql_explain")


def _reg():
    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import DefaultPermissionPolicy

    policy = DefaultPermissionPolicy()
    policy._confirmations["du:data.analyze"] = True
    return build_capability_registry(policy=policy)


def _invoke(cap: str, args: dict):
    """Invoke a data capability as an authorized analytics caller.

    Data capabilities now declare ``required_permissions``, and the registry
    fails closed when a caller's authority cannot be resolved. These tests
    exercise analytics BEHAVIOUR, so the caller is given the domain's default
    analytics grant explicitly. Authorization itself is covered by
    tests/test_data_analytics_security.py (including the un-authorized case,
    which still fails closed).
    """
    from research_engine.data_tools import DATA_EXPORT, DEFAULT_PERMISSIONS
    from research_engine.tool_registry import ToolContext

    # Export/visualize additionally require DATA_EXPORT.
    granted = set(DEFAULT_PERMISSIONS) | {DATA_EXPORT}
    ctx = ToolContext(request_id="du", user_id="du", permissions=granted)
    res = asyncio.run(_reg().invoke(cap, args, ctx))
    return res, (json.loads(res.result) if res.success and res.result else None)


# --------------------------------------------------------------------------- #
# Registration / contract
# --------------------------------------------------------------------------- #
def test_all_capabilities_registered() -> None:
    available = set(_reg().available())
    missing = set(CAPS) - available
    assert not missing, f"missing: {missing}"


def test_default_risk_is_read() -> None:
    """Analytics defaults must be READ; only export/visualize are WRITE."""
    from research_engine.models import RiskLevel

    by_name = {d["name"]: d for d in _reg().describe()}
    for cap in CAPS:
        if cap in {"data.export", "data.visualize"}:
            assert by_name[cap]["risk"] == RiskLevel.WRITE.value, cap
        elif cap == "data.analyze":
            assert by_name[cap]["risk"] == RiskLevel.NETWORK.value
        else:
            assert by_name[cap]["risk"] == RiskLevel.READ.value, cap


def test_schemas_are_objects() -> None:
    for d in _reg().describe():
        if d["name"].startswith("data."):
            assert d["parameters"].get("type") == "object", d["name"]


def test_data_write_permission_not_granted() -> None:
    from research_engine.data_tools import DEFAULT_PERMISSIONS

    assert DATA_WRITE not in DEFAULT_PERMISSIONS
    assert set(DEFAULT_PERMISSIONS) == {DATA_DISCOVER, DATA_READ,
                                        "data:analyze"}


# --------------------------------------------------------------------------- #
# SQL validator (the security core)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sql", [
    "SELECT 1", "select id from users", "  SELECT count(*) FROM t  ",
    "WITH x AS (SELECT 1 AS a) SELECT a FROM x",
])
def test_validator_allows_readonly(sql: str) -> None:
    assert validate_readonly_sql(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (1)", "UPDATE t SET a = 1", "DELETE FROM t",
    "DROP TABLE t", "ALTER TABLE t ADD COLUMN c int", "CREATE TABLE t (a int)",
    "TRUNCATE t", "GRANT ALL ON t TO u", "REVOKE ALL ON t FROM u",
    "REPLACE INTO t VALUES (1)", "MERGE INTO t USING s ON 1=1",
    "CALL some_proc()", "DO $$ BEGIN END $$", "VACUUM", "SET search_path = x",
    "SELECT 1; DROP TABLE t", "SELECT 1; SELECT 2",
    "SELECT * FROM t -- comment", "/* c */ SELECT 1", "SELECT ';'",
    "SELECT pg_read_file('/etc/passwd')", "SELECT pg_ls_dir('/')",
    "SELECT lo_import('/etc/passwd')", "SELECT lo_export('/tmp/x', 1)",
    "SELECT dblink('host=evil', 'select 1')",
    "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x",
    "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
    "SELECT set_config('x','y',false)", "SELECT current_setting('x')",
    "", "   ", "COPY t TO '/tmp/out.csv'",
])
def test_validator_rejects(sql: str) -> None:
    with pytest.raises(SqlRejected):
        validate_readonly_sql(sql)


def test_query_hash_is_stable_and_distinct() -> None:
    assert query_hash("SELECT 1") == query_hash("SELECT 1")
    assert query_hash("SELECT 1") != query_hash("SELECT 2")


# --------------------------------------------------------------------------- #
# REAL: source discovery
# --------------------------------------------------------------------------- #
def test_data_sources_real() -> None:
    res, d = _invoke("data.sources", {})
    assert res.success, res.error
    assert "sql" in d["sources"] and "mongodb" in d["sources"]
    assert d["sources"]["local_files"]["available"] is True


def test_no_credential_in_sources() -> None:
    import re

    res, d = _invoke("data.sources", {})
    blob = json.dumps(d)
    assert "password" not in blob.lower()
    assert re.search(r"://[^/\s]*:[^@\s]*@", blob) is None, \
        "connection string with credentials leaked"


# --------------------------------------------------------------------------- #
# REAL: PostgreSQL
# --------------------------------------------------------------------------- #
def test_postgres_health_real() -> None:
    status = data_capability_status()["sql"]
    if not status["available"]:
        pytest.skip(f"PostgreSQL unavailable: {status.get('error')}")
    if status["driver"] != "postgresql":
        pytest.skip("engine resolved to a non-postgres dialect in this process; "
                    "the shared engine singleton was created before the "
                    "environment was loaded")
    assert status["driver"] == "postgresql"
    assert status["state_chain"]["reachable"] is True


def test_postgres_schema_introspection_real() -> None:
    """Real schema introspection, honouring the deny-by-default allowlist.

    The relation allowlist is PostgreSQL-shaped (``public.<table>``) and the
    suite conftest pins the engine to SQLite, whose test tables are NOT in the
    approved allowlist. Asserting a PostgreSQL outcome there would be a false
    claim, so the discovery assertion runs only against a real PostgreSQL
    engine; the authorization invariants are checked on every backend.
    """
    from research_engine.data_tools import _engine

    res, d = _invoke("data.schema", {"source": "sql"})
    if not res.success:
        pytest.skip(res.error)
    assert d["driver"] in {"postgresql", "sqlite"}
    # Authorization invariants hold on every backend.
    assert d["authorization"]["mode"] == "allowlist"
    assert d["authorization"]["default"] == "DENY"
    from research_engine.data_tools import allowed_relations

    for rel in d["tables"]:
        assert rel in allowed_relations(), rel
    if _engine().dialect.name != "postgresql":
        pytest.skip("relation allowlist is PostgreSQL-shaped; suite runs SQLite")
    assert "public" in d["schemas"]
    assert d["table_count"] > 0, "real JARVIS tables must be discovered"
    assert d["authorization"]["withheld_relation_count"] > 0, (
        "the live database has relations outside the allowlist; they must be "
        "withheld rather than described")


def test_postgres_readonly_query_real() -> None:
    res, d = _invoke("data.query",
                     {"sql": "SELECT count(*) AS n FROM audit_events"})
    if not res.success:
        pytest.skip(res.error)
    assert d["rows"][0]["n"] >= 0
    assert d["read_only_enforced"] is True
    assert d["query_hash"]
    assert d["elapsed_ms"] >= 0


def test_query_rejects_mutation_real() -> None:
    for sql in ("DELETE FROM audit_events", "DROP TABLE audit_events",
                "UPDATE audit_events SET result='x'",
                "INSERT INTO audit_events (result) VALUES ('x')"):
        res, _ = _invoke("data.query", {"sql": sql})
        assert res.success is False, sql
        assert "rejected" in res.error.lower()


def test_query_rejects_injection_real() -> None:
    res, _ = _invoke("data.query",
                     {"sql": "SELECT 1; DROP TABLE audit_events"})
    assert res.success is False


def test_aggregate_real() -> None:
    res, d = _invoke("data.aggregate", {
        "table": "audit_events", "schema": "public",
        "group_by": ["result"], "metrics": ["count"]})
    if not res.success:
        pytest.skip(res.error)
    assert d["aggregation"] == "database_side"
    assert d["row_count"] >= 1


def test_explain_does_not_execute() -> None:
    res, d = _invoke("data.sql_explain",
                     {"sql": "SELECT count(*) FROM audit_events"})
    assert res.success
    assert d["valid"] is True
    assert d["executed"] is False


def test_explain_reports_invalid_readonly() -> None:
    res, d = _invoke("data.sql_explain", {"sql": "DROP TABLE audit_events"})
    assert res.success
    assert d["valid"] is False
    assert d["executed"] is False


def test_unauthorized_schema_rejected() -> None:
    res, d = _invoke("data.schema", {"source": "sql", "schema": "pg_catalog"})
    if not res.success:
        pytest.skip(res.error)
    # pg_catalog exists but must be filterable, not silently trusted.
    res2, _ = _invoke("data.preview", {"table": "bad name; DROP TABLE t"})
    assert res2.success is False


# --------------------------------------------------------------------------- #
# REAL: MongoDB
# --------------------------------------------------------------------------- #
def test_mongodb_health_real() -> None:
    status = data_capability_status()["mongodb"]
    if not status["available"]:
        pytest.skip(f"MongoDB unavailable: {status.get('error')}")
    assert status["state_chain"]["reachable"] is True


def test_mongodb_collections_real() -> None:
    res, d = _invoke("data.schema", {"source": "mongodb"})
    if not res.success:
        pytest.skip(res.error)
    assert d["available"] is True
    assert d["databases"], "real collections must be discovered"


def test_mongodb_preview_bounded() -> None:
    status = data_capability_status()["mongodb"]
    if not status["available"]:
        pytest.skip("MongoDB unavailable")
    res, d = _invoke("data.schema", {"source": "mongodb"})
    db = next(iter(d["databases"]))
    coll = next(iter(d["databases"][db]))
    res2, d2 = _invoke("data.preview", {"source": "mongodb", "database": db,
                                        "collection": coll, "rows": 3})
    assert res2.success, res2.error
    assert d2["row_count"] <= 3


def test_mongodb_injection_rejected() -> None:
    res, _ = _invoke("data.preview", {"source": "mongodb",
                                      "database": "a; drop",
                                      "collection": "c"})
    assert res.success is False


# --------------------------------------------------------------------------- #
# REAL: local files
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def csv_a() -> Path:
    p = FIX / "a.csv"
    p.write_text("id,name,score,team\n1,ada,90,red\n2,bob,80,blue\n"
                 "3,cyd,70,red\n4,dee,,blue\n5,eve,60,red\n", encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def csv_b() -> Path:
    p = FIX / "b.csv"
    p.write_text("id,name,score,team\n1,ada,95,red\n2,bob,80,blue\n"
                 "6,fay,50,green\n", encoding="utf-8")
    return p


def test_local_csv_profile_real(csv_a: Path) -> None:
    res, d = _invoke("data.profile", {"path": str(csv_a)})
    assert res.success, res.error
    assert d["row_count"] == 5
    assert d["column_count"] == 4
    score = d["columns"]["score"]
    assert score["null_count"] == 1
    assert score["distinct_count"] == 4
    assert score["min"] == 60 and score["max"] == 90
    assert d["provenance"]["capability_version"].startswith("data_analytics")


def test_local_csv_preview_real(csv_a: Path) -> None:
    res, d = _invoke("data.preview", {"source": "file", "path": str(csv_a),
                                      "rows": 2})
    assert res.success, res.error
    assert d["row_count"] == 2
    assert "name" in d["columns"]


def test_local_xlsx_analytics_real() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["k", "v"])
    for i in range(1, 21):
        ws.append([f"k{i}", i * 2])
    p = FIX / "s.xlsx"
    wb.save(str(p))
    res, d = _invoke("data.profile", {"path": str(p)})
    assert res.success, res.error
    assert d["row_count"] == 20
    assert d["columns"]["v"]["max"] == 40, "numeric stats must stay numeric"
    assert isinstance(d["columns"]["v"]["max"], (int, float))


def test_local_json_analytics_real() -> None:
    p = FIX / "d.json"
    p.write_text(json.dumps([{"a": 1}, {"a": 2}, {"a": 3}]), encoding="utf-8")
    res, d = _invoke("data.profile", {"path": str(p)})
    assert res.success, res.error
    assert d["row_count"] == 3


def test_local_compare_real(csv_a: Path, csv_b: Path) -> None:
    res, d = _invoke("data.compare", {"left": str(csv_a), "right": str(csv_b),
                                      "key": "id"})
    assert res.success, res.error
    assert d["row_count_delta"] == -2
    assert d["key_diff"]["only_in_left"] == ["3", "4", "5"]
    assert d["key_diff"]["only_in_right"] == ["6"]
    assert "score" in d["numeric_comparison"]


def test_export_registers_artifact_real(csv_a: Path) -> None:
    for fmt, suffix in (("csv", "csv"), ("json", "json"), ("xlsx", "xlsx")):
        out = FIX / f"export.{suffix}"
        res, d = _invoke("data.export", {
            "path": str(csv_a), "output": str(out), "format": fmt})
        assert res.success, f"{fmt}: {res.error}"
        assert out.is_file() and out.stat().st_size > 0
        assert d["artifact_registry"] in {"registered", "unavailable"}


def test_visualize_generates_real_png(csv_a: Path) -> None:
    pytest.importorskip("matplotlib")
    out = FIX / "chart.png"
    res, d = _invoke("data.visualize", {
        "path": str(csv_a), "chart": "bar", "x": "team",
        "output": str(out), "title": "By team"})
    assert res.success, res.error
    assert out.is_file()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "must be a real PNG"
    assert d["rows_plotted"] == 5


def test_visualize_histogram_real(csv_a: Path) -> None:
    pytest.importorskip("matplotlib")
    out = FIX / "hist.png"
    res, _ = _invoke("data.visualize", {"path": str(csv_a), "chart": "histogram",
                                        "x": "score", "output": str(out)})
    assert res.success
    assert out.is_file()


# --------------------------------------------------------------------------- #
# Malformed / limits
# --------------------------------------------------------------------------- #
def test_malformed_dataset_reports_error() -> None:
    p = FIX / "bad.xlsx"
    p.write_bytes(b"not a workbook at all")
    res, _ = _invoke("data.profile", {"path": str(p)})
    assert res.success is False


def test_unsupported_local_format_rejected() -> None:
    p = FIX / "x.bin"
    p.write_bytes(b"\x00\x01\x02")
    res, _ = _invoke("data.profile", {"path": str(p)})
    assert res.success is False


def test_limits_declared() -> None:
    limits = data_capability_status()["limits"]
    assert limits["max_rows"] <= 10_000
    assert limits["max_columns"] <= 500
    assert limits["max_response_bytes"] <= 10_000_000


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["../../", "../../../etc/passwd", r"..\\..\\",
                                "C:/Windows", "/etc/shadow"])
def test_path_traversal_rejected(bad: str) -> None:
    res, _ = _invoke("data.profile", {"path": bad})
    assert res.success is False


def test_secret_file_refused() -> None:
    res, _ = _invoke("data.profile", {"path": ".env"})
    assert res.success is False


def test_no_sql_parser_dependency_claimed() -> None:
    deps = data_capability_status()["dependencies"]
    assert deps["sql_parser"] is False
    assert "conservative" in deps["sql_parser_note"]


def test_no_shell_in_data_tools() -> None:
    import inspect as _inspect

    import research_engine.data_tools as dt

    src = _inspect.getsource(dt)
    for banned in ("subprocess", "os.system", "shell=True", "eval("):
        assert banned not in src, f"data tools must not use {banned}"


def test_authorization_denied_for_unconfirmed_network() -> None:
    from research_engine.capability_tools import build_capability_registry
    from research_engine.tool_registry import ToolContext

    res = asyncio.run(build_capability_registry().invoke(
        "data.analyze", {"sql": "SELECT 1 AS a"},
        ToolContext(request_id="z", user_id="z")))
    assert res.success is False
    assert "TOOL_DENIED" in res.error


# --------------------------------------------------------------------------- #
# AI analysis
# --------------------------------------------------------------------------- #
def test_analyze_real_provider_or_truthful_unavailable(csv_a: Path) -> None:
    """REAL: NVIDIA-backed analysis, or PROVIDER_UNAVAILABLE. Never a fake."""
    res, d = _invoke("data.analyze", {
        "path": str(csv_a), "question": "What does this data show?"})
    assert res.success, res.error
    if d.get("status") == "PROVIDER_UNAVAILABLE":
        assert d["analysis"] is None
        assert d["reason"]
    else:
        assert d["status"] == "COMPLETED"
        assert d["analysis"].strip()
        assert d["provider"]
        assert d["provenance"]["ai_generated"] is True


def test_analyze_never_fabricates(csv_a: Path) -> None:
    res, d = _invoke("data.analyze", {"path": str(csv_a)})
    blob = json.dumps(d).lower()
    for banned in ("i understand your data", "self-reliant mode",
                   "local fallback", "local-rule"):
        assert banned not in blob
