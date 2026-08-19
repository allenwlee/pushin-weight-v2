from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_add_posts_created_covering_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="commentary_en",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="post",
            name="commentary_zh_cn",
            field=models.TextField(blank=True, null=True),
        ),
    ]
