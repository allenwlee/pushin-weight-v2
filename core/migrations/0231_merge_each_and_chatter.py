"""Join additive Each facts with the preserved staging Chatter history."""
from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0228_each_chart_facts"),
        ("core", "0230_chatter_source_resource_admission"),
    ]
    operations: ClassVar[list] = []
