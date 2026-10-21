"""Generalize unpublished count lifecycle state without losing publication data."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations, models

_HOME_KEY = "home.brand_time_counts.v1"
# Reuse only frozen migration SQL, never mutable application reader code.
_OLD_FUNCTIONS = (
    import_module("core.migrations.0093_homepage_count_materialization")
    .TRIGGER_SQL.split("CREATE TRIGGER home_counts_brand_identity", 1)[0]
    .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
)
_NEW_FUNCTIONS = _OLD_FUNCTIONS.replace(
    "home_count_snapshot", "materialization_state"
).replace("WHERE id = 1", f"WHERE dataset_key = '{_HOME_KEY}'")
GRANT_SQL = """
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'staging_refresh_reader') THEN
        GRANT MAINTAIN ON materialization_state TO staging_refresh_reader;
    END IF;
END;
$grant$;
"""


def version_home_key(apps, schema_editor):
    state = apps.get_model("core", "MaterializationState")
    state.objects.using(schema_editor.connection.alias).filter(pk="1").update(
        dataset_key=_HOME_KEY
    )


def restore_singleton(apps, schema_editor):
    state = apps.get_model("core", "MaterializationState")
    rows = state.objects.using(schema_editor.connection.alias)
    if rows.exclude(pk=_HOME_KEY).exists():
        raise RuntimeError(
            "Cannot restore singleton while other materialization state exists"
        )
    rows.filter(pk=_HOME_KEY).update(dataset_key="1")


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0093_homepage_count_materialization")]
    operations: ClassVar[list] = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '2s'", reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RenameModel("HomeCountSnapshot", "MaterializationState"),
        migrations.RemoveConstraint("materializationstate", "ck_home_count_singleton"),
        migrations.RemoveConstraint("materializationstate", "ck_home_count_generation"),
        migrations.RemoveConstraint(
            "materializationstate", "ck_home_count_publication"
        ),
        migrations.RenameField("materializationstate", "id", "dataset_key"),
        migrations.AlterField(
            "materializationstate",
            "dataset_key",
            models.CharField(
                max_length=160, primary_key=True, serialize=False, db_collation="C"
            ),
        ),
        migrations.AlterModelTable("materializationstate", "materialization_state"),
        migrations.RunPython(version_home_key, restore_singleton),
        migrations.AddConstraint(
            "materializationstate",
            models.CheckConstraint(
                condition=models.Q(
                    dataset_key__regex=r"^[a-z][a-z0-9_.-]*\.v[1-9][0-9]*$"
                ),
                name="ck_materialization_key",
            ),
        ),
        migrations.AddConstraint(
            "materializationstate",
            models.CheckConstraint(
                condition=models.Q(published_generation__isnull=True)
                | models.Q(published_generation__lte=models.F("source_generation")),
                name="ck_materialization_generation",
            ),
        ),
        migrations.AddConstraint(
            "materializationstate",
            models.CheckConstraint(
                condition=models.Q(
                    published_generation__isnull=True,
                    cutoff__isnull=True,
                    refreshed_at__isnull=True,
                )
                | models.Q(
                    published_generation__isnull=False,
                    cutoff__isnull=False,
                    refreshed_at__isnull=False,
                ),
                name="ck_materialization_publication",
            ),
        ),
        migrations.RunSQL(_NEW_FUNCTIONS, reverse_sql=_OLD_FUNCTIONS),
        migrations.RunSQL(GRANT_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(
            migrations.RunSQL.noop, reverse_sql="SET LOCAL lock_timeout = '2s'"
        ),
    ]
