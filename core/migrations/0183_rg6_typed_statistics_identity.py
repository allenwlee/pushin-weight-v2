"""Protect typed statistics identity while retaining the rolling-release guard."""

from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies: ClassVar[list] = [
        ("core", "0182_rg6_unarchived_observation_index"),
    ]

    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "CREATE UNIQUE INDEX CONCURRENTLY uq_source_statistics_typed "
                    "ON collection_observations (observation_key) "
                    "WHERE projection_kind = 'source-statistics-v1'",
                    "DROP INDEX CONCURRENTLY uq_source_statistics_typed",
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="collectionobservation",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(projection_kind="source-statistics-v1"),
                        fields=("observation_key",),
                        name="uq_source_statistics_typed",
                    ),
                ),
            ],
        ),
    ]
