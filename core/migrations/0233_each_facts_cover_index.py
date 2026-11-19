"""Read compact Post facts online while retaining every wide historical value."""

from contextlib import contextmanager
from importlib import import_module
from typing import ClassVar

from django.db import migrations, models, transaction
from django.db.models.functions import Coalesce
from django.db.models.lookups import LessThanOrEqual

COVER_NAME = "idx_posts_each_facts_cover"
WIDE_NAME = "idx_posts_each_facts_wide"
INDEX_LOCK = 726_514_096
BUILD_TIMEOUT = "5min"
LOCK_TIMEOUT = "2s"
COLUMNS = ("created_at", "tweet_id", "lang_detected", "lang", "author_account_key")
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
    (COVER_NAME, COLUMNS, SHORT_SQL, SHORT_NATIVE),
    (WIDE_NAME, ("created_at",), "NOT " + SHORT_SQL, WIDE_NATIVE),
)
_GROUPED = import_module("core.migrations.0232_each_facts_grouped_build")
POST_PROJECTION = (
    "SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE "
    + SHORT_SQL
    + " UNION ALL "
    "SELECT tweet_id,created_at,lang_detected,lang,author_account_key FROM posts WHERE NOT "
    + SHORT_SQL
)
SPLIT_SELECT = _GROUPED.GROUPED_SELECT.replace(
    "JOIN posts p ON p.tweet_id=pb.post_id",
    "JOIN (" + POST_PROJECTION + ") p ON p.tweet_id=pb.post_id",
    1,
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


def forwards(apps, schema_editor):
    db = schema_editor.connection
    with online_operation(db) as (cursor, schema):
        result = build_indexes(cursor, schema, db.ops.quote_name)
        with transaction.atomic(using=db.alias):
            _GROUPED.replace_saved_view(schema_editor, SPLIT_SELECT)
        return result


def backwards(apps, schema_editor):
    db = schema_editor.connection
    quote = db.ops.quote_name
    with online_operation(db) as (cursor, schema):
        existing = inspect_existing(cursor)
        # Withdraw publication and restore the prior body atomically before
        # removing these two optional access paths outside that transaction.
        with transaction.atomic(using=db.alias):
            _GROUPED.replace_saved_view(schema_editor, _GROUPED.GROUPED_SELECT)
        for spec in INDEXES:
            name = spec[0]
            if existing[name] is not None:
                cursor.execute(f"DROP INDEX CONCURRENTLY {quote(schema)}.{quote(name)}")


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0232_each_facts_grouped_build")]
    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, backwards, atomic=False)
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="post",
                    index=models.Index(
                        fields=["created_at"],
                        name=COVER_NAME,
                        include=["tweet_id", "lang_detected", "lang", "author"],
                        condition=SHORT_CONDITION,
                    ),
                ),
                migrations.AddIndex(
                    model_name="post",
                    index=models.Index(
                        fields=["created_at"],
                        name=WIDE_NAME,
                        condition=~SHORT_CONDITION,
                    ),
                ),
            ],
        ),
    ]
