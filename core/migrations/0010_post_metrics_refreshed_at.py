# Generated for plan 2026-08-10-002 — one-shot metrics refresh

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_accounts_handle_unique_ci"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="metrics_refreshed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
