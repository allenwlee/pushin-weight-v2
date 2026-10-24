"""Grant a dedicated serving login canonical access without source evidence.

Run with an owner connection during deployment. This module never creates or
prints credentials, grants owner membership, or adds a second web connection.
"""

from psycopg import sql

# Both names are denied during the rolling-image bridge. Old entries disappear
# from the physical inventory after final deletion; they must never be granted.
SOURCE_COLUMNS = {
    "accounts": {"location", "reported_profile_location"},
    "x_account_details": {"account_based_in", "reported_based_in"},
    "posts": {"author_location", "reported_author_location"},
    "account_profile_snapshots": {"location", "reported_location", "profile_data", "raw_profile_payload"},
    "people_brand_affiliations": {"location", "reported_location"},
    "people_brand_affiliation_evidence": {"extracted_claim_data"},
    "job_listings": {"locations", "locations_raw", "raw_payload"},
    "job_listing_evidence": {"raw_evidence"},
    "job_listing_locations": {"reported_value"},
    "collection_evidence_archives": {"body"},
    "collection_runs": {"raw_payload", "request_params", "source_metadata", "report"},
    "collection_scope_runs": {"ownership", "envelopes"},
    "collection_observations": {"source_metadata"},
}
CATALOGUES = frozenset({"geolocations", "geolocation_alternate_names", "geolocation_policies", "django_migrations"})
SERVING_VIEWS = frozenset({
    "trend_narrative_versions", "brand_trend_narratives", "editorial_pictures",
    "trend_narrative_provider_calls", "trend_narrative_runs", "trend_narrative_visible_runs",
    "brand_trend_narrative_texts", "home_brand_time_counts",
})


def apply_serving_grants(connection, role, *, schema="public"):
    """Reconcile grants on one dedicated role; refuse privileged/mixed roles."""
    if connection.get_autocommit():
        raise ValueError("Serving grant reconciliation requires one transaction")
    identifier = sql.Identifier(role)
    namespace = sql.Identifier(schema)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user,current_database()")
        owner, database = cursor.fetchone()
        if role == owner:
            raise ValueError("Serving access needs a separate dedicated login")
        cursor.execute("SELECT oid,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolcanlogin,rolconfig FROM pg_roles WHERE rolname=%s", [role])
        found = cursor.fetchone()
        if found is None or any(found[1:5]) or not found[5] or found[6]:
            raise ValueError("Serving login must have no elevated attributes or role settings")
        role_id = found[0]
        cursor.execute("SELECT 1 FROM pg_auth_members WHERE member=%s LIMIT 1", [role_id])
        if cursor.fetchone():
            raise ValueError("Serving login must not inherit or assume another role")
        cursor.execute("SELECT 1 FROM pg_class WHERE relowner=%s LIMIT 1", [role_id])
        if cursor.fetchone():
            raise ValueError("Serving login must not own database objects")
        cursor.execute("SELECT 1 FROM pg_proc WHERE pronamespace=%s::regnamespace AND prosecdef LIMIT 1", [schema])
        if cursor.fetchone():
            raise ValueError("Review security-definer functions before granting serving access")
        cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(namespace, identifier))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(namespace, identifier))
        cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), identifier))
        cursor.execute("""SELECT c.relname,c.relkind,array_agg(a.attname ORDER BY a.attnum)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
            WHERE n.nspname=%s AND c.relkind IN ('r','p','v','m') GROUP BY c.relname,c.relkind""", [schema])
        relations = cursor.fetchall()
        for table, kind, columns in relations:
            relation = sql.Identifier(schema, table)
            all_columns = sql.SQL(",").join(map(sql.Identifier, columns))
            cursor.execute(sql.SQL("REVOKE ALL ON {} FROM {}").format(relation, identifier))
            for operation in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                cursor.execute(sql.SQL("REVOKE {} ({}) ON {} FROM {}").format(sql.SQL(operation), all_columns, relation, identifier))
            if kind in {"v", "m"}:
                if table not in SERVING_VIEWS:
                    cursor.execute("SELECT has_table_privilege(%s,%s,'SELECT')", [role, f'{schema}.{table}'])
                    if cursor.fetchone()[0]:
                        raise ValueError("Unapproved view remains readable through shared grants: " + table)
                    continue
                cursor.execute("""SELECT DISTINCT origin.relname,a.attname FROM pg_rewrite r
                    JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass
                    JOIN pg_class origin ON origin.oid=d.refobjid
                    JOIN pg_attribute a ON a.attrelid=origin.oid AND a.attnum=d.refobjsubid
                    WHERE r.ev_class=%s::regclass AND d.refobjsubid>0""", [f'{schema}.{table}'])
                if any(column in SOURCE_COLUMNS.get(origin, ()) for origin, column in cursor.fetchall()):
                    raise ValueError("Serving view exposes source evidence: " + table)
                cursor.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(relation, identifier))
                continue
            safe = [column for column in columns if column not in SOURCE_COLUMNS.get(table, ())]
            if not safe:
                continue
            selected = sql.SQL(",").join(map(sql.Identifier, safe))
            for operation in (("SELECT",) if table in CATALOGUES else ("SELECT", "INSERT", "UPDATE")):
                cursor.execute(sql.SQL("GRANT {} ({}) ON {} TO {}").format(sql.SQL(operation), selected, relation, identifier))
            if table not in SOURCE_COLUMNS and table not in CATALOGUES:
                cursor.execute(sql.SQL("GRANT DELETE ON {} TO {}").format(relation, identifier))
        cursor.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(namespace, identifier))
        for table, _kind, columns in relations:
            for column in SOURCE_COLUMNS.get(table, set()).intersection(columns):
                cursor.execute("SELECT has_column_privilege(%s,%s,%s,'SELECT')", [role, f'{schema}.{table}', column])
                if cursor.fetchone()[0]:
                    raise ValueError("Source evidence remains readable through shared grants: " + table + "." + column)
        cursor.execute("SELECT has_schema_privilege(%s,%s,'CREATE')", [role, schema])
        if cursor.fetchone()[0]:
            raise ValueError("Serving login can still create schema objects through another grant")
        return {"role": role, "schema": schema, "relations_checked": len(relations)}
