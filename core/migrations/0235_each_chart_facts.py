"""Fresh Each raw facts and online Post access paths after the Pulse schema.

No ordinary tables or JSON columns are added. The source view is the live oracle;
the saved view changes only the physical build of those exact raw facts.
"""

from contextlib import contextmanager
from typing import ClassVar

from django.db import migrations, models, transaction
from django.db.models.functions import Coalesce
from django.db.models.lookups import LessThanOrEqual

SOURCE_TABLES = (
    "posts",
    "posts_brands",
    "posts_brands_classification_states",
    "posts_brands_signals",
    "posts_brands_product_labels",
    "posts_brands_audience_topics",
    "posts_brands_geopolitical_modes",
    "posts_untracked_brand_promotions",
)
COLUMNS = """brand_id, post_id, created_at, lang_detected, lang,
    author_account_key, state_present, state_brand_id, state_contract_version,
    state_taxonomy_version, state_outcome, state_sentiment,
    legacy_sentiment_brand_ids, legacy_sentiment_values, post_type_keys,
    product_label_keys, audience_topic_edges, geopolitical_mode_versions,
    geopolitical_mode_keys, promotion_keys"""
VIEW_SQL = """
SET LOCAL lock_timeout = '2s';
INSERT INTO materialization_state(dataset_key, source_generation)
VALUES ('each.brand_post_facts.v1', 0) ON CONFLICT DO NOTHING;
CREATE VIEW each_brand_post_facts_source AS
SELECT pb.brand_id, pb.post_id, p.created_at, p.lang_detected, p.lang,
    p.author_account_key, (s.post_id IS NOT NULL) AS state_present,
    s.brand_id::text AS state_brand_id,
    s.contract_version AS state_contract_version,
    s.taxonomy_version AS state_taxonomy_version,
    s.outcome AS state_outcome, s.sentiment::text AS state_sentiment,
    COALESCE(legacy.brand_ids, ARRAY[]::text[]) AS legacy_sentiment_brand_ids,
    COALESCE(legacy.sentiments, ARRAY[]::text[]) AS legacy_sentiment_values,
    ARRAY(SELECT DISTINCT g.post_type_key::text COLLATE "C"
          FROM posts_brands_signals g
          WHERE g.post_id=pb.post_id AND g.brand_id=pb.brand_id
          ORDER BY 1) AS post_type_keys,
    ARRAY(SELECT DISTINCT l.product_label_key::text COLLATE "C"
          FROM posts_brands_product_labels l
          WHERE l.post_id=pb.post_id AND l.brand_id=pb.brand_id
          ORDER BY 1) AS product_label_keys,
    ARRAY(SELECT DISTINCT (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C"
          FROM posts_brands_audience_topics a
          WHERE a.post_id=pb.post_id AND a.brand_id=pb.brand_id
          AND a.scheme_key='ai_audience_topics/v1'
          ORDER BY 1) AS audience_topic_edges,
    COALESCE(geo.versions, ARRAY[]::text[]) AS geopolitical_mode_versions,
    COALESCE(geo.keys, ARRAY[]::text[]) AS geopolitical_mode_keys,
    ARRAY(SELECT item #>> '{}' FROM jsonb_array_elements(
          CASE WHEN jsonb_typeof(u.promotion_keys)='array'
               THEN u.promotion_keys ELSE '[]'::jsonb END) item
          WHERE jsonb_typeof(item)='string' ORDER BY (item #>> '{}') COLLATE "C") AS promotion_keys
FROM posts_brands pb JOIN posts p ON p.tweet_id=pb.post_id
LEFT JOIN posts_brands_classification_states s
  ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
LEFT JOIN posts_untracked_brand_promotions u ON u.post_id=pb.post_id
LEFT JOIN LATERAL (
    SELECT array_agg(v.brand_id ORDER BY v.brand_id COLLATE "C") AS brand_ids,
           array_agg(v.sentiment ORDER BY v.brand_id COLLATE "C") AS sentiments
    FROM (
        SELECT g.brand_id::text COLLATE "C" AS brand_id,
            CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
                 THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=pb.post_id AND g.brand_id=pb.brand_id
        GROUP BY g.brand_id::text COLLATE "C"
    ) v
) legacy ON TRUE
LEFT JOIN LATERAL (
    SELECT array_agg(g.taxonomy_version::text ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS versions,
           array_agg(g.geopolitical_mode_key::text ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS keys
    FROM posts_brands_geopolitical_modes g
    WHERE g.post_id=pb.post_id AND g.brand_id=pb.brand_id
) geo ON TRUE;
"""
SQL_SHA256 = "44cc964d723f1224afb906288d2bbe92bc7ee209bf98c2d48179f17ee7435960"
# Frozen body accepted after same-snapshot physical parity and a 47% staging
# SELECT improvement at default memory. Current source facts remain authoritative.
OPTIMIZED_SELECT = r"""WITH signal_stats AS (
    SELECT g.post_id, g.brand_id, count(*) AS row_count,
        min(g.brand_id::text COLLATE "C") AS brand_min,
        max(g.brand_id::text COLLATE "C") AS brand_max,
        min(nullif(g.sentiment::text, '') COLLATE "C") AS sentiment_min,
        max(nullif(g.sentiment::text, '') COLLATE "C") AS sentiment_max,
        min(g.post_type_key::text COLLATE "C") AS post_type_min
    FROM posts_brands_signals g GROUP BY g.post_id, g.brand_id
), signal_facts AS (
    SELECT stats.post_id, stats.brand_id,
        CASE WHEN stats.row_count=1 THEN ARRAY[stats.post_type_min]
             ELSE ARRAY(SELECT DISTINCT g.post_type_key::text COLLATE "C"
                        FROM posts_brands_signals g
                        WHERE g.post_id=stats.post_id AND g.brand_id=stats.brand_id
                        ORDER BY 1) END AS post_type_keys,
        CASE WHEN stats.brand_min=stats.brand_max THEN ARRAY[stats.brand_min]
             ELSE ARRAY(SELECT literal.spelling FROM (SELECT g.brand_id::text COLLATE "C" AS spelling,
            CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
                 THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=stats.post_id AND g.brand_id=stats.brand_id
        GROUP BY g.brand_id::text COLLATE "C") literal
                        ORDER BY literal.spelling COLLATE "C") END AS brand_ids,
        CASE WHEN stats.brand_min=stats.brand_max THEN ARRAY[
                  CASE WHEN stats.sentiment_min IS NOT DISTINCT FROM stats.sentiment_max
                       THEN stats.sentiment_min END]
             ELSE ARRAY(SELECT literal.sentiment FROM (SELECT g.brand_id::text COLLATE "C" AS spelling,
            CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
                 THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
        FROM posts_brands_signals g
        WHERE g.post_id=stats.post_id AND g.brand_id=stats.brand_id
        GROUP BY g.brand_id::text COLLATE "C") literal
                        ORDER BY literal.spelling COLLATE "C") END AS sentiments
    FROM signal_stats stats
), labels AS (
    SELECT l.post_id, l.brand_id,
        array_agg(DISTINCT l.product_label_key::text COLLATE "C"
                  ORDER BY l.product_label_key::text COLLATE "C") AS keys
    FROM posts_brands_product_labels l GROUP BY l.post_id, l.brand_id
), audience AS (
    SELECT a.post_id, a.brand_id,
        array_agg(DISTINCT (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C"
                  ORDER BY (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C") AS edges
    FROM posts_brands_audience_topics a WHERE a.scheme_key='ai_audience_topics/v1'
    GROUP BY a.post_id, a.brand_id
), geo AS (
    SELECT g.post_id, g.brand_id,
        array_agg(g.taxonomy_version::text
                  ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS versions,
        array_agg(g.geopolitical_mode_key::text
                  ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS keys
    FROM posts_brands_geopolitical_modes g GROUP BY g.post_id, g.brand_id
), promotions AS (
    SELECT u.post_id,
        array_agg(item #>> '{}' ORDER BY (item #>> '{}') COLLATE "C") AS keys
    FROM posts_untracked_brand_promotions u
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(u.promotion_keys)='array'
             THEN u.promotion_keys ELSE '[]'::jsonb END
    ) item
    WHERE jsonb_typeof(item)='string' GROUP BY u.post_id
)
SELECT pb.brand_id, pb.post_id, p.created_at, p.lang_detected, p.lang,
    p.author_account_key, (s.post_id IS NOT NULL) AS state_present,
    s.brand_id::text AS state_brand_id,
    s.contract_version AS state_contract_version,
    s.taxonomy_version AS state_taxonomy_version,
    s.outcome AS state_outcome, s.sentiment::text AS state_sentiment,
    COALESCE(signal_facts.brand_ids, ARRAY[]::text[]) AS legacy_sentiment_brand_ids,
    COALESCE(signal_facts.sentiments, ARRAY[]::text[]) AS legacy_sentiment_values,
    COALESCE(signal_facts.post_type_keys, ARRAY[]::text[]) AS post_type_keys,
    COALESCE(labels.keys, ARRAY[]::text[]) AS product_label_keys,
    COALESCE(audience.edges, ARRAY[]::text[]) AS audience_topic_edges,
    COALESCE(geo.versions, ARRAY[]::text[]) AS geopolitical_mode_versions,
    COALESCE(geo.keys, ARRAY[]::text[]) AS geopolitical_mode_keys,
    COALESCE(promotions.keys, ARRAY[]::text[]) AS promotion_keys
FROM posts_brands pb JOIN (SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE (octet_length(tweet_id) <= 256 AND COALESCE(octet_length(lang_detected),0) <= 256 AND COALESCE(octet_length(lang),0) <= 256) UNION ALL SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE NOT (octet_length(tweet_id) <= 256 AND COALESCE(octet_length(lang_detected),0) <= 256 AND COALESCE(octet_length(lang),0) <= 256)) p ON p.tweet_id=pb.post_id
LEFT JOIN posts_brands_classification_states s
    ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
LEFT JOIN signal_facts ON signal_facts.post_id=pb.post_id AND signal_facts.brand_id=pb.brand_id
LEFT JOIN labels ON labels.post_id=pb.post_id AND labels.brand_id=pb.brand_id
LEFT JOIN audience ON audience.post_id=pb.post_id AND audience.brand_id=pb.brand_id
LEFT JOIN geo ON geo.post_id=pb.post_id AND geo.brand_id=pb.brand_id
LEFT JOIN promotions ON promotions.post_id=pb.post_id
WHERE p.created_at < date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'
"""

