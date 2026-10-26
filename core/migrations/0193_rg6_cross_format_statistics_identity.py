"""Keep statistics snapshots unique while old and typed writer images overlap."""

from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies: ClassVar[list] = [
        ("core", "0192_campaign_imported_reservation_baseline"),
    ]

    operations: ClassVar[list] = [
        migrations.RunSQL(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_source_statistics_crossformat "
            "ON collection_observations (observation_key) "
            "WHERE projection_kind = 'source-statistics-v1' "
            "OR source_metadata->'projection_kind' = '\"source-statistics-v1\"'::jsonb",
            "DROP INDEX CONCURRENTLY uq_source_statistics_crossformat",
        ),
    ]
