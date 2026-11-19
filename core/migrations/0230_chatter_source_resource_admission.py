"""Keep ranked Chatter searches governed by measured bytes, time and money."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS = import_module("core.migrations.0223_chatter_collection_operation").FORWARD
ALLOW_NULL = """COALESCE((NEW.source_id='x' AND NEW.purpose='content'
    AND NEW.owner_kind='source' AND NEW.operation='chatter_search'
    AND NEW.definition#>>'{options,workflow_version}'='chatter-trends-sources-v1'), FALSE)"""
FORWARD = PREVIOUS.replace(
    "OR NEW.max_requests IS NULL OR NEW.max_requests NOT BETWEEN 1 AND 10000",
    f"OR (NEW.max_requests IS NULL AND NOT {ALLOW_NULL}) OR NEW.max_requests NOT BETWEEN 1 AND 10000",
).replace(
    "OR NEW.max_items IS NULL OR NEW.max_items NOT BETWEEN 1 AND 100000",
    f"OR (NEW.max_items IS NULL AND NOT {ALLOW_NULL}) OR NEW.max_items NOT BETWEEN 1 AND 100000",
)


def forwards(apps, schema_editor):
    schema_editor.execute(FORWARD)


def backwards(apps, schema_editor):
    # Prevent a concurrent registration between this check and restoring the guard.
    # NOWAIT refuses an occupied rollback instead of waiting on active collectors.
    schema_editor.execute("LOCK TABLE collection_jobs IN SHARE MODE NOWAIT")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""SELECT EXISTS(SELECT 1 FROM collection_jobs WHERE instruction_version=2
            AND (max_requests IS NULL OR max_items IS NULL))""")
        if cursor.fetchone()[0]:
            raise RuntimeError("ranked Chatter jobs still require nullable resource admission")
    schema_editor.execute(PREVIOUS)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0229_chatter_personalized_trend_appearance")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunPython(forwards, backwards),
    ]
