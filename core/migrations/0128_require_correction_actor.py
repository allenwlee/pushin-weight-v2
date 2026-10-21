from typing import ClassVar

from django.db import migrations


def require_registered_actors(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM collection_corrections WHERE actor_id IS NULL"
        )
        missing = cursor.fetchone()[0]
    if missing:
        raise RuntimeError(
            f"collection_corrections has {missing} rows without actor_id; "
            "the required registered actor reference cannot be enforced"
        )


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0127_remove_legacy_identity_columns"),
    ]

    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "SET LOCAL lock_timeout='5s'",
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "SET LOCAL statement_timeout='30s'",
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunPython(
                    require_registered_actors,
                    reverse_code=migrations.RunPython.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE collection_corrections "
                    "ALTER COLUMN actor_id SET NOT NULL",
                    reverse_sql=(
                        "ALTER TABLE collection_corrections "
                        "ALTER COLUMN actor_id DROP NOT NULL"
                    ),
                ),
            ],
            state_operations=[],
        ),
    ]
