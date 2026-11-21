"""Join production and Chatter histories with the combined instruction guard."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

COMBINED = import_module("core.migrations.0230_chatter_source_resource_admission")


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0230_chatter_source_resource_admission"),
        ("core", "0235_each_chart_facts"),
    ]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(COMBINED.FORWARD, migrations.RunSQL.noop),
    ]
