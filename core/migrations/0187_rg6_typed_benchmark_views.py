"""Install reviewed benchmark views after the RG6 typed-history copy."""

from typing import ClassVar

from django.db import migrations

from ._benchmark_serving_v2 import install as install_bridge
from ._benchmark_serving_v3 import install as install_typed


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0186_source_datasets"),
    ]

    operations: ClassVar[list] = [
        migrations.RunPython(install_typed, install_bridge),
    ]
