"""Frozen RG6 retirement; full source parity is an external release precondition.

Populated installations require an explicit connection setting, supplied to one
owner migration process with PGOPTIONS='-c pushinweight.rg6_retirement_ready=0199'.
The setting authorizes deletion; it does not assert or calculate source parity.
Set it only after final copy/parity and every old executable image has drained.
Automatic deployment without that setting fails closed on populated databases.

Render owner builds run migrations. For each staged/production retirement,
append this option to the selected owner service's existing PGOPTIONS before
its0199 build, keep other owner builds behind that migration, verify the ledger,
13 absent columns and serving grants, then restore the prior PGOPTIONS value.
Subsequent builds need no override because0199 is already applied. If the exact
candidate is available for a separate owner migration process, set PGOPTIONS
only on that process instead. Never leave the override as a permanent bypass.
"""

import re

from django.db import transaction
from psycopg import sql

from ._benchmark_serving_v3 import VIEWS as BENCHMARK_VIEWS
from ._benchmark_serving_v3 import validate_view

FIELDS = {
    "collection_runs": ("request_params", "source_metadata", "raw_payload", "invocations", "report"),
    "collection_scope_runs": ("ownership", "cursor_history", "envelopes"),
    "collection_observations": ("dimensions", "source_metadata", "listing", "envelopes", "groups"),
}
RUN_COLUMNS = (
    "id", "batch_id", "ingestion_key", "status", "started_at", "lease_expires_at",
    "observed_at", "completed_at", "source_as_of", "source_url", "request_params",
    "source_metadata", "request_count", "selected_count", "success_count",
    "payload_sha256", "raw_payload", "error_code", "contract_id", "source_id",
    "purpose", "scope", "invocations", "report", "updated_at",
)
OBSERVATION_COLUMNS = (
    "id", "source_identifier", "source_subject_kind", "observed_at", "dimensions",
    "source_metadata", "observation_key", "status", "published_at", "published_date",
    "publication_precision", "error_code", "run_id", "mapping_id", "scope_run_id",
    "resource_key", "product_id", "created_product", "listing", "envelopes", "groups",
    "processing_outcome", "updated_at", "post_id",
)
ALIASES = {
    "metric_collection_runs": ("collection_runs", RUN_COLUMNS),
    "metric_observations": ("collection_observations", OBSERVATION_COLUMNS),
}
PREDICATES = {
    "uq_source_statistics_snapshot": "source_metadata->'projection_kind'='\"source-statistics-v1\"'::jsonb",
    "uq_source_statistics_typed": "projection_kind='source-statistics-v1'",
    "uq_source_statistics_crossformat": (
        "projection_kind='source-statistics-v1' OR "
        "source_metadata->'projection_kind'='\"source-statistics-v1\"'::jsonb"
    ),
}


def alias_query(name, *, retired):
    table, columns = ALIASES[name]
    selected = [column for column in columns if not retired or column not in FIELDS[table]]
    if table == "collection_runs":
        expressions = []
        for column in selected:
            if column in {"contract_id", "source_id", "purpose", "scope"}:
                value = "j.definition->'scope'" if column == "scope" else "j." + column
                expressions.append(f"(SELECT {value} FROM collection_jobs j WHERE j.id=r.job_id) AS {column}")
            else:
                expressions.append("r." + column)
        return "SELECT " + ",".join(expressions) + " FROM collection_runs r WHERE (SELECT j.purpose FROM collection_jobs j WHERE j.id=r.job_id)='metric'"
    return "SELECT " + ",".join("o." + column for column in selected) + " FROM collection_observations o WHERE o.run_id IN (SELECT r.id FROM collection_runs r WHERE (SELECT j.purpose FROM collection_jobs j WHERE j.id=r.job_id)='metric')"


def _predicate(value):
    # pg_get_expr adds grouping, whitespace and inferred casts. Strip only
    # outside SQL literals: changing quoted marker text would accept a different
    # partial index, leaving some real statistics snapshots unprotected.
    return re.sub(
        r"'(?:[^']|'')*'|::(?:text|jsonb)\b|[\s()]+",
        lambda match: match[0] if match[0].startswith("'") else "",
        value or "",
    )


def _check_indexes(cursor):
    for name, predicate in PREDICATES.items():
        cursor.execute("""SELECT i.indisunique,i.indisvalid,i.indisready,i.indnatts,
            i.indnkeyatts,i.indexprs IS NULL,i.indkey::text,a.attnum::text,
            am.amname,pg_get_expr(i.indpred,i.indrelid)
            FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
            JOIN pg_am am ON am.oid=c.relam
            JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attname='observation_key'
            WHERE i.indexrelid=to_regclass(%s) AND i.indrelid='collection_observations'::regclass""", [name])
        found = cursor.fetchone()
        if (found is None or found[:6] != (True, True, True, 1, 1, True)
                or found[6] != found[7] or found[8] != "btree"
                or _predicate(found[9]) != _predicate(predicate)):
            raise RuntimeError("Unready RG6 statistics index: " + name)