TRIGGER_SQL = """
CREATE FUNCTION each_facts_invalidate() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
    changed_since timestamptz;
    post_key text;
    candidate timestamptz;
BEGIN
    IF TG_OP='TRUNCATE' THEN
        changed_since := '0001-01-01 00:00:00+00'::timestamptz;
    ELSIF TG_TABLE_NAME='posts' THEN
        changed_since := least(OLD.created_at,NEW.created_at);
    ELSE
        IF TG_OP <> 'INSERT' THEN
            post_key := OLD.post_id;
            SELECT p.created_at INTO candidate FROM posts p WHERE p.tweet_id=post_key;
            IF NOT FOUND THEN candidate := '0001-01-01 00:00:00+00'::timestamptz; END IF;
            changed_since := candidate;
        END IF;
        IF TG_OP <> 'DELETE' THEN
            post_key := NEW.post_id;
            SELECT p.created_at INTO candidate FROM posts p WHERE p.tweet_id=post_key;
            IF NOT FOUND THEN candidate := '0001-01-01 00:00:00+00'::timestamptz; END IF;
            changed_since := least(changed_since,candidate);
        END IF;
    END IF;
    IF changed_since < date_trunc('day', clock_timestamp(), 'UTC') - interval '1 day' THEN
        UPDATE materialization_state SET source_generation=source_generation+1,
            dirty_since=least(dirty_since,changed_since)
        WHERE dataset_key='each.brand_post_facts.v1';
    END IF;
    RETURN NULL;
END
$fn$;
CREATE FUNCTION each_facts_brand_identity() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    IF EXISTS ((SELECT nickname COLLATE "C" FROM old_rows EXCEPT SELECT nickname COLLATE "C" FROM new_rows)
        UNION ALL (SELECT nickname COLLATE "C" FROM new_rows EXCEPT SELECT nickname COLLATE "C" FROM old_rows)) THEN
        UPDATE materialization_state SET source_generation=source_generation+1,
            dirty_since='0001-01-01 00:00:00+00'::timestamptz
        WHERE dataset_key='each.brand_post_facts.v1';
    END IF;
    RETURN NULL;
END
$fn$;
CREATE TRIGGER each_facts_brand_identity AFTER UPDATE ON brands
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT EXECUTE FUNCTION each_facts_brand_identity();
CREATE TRIGGER each_facts_truncate AFTER TRUNCATE ON brands
FOR EACH STATEMENT EXECUTE FUNCTION each_facts_invalidate();
"""
# Field ownership and actual SQL columns are frozen in this migration.
UPDATE_COLUMNS = {
    "posts": [
        ("tweet_id", True),
        ("created_at", False),
        ("lang_detected", True),
        ("lang", True),
        ("author_account_key", False),
    ],
    "posts_brands": [("post_id", True), ("brand_id", True)],
    "posts_brands_classification_states": [
        (x, True)
        for x in (
            "post_id",
            "brand_id",
            "contract_version",
            "taxonomy_version",
            "outcome",
            "sentiment",
        )
    ],
    "posts_brands_signals": [
        (x, True) for x in ("post_id", "brand_id", "post_type_key", "sentiment")
    ],
    "posts_brands_product_labels": [
        (x, True) for x in ("post_id", "brand_id", "product_label_key")
    ],
    "posts_brands_audience_topics": [
        ("post_id", True),
        ("brand_id", True),
        ("concept_id", False),
        ("scheme_key", True),
        ("scheme_revision", False),
    ],
    "posts_brands_geopolitical_modes": [
        (x, True)
        for x in ("post_id", "brand_id", "geopolitical_mode_key", "taxonomy_version")
    ],
    "posts_untracked_brand_promotions": [("post_id", True), ("promotion_keys", False)],
}
REVERSE_SQL = "SET LOCAL lock_timeout = '2s';\nDROP TRIGGER IF EXISTS each_facts_brand_identity ON brands;\nDROP TRIGGER IF EXISTS each_facts_truncate ON brands;\n"
for table in SOURCE_TABLES:
    for event in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
        if table == "posts" and event in ("INSERT", "DELETE"):
            continue
        condition = ""
        if event == "UPDATE":
            changes = []
            for column, binary in UPDATE_COLUMNS[table]:
                collate = ' COLLATE "C"' if binary else ""
                changes.append(
                    f"OLD.{column}{collate} IS DISTINCT FROM NEW.{column}{collate}"
                )
            condition = " WHEN (" + " OR ".join(changes) + ")"
        level = "STATEMENT" if event == "TRUNCATE" else "ROW"
        TRIGGER_SQL += f"CREATE TRIGGER each_facts_{event.lower()} AFTER {event} ON {table} FOR EACH {level}{condition} EXECUTE FUNCTION each_facts_invalidate();\n"
        REVERSE_SQL += f"DROP TRIGGER IF EXISTS each_facts_{event.lower()} ON {table};\n"
