"""Switch ORM readers and writers while retaining old columns for rolling deploys."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0129_rg2_locale_owners_expand"),
    ]

    operations = [
        migrations.AlterField(
            model_name="personname",
            name="locale",
            field=models.ForeignKey(
                db_column="locale_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="person_names",
                to="core.locale",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="account", name="bio_en"),
                migrations.RemoveField(model_name="account", name="bio_zh_cn"),
                migrations.RemoveField(model_name="company", name="display_name"),
                migrations.RemoveField(model_name="company", name="display_name_en"),
                migrations.RemoveField(model_name="company", name="display_name_zh_cn"),
                migrations.RemoveField(model_name="originalcontent", name="brand_name_en_snapshot"),
                migrations.RemoveField(model_name="originalcontent", name="brand_name_zh_cn_snapshot"),
                migrations.RemoveField(model_name="person", name="display_name"),
                migrations.RemoveField(model_name="person", name="display_name_en"),
                migrations.RemoveField(model_name="person", name="display_name_ja"),
                migrations.RemoveField(model_name="person", name="display_name_zh_cn"),
                migrations.RemoveField(model_name="personname", name="language"),
                migrations.RemoveField(model_name="trendnarrativesubject", name="name_en_snapshot"),
                migrations.RemoveField(model_name="trendnarrativesubject", name="name_zh_cn_snapshot"),
            ],
            database_operations=[],
        ),
    ]
