"""Build the General ordering index online, with safe interrupted-build retry."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations, models
from django.db.models.functions import Collate

NAME = "idx_posts_fetched_id_c"
INDEX = models.Index(
    models.F("fetched_at").desc(), Collate("tweet_id", "C"), name=NAME
)


def _validate_definition(cursor, status):
    cursor.execute("SELECT 'pg_catalog.\"C\"'::regcollation::oid")
    c_collation = cursor.fetchone()[0]
    expected = {
        "kind": "i", "method": "btree", "on_posts": True,
        "unique": False, "primary": False, "exclusion": False,
        "clustered": False, "key_count": 2, "column_count": 2,
        "predicate": None, "no_expression": True, "options": [3, 0],
        "collations": [0, c_collation], "storage_options": None,
        "columns": ["fetched_at", "tweet_id"], "default_key_opclass": True,
    }
    wrong = [key for key, value in expected.items() if status.get(key) != value]
    cursor.execute(
        """
        SELECT i.indclass[1] = (
            SELECT op.oid FROM pg_opclass op JOIN pg_am method ON method.oid=op.opcmethod
            JOIN pg_attribute a ON a.attrelid='posts'::regclass AND a.attname='tweet_id'
            WHERE op.opcnamespace='pg_catalog'::regnamespace AND op.opcdefault
              AND op.opcintype=a.atttypid AND method.amname='btree'
        ) FROM pg_index i WHERE i.indexrelid=%s
        """,
        [status["oid"]],
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        wrong.append("second_key_opclass")
    if wrong:
        raise RuntimeError(f"Refusing to change existing {NAME}: incompatible ({', '.join(wrong)})")


def _existing(cursor, base):
    status = base.index_status(cursor, NAME)
    if status is not None:
        _validate_definition(cursor, status)
    return status


def create_index(apps, schema_editor):
    db = schema_editor.connection
    base = import_module("core.migrations.0235_each_chart_facts")
    with base.online_operation(db) as (cursor, schema):
        status = _existing(cursor, base)
        qualified = f"{db.ops.quote_name(schema)}.{db.ops.quote_name(NAME)}"
        if status is not None:
            if status["valid"] and status["ready"] and status["live"]:
                return
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_progress_create_index WHERE index_relid=%s)",
                [status["oid"]],
            )
            if not status["live"] or cursor.fetchone()[0]:
                raise RuntimeError(f"Refusing to repair {NAME}: index operation is still active")
            cursor.execute(f"DROP INDEX CONCURRENTLY {qualified}")
        cursor.execute(
            f"CREATE INDEX CONCURRENTLY {db.ops.quote_name(NAME)} "
            f"ON {db.ops.quote_name(schema)}.{db.ops.quote_name('posts')} "
            '(fetched_at DESC, tweet_id COLLATE "C")'
        )
        built = _existing(cursor, base)
        if not built or not all(built[key] for key in ("valid", "ready", "live")):
            raise RuntimeError(f"{NAME} did not finish building")


def remove_index(apps, schema_editor):
    db = schema_editor.connection
    base = import_module("core.migrations.0235_each_chart_facts")
    with base.online_operation(db) as (cursor, schema):
        status = _existing(cursor, base)
        if status is not None:
            if not all(status[key] for key in ("valid", "ready", "live")):
                raise RuntimeError(f"Refusing to remove invalid {NAME}")
            cursor.execute(
                f"DROP INDEX CONCURRENTLY {db.ops.quote_name(schema)}.{db.ops.quote_name(NAME)}"
            )


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0241_each_refresh_tracking")]
    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(create_index, remove_index)],
            state_operations=[migrations.AddIndex(model_name="post", index=INDEX)],
        ),
    ]