REVERSE_SQL += """
DROP FUNCTION IF EXISTS each_facts_brand_identity();
DROP FUNCTION IF EXISTS each_facts_invalidate();
DROP MATERIALIZED VIEW IF EXISTS each_brand_post_facts;
DROP VIEW IF EXISTS each_brand_post_facts_source;
DELETE FROM materialization_state WHERE dataset_key='each.brand_post_facts.v1';
"""

COVER_NAME = "idx_posts_each_facts_cover"
WIDE_NAME = "idx_posts_each_facts_wide"
INDEX_LOCK = 726_514_096
BUILD_TIMEOUT = "5min"
LOCK_TIMEOUT = "2s"
POST_INDEX_COLUMNS = ("created_at", "tweet_id", "lang_detected", "lang", "author_account_key")
SHORT_SQL = "(octet_length(tweet_id) <= 256 AND COALESCE(octet_length(lang_detected),0) <= 256 AND COALESCE(octet_length(lang),0) <= 256)"
SHORT_NATIVE = "((octet_length(tweet_id) <= 256) AND (COALESCE(octet_length(lang_detected), 0) <= 256) AND (COALESCE(octet_length(lang), 0) <= 256))"
WIDE_NATIVE = "(NOT ((octet_length(tweet_id) <= 256) AND (COALESCE(octet_length(lang_detected), 0) <= 256) AND (COALESCE(octet_length(lang), 0) <= 256)))"
SHORT_CONDITION = models.Q(
    LessThanOrEqual(
        models.Func(
            "tweet_id", function="octet_length", output_field=models.IntegerField()
        ),
        models.Value(256),
    ),
    LessThanOrEqual(
        Coalesce(
            models.Func(
                "lang_detected",
                function="octet_length",
                output_field=models.IntegerField(),
            ),
            models.Value(0),
        ),
        models.Value(256),
    ),
    LessThanOrEqual(
        Coalesce(
            models.Func(
                "lang", function="octet_length", output_field=models.IntegerField()
            ),
            models.Value(0),
        ),
        models.Value(256),
    ),
)
INDEXES = (
    (COVER_NAME, POST_INDEX_COLUMNS, SHORT_SQL, SHORT_NATIVE),
    (WIDE_NAME, ("created_at",), "NOT " + SHORT_SQL, WIDE_NATIVE),
)

