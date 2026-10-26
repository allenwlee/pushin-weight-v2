import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0193_rg6_cross_format_statistics_identity")]  # noqa: RUF012

    operations = [  # noqa: RUF012
        migrations.AddField(
            model_name="collectionscoperun",
            name="result_run",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="archive_import_scopes",
                to="core.collectionrun",
            ),
        ),
    ]
