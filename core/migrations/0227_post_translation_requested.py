from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0226_chart_native_lookup_index")]

    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.AddField(
            model_name="postenrichmentstate",
            name="translation_requested",
            field=models.BooleanField(default=False, db_default=False),
        ),
    ]