def _check_alias(cursor, name):
    cursor.execute("CREATE TEMP VIEW pw_rg6_expected_alias AS " + alias_query(name, retired=False))
    try:
        cursor.execute("""SELECT pg_get_viewdef(%s::regclass)=pg_get_viewdef('pg_temp.pw_rg6_expected_alias'::regclass),
            reloptions FROM pg_class WHERE oid=%s::regclass AND relkind='v'""", [name, name])
        if cursor.fetchone() != (True, ["check_option=local"]):
            raise RuntimeError("Unreviewed RG6 compatibility view: " + name)
    finally:
        cursor.execute("DROP VIEW pg_temp.pw_rg6_expected_alias")


def _check_dependencies(cursor):
    """Allow only these aliases, the two obsolete indexes, defaults and NOT NULL."""
    for table, columns in FIELDS.items():
        cursor.execute("""SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass
            AND attname=ANY(%s) AND attnum>0 AND NOT attisdropped AND atttypid='jsonb'::regtype""", [table, list(columns)])
        if {row[0] for row in cursor.fetchall()} != set(columns):
            raise RuntimeError("Incomplete RG6 retirement columns: " + table)
        cursor.execute("""SELECT a.attname,d.deptype,d.classid::regclass::text,
            CASE WHEN d.classid='pg_rewrite'::regclass THEN rw.ev_class::regclass::text
                 WHEN d.classid='pg_class'::regclass THEN d.objid::regclass::text END,
            co.contype,co.conrelid=a.attrelid AND co.conkey=ARRAY[a.attnum],
            ad.adrelid=a.attrelid AND ad.adnum=a.attnum,rw.rulename
            FROM pg_attribute a JOIN pg_depend d ON d.refclassid='pg_class'::regclass
                AND d.refobjid=a.attrelid AND d.refobjsubid=a.attnum
            LEFT JOIN pg_rewrite rw ON d.classid='pg_rewrite'::regclass AND rw.oid=d.objid
            LEFT JOIN pg_constraint co ON d.classid='pg_constraint'::regclass AND co.oid=d.objid
            LEFT JOIN pg_attrdef ad ON d.classid='pg_attrdef'::regclass AND ad.oid=d.objid
            WHERE a.attrelid=%s::regclass AND a.attname=ANY(%s) AND NOT a.attisdropped""", [table, list(columns)])
        for column, kind, catalogue, name, constraint, own_constraint, own_default, rule in cursor.fetchall():
            allowed = (
                kind == "a" and catalogue == "pg_attrdef" and own_default
                or kind == "a" and catalogue == "pg_constraint" and constraint == "n" and own_constraint
                or kind == "a" and catalogue == "pg_class" and table == "collection_observations"
                and column == "source_metadata" and name in {"uq_source_statistics_snapshot", "uq_source_statistics_crossformat"}
                or kind == "n" and catalogue == "pg_rewrite" and rule == "_RETURN"
                and name in ALIASES and ALIASES[name][0] == table
            )
            if not allowed:
                raise RuntimeError(f"Unreviewed RG6 dependency: {table}.{column} ({catalogue})")


def prepare_retirement(apps, schema_editor):
    """Bounded readiness/coverage checks, before taking exclusive table locks."""
    with transaction.atomic(using=schema_editor.connection.alias), schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='15s'")
        populated = False
        for table in FIELDS:
            cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {table})")
            has_rows = cursor.fetchone()[0]
            populated = populated or has_rows
        if populated:
            cursor.execute("SELECT current_setting('pushinweight.rg6_retirement_ready',true)")
            if cursor.fetchone() != ("0199",):
                raise RuntimeError("RG6 populated retirement requires explicit connection authorization")
        _check_indexes(cursor)
        _check_dependencies(cursor)
        cursor.execute("""SELECT EXISTS(SELECT 1 FROM collection_observations
            WHERE source_metadata->'projection_kind'='"source-statistics-v1"'::jsonb
                AND projection_kind IS DISTINCT FROM 'source-statistics-v1')""")
        if cursor.fetchone()[0]:
            raise RuntimeError("RG6 legacy statistics lack the typed uniqueness owner")
        for name in ALIASES:
            _check_alias(cursor, name)
        cursor.execute("SELECT current_schema()")
        schema = cursor.fetchone()[0]
        for name in BENCHMARK_VIEWS:
            validate_view(cursor, schema, name)
        for table, columns in FIELDS.items():
            differences = []
            for column in columns:
                empty = "NULL" if column == "raw_payload" else "'[]'::jsonb" if column in {"invocations", "cursor_history", "envelopes"} else "'{}'::jsonb"
                differences.append(f"t.{column} IS DISTINCT FROM {empty}")
            # The observation NULL-owner path has idx_rg6_obs_unarchived.
            # This is absence detection only; exact archive bytes/typed parity
            # are verified by the separate, frozen final-copy receipt.
            cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {table} t WHERE t.legacy_archive_id IS NULL AND ({' OR '.join(differences)}))")
            if cursor.fetchone()[0]:
                raise RuntimeError("Unarchived RG6 source documents: " + table)


