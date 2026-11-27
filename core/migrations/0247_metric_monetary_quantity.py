"""Allow monetary metric definitions by widening ck_metric_quantity in place.

Only the CHECK constraint changes: no column, table or row is added or rewritten.
"""

from typing import ClassVar

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar = [
        ("core", "0246_home_classification_masks"),
    ]

    operations: ClassVar = [
        migrations.RemoveConstraint(
            model_name="sourcemetric",
            name="ck_metric_quantity",
        ),
        migrations.AddConstraint(
            model_name="sourcemetric",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "quantity_form__in",
                        ["count", "score", "rank", "variance", "ratio", "monetary"],
                    )
                ),
                name="ck_metric_quantity",
            ),
        ),
    ]
