"""Add an optional Product reference without rewriting frozen dossier claims."""

from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models, transaction


def add_column_and_fk(apps, schema_editor):
    with transaction.atomic(using=schema_editor.connection.alias):
        schema_editor.execute("SET LOCAL lock_timeout = '5s'")
        schema_editor.execute("ALTER TABLE event_dossier_claims ADD COLUMN reported_product_id bigint NULL")
        schema_editor.execute(
            "ALTER TABLE event_dossier_claims ADD CONSTRAINT fk_ed_claim_reported_product "
            "FOREIGN KEY (reported_product_id) REFERENCES products(id) DEFERRABLE INITIALLY DEFERRED NOT VALID"
        )


def drop_column_and_fk(apps, schema_editor):
    with transaction.atomic(using=schema_editor.connection.alias):
        schema_editor.execute("SET LOCAL lock_timeout = '5s'")
        schema_editor.execute("LOCK TABLE event_dossier_claims IN ACCESS EXCLUSIVE MODE NOWAIT")
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM event_dossier_claims WHERE reported_product_id IS NOT NULL)")
            if cursor.fetchone()[0]:
                raise RuntimeError("Preserve reported Product references before reversing this migration")
        schema_editor.execute("ALTER TABLE event_dossier_claims DROP CONSTRAINT fk_ed_claim_reported_product")
        schema_editor.execute("ALTER TABLE event_dossier_claims DROP COLUMN reported_product_id")


def refuse_loss(apps, schema_editor):
    claim = apps.get_model("core", "EventDossierClaim")
    if claim.objects.using(schema_editor.connection.alias).filter(reported_product__isnull=False).exists():
        raise RuntimeError("Preserve reported Product references before reversing this migration")


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0213_release_metric_followup_index")]
    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_column_and_fk, drop_column_and_fk, atomic=True)],
            state_operations=[migrations.AddField(
                model_name="eventdossierclaim", name="reported_product",
                field=models.ForeignKey(blank=True, db_index=False, null=True,
                    on_delete=django.db.models.deletion.PROTECT, related_name="dossier_claims", to="core.product"),
            )],
        ),
        migrations.RunSQL(
            "ALTER TABLE event_dossier_claims VALIDATE CONSTRAINT fk_ed_claim_reported_product",
            migrations.RunSQL.noop,
        ),
        migrations.RunPython(migrations.RunPython.noop, refuse_loss),
    ]
