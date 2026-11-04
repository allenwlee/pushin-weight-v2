"""Preserve both independently developed additive migration branches."""

from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0220_chatter_consideration_ownership"),
        ("core", "0221_affiliation_trigger_column_permissions"),
    ]
    operations: ClassVar[list] = []