POST_PROJECTION = (
    "SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE "
    + SHORT_SQL
    + " UNION ALL "
    "SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE NOT "
    + SHORT_SQL
)

def index_status(cursor, name):
    """Inspect the named native object, including its exact frozen predicate."""
    cursor.execute(
        """
        SELECT c.oid,c.relkind,pg_get_indexdef(i.indexrelid),am.amname,
            i.indrelid='posts'::regclass,i.indisvalid,i.indisready,i.indislive,
            i.indisunique,i.indisprimary,i.indisexclusion,i.indisclustered,
            i.indnkeyatts,i.indnatts,pg_get_expr(i.indpred,i.indrelid),i.indexprs IS NULL,
            i.indoption::smallint[],i.indcollation::oid[],c.reloptions,
            ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY k(n,o)
                  JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.n ORDER BY k.o),
            i.indclass[0] = (
                SELECT op.oid FROM pg_opclass op JOIN pg_am method ON method.oid=op.opcmethod
                JOIN pg_attribute a ON a.attrelid='posts'::regclass AND a.attname='created_at'
                WHERE op.opcnamespace='pg_catalog'::regnamespace AND op.opcdefault
                  AND op.opcintype=a.atttypid AND method.amname='btree'
            )
        FROM pg_class c LEFT JOIN pg_index i ON i.indexrelid=c.oid
        LEFT JOIN pg_am am ON am.oid=c.relam
        WHERE c.relnamespace=(SELECT relnamespace FROM pg_class WHERE oid='posts'::regclass)
          AND c.relname=%s
        """,
        [name],
    )
    row = cursor.fetchone()
    if row is None:
        return None
    names = (
        "oid",
        "kind",
        "definition",
        "method",
        "on_posts",
        "valid",
        "ready",
        "live",
        "unique",
        "primary",
        "exclusion",
        "clustered",
        "key_count",
        "column_count",
        "predicate",
        "no_expression",
        "options",
        "collations",
        "storage_options",
        "columns",
        "default_key_opclass",
    )
    return dict(zip(names, row, strict=True))


