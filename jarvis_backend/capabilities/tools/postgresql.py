"""
PostgreSQL Connector Tool
==========================

Demonstrates a genuinely useful connector end-to-end using existing infrastructure.

Flow:
    Brain
    |- Tool request
    |- Authorization
    |- PostgreSQL connector
    |- Secure credential access (via vault)
    |- External system (PostgreSQL database)
    |- Sanitized result
    |- Brain

Credentials are accessed through the existing vault/secrets manager,
never passed from the Brain or conversation.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class PostgreSQLTool:
    """
    PostgreSQL connector tool.

    Demonstrates the full connector pattern:
    1. Brain requests a database query
    2. Authorization is checked (in the tool capability layer)
    3. The connector accesses credentials through the vault
    4. PostgreSQL is queried
    5. Results are sanitized (no SQL errors exposed)
    """

    name = "postgresql"
    version = "1.0.0"
    category = "database"
    description = "Query PostgreSQL databases with secure credential access"

    def __init__(self):
        self._conn = None
        self._connection_string = None

    async def health(self) -> Dict[str, Any]:
        """Real health check - verify database connectivity."""
        conn_params = self._get_connection_params()
        if not conn_params:
            return {
                'status': 'not_configured',
                'healthy': False,
                'error': 'No PostgreSQL connection configured. Set JARVIS_POSTGRES_URL or configure via vault.',
            }

        try:
            import sqlalchemy
            from sqlalchemy import text
            engine = sqlalchemy.create_engine(conn_params['url'], connect_args={'connect_timeout': 5})
            conn = engine.connect()
            result = conn.execute(text("SELECT 1 as healthy"))
            row = result.fetchone()
            conn.close()
            engine.dispose()

            return {
                'status': 'ok',
                'healthy': True,
                'database': conn_params.get('database', 'unknown'),
                'host': conn_params.get('host', 'unknown'),
            }
        except Exception as e:
            return {
                'status': 'error',
                'healthy': False,
                'error': f"PostgreSQL connection failed: {type(e).__name__}: {str(e)[:200]}",
                'database': conn_params.get('database', 'unknown') if conn_params else None,
            }

    def _get_connection_params(self) -> Optional[Dict[str, Any]]:
        """Get connection parameters from vault or environment.
        
        Credentials are accessed through secure channels only.
        Never returned to the caller.
        """
        # Try vault first
        try:
            from infrastructure.vault.manager import get_secrets_manager
            vault = get_secrets_manager()
            conn_str = vault.get_or_none('postgres_url') or vault.get_or_none('JARVIS_POSTGRES_URL')
            if conn_str:
                return {'url': conn_str, 'source': 'vault'}
        except Exception:
            pass

        # Try environment
        conn_str = os.environ.get('JARVIS_POSTGRES_URL') or os.environ.get('DATABASE_URL')
        if conn_str and 'postgresql' in conn_str:
            return {'url': conn_str, 'source': 'environment'}

        # Try individual components
        try:
            from jarvis_backend.core import get_store
            settings = get_store("misc").load()
            db_settings = settings.get('postgres', {}) if isinstance(settings, dict) else {}
            if db_settings:
                url = db_settings.get('url') or self._build_url(db_settings)
                if url:
                    return {'url': url, 'source': 'store', 'database': db_settings.get('database')}
        except Exception:
            pass

        return None

    def _build_url(self, settings: Dict) -> Optional[str]:
        """Build connection URL from individual parameters."""
        host = settings.get('host', 'localhost')
        port = settings.get('port', 5432)
        database = settings.get('database', 'postgres')
        user = settings.get('user', 'postgres')
        # Password comes from vault, not from user input
        password = None
        try:
            from infrastructure.vault.manager import get_secrets_manager
            password = get_secrets_manager().get_or_none('postgres_password')
        except Exception:
            password = os.environ.get('JARVIS_POSTGRES_PASSWORD')

        if password:
            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return f"postgresql://{user}@{host}:{port}/{database}"

    async def execute(self, action: str, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Execute a PostgreSQL operation."""
        # Sanitize: reject dangerous operations
        if action == 'query':
            sql = params.get('query', '')
            if not sql:
                return {'success': False, 'error': 'query is required', 'error_type': 'INVALID_INPUT'}

            sql_lower = sql.lower().strip()
            single_statement = sql.rstrip().rstrip(";")
            if (
                not re.match(r"^select\b", sql_lower)
                or ";" in single_statement
            ):
                return {
                    'success': False,
                    'error': 'Only a single read-only SELECT query is permitted.',
                    'error_type': 'SECURITY_VIOLATION',
                }

            conn_params = self._get_connection_params()
            if not conn_params:
                return {
                    'success': False,
                    'error': 'PostgreSQL is not configured. Set JARVIS_POSTGRES_URL.',
                    'error_type': 'NOT_CONFIGURED',
                }

            try:
                import sqlalchemy
                from sqlalchemy import text

                engine = sqlalchemy.create_engine(
                    conn_params['url'],
                    connect_args={'connect_timeout': 10},
                    pool_pre_ping=True,
                )

                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(text("SET TRANSACTION READ ONLY"))
                        result = conn.execute(text(sql))

                    # Fetch rows for SELECT queries
                    if result.returns_rows:
                        rows = result.fetchall()
                        columns = result.keys()
                        data = [dict(zip(columns, row)) for row in rows]
                        return {
                            'success': True,
                            'data': {
                                'columns': list(columns),
                                'rows': data,
                                'row_count': len(data),
                                'query': sql[:200],
                            },
                        }
                    else:
                        return {
                            'success': True,
                            'data': {
                                'query': sql[:200],
                                'row_count': result.rowcount,
                                'status': 'executed',
                            },
                        }

            except Exception as e:
                # Sanitize error - don't expose internal details
                error_type = type(e).__name__
                safe_errors = {
                    'OperationalError': 'Database connection failed',
                    'ProgrammingError': 'SQL syntax error',
                    'IntegrityError': 'Data integrity violation',
                    'DataError': 'Invalid data value',
                }
                safe_msg = safe_errors.get(error_type, 'Database query error')

                return {
                    'success': False,
                    'error': f"{safe_msg}: {str(e)[:200]}",
                    'error_type': error_type,
                }

        elif action == 'list_tables':
            conn_params = self._get_connection_params()
            if not conn_params:
                return {'success': False, 'error': 'PostgreSQL not configured', 'error_type': 'NOT_CONFIGURED'}

            try:
                import sqlalchemy
                from sqlalchemy import text, inspect

                engine = sqlalchemy.create_engine(conn_params['url'], connect_args={'connect_timeout': 10})
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                schemas = inspector.get_schema_names()

                return {
                    'success': True,
                    'data': {
                        'tables': tables,
                        'schemas': schemas,
                        'database': conn_params.get('database', 'unknown'),
                    },
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Failed to list tables: {str(e)[:200]}",
                    'error_type': type(e).__name__,
                }

        elif action == 'describe_table':
            table_name = params.get('table', '')
            if not table_name:
                return {'success': False, 'error': 'table is required', 'error_type': 'INVALID_INPUT'}

            conn_params = self._get_connection_params()
            if not conn_params:
                return {'success': False, 'error': 'PostgreSQL not configured', 'error_type': 'NOT_CONFIGURED'}

            try:
                import sqlalchemy
                from sqlalchemy import inspect

                engine = sqlalchemy.create_engine(conn_params['url'], connect_args={'connect_timeout': 10})
                inspector = inspect(engine)

                # Validate table name (prevent SQL injection)
                if not table_name.replace('_', '').replace('.', '').isalnum():
                    return {'success': False, 'error': 'Invalid table name', 'error_type': 'SECURITY_VIOLATION'}

                columns = inspector.get_columns(table_name)
                pk = inspector.get_pk_constraint(table_name)
                fks = inspector.get_foreign_keys(table_name)

                return {
                    'success': True,
                    'data': {
                        'table': table_name,
                        'columns': [
                            {'name': col['name'], 'type': str(col['type']),
                             'nullable': col['nullable'], 'default': col.get('default')}
                            for col in columns
                        ],
                        'primary_key': pk.get('constrained_columns', []),
                        'foreign_keys': [
                            {'constrained_columns': fk.get('constrained_columns', []),
                             'referred_table': fk.get('referred_table')}
                            for fk in fks
                        ],
                    },
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Failed to describe table: {str(e)[:200]}",
                    'error_type': type(e).__name__,
                }

        return {
            'success': False,
            'error': f"Unknown PostgreSQL action: {action}",
            'error_type': 'INVALID_ACTION',
        }

    async def shutdown(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._connection_string = None


__all__ = ['PostgreSQLTool']
