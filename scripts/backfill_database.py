"""Scoped, read-only backfill export and transactional import into a new database.

This operator never reads credentials from arguments or prints connection URLs.
It preserves primary keys, receipts and immutable instructions. Export includes
owned children and the transitive foreign-key dependencies of selected records;
it does not clone the source database or activate a runner.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from collections import defaultdict, deque
from contextlib import ExitStack
from pathlib import Path

import psycopg
from psycopg import sql

FORMAT = "x-backfill-database-copy/v1"
MARKER = "x-backfill-copy/v1:"
BATCH = 200
# These roots own their children. Referenced evidence owners do not: copying one
# referenced run must not pull every unrelated observation belonging to its job.
OWNED = {
    "collection_jobs",
    "collection_runs",
    "collection_scope_runs",
    "collection_attempts",
    "collection_observations",
    "collection_requests",
    "collection_corrections",
    "provider_batches",
    "original_content_calls",
    "original_content",
    "original_content_runs",
    "post_translation_artifacts",
    "post_synthesis_artifacts",
    "rare_type_search_runs",
    "rare_type_search_hits",
    "rare_type_decisions",
    "rare_type_decision_processing_cycles",
    "targeted_extraction_states",
    "events",
    "opportunities",
    "job_listings",
    "model_releases",
}
ACCOUNT_CHILDREN = {
    "x_account_details",
    "account_profile_snapshots",
    "account_profile_text_translations",
}
EXCLUDED_POST_CHILDREN = {
    "posts",  # Later quotes are not owned by their quoted parent.
    "collection_observations",
    "account_profile_snapshots",
    "rare_type_search_hits",
}
# Migrations create reference evidence in this shared archive. Only referenced
# documents belong in the copy, never the source's entire response history.
DEPENDENCY_ONLY_SEEDS = {"collection_evidence_archives"}


def checked(condition, message):
    if not condition:
        raise ValueError(message)


def emit(event, **values):
    print(json.dumps({"event": event, **values}, sort_keys=True), flush=True)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def identity(conn):
    name, user = conn.execute("SELECT current_database(),session_user").fetchone()
    return {"name": name, "user": user, "host": conn.info.host}


def catalog(conn):
    columns = defaultdict(list)
    generated_columns = defaultdict(dict)
    for table, column, kind, generated, expression in conn.execute("""
        SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attgenerated,
               pg_get_expr(d.adbin,d.adrelid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname=current_schema() AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname,a.attname
    """):
        if generated:
            generated_columns[table][column] = expression
        columns[table].append((column, kind))
    keys = {}
    edges = []
    for table, kind, parent, local, remote in conn.execute("""
        SELECT c.conrelid::regclass::text,c.contype,c.confrelid::regclass::text,
          ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num,ord)
                JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num ORDER BY k.ord),
          ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num,ord)
                JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num ORDER BY k.ord)
        FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
        WHERE n.nspname=current_schema() AND c.contype IN ('p','f')
    """):
        if kind == "p":
            keys[table] = local
        else:
            edges.append((table, local, parent, remote))
    return {
        t: {"columns": cols, "pk": keys.get(t), "generated": generated_columns[t]}
        for t, cols in columns.items()
    }, edges


def where_keys(columns, values):
    values = list(values)
    if not values:
        return sql.SQL("false"), []
    names = sql.SQL(",").join(map(sql.Identifier, columns))
    row = (
        sql.SQL("(")
        + sql.SQL(",").join(sql.Placeholder() for _ in columns)
        + sql.SQL(")")
    )
    return (
        sql.SQL("({}) IN ({})").format(names, sql.SQL(",").join(row for _ in values)),
        [v for value in values for v in value],
    )


def reverse_owned(parent, child):
    if parent == "accounts":
        return child in ACCOUNT_CHILDREN
    if parent == "posts":
        return child not in EXCLUDED_POST_CHILDREN and not child.startswith(
            "collection_"
        )
    return parent in OWNED


def export_snapshot(source, destination, directory, prefixes):
    directory = Path(directory)
    checked(not (directory / "snapshot.json").exists(), "snapshot_already_exists")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    source.execute("SET LOCAL statement_timeout='45s'")
    source.execute("SET LOCAL lock_timeout='2s'")
    source.execute("SET LOCAL TIME ZONE 'UTC'")
    destination.execute("SET TRANSACTION READ ONLY")
    src, dst = identity(source), identity(destination)
    checked(src != dst and src["host"] != dst["host"], "separate_destination_required")
    checked(
        dst["name"] == "xbackfiller" and dst["user"] == "xbackfiller",
        "dedicated_destination_required",
    )
    schema, edges = catalog(source)
    target_schema, target_edges = catalog(destination)
    checked(
        schema == target_schema and sorted(edges) == sorted(target_edges),
        "source_destination_schema_mismatch",
    )
    migrations = list(
        source.execute("SELECT app,name FROM django_migrations ORDER BY app,name")
    )
    checked(
        migrations
        == list(
            destination.execute(
                "SELECT app,name FROM django_migrations ORDER BY app,name"
            )
        ),
        "source_destination_migrations_mismatch",
    )
    checked(
        not destination.execute(
            "SELECT EXISTS(SELECT 1 FROM posts) OR EXISTS(SELECT 1 FROM collection_jobs)"
        ).fetchone()[0],
        "destination_application_data_not_empty",
    )
    checked(
        not source.execute("""SELECT EXISTS(SELECT 1 FROM collection_runs r JOIN collection_jobs j ON j.id=r.job_id
      WHERE j.operation='x_backfill' AND r.status='running' AND r.lease_expires_at>now())""").fetchone()[
            0
        ],
        "source_backfill_active",
    )
    checked(
        not source.execute("""SELECT EXISTS(SELECT 1 FROM provider_batches b JOIN collection_jobs j ON j.id=b.source_collection_job_id
      WHERE j.operation='x_backfill' AND (b.claim_expires_at>now() OR b.state IN ('uploading','uploaded','submitting','waiting','ambiguous','importing')))""").fetchone()[
            0
        ],
        "source_enrichment_active",
    )
    selected, expanded = defaultdict(set), defaultdict(set)
    queue = deque()
    metadata = {}
    files = {}
    streams = ExitStack()
    total_bytes = 0
    jobs = []

    def query_for(table, condition):
        checked(
            table in schema and schema[table]["pk"],
            "copy_table_requires_primary_key:" + table,
        )
        query = (
            sql.SQL("SELECT row_to_json(t)::text FROM {} t WHERE ").format(
                sql.Identifier(table)
            )
            + condition
        )
        return query

    def read(table, condition, params):
        return source.execute(query_for(table, condition), params)

    def add(table, condition, params=(), owned=False, records=None):
        nonlocal total_bytes
        for (raw,) in records if records is not None else read(table, condition, params):
            record = json.loads(raw)
            key = tuple(record[k] for k in schema[table]["pk"])
            if key not in selected[table]:
                selected[table].add(key)
                body = raw.encode() + b"\n"
                total_bytes += len(body)
                checked(
                    total_bytes <= 2 * 1024**3,
                    "scoped_export_exceeds_two_gib_review_selection",
                )
                if table not in files:
                    files[table] = streams.enter_context(
                        gzip.open(directory / (table + ".jsonl.gz"), "wb")  # noqa: SIM115 -- ExitStack owns the stream
                    )
                    metadata[table] = {"rows": 0, "sha256": hashlib.sha256()}
                files[table].write(body)
                metadata[table]["rows"] += 1
                metadata[table]["sha256"].update(body)
                queue.append((table, record, False))
                if table == "collection_jobs":
                    jobs.append(
                        {
                            k: record[k]
                            for k in (
                                "id",
                                "job_key",
                                "definition_sha256",
                                "definition",
                            )
                        }
                    )
            if owned and key not in expanded[table]:
                expanded[table].add(key)
                queue.append((table, record, True))

    try:
        seed_tables = []
        for table in sorted(schema):
            if table.startswith(("django_", "auth_")):
                continue
            exists = destination.execute(
                sql.SQL("SELECT EXISTS(SELECT 1 FROM {})").format(sql.Identifier(table))
            ).fetchone()[0]
            if exists:
                seed_tables.append(table)
                if table not in DEPENDENCY_ONLY_SEEDS:
                    add(table, sql.SQL("true"))
        for table in (
            "brands",
            "brand_keywords",
            "brand_search_terms",
            "brand_hashtags",
            "twitter_list_memberships",
            "brands_accounts",
            "roles",
            "role_labels",
        ):
            if table in schema:
                add(table, sql.SQL("true"))
        conditions = sql.SQL(" OR ").join(sql.SQL("job_key LIKE %s") for _ in prefixes)
        params = [p + "%" for p in prefixes]
        add(
            "collection_jobs",
            sql.SQL("operation='x_backfill' AND mode='historical' AND (")
            + conditions
            + sql.SQL(")"),
            params,
            True,
        )
        root_jobs = [
            j["id"] for j in jobs if any(j["job_key"].startswith(p) for p in prefixes)
        ]
        checked(root_jobs, "no_source_jobs_selected")
        add(
            "posts",
            sql.SQL(
                "tweet_id IN (SELECT o.post_id FROM collection_observations o JOIN collection_runs r ON r.id=o.run_id WHERE r.job_id = ANY(%s::uuid[]) AND o.post_id IS NOT NULL)"
            ),
            [root_jobs],
            True,
        )
        add(
            "rare_type_search_runs",
            sql.SQL(" OR ").join(sql.SQL("lane LIKE %s") for _ in root_jobs),
            ["bf:" + j + ":%" for j in root_jobs],
            True,
        )
        while queue:
            # Group work to avoid one network round trip for each foreign key.
            group = [queue.popleft() for _ in range(min(BATCH, len(queue)))]
            forward, reverse = defaultdict(set), defaultdict(set)
            for table, record, owned in group:
                for child, local, parent, remote in edges:
                    if not owned and child == table:
                        values = tuple(record[c] for c in local)
                        if all(v is not None for v in values):
                            forward[(parent, tuple(remote))].add(values)
                    if parent == table and (
                        (owned and reverse_owned(parent, child))
                        or (parent == "accounts" and child in ACCOUNT_CHILDREN)
                    ):
                        reverse[(child, tuple(local))].add(
                            tuple(record[c] for c in remote)
                        )
                if (
                    table == "original_content_calls"
                    and not owned
                    and record.get("member_post_ids")
                ):
                    forward[("posts", ("tweet_id",))].update(
                        (p,) for p in record["member_post_ids"]
                    )
            reads = []
            for (table, columns), values in forward.items():
                if list(columns) == schema[table]["pk"]:
                    values -= selected[table]
                if not values:
                    continue
                condition, params = where_keys(columns, values)
                reads.append((table, condition, params, False))
            for (table, columns), values in reverse.items():
                condition, params = where_keys(columns, values)
                reads.append((table, condition, params, True))
            # These reads share one immutable snapshot and do not depend on one
            # another. Pipeline their round trips; ingest results in order.
            # Each attempt owns hundreds of scopes. Fetch those through a
            # server cursor so one response cannot contain an entire run tree.
            streamed = [row for row in reads if row[0] == "collection_scope_runs"]
            reads = [row for row in reads if row[0] != "collection_scope_runs"]
            cursors = []
            try:
                with source.pipeline():
                    for table, condition, params, _ in reads:
                        cursors.append(read(table, condition, params))
            except psycopg.Error:
                emit("export_read_failed", reads=[
                    {"table": row[0], "parameters": len(row[2]),
                     "status": cursor.pgresult.status if cursor.pgresult else None}
                    for row, cursor in zip(reads, cursors, strict=False)])
                raise
            for (table, condition, params, owned), cursor in zip(reads, cursors, strict=True):
                add(table, condition, params, owned, records=cursor)
            for table, condition, params, owned in streamed:
                with source.cursor(name="backfill_copy_scopes") as cursor:
                    cursor.itersize = 500
                    cursor.execute(query_for(table, condition), params)
                    add(table, condition, params, owned, records=cursor)
            if sum(len(v) for v in selected.values()) % 5000 < BATCH:
                emit(
                    "export_progress",
                    rows=sum(len(v) for v in selected.values()),
                    bytes=total_bytes,
                    pending=len(queue),
                )
    finally:
        streams.close()
    result = {
        "format": FORMAT,
        "source": src,
        "destination": dst,
        "schema": schema,
        "tables": {
            t: {"rows": m["rows"], "sha256": m["sha256"].hexdigest()}
            for t, m in metadata.items()
        },
        "root_job_ids": root_jobs,
        "jobs": jobs,
        "seed_tables": seed_tables,
        "bytes": total_bytes,
        "migrations": migrations,
    }
    result["snapshot_sha256"] = fingerprint(result)
    (directory / "snapshot.json").write_text(json.dumps(result, sort_keys=True))
    emit(
        "export_complete",
        tables=len(metadata),
        rows=sum(m["rows"] for m in metadata.values()),
        bytes=total_bytes,
        snapshot_sha256=result["snapshot_sha256"],
    )
    return result


def iter_batches(path):
    with gzip.open(path, "rt") as stream:
        batch, size = [], 0
        for row in stream:
            batch.append(row.rstrip("\n"))
            size += len(row)
            if len(batch) >= BATCH or size >= 4 * 1024**2:
                yield batch
                batch, size = [], 0
        if batch:
            yield batch


def copy_marker(conn):
    return conn.execute(
        "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).fetchone()[0]


def set_copy_marker(conn, name, value):
    conn.execute(
        sql.SQL("COMMENT ON DATABASE {} IS {}").format(
            sql.Identifier(name), sql.Literal(value)
        )
    )


def import_snapshot(conn, directory):
    directory = Path(directory)
    snapshot = json.loads((directory / "snapshot.json").read_text())
    signature = snapshot.pop("snapshot_sha256")
    checked(
        snapshot["format"] == FORMAT and fingerprint(snapshot) == signature,
        "snapshot_manifest_changed",
    )
    actual = identity(conn)
    checked(actual == snapshot["destination"], "copy_destination_changed")
    schema, _ = catalog(conn)
    checked(
        json.loads(json.dumps(schema)) == snapshot["schema"],
        "copy_destination_schema_changed",
    )
    marker = copy_marker(conn)
    if marker == MARKER + signature:
        return {"status": "already_imported", "snapshot_sha256": signature}
    checked(not marker, "destination_has_existing_copy_marker")
    checked(
        not conn.execute(
            "SELECT EXISTS(SELECT 1 FROM posts) OR EXISTS(SELECT 1 FROM collection_jobs)"
        ).fetchone()[0],
        "destination_application_data_not_empty",
    )
    for table, entry in snapshot["tables"].items():
        sha, count = hashlib.sha256(), 0
        with gzip.open(directory / (table + ".jsonl.gz"), "rb") as stream:
            for row in stream:
                sha.update(row)
                count += 1
        checked(
            sha.hexdigest() == entry["sha256"] and count == entry["rows"],
            "copy_file_changed:" + table,
        )
    conn.execute("SET LOCAL TIME ZONE 'UTC'")
    conn.execute("SET LOCAL statement_timeout='120s'")
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    tables = sorted(snapshot["tables"])
    checked(not conn.execute("""
        SELECT EXISTS(SELECT 1 FROM pg_trigger
          WHERE NOT tgisinternal AND tgenabled<>'O'
            AND tgrelid::regclass::text=ANY(%s))
    """, [tables]).fetchone()[0], "copy_requires_explicit_nonstandard_trigger_policy")
    for child, parent in conn.execute("""
        SELECT conrelid::regclass::text,confrelid::regclass::text
        FROM pg_constraint WHERE contype='f' AND NOT condeferrable
          AND connamespace=current_schema()::regnamespace
    """):
        if child in tables and parent in tables:
            checked(tables.index(parent) < tables.index(child),
                    "copy_requires_immediate_fk_order:" + child)
    for table in tables:
        conn.execute(
            sql.SQL("ALTER TABLE {} DISABLE TRIGGER USER").format(sql.Identifier(table))
        )
    # The destination has only fresh migration seed data. Clear it transactionally
    # to avoid collisions with source UUIDs representing the same reference row.
    if snapshot["seed_tables"]:
        conn.execute(
            sql.SQL("TRUNCATE {} CASCADE").format(
                sql.SQL(",").join(map(sql.Identifier, snapshot["seed_tables"]))
            )
        )
    for table in tables:
        # Generated values are recomputed by the identical target expression,
        # then included in the whole-row parity comparison below.
        columns = [
            c[0]
            for c in schema[table]["columns"]
            if c[0] not in schema[table]["generated"]
        ]
        names = sql.SQL(",").join(map(sql.Identifier, columns))
        query = sql.SQL(
            "INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE SELECT {} FROM jsonb_populate_recordset(NULL::{},%s::jsonb) ON CONFLICT ({}) DO NOTHING"
        ).format(
            sql.Identifier(table),
            names,
            names,
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, schema[table]["pk"])),
        )
        for batch in iter_batches(directory / (table + ".jsonl.gz")):
            conn.execute(query, ["[" + ",".join(batch) + "]"])
        emit("import_table", table=table, rows=snapshot["tables"][table]["rows"])
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    for table in tables:
        # Compare whole rows in export order using real PostgreSQL type parsing.
        columns = [c[0] for c in schema[table]["columns"]]
        pk = schema[table]["pk"]
        joins = sql.SQL(" AND ").join(
            sql.SQL("a.{}=b.{}").format(sql.Identifier(k), sql.Identifier(k))
            for k in pk
        )
        query = sql.SQL(
            "SELECT count(*) FROM jsonb_populate_recordset(NULL::{},%s::jsonb) a LEFT JOIN {} b ON {} WHERE b IS NULL OR to_jsonb(a) IS DISTINCT FROM to_jsonb(b)"
        ).format(sql.Identifier(table), sql.Identifier(table), joins)
        for batch in iter_batches(directory / (table + ".jsonl.gz")):
            checked(
                conn.execute(query, ["[" + ",".join(batch) + "]"]).fetchone()[0] == 0,
                "copy_row_parity_failed:" + table,
            )
        for column in columns:
            sequence = conn.execute(
                "SELECT pg_get_serial_sequence(%s,%s)", [table, column]
            ).fetchone()[0]
            if sequence:
                conn.execute(
                    sql.SQL(
                        "SELECT setval(%s, GREATEST(COALESCE(max({}),1),1), count(*)>0) FROM {}"
                    ).format(sql.Identifier(column), sql.Identifier(table)),
                    [sequence],
                )
        conn.execute(
            sql.SQL("ALTER TABLE {} ENABLE TRIGGER USER").format(sql.Identifier(table))
        )
    set_copy_marker(conn, actual["name"], MARKER + signature)
    return {
        "status": "verified",
        "snapshot_sha256": signature,
        "rows": sum(t["rows"] for t in snapshot["tables"].values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("--source-env", default="BACKFILL_SOURCE_DATABASE_URL")
    parser.add_argument("--destination-env", default="BACKFILL_DATABASE_URL")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--job-prefix", action="append")
    args = parser.parse_args()
    with psycopg.connect(os.environ[args.destination_env]) as destination:
        if args.action == "export":
            checked(args.job_prefix, "explicit_job_prefix_required")
            with psycopg.connect(os.environ[args.source_env]) as source:
                export_snapshot(source, destination, args.directory, args.job_prefix)
        else:
            result = import_snapshot(destination, args.directory)
            destination.commit()
            (args.directory / "import.json").write_text(
                json.dumps(result, sort_keys=True)
            )
            emit("import_complete", **result)


if __name__ == "__main__":
    main()