def validate_index(status, spec):
    name, columns, _predicate, native_predicate = spec
    expected = {
        "kind": "i",
        "method": "btree",
        "on_posts": True,
        "valid": True,
        "ready": True,
        "live": True,
        "unique": False,
        "primary": False,
        "exclusion": False,
        "clustered": False,
        "key_count": 1,
        "column_count": len(columns),
        "predicate": native_predicate,
        "no_expression": True,
        "options": [0],
        "collations": [0],
        "storage_options": None,
        "columns": list(columns),
        "default_key_opclass": True,
    }
    wrong = [key for key, value in expected.items() if status.get(key) != value]
    if wrong:
        raise RuntimeError(
            f"Refusing to change existing {name}: incompatible or invalid "
            f"native object ({', '.join(wrong)}); inspect its definition/state before retrying"
        )


@contextmanager
def online_operation(db):
    """Never queue an advisory waiter or retain changed session timeout limits."""
    if db.in_atomic_block or not db.get_autocommit():
        raise RuntimeError("Each facts indexes require an autocommit connection")
    with db.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [INDEX_LOCK])
        if not cursor.fetchone()[0]:
            raise RuntimeError(
                "Each facts index operation is already running; retry after it finishes"
            )
        previous = None
        try:
            cursor.execute("SHOW statement_timeout")
            statement = cursor.fetchone()[0]
            cursor.execute("SHOW lock_timeout")
            lock = cursor.fetchone()[0]
            previous = (statement, lock)
            cursor.execute(
                "SELECT set_config('statement_timeout',%s,false),set_config('lock_timeout',%s,false)",
                [BUILD_TIMEOUT, LOCK_TIMEOUT],
            )
            cursor.execute(
                "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid='posts'::regclass"
            )
            yield cursor, cursor.fetchone()[0]
        finally:
            try:
                if previous is not None:
                    cursor.execute(
                        "SELECT set_config('statement_timeout',%s,false),set_config('lock_timeout',%s,false)",
                        list(previous),
                    )
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [INDEX_LOCK])


