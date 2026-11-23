"""Add compact provider attribution without rewriting physical receipts."""

from typing import ClassVar

from django.db import migrations, models, transaction


def add_columns(apps, schema_editor):
    with transaction.atomic(using=schema_editor.connection.alias):
        schema_editor.execute("SET LOCAL lock_timeout = '5s'")
        schema_editor.execute(
            "ALTER TABLE collection_requests ADD COLUMN provider_source_id varchar(32), "
            "ADD COLUMN credential_purpose varchar(16), ADD COLUMN returned_count integer"
        )
        schema_editor.execute(
            "ALTER TABLE collection_requests ADD CONSTRAINT fk_collection_request_provider "
            "FOREIGN KEY (provider_source_id) REFERENCES data_sources(id) "
            "DEFERRABLE INITIALLY DEFERRED NOT VALID"
        )
        schema_editor.execute(
            "ALTER TABLE collection_requests ADD CONSTRAINT ck_collection_request_returned_count "
            "CHECK (returned_count >= 0) NOT VALID"
        )


def drop_columns(apps, schema_editor):
    with transaction.atomic(using=schema_editor.connection.alias):
        schema_editor.execute("SET LOCAL lock_timeout = '5s'")
        schema_editor.execute("LOCK TABLE collection_requests IN ACCESS EXCLUSIVE MODE NOWAIT")
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM collection_requests WHERE provider_source_id IS NOT NULL "
                "OR credential_purpose IS NOT NULL OR returned_count IS NOT NULL)"
            )
            if cursor.fetchone()[0]:
                raise RuntimeError("Preserve provider request evidence before reversing this migration")
        schema_editor.execute(
            "ALTER TABLE collection_requests DROP COLUMN provider_source_id, "
            "DROP COLUMN credential_purpose, DROP COLUMN returned_count"
        )


def register_providers(apps, schema_editor):
    source = apps.get_model("core", "DataSource")
    for key, name in (("twitterapi", "TwitterAPI.io"), ("twexapi", "TwexAPI")):
        source.objects.using(schema_editor.connection.alias).get_or_create(
            pk=key, defaults={"name": name, "source_type": "social"},
        )


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0237_merge_chatter_search_provider")]
    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_columns, drop_columns, atomic=True)],
            state_operations=[
                migrations.AddField(
                    model_name="collectionrequest", name="provider_source",
                    field=models.ForeignKey(
                        "core.DataSource", on_delete=models.PROTECT, null=True, db_index=False,
                        related_name="provider_requests",
                    ),
                ),
                migrations.AddField(
                    model_name="collectionrequest", name="credential_purpose",
                    field=models.CharField(max_length=16, null=True),
                ),
                migrations.AddField(
                    model_name="collectionrequest", name="returned_count",
                    field=models.PositiveIntegerField(null=True),
                ),
            ],
        ),
        migrations.RunPython(register_providers, migrations.RunPython.noop, atomic=True),
    ]
