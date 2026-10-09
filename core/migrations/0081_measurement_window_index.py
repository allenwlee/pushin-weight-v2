from typing import ClassVar

from django.contrib.postgres.indexes import GistIndex
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0080_measurement_window")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="metricvalue",
            index=GistIndex(
                fields=["window_range"],
                condition=models.Q(window_range__isnull=False),
                name="idx_value_window_range",
            ),
        ),
    ]
