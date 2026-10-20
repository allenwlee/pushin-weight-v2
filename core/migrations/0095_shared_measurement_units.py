from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0094_shared_languages_locales")]
    operations: ClassVar[list] = [
        migrations.CreateModel(
            name="MeasurementUnit",
            fields=[
                (
                    "code",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
            ],
            options={
                "db_table": "measurement_units",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("code__regex", "^[a-z][a-z0-9_]*$")),
                        name="ck_measurement_unit_code_grammar",
                    )
                ],
            },
        ),
    ]
