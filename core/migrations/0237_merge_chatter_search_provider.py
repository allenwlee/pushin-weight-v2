"""Merge the independent Chatter and search-provider migration histories."""

from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0236_merge_chatter_production"),
        ("core", "0236_search_provider_circuit"),
    ]
    operations: ClassVar[list] = []
