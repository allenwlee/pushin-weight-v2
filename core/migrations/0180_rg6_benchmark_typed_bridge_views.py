"""Serve new typed benchmark rows while retained old rows are copied."""

from typing import ClassVar

from django.db import migrations

from ._benchmark_serving_v2 import install


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0179_rg6_run_metadata_archive"),
    ]

    operations: ClassVar[list] = [
        migrations.RunPython(install, migrations.RunPython.noop),
    ]
