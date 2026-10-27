"""Rename the reviewed detail without dropping data and switch dossier guards."""

import django.db.models.deletion
from django.db import migrations, models

# Django migration declarations are class-level values.
# ruff: noqa: RUF012


def rename_kind(apps, schema_editor):
    kinds = apps.get_model("core", "EventKind").objects.using(
        schema_editor.connection.alias
    )
    if kinds.filter(code="product_release").exists():
        raise RuntimeError("product_release kind already exists")
    # This one reviewed code rename preserves the row's primary key. The
    # catalogue guard normally freezes codes, so lift it only in this atomic
    # migration and restore it before commit.
    schema_editor.execute(
        "ALTER TABLE event_kinds DISABLE TRIGGER pw_rg4_catalogue_identity"
    )
    changed = kinds.filter(code="model_release").update(code="product_release")
    if changed == 0:
        # A flushed test database may have no dossier-kind catalogue rows.
        dossier = apps.get_model("core", "EventDossier")
        if dossier.objects.using(schema_editor.connection.alias).exists():
            raise RuntimeError("Dossiers exist without a model_release event kind")
        kinds.create(code="product_release")
    elif changed != 1:
        raise RuntimeError("Expected at most one model_release event kind")
    schema_editor.execute(
        "ALTER TABLE event_kinds ENABLE TRIGGER pw_rg4_catalogue_identity"
    )


def restore_kind(apps, schema_editor):
    kinds = apps.get_model("core", "EventKind").objects.using(
        schema_editor.connection.alias
    )
    schema_editor.execute(
        "ALTER TABLE event_kinds DISABLE TRIGGER pw_rg4_catalogue_identity"
    )
    if kinds.filter(code="product_release").update(code="model_release") != 1:
        raise RuntimeError("Expected one product_release event kind")
    schema_editor.execute(
        "ALTER TABLE event_kinds ENABLE TRIGGER pw_rg4_catalogue_identity"
    )


def replace_guard(apps, schema_editor):
    from core.migrations._rg4_retirement_v1 import dossier_functions_sql

    sql = dossier_functions_sql()
    sql = sql.replace("model_release_details", "product_release_details")
    sql = sql.replace("kind = 'model_release'", "kind = 'product_release'")
    schema_editor.execute(sql.replace("%", "%%"))


def restore_guard(apps, schema_editor):
    from core.migrations._rg4_retirement_v1 import dossier_functions_sql

    schema_editor.execute(dossier_functions_sql().replace("%", "%%"))


class Migration(migrations.Migration):
    dependencies = [("core", "0202_rg7_expand")]

    operations = [
        migrations.RemoveConstraint(
            model_name="modelreleasedetail", name="ck_ed_release_identity"
        ),
        migrations.RenameModel("ModelReleaseDetail", "ProductReleaseDetail"),
        migrations.AlterModelTable(
            name="productreleasedetail", table="product_release_details"
        ),
        migrations.AlterField(
            model_name="productreleasedetail",
            name="review",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                primary_key=True,
                related_name="product_release",
                serialize=False,
                to="core.eventdossierreview",
            ),
        ),
        migrations.AlterField(
            model_name="productreleasedetail",
            name="native_identifier",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="productreleasedetail",
            constraint=models.CheckConstraint(
                condition=~models.Q(observed_name="")
                & (
                    models.Q(native_identifier__isnull=True)
                    | ~models.Q(native_identifier="")
                ),
                name="ck_ed_release_identity",
            ),
        ),
        migrations.RunPython(rename_kind, restore_kind),
        migrations.RunPython(replace_guard, restore_guard),
    ]
