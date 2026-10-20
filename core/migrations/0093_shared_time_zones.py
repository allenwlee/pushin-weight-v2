from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0092_measurement_window_index")]
    operations: ClassVar[list] = [
        migrations.CreateModel(
            name="TimeZone",
            fields=[
                (
                    "code",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
            ],
            options={
                "db_table": "time_zones",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("code__regex", "^[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*$")
                        ),
                        name="ck_time_zone_code_grammar",
                    )
                ],
            },
        ),
    ]
