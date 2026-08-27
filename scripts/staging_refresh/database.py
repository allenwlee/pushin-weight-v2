from __future__ import annotations

from typing import Any

import psycopg

from .policy import DatabaseInspection, RefreshPolicy


class PostgresRuntime:
    """PostgreSQL inspection boundary; lifecycle mutations are added separately."""

    def __init__(self, policy: RefreshPolicy) -> None:
        self.policy = policy

    @staticmethod
    def _inspect(url: str) -> DatabaseInspection:
        with psycopg.connect(url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), session_user, "
                "current_setting('server_version_num')::integer, "
                "current_setting('default_transaction_read_only')::boolean, "
                "r.rolcreatedb, "
                "r.rolsuper OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls "
                "FROM pg_roles r WHERE r.rolname = session_user"
            )
            database, role, version, read_only, can_create, elevated = cursor.fetchone()
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_stat_ssl WHERE pid = pg_backend_pid() AND ssl"
                ")"
            )
            tls = bool(cursor.fetchone()[0])
            cursor.execute(
                "SELECT c.relname, c.relkind, "
                "CASE WHEN c.relkind IN ('r', 'p') THEN "
                "has_table_privilege(current_user, c.oid, 'SELECT') ELSE FALSE END, "
                "CASE WHEN c.relkind = 'S' THEN "
                "has_sequence_privilege(current_user, c.oid, 'SELECT') ELSE FALSE END, "
                "CASE WHEN c.relkind IN ('r', 'p') THEN "
                "has_table_privilege(current_user, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE') "
                "ELSE FALSE END "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v')"
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
            cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            schema_write = bool(cursor.fetchone()[0])

        base_tables = frozenset(str(row[0]) for row in rows if row[1] in {"r", "p"})
        views = frozenset(str(row[0]) for row in rows if row[1] == "v")
        sequences = frozenset(str(row[0]) for row in rows if row[1] == "S")
        readable_tables = frozenset(
            str(row[0]) for row in rows if row[1] in {"r", "p"} and row[2]
        )
        readable_sequences = frozenset(
            str(row[0]) for row in rows if row[1] == "S" and row[3]
        )
        table_write = any(bool(row[4]) for row in rows)
        return DatabaseInspection(
            database=str(database),
            role=str(role),
            server_version=int(version),
            tls=tls,
            default_transaction_read_only=bool(read_only),
            has_write_privileges=bool(elevated) or schema_write or table_write,
            can_create_database=bool(can_create),
            readable_tables=readable_tables,
            readable_sequences=readable_sequences,
            base_tables=base_tables,
            views=views,
            sequences=sequences,
        )

    def inspect_source(self, url: str) -> DatabaseInspection:
        return self._inspect(url)

    def inspect_target(self, url: str) -> DatabaseInspection:
        return self._inspect(url)

    def execute(self, action: str, *, recovery: str | None = None) -> dict[str, str]:
        raise RuntimeError("lifecycle_not_implemented")