def inspect_existing(cursor):
    existing = {spec[0]: index_status(cursor, spec[0]) for spec in INDEXES}
    # Validate both before creating/removing either. An interrupted build's
    # invalid residue is never repaired by deleting an unidentified object.
    for spec in INDEXES:
        if existing[spec[0]] is not None:
            validate_index(existing[spec[0]], spec)
    return existing


def build_indexes(cursor, schema, quote):
    existing = inspect_existing(cursor)
    result = {}
    for spec in INDEXES:
        name, columns, predicate, _native_predicate = spec
        if existing[name] is not None:
            result[name] = "adopted"
            continue
        include = " INCLUDE (" + ",".join(columns[1:]) + ")" if len(columns) > 1 else ""
        cursor.execute(
            f"CREATE INDEX CONCURRENTLY {quote(name)} ON {quote(schema)}.{quote('posts')} "
            f"USING btree (created_at){include} WHERE {predicate}"
        )
        built = index_status(cursor, name)
        if built is None:
            raise RuntimeError(f"{name} disappeared during creation")
        validate_index(built, spec)
        result[name] = "created"
    return result


def prebuild_indexes(apps, schema_editor):
    """Optional online prebuild only: no MV changes and no migration recording.

    An interrupted concurrent build may leave an invalid index. Inspect its
    native state and original build receipt before separately reviewed cleanup.
    """
    db = schema_editor.connection
    with online_operation(db) as (cursor, schema):
        return build_indexes(cursor, schema, db.ops.quote_name)



VIEW_SQL += f"""
CREATE MATERIALIZED VIEW each_brand_post_facts AS
{OPTIMIZED_SELECT}
WITH NO DATA;
CREATE UNIQUE INDEX each_brand_post_facts_key ON each_brand_post_facts(brand_id, post_id);
CREATE INDEX each_brand_post_facts_window ON each_brand_post_facts(brand_id, created_at);
"""


def create_storage(apps, schema_editor):
    db = schema_editor.connection
    # Concurrent indexes are outside this short, all-or-nothing DDL transaction.
    with transaction.atomic(using=db.alias), db.cursor() as cursor:
        cursor.execute(VIEW_SQL + TRIGGER_SQL)


def drop_storage(apps, schema_editor):
    db = schema_editor.connection
    with transaction.atomic(using=db.alias), db.cursor() as cursor:
        cursor.execute(REVERSE_SQL)


def forwards(apps, schema_editor):
    db = schema_editor.connection
    with online_operation(db) as (cursor, schema):
        result = build_indexes(cursor, schema, db.ops.quote_name)
        create_storage(apps, schema_editor)
        return result


def backwards(apps, schema_editor):
    db = schema_editor.connection
    with online_operation(db) as (cursor, schema):
        existing = inspect_existing(cursor)
        for spec in INDEXES:
            if existing[spec[0]] is not None:
                cursor.execute(
                    f"DROP INDEX CONCURRENTLY {db.ops.quote_name(schema)}.{db.ops.quote_name(spec[0])}"
                )
        drop_storage(apps, schema_editor)


def remove_indexes(apps, schema_editor):
    """Reverse only these verified access paths; retain authoritative source data."""
    db = schema_editor.connection
    with online_operation(db) as (cursor, schema):
        existing = inspect_existing(cursor)
        for spec in INDEXES:
            if existing[spec[0]] is not None:
                cursor.execute(
                    f"DROP INDEX CONCURRENTLY {db.ops.quote_name(schema)}.{db.ops.quote_name(spec[0])}"
                )


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0234_pulse_category_evidence_guard")]
    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(forwards, backwards, atomic=False)],
            state_operations=[
                migrations.AddIndex(
                    model_name="post",
                    index=models.Index(
                        fields=["created_at"], name=COVER_NAME,
                        include=["tweet_id", "lang_detected", "lang", "author"],
                        condition=SHORT_CONDITION,
                    ),
                ),
                migrations.AddIndex(
                    model_name="post",
                    index=models.Index(
                        fields=["created_at"], name=WIDE_NAME, condition=~SHORT_CONDITION,
                    ),
                ),
            ],
        ),
    ]