def _acl(cursor, name):
    cursor.execute("""SELECT c.relowner,pg_get_userbyid(c.relowner),obj_description(c.oid,'pg_class')
        FROM pg_class c WHERE c.oid=%s::regclass""", [name])
    owner_id, owner, comment = cursor.fetchone()
    cursor.execute("""SELECT NULL::text,x.grantor,x.grantee,x.privilege_type,x.is_grantable
        FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) x WHERE c.oid=%s::regclass
        UNION ALL SELECT a.attname,x.grantor,x.grantee,x.privilege_type,x.is_grantable
        FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) x
        WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped""", [name, name])
    permissions = cursor.fetchall()
    if any(grantor != owner_id for _column, grantor, _grantee, _privilege, _option in permissions):
        raise RuntimeError("Unreviewed RG6 compatibility grant chain: " + name)
    return owner, comment, permissions


def _role(cursor, role_id):
    if role_id == 0:
        return sql.SQL("PUBLIC")
    cursor.execute("SELECT rolname FROM pg_roles WHERE oid=%s", [role_id])
    found = cursor.fetchone()
    if found is None:
        raise RuntimeError("RG6 compatibility grantee disappeared")
    return sql.Identifier(found[0])


def _restore_acl(cursor, name, retained, saved):
    owner, comment, permissions = saved
    view = sql.Identifier(name)
    cursor.execute(sql.SQL("ALTER VIEW {} OWNER TO {}").format(view, sql.Identifier(owner)))
    # CREATE can introduce default grants. Remove those before replaying the
    # prior grants, so replacing an alias cannot widen serving access.
    cursor.execute("SELECT x.grantee FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) x WHERE c.oid=%s::regclass", [name])
    for role_id in {row[0] for row in cursor.fetchall()}:
        cursor.execute(sql.SQL("REVOKE ALL ON {} FROM {}").format(view, _role(cursor, role_id)))
    for column, _grantor, grantee, privilege, grantable in permissions:
        if column is not None and column not in retained:
            continue
        target = sql.SQL("") if column is None else sql.SQL(" ({})").format(sql.Identifier(column))
        cursor.execute(sql.SQL("GRANT {}{} ON {} TO {}{}").format(
            sql.SQL(privilege), target, view, _role(cursor, grantee),
            sql.SQL(" WITH GRANT OPTION" if grantable else ""),
        ))
    if comment is not None:
        cursor.execute(sql.SQL("COMMENT ON VIEW {} IS %s").format(view), [comment])


def remove_storage(apps, schema_editor):
    """One short atomic drop; failure rolls back aliases, columns and grants."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
        _check_indexes(cursor)
        _check_dependencies(cursor)
        saved = {}
        for name in ALIASES:
            _check_alias(cursor, name)
            saved[name] = _acl(cursor, name)
        # Lock/drop the view before its base tables to avoid holding a base
        # lock while waiting for a reader that already locked the view.
        cursor.execute("DROP VIEW metric_observations,metric_collection_runs RESTRICT")
        cursor.execute("LOCK TABLE collection_runs,collection_scope_runs,collection_observations IN ACCESS EXCLUSIVE MODE")
        _check_dependencies(cursor)
        for table, columns in FIELDS.items():
            cursor.execute(f"ALTER TABLE {table} " + ",".join("DROP COLUMN " + column + " RESTRICT" for column in columns))
        for name, (table, columns) in ALIASES.items():
            cursor.execute(f"CREATE VIEW {name} AS " + alias_query(name, retired=True) + " WITH LOCAL CHECK OPTION")
            retained = set(columns) - set(FIELDS[table])
            _restore_acl(cursor, name, retained, saved[name])
            expected = [row for row in saved[name][2] if row[0] is None or row[0] in retained]
            actual = _acl(cursor, name)
            if actual[:2] != saved[name][:2] or set(actual[2]) != set(expected):
                raise RuntimeError("RG6 compatibility permissions changed: " + name)
        for name in ("uq_source_statistics_snapshot", "uq_source_statistics_crossformat"):
            cursor.execute("SELECT to_regclass(%s)", [name])
            if cursor.fetchone() != (None,):
                raise RuntimeError("RG6 obsolete statistics index survived")
        cursor.execute("SELECT indisvalid AND indisready FROM pg_index WHERE indexrelid='uq_source_statistics_typed'::regclass")
        if cursor.fetchone() != (True,):
            raise RuntimeError("RG6 typed statistics index did not survive")
