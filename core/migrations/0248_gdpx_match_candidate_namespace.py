"""Let GDPx crosswalk candidates resolve their identifier namespace.

The collection_job_targets source guard installed by migrations 0165/0166
resolves match_candidate subject kinds only for hf, arena and openrouter, so
recording a reviewed GDPx match failed with a cross-source namespace error.
This rewrites only that source list inside the existing guard function.
"""

from typing import ClassVar

from django.db import migrations

FUNCTION = "pw_rg5_source_collection_job_targets"
BEFORE = "j.source_id IN ('hf','arena','openrouter') THEN 'model'"
AFTER = "j.source_id IN ('hf','arena','openrouter','gdpx') THEN 'model'"


def _rewrite(schema_editor, old, new):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
        cursor.execute("SELECT pg_get_functiondef(%s::regproc)", [FUNCTION])
        definition = cursor.fetchone()[0]
        if definition.count(old) != 1:
            raise RuntimeError(f"{FUNCTION} does not contain the expected source list exactly once")
        cursor.execute(definition.replace(old, new))


def forwards(apps, schema_editor):
    _rewrite(schema_editor, BEFORE, AFTER)


def backwards(apps, schema_editor):
    _rewrite(schema_editor, AFTER, BEFORE)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0247_metric_monetary_quantity"),
    ]

    operations: ClassVar[list] = [
        migrations.RunPython(forwards, backwards),
    ]
