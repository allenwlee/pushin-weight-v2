from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0194_rg6_archive_import_result_run")]  # noqa: RUF012

    operations = [  # noqa: RUF012
        migrations.AddConstraint(
            model_name="collectionscoperun",
            constraint=models.CheckConstraint(
                condition=models.Q(result_run__isnull=True) | models.Q(scope_kind="archive_import"),
                name="ck_scope_result_run_kind",
            ),
        ),
    ]
