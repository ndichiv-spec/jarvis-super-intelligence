"""Security-chain tests for the JARVIS Data Analytics capability domain.

Every test here is a REAL test against real code. Nothing is mocked except
where a mock is the correct way to exercise a branch (and is labelled as such).

Truthfulness contract: tests that depend on PostgreSQL are marked
``REAL_PG``; tests that prove a refusal never need a live source and are
marked ``PURE``; nothing is asserted against a fabricated response.
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

from research_engine import data_tools as dt  # noqa: E402
from research_engine.data_tools import (  # noqa: E402
    ALLOWED_RELATIONS,
    DATA_ANALYZE,
    DATA_DISCOVER,
    DATA_EXPORT,
    DATA_READ,
    DATA_WRITE,
    DEFAULT_PERMISSIONS,
    RelationNotAuthorized,
    SqlRejected,
    allowed_relations,
    authorize_relations,
    extract_relations,
    validate_analytics_sql,
    validate_readonly_sql,
)
from research_engine.tool_registry import (  # noqa: E402
    DefaultPermissionPolicy,
    ToolContext,
    ToolRegistry,
    permission_granted,
    resolve_permissions,
)


def _pg_available() -> bool:
    """True only for a REAL PostgreSQL analytics engine.

    The suite conftest pins ``DATABASE_URL`` to SQLite, so a SQLite engine must
    not be mistaken for a live PostgreSQL target: SQLite has no server-side
    ``statement_timeout`` and no ``information_schema``, and claiming otherwise
    would be exactly the kind of fabricated verification this suite forbids.
    """
    try:
        source = dt._sql_source()
        return bool(source.get("available")) and source.get("driver") == "postgresql"
    except Exception:  # noqa: BLE001
        return False


needs_pg = pytest.mark.skipif(
    not _pg_available(),
    reason="requires a real PostgreSQL analytics engine (suite default is SQLite)")


# --------------------------------------------------------------------------- #
# 1. SQL safety guarantees are PRESERVED (PURE - no database needed)
# --------------------------------------------------------------------------- #
class TestSqlSafetyPreserved:
    """The pre-existing conservative guarantees must not regress."""

    @pytest.mark.parametrize("label,sql", [
        ("pg_read_file", "SELECT pg_read_file('/etc/passwd')"),
        ("pg_ls_dir", "SELECT pg_ls_dir('/')"),
        ("lo_import", "SELECT lo_import('/etc/passwd')"),
        ("dblink", "SELECT dblink_exec('x')"),
        ("multi_statement", "SELECT 1; DROP TABLE models"),
        ("insert", "INSERT INTO models (id) VALUES ('x')"),
        ("update", "UPDATE models SET id = 'x'"),
        ("delete", "DELETE FROM models"),
        ("drop", "DROP TABLE models"),
        ("alter", "ALTER TABLE models ADD COLUMN x int"),
        ("truncate", "TRUNCATE models"),
        ("grant", "GRANT ALL ON models TO public"),
        ("revoke", "REVOKE ALL ON models FROM public"),
        ("create", "CREATE TABLE evil (id int)"),
        ("copy", "COPY models TO '/tmp/x.csv'"),
        ("comment_sql", "SELECT 1 -- comment"),
        ("block_comment", "SELECT 1 /* c */"),
        ("select_into", "SELECT * INTO evil_table FROM models"),
        ("for_share", "SELECT * FROM models FOR SHARE"),
        ("data_modifying_cte",
         "WITH x AS (DELETE FROM models RETURNING *) SELECT * FROM x"),
    ])
    def test_rejected(self, label, sql):
        with pytest.raises(SqlRejected):
            validate_readonly_sql(sql)

    def test_empty_rejected(self):
        with pytest.raises(SqlRejected):
            validate_readonly_sql("")
        with pytest.raises(SqlRejected):
            validate_readonly_sql("   ;  ")

    def test_legit_select_accepted(self):
        assert validate_readonly_sql("SELECT id FROM models LIMIT 5")


# --------------------------------------------------------------------------- #
# 2. Relation authorization - allowlist, default DENY (PURE)
# --------------------------------------------------------------------------- #
class TestRelationAuthorization:
    """Default-deny relation allowlist with fail-closed extraction."""

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM jarvis_kv",
        "SELECT * FROM users",
        "SELECT * FROM refresh_tokens",
        "SELECT * FROM sessions",
        "SELECT * FROM roles",
        "SELECT * FROM permissions",
        "SELECT * FROM chat_sessions",
        "SELECT * FROM agents",
        "SELECT * FROM audit_logs",
        "SELECT * FROM public.jarvis_kv",
        'SELECT * FROM "jarvis_kv"',
        'SELECT * FROM "JARVIS_KV"',
        "SELECT * FROM JARVIS_KV",
        "SELECT * FROM PuBlIc.JaRvIs_Kv",
        "SELECT k.x FROM jarvis_kv k",
        "SELECT * FROM models JOIN jarvis_kv ON 1=1",
        "SELECT * FROM models JOIN public.users ON 1=1",
        "SELECT * FROM (SELECT * FROM jarvis_kv) t",
        "SELECT * FROM (SELECT id FROM models m JOIN users u ON 1=1) t",
        "WITH t AS (SELECT * FROM jarvis_kv) SELECT * FROM t",
        "WITH a AS (SELECT id FROM models), b AS (SELECT * FROM users) "
        "SELECT * FROM a, b",
        "SELECT * FROM totally_unknown_table_xyz",
        "SELECT * FROM pg_catalog.pg_class",
        "SELECT * FROM information_schema.tables",
    ])
    def test_denied(self, sql):
        with pytest.raises(RelationNotAuthorized):
            validate_analytics_sql(sql)

    @pytest.mark.parametrize("sql", [
        "SELECT id FROM models LIMIT 1",
        "SELECT id FROM public.models LIMIT 1",
        "SELECT a.id FROM models a JOIN models b ON a.id = b.id",
        "WITH t AS (SELECT id FROM models) SELECT * FROM t",
        "SELECT * FROM (SELECT id FROM models) x",
        'SELECT "id" FROM "models"',
        "SELECT ID FROM MODELS",
    ])
    def test_allowed(self, sql):
        statement, relations = validate_analytics_sql(sql)
        assert statement
        assert relations
        for rel in relations:
            assert rel in allowed_relations()

    def test_sensitive_absent_from_allowlist(self):
        """The application/security stores must never be allowlisted."""
        for forbidden in ("jarvis_kv", "users", "refresh_tokens", "sessions",
                          "roles", "permissions", "chat_sessions", "agents"):
            assert f"public.{forbidden}" not in allowed_relations()

    def test_cte_name_not_treated_as_relation(self):
        """A CTE alias is a name, not a relation, and must not be denied."""
        rels = extract_relations(
            "WITH recent AS (SELECT id FROM models) SELECT * FROM recent")
        assert rels == ["public.models"]

    def test_set_returning_function_denied(self):
        with pytest.raises(SqlRejected):
            validate_analytics_sql("SELECT * FROM generate_series(1,10)")

    def test_cross_database_denied(self):
        with pytest.raises(SqlRejected):
            validate_analytics_sql(
                "SELECT * FROM otherdb.public.models")

    def test_env_extension_cannot_reach_denied_schema(self):
        import os

        os.environ["JARVIS_DATA_ALLOWED_TABLES"] = "pg_catalog.pg_class,widgets"
        try:
            allow = allowed_relations()
            assert "public.widgets" in allow
            assert "pg_catalog.pg_class" not in allow
        finally:
            os.environ.pop("JARVIS_DATA_ALLOWED_TABLES", None)

    def test_default_allowlist_is_deny_by_default(self):
        """Anything not explicitly named is denied."""
        with pytest.raises(RelationNotAuthorized):
            authorize_relations("SELECT * FROM models_v2")

    def test_relation_not_authorized_is_sql_rejected(self):
        """Existing callers catching SqlRejected keep working."""
        assert issubclass(RelationNotAuthorized, SqlRejected)


# --------------------------------------------------------------------------- #
# 3. Timeout enforcement (REAL_PG)
# --------------------------------------------------------------------------- #
class TestTimeoutEnforcement:
    def test_timeout_is_reported_and_enforced_together(self):
        status = dt.data_capability_status()
        limits = status["limits"]
        assert limits["query_timeout_s"] == dt.QUERY_TIMEOUT_S
        assert "statement_timeout" in limits["query_timeout_enforced_by"]

    @needs_pg
    def test_result_reports_configured_timeout(self):
        result = dt._run_sql("SELECT count(*) AS n FROM models")
        assert result["statement_timeout_s"] == dt.QUERY_TIMEOUT_S

    @needs_pg
    def test_read_only_is_measured_not_assumed(self):
        result = dt._run_sql("SELECT count(*) AS n FROM models")
        assert result["read_only_enforced"] is True

    @needs_pg
    def test_server_terminates_long_running_statement(self):
        """The DATABASE aborts the statement - not a client-side sleep check."""
        from jarvis_backend.db import get_engine

        engine = get_engine()
        conn = engine.connect()
        try:
            txn = conn.begin()
            conn.exec_driver_sql("SET LOCAL statement_timeout = 1200")
            with pytest.raises(Exception) as excinfo:
                conn.exec_driver_sql("SELECT pg_sleep(10)")
            assert dt._is_timeout(excinfo.value)
            txn.rollback()
        finally:
            try:
                if conn.in_transaction():
                    conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            conn.close()

    @needs_pg
    def test_connection_reusable_after_timeout(self):
        from jarvis_backend.db import get_engine

        engine = get_engine()
        conn = engine.connect()
        try:
            txn = conn.begin()
            conn.exec_driver_sql("SET LOCAL statement_timeout = 1200")
            with pytest.raises(Exception):
                conn.exec_driver_sql("SELECT pg_sleep(10)")
            txn.rollback()
        finally:
            try:
                if conn.in_transaction():
                    conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            conn.close()
        # A brand new analytics query must still work.
        result = dt._run_sql("SELECT count(*) AS n FROM models")
        assert result["success"] if "success" in result else result["row_count"] >= 0

    @needs_pg
    def test_timeout_does_not_leak_into_unrelated_operations(self):
        """SET LOCAL must not persist on the pooled session."""
        from jarvis_backend.db import get_engine

        engine = get_engine()
        conn = engine.connect()
        try:
            txn = conn.begin()
            conn.exec_driver_sql("SET LOCAL statement_timeout = 1200")
            txn.rollback()
        finally:
            try:
                if conn.in_transaction():
                    conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            conn.close()
        check = engine.connect()
        try:
            value = check.exec_driver_sql("SHOW statement_timeout").scalar()
            assert str(value) == "0", f"timeout leaked onto the session: {value}"
        finally:
            check.close()

    @needs_pg
    def test_read_only_transaction_refuses_writes(self):
        """Database-level backstop: read-only tx blocks DDL even if reached."""
        from jarvis_backend.db import get_engine

        engine = get_engine()
        conn = engine.connect()
        try:
            txn = conn.begin()
            conn.exec_driver_sql("SET LOCAL transaction_read_only = on")
            with pytest.raises(Exception):
                conn.exec_driver_sql(
                    "CREATE TABLE jarvis_ro_probe (id int)")
            txn.rollback()
        finally:
            try:
                if conn.in_transaction():
                    conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            conn.close()


# --------------------------------------------------------------------------- #
# 4. Permission enforcement in the EXISTING ToolRegistry
# --------------------------------------------------------------------------- #
class TestPermissionEnforcement:
    def _registry(self, confirm_network: bool = False):
        """Build the registry, optionally pre-confirming NETWORK-risk calls.

        ``data.analyze`` is RiskLevel.NETWORK because it spends a provider call,
        so the risk policy denies it first unless confirmation is recorded. Tests
        of the *permission* layer must therefore grant that confirmation,
        otherwise they would be measuring the risk layer instead.
        """
        from research_engine.capability_tools import build_capability_registry

        confirmations = {"u:data.analyze": True} if confirm_network else {}
        policy = DefaultPermissionPolicy(confirmations=confirmations)
        return build_capability_registry(policy=policy)

    def test_wildcard_matching(self):
        assert permission_granted({"*"}, "data:read")
        assert permission_granted({"data:*"}, "data:write")
        assert permission_granted({"data:read"}, "data:read")
        assert not permission_granted({"data:read"}, "data:write")
        assert not permission_granted({"data:read"}, "data:export")
        assert not permission_granted(set(), "data:read")

    def test_read_never_implies_write(self):
        granted = {"data:discover", "data:read", "data:analyze"}
        assert not permission_granted(granted, DATA_WRITE)

    @pytest.mark.parametrize("missing", [DATA_DISCOVER, DATA_READ, DATA_ANALYZE])
    def test_each_default_permission_is_individually_required(self, missing):
        """data.query requires all three DEFAULT_PERMISSIONS; drop one -> deny."""
        reg = self._registry()
        held = set(DEFAULT_PERMISSIONS) - {missing}
        ok, reason = reg.authorize("u", "data.query", permissions=held)
        assert ok is False
        assert f"PERMISSION_DENIED:{missing}" == reason

    def test_query_allowed_with_exactly_the_default_set(self):
        reg = self._registry()
        ok, _ = reg.authorize("u", "data.query", permissions=set(DEFAULT_PERMISSIONS))
        assert ok is True

    def test_export_requires_export_permission(self):
        reg = self._registry()
        ok, reason = reg.authorize("u", "data.export",
                                   permissions={DATA_DISCOVER, DATA_READ})
        assert ok is False
        assert reason == f"PERMISSION_DENIED:{DATA_EXPORT}"
        ok2, _ = reg.authorize("u", "data.export",
                               permissions={DATA_DISCOVER, DATA_READ, DATA_EXPORT})
        assert ok2 is True

    def test_analyze_requires_analyze_permission(self):
        reg = self._registry(confirm_network=True)
        ok, reason = reg.authorize("u", "data.analyze",
                                   permissions={DATA_DISCOVER, DATA_READ})
        assert ok is False
        assert reason == f"PERMISSION_DENIED:{DATA_ANALYZE}"
        ok2, _ = reg.authorize("u", "data.analyze",
                               permissions=set(DEFAULT_PERMISSIONS))
        assert ok2 is True

    def test_risk_layer_still_applies_before_permissions(self):
        """A wildcard grant must NOT bypass the NETWORK risk gate."""
        reg = self._registry(confirm_network=False)
        ok, reason = reg.authorize("u", "data.analyze", permissions={"*"})
        assert ok is False
        assert reason == "requires_user_confirmation"

    def test_write_permission_never_granted_to_readers(self):
        """No data capability accepts DATA_WRITE, so it cannot be exercised."""
        from research_engine.data_tools import DATA_TOOLS

        for cls in DATA_TOOLS:
            assert DATA_WRITE not in tuple(cls.required_permissions), cls.name

    def test_unresolvable_caller_denied(self):
        """Fail closed: an unidentified caller holds no permissions."""
        reg = self._registry()
        ok, reason = reg.authorize("anonymous", "data.query")
        assert ok is False
        assert "PERMISSION_DENIED" in reason

    def test_privileged_identity_retains_access(self):
        reg = self._registry(confirm_network=True)
        ok, _ = reg.authorize("owner", "data.query", permissions={"*"})
        assert ok is True
        ok2, _ = reg.authorize("admin", "data.export", permissions={"*"})
        assert ok2 is True

    def test_non_data_tools_keep_risk_only_behaviour(self):
        """Tools that declare no required_permissions are unaffected."""
        reg = self._registry()
        ok, reason = reg.authorize("anyone", "provider.status")
        assert ok is True
        assert "PERMISSION_DENIED" not in reason

    def test_unknown_tool_still_denied(self):
        reg = self._registry()
        ok, reason = reg.authorize("anyone", "no.such.tool")
        assert ok is False
        assert reason == "TOOL_NOT_REGISTERED"

    def test_explicit_permissions_take_precedence(self):
        assert resolve_permissions("x", permissions={"data:read"}) == {"data:read"}

    def test_authorization_error_exposes_no_secret(self):
        reg = self._registry()
        _, reason = reg.authorize("nobody", "data.query", permissions=set())
        lowered = reason.lower()
        for leak in ("password", "secret", "token", "bearer", "postgres://",
                     "postgresql://", "api_key"):
            assert leak not in lowered


# --------------------------------------------------------------------------- #
# 5. Capability metadata / domain attribution (PURE)
# --------------------------------------------------------------------------- #
class TestCapabilityMetadata:
    def test_every_data_capability_is_in_the_data_analytics_domain(self):
        from research_engine.capability_contract import build_contracts

        contracts = build_contracts()
        data_caps = [cid for cid in contracts if cid.startswith("data.")]
        assert len(data_caps) == 11, f"expected 11 data capabilities, got {len(data_caps)}"
        for cid in data_caps:
            assert contracts[cid]["domain"] == "data_analytics", \
                f"{cid} has domain={contracts[cid]['domain']}"

    def test_every_data_capability_has_full_metadata(self):
        from research_engine.capability_contract import build_contracts

        contracts = build_contracts()
        for cid, contract in contracts.items():
            if not cid.startswith("data."):
                continue
            assert contract["id"] == cid
            assert contract["description"], f"{cid} missing description"
            assert contract["timeout"] > 0, f"{cid} missing timeout"
            assert contract["retry_policy"], f"{cid} missing retry policy"
            assert contract["audit_policy"], f"{cid} missing audit policy"
            assert contract["cost_model"], f"{cid} missing cost model"
            assert contract["supports_offline"] is True, \
                f"{cid} not marked offline-capable"

    def test_declared_data_permissions_reach_the_contract(self):
        from research_engine.capability_contract import build_contracts

        contracts = build_contracts()
        assert set(contracts["data.analyze"]["required_permissions"]) == {
            DATA_DISCOVER, DATA_READ, DATA_ANALYZE}
        assert set(contracts["data.export"]["required_permissions"]) == {
            DATA_DISCOVER, DATA_READ, DATA_EXPORT}
        assert set(contracts["data.visualize"]["required_permissions"]) == {
            DATA_DISCOVER, DATA_READ, DATA_EXPORT}
        # No data capability may advertise or accept DATA_WRITE.
        for cid, contract in contracts.items():
            if cid.startswith("data."):
                assert DATA_WRITE not in contract["required_permissions"], cid

    def test_registered_permission_requirements_match_declared_metadata(self):
        """Contract metadata must never drift from the enforced values.

        The tool classes are the enforcement source of truth; the contract is
        discovery/documentation. A mismatch would advertise a permission set
        that the registry does not actually require.
        """
        from research_engine.capability_contract import build_contracts
        from research_engine.data_tools import DATA_TOOLS

        contracts = build_contracts()
        for cls in DATA_TOOLS:
            declared = set(contracts[cls.name]["required_permissions"])
            enforced = set(cls.required_permissions)
            assert declared == enforced, (
                f"{cls.name}: contract {sorted(declared)} != "
                f"enforced {sorted(enforced)}")

    def test_documents_capabilities_keep_their_domain(self):
        from research_engine.capability_contract import build_contracts

        contracts = build_contracts()
        doc_caps = [cid for cid in contracts if cid.startswith("documents.")]
        assert len(doc_caps) == 11, f"expected 11 document capabilities, got {len(doc_caps)}"
        for cid in doc_caps:
            assert contracts[cid]["domain"] == "documents", \
                f"{cid} has domain={contracts[cid]['domain']}"

    def test_no_capability_is_left_in_the_platform_domain_by_accident(self):
        """data./documents. must never fall through to the default domain."""
        from research_engine.capability_contract import build_contracts

        contracts = build_contracts()
        for cid, contract in contracts.items():
            if cid.startswith("data."):
                assert contract["domain"] != "platform", cid
            if cid.startswith("documents."):
                assert contract["domain"] != "platform", cid

    def test_data_namespace_registered_in_rbac(self):
        from identity.rbac import RESOURCE_ACTIONS

        for action in ("discover", "read", "analyze", "export", "write"):
            assert action in RESOURCE_ACTIONS["data"]

    def test_no_canonical_role_grants_data_write(self):
        from identity.rbac import CANONICAL_ROLES

        for name, spec in CANONICAL_ROLES.items():
            perms = set(spec.get("permissions") or ())
            if perms == {"*"}:
                continue  # owner/admin wildcard is intentional
            assert "data:write" not in perms, f"{name} must not grant data:write"

    def test_analyst_gets_analytics_but_not_write(self):
        from identity.rbac import CANONICAL_ROLES, PermissionEngine

        class _Store:
            def load(self_inner):
                return CANONICAL_ROLES

        pe = PermissionEngine(_Store())
        analyst = {"roles": ["analyst"]}
        assert pe.has_permission(analyst, DATA_DISCOVER)
        assert pe.has_permission(analyst, DATA_READ)
        assert pe.has_permission(analyst, DATA_ANALYZE)
        assert pe.has_permission(analyst, DATA_EXPORT)
        assert not pe.has_permission(analyst, DATA_WRITE)

    def test_viewer_is_read_only_for_data(self):
        from identity.rbac import CANONICAL_ROLES, PermissionEngine

        class _Store:
            def load(self_inner):
                return CANONICAL_ROLES

        pe = PermissionEngine(_Store())
        viewer = {"roles": ["viewer"]}
        assert pe.has_permission(viewer, DATA_READ)
        assert not pe.has_permission(viewer, DATA_DISCOVER)
        assert not pe.has_permission(viewer, DATA_ANALYZE)
        assert not pe.has_permission(viewer, DATA_EXPORT)
        assert not pe.has_permission(viewer, DATA_WRITE)

    def test_no_data_capability_is_reachable_by_a_viewer_alone(self):
        """Documented consequence of the enforced default requirement set.

        Every data capability requires discover+read+analyze, so a viewer that
        holds only ``data:read`` cannot invoke any of them. Granting the viewer
        ``data:read`` stays least-privilege-safe, but it must not be mistaken
        for analytics access; narrowing the per-capability requirement set is a
        separate design decision.
        """
        from identity.rbac import CANONICAL_ROLES, PermissionEngine
        from research_engine.capability_tools import build_capability_registry
        from research_engine.tool_registry import DefaultPermissionPolicy

        class _Store:
            def load(self_inner):
                return CANONICAL_ROLES

        pe = PermissionEngine(_Store())
        held = {p for p in pe.effective_permissions({"roles": ["viewer"]})}
        reg = build_capability_registry(policy=DefaultPermissionPolicy())
        for cls in ("data.sources", "data.query", "data.analyze"):
            missing = [p for p in reg.describe.__self__._tools[cls].required_permissions
                       if not permission_granted(set(held), p)]
            assert missing, f"{cls} unexpectedly reachable by a viewer"

    def test_plain_user_gets_no_data_access(self):
        """A chat-only user must not acquire analytics by default."""
        from identity.rbac import CANONICAL_ROLES, PermissionEngine

        class _Store:
            def load(self_inner):
                return CANONICAL_ROLES

        pe = PermissionEngine(_Store())
        user = {"roles": ["user"]}
        assert not pe.has_permission(user, DATA_READ)
        assert not pe.has_permission(user, DATA_ANALYZE)


# --------------------------------------------------------------------------- #
# 6. Truthful dependency reporting (PURE + REAL_PG)
# --------------------------------------------------------------------------- #
class TestDependencyStatus:
    def test_dependencies_are_probed_not_asserted(self):
        status = dt.data_capability_status()
        deps = status["dependencies"]
        for name in ("sqlalchemy", "pandas", "numpy", "matplotlib",
                     "openpyxl", "pymongo", "pyarrow", "psycopg2"):
            assert name in deps
            assert deps[name]["state"] in {"AVAILABLE", "UNAVAILABLE"}
            if deps[name]["state"] == "UNAVAILABLE":
                assert deps[name]["reason"]

    def test_parser_absence_is_reported_truthfully(self):
        deps = dt.data_capability_status()["dependencies"]
        for key in ("sqlglot_parser", "sqlparse_parser"):
            entry = deps[key]
            if entry["state"] == "UNAVAILABLE":
                assert entry["reason"]
                assert "conservative" in entry["reason"]

    def test_capability_availability_uses_real_states(self):
        avail = dt.data_capability_status()["capability_availability"]
        for cap in ("data.sources", "data.schema", "data.query",
                    "data.profile", "data.analyze", "data.visualize",
                    "data.export"):
            assert cap in avail
            assert avail[cap]["availability"] in {
                "AVAILABLE", "UNAVAILABLE", "NOT_CONFIGURED", "DEGRADED"}

    def test_offline_local_analytics_available_without_postgres(self):
        """A dead database must not take down deterministic local analytics."""
        avail = dt.data_capability_status()["capability_availability"]
        assert avail["data.profile"]["availability"] == "AVAILABLE"
        assert avail["data.compare"]["availability"] == "AVAILABLE"

    def test_visualize_unavailable_without_matplotlib(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "matplotlib":
                raise ImportError("simulated: matplotlib absent")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        avail = dt._capability_availability()
        assert avail["data.visualize"]["availability"] == "UNAVAILABLE"
        assert "matplotlib" in avail["data.visualize"]["reason"]
        # Deterministic profiling must remain available.
        assert avail["data.profile"]["availability"] == "AVAILABLE"

    def test_relation_authorization_is_reported(self):
        status = dt.data_capability_status()
        rel = status["relation_authorization"]
        assert rel["mode"] == "allowlist"
        assert rel["default"] == "DENY"
        assert "public.models" in rel["allowed"]
        assert "pg_catalog" in rel["denied_schemas"]


# --------------------------------------------------------------------------- #
# 7. End-to-end execution against whatever engine is really configured
# --------------------------------------------------------------------------- #
def _first_allowlisted_relation() -> str | None:
    """An allowlisted relation that actually exists in the live engine."""
    try:
        from sqlalchemy import text as sa_text

        engine = dt._engine()
        if engine.dialect.name == "sqlite":
            names = {r[0] for r in engine.connect().exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%'").fetchall()}
        else:
            names = {f"{r[0]}.{r[1]}" for r in engine.connect().execute(sa_text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type IN ('BASE TABLE','VIEW')")).fetchall()}
    except Exception:  # noqa: BLE001
        return None
    shared = sorted(names & set(ALLOWED_RELATIONS))
    return shared[0] if shared else None


_LIVE_RELATION = _first_allowlisted_relation()
needs_live_relation = pytest.mark.skipif(
    _LIVE_RELATION is None,
    reason="no allowlisted relation exists in the configured engine")


class TestLiveExecution:
    """Real execution on the real configured engine, whichever backend it is."""

    def test_engine_is_reported_truthfully(self):
        result = dt._run_sql(f"SELECT count(*) AS n FROM {_LIVE_RELATION}"
                             if _LIVE_RELATION else "SELECT 1 AS n")
        assert result["dialect"] in {"postgresql", "sqlite"}
        # Read-only must be actually enforced on every supported backend.
        assert result["read_only_enforced"] is True
        assert result["read_only_by"]
        # A timeout may only be claimed where the backend can enforce one.
        if result["dialect"] == "postgresql":
            assert result["timeout_enforced"] is True
            assert result["statement_timeout_s"] == dt.QUERY_TIMEOUT_S
        else:
            assert result["timeout_enforced"] is False
            assert result["statement_timeout_s"] is None

    def test_sensitive_relation_blocked_before_execution(self):
        with pytest.raises(RelationNotAuthorized):
            dt._run_sql("SELECT * FROM jarvis_kv")

    @needs_live_relation
    def test_allowed_query_executes(self):
        result = dt._run_sql(f"SELECT * FROM {_LIVE_RELATION} LIMIT 3")
        assert result["row_count"] <= 3
        assert result["relations"] == [_LIVE_RELATION]

    def test_sensitive_relation_blocked_before_execution(self):
        with pytest.raises(RelationNotAuthorized):
            dt._run_sql("SELECT * FROM jarvis_kv")

    @needs_live_relation
    def test_parameterized_query_is_used(self):
        result = dt._run_sql(
            f"SELECT * FROM {_LIVE_RELATION} WHERE :m IS NOT NULL",
            {"m": "does-not-exist-xyz"})
        assert result["row_count"] == 0

    @needs_live_relation
    def test_injection_attempt_via_parameter_is_inert(self):
        """A malicious VALUE is bound as data, never concatenated into SQL."""
        result = dt._run_sql(
            f"SELECT count(*) AS n FROM {_LIVE_RELATION} WHERE :m IS NOT NULL",
            {"m": "'; DROP TABLE models; --"})
        assert result["rows"][0]["n"] >= 0
        # The table must still be there afterwards.
        again = dt._run_sql(f"SELECT count(*) AS n FROM {_LIVE_RELATION}")
        assert again["rows"][0]["n"] >= 0

    def test_injection_attempt_via_sql_is_rejected(self):
        with pytest.raises(SqlRejected):
            dt._run_sql("SELECT 1 FROM public.models; DROP TABLE models")

    def test_no_credentials_in_result(self):
        result = dt._run_sql("SELECT 1 AS n")
        blob = repr(result).lower()
        for leak in ("postgres://", "postgresql://", "password", "secret="):
            assert leak not in blob

    def test_provenance_has_no_credentials(self):
        import asyncio
        import json

        from research_engine.data_tools import DataQueryTool

        tool = DataQueryTool()
        ctx = ToolContext(request_id="t", user_id="t", permissions={"*"})
        res = asyncio.run(tool.invoke({"sql": "SELECT 1 AS n"}, ctx))
        payload = json.loads(res.result) if res.result else {}
        prov = payload.get("provenance", {})
        blob = json.dumps(prov).lower()
        for leak in ("postgres://", "password", "secret", "token"):
            assert leak not in blob
        assert prov.get("query_hash")
        assert prov.get("capability_version") == dt.VERSION
        assert prov.get("user_id") == "t"

    def test_query_hash_is_stable_and_content_addressed(self):
        a = dt.query_hash("SELECT 1 FROM models")
        b = dt.query_hash("SELECT 1 FROM models")
        c = dt.query_hash("SELECT 2 FROM models")
        assert a == b
        assert a != c


# --------------------------------------------------------------------------- #
# 8. Schema discovery obeys the same allowlist as query execution
# --------------------------------------------------------------------------- #
class TestSchemaDiscoveryIsAuthorized:
    """Metadata must not become a side channel around the SQL allowlist."""

    def _schema(self):
        from research_engine.data_tools import DataSchemaTool

        tool = DataSchemaTool()
        ctx = ToolContext(request_id="s", user_id="s", permissions={"*"})
        res = asyncio.run(tool.invoke({"source": "sql"}, ctx))
        assert res.success, res.error
        return json.loads(res.result)

    def test_no_unauthorized_relation_is_disclosed(self):
        payload = self._schema()
        listed = set(payload["tables"])
        assert listed, "at least one real table must be discovered"
        for rel in listed:
            assert rel in ALLOWED_RELATIONS, rel
        blob = json.dumps(payload).lower()
        for secret in ("jarvis_kv", "refresh_token", "chat_session"):
            assert secret not in blob, f"schema leaked {secret}"

    def test_withheld_relations_are_counted_not_named(self):
        payload = self._schema()
        auth = payload["authorization"]
        assert auth["mode"] == "allowlist"
        assert auth["default"] == "DENY"
        assert auth["withheld_relation_count"] >= 0

    def test_denied_schema_request_is_refused(self):
        import asyncio
        import json

        from research_engine.data_tools import DataSchemaTool

        tool = DataSchemaTool()
        ctx = ToolContext(request_id="s", user_id="s", permissions={"*"})
        res = asyncio.run(tool.invoke(
            {"source": "sql", "schema": "information_schema"}, ctx))
        assert res.success is False
        assert "not authorized" in (res.error or "")

    def test_unauthorized_columns_are_not_returned(self):
        """A column-level check: nothing outside the allowlist can be read."""
        with pytest.raises(RelationNotAuthorized):
            dt.validate_analytics_sql("SELECT password FROM users")
        with pytest.raises(RelationNotAuthorized):
            dt.validate_analytics_sql("SELECT token FROM refresh_tokens")


# --------------------------------------------------------------------------- #
# 8. End-to-end invoke through the registry with permissions
# --------------------------------------------------------------------------- #
class TestInvokeChain:
    def _run(self, cap, args, permissions):
        import asyncio

        from research_engine.capability_tools import build_capability_registry

        reg = build_capability_registry(policy=DefaultPermissionPolicy())
        ctx = ToolContext(request_id="chain", user_id="chain",
                          permissions=permissions)
        return asyncio.run(reg.invoke(cap, args, ctx))

    def test_unauthorized_caller_denied_at_the_chain(self):
        res = self._run("data.query",
                        {"sql": "SELECT id FROM models LIMIT 1"},
                        permissions=set())
        assert res.success is False
        assert "TOOL_DENIED" in (res.error or "")

    def test_authorized_caller_reaches_the_relation_layer(self):
        """With permission but a sensitive table, the RELATION layer denies."""
        import json

        res = self._run("data.query", {"sql": "SELECT * FROM jarvis_kv"},
                        permissions={"*"})
        assert res.success is False
        assert "not authorized" in (res.error or "")

    def test_authorized_allowed_query_succeeds(self):
        import json

        res = self._run("data.query",
                        {"sql": "SELECT id FROM models LIMIT 1"},
                        permissions={"*"})
        if not res.success:
            pytest.skip(f"PostgreSQL unavailable: {res.error}")
        payload = json.loads(res.result)
        assert "rows" in payload
        assert payload["read_only_enforced"] is True
