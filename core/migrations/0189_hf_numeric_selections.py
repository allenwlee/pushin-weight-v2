from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0188_x_page_receipts")]

    operations: ClassVar[list] = [
        migrations.AddField(
            model_name="collectionobservation",
            name="numeric_fields_explicit",
            field=models.BooleanField(null=True),
        ),
        migrations.CreateModel(
            name="CollectionObservationMetricSelection",
            fields=[
                ("pk", models.CompositePrimaryKey("observation", "source_metric", blank=True,
                                                  editable=False, primary_key=True, serialize=False)),
                ("observation", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="numeric_selections", to="core.collectionobservation",
                )),
                ("source_metric", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, to="core.sourcemetric",
                )),
            ],
            options={"db_table": "collection_observation_metric_selections"},
        ),
    ]
