"""Exercise real refresh SQL in an owned schema of the permanent test DB.

Only catalog scope and the lifecycle marker's storage are redirected. Dump,
restore, migrations, scrubbing, parity checks and application readers remain
real. Database creation/swap belong to the separate lifecycle tests.
"""

import re

import psycopg
from psycopg.conninfo import conninfo_to_dict


def schema_connector(namespace, database):
    assert re.fullmatch(r"migration_rehearsal_[a-f0-9]{32}", namespace)
    assert database.startswith("test_")
    search_path = f"{namespace},{namespace}_extensions"

    class SchemaCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kwargs):
            statement = (
                query if isinstance(query, str) else query.as_string(self.connection)
            )
            if re.search(
                r"\b(?:CREATE|DROP|ALTER)\s+DATABASE\b", statement, re.IGNORECASE
            ):
                raise AssertionError("Schema rehearsal cannot change databases")
            marker_query = (
                "SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = %s"
            )
            if statement == marker_query:
                assert list(params) == [database]
                statement = (
                    "SELECT obj_description(oid, 'pg_namespace') "
                    "FROM pg_namespace WHERE nspname = %s"
                )
                params = [namespace]
            elif statement.startswith("COMMENT ON DATABASE "):
                prefix = f'COMMENT ON DATABASE "{database}" IS '
                assert statement.startswith(prefix)
                statement = (
                    f'COMMENT ON SCHEMA "{namespace}" IS ' + statement[len(prefix) :]
                )
            statement = statement.replace("'public'", f"'{namespace}'")
            statement = statement.replace("'public.", f"'{namespace}.")
            return super().execute(statement, params, **kwargs)

    def connect(conninfo="", **kwargs):
        parameters = {**conninfo_to_dict(conninfo), **kwargs}
        # mark_validated asks for the administrative database. Its marker is
        # redirected to this schema; it never opens or mutates postgres/public.
        assert parameters.get("dbname") in {database, "postgres"}
        parameters["dbname"] = database
        parameters["options"] = f"-csearch_path={search_path}"
        parameters["cursor_factory"] = SchemaCursor
        return psycopg.connect(**parameters)

    return connect, search_path
