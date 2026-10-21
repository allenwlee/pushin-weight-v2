"""Join independently deployed histories without changing either schema."""

from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0119_geography_label_locale_references"),
        ("core", "0094_shared_materialization_state"),
    ]
    operations: ClassVar[list] = []
