"""Permit the bounded, local-only lineage wakeup instruction."""

import json
from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS_GRAMMAR = import_module("core.migrations.0223_chatter_collection_operation").GRAMMAR
PREVIOUS_SQL = import_module("core.migrations.0230_chatter_source_resource_admission").FORWARD
GRAMMAR = dict(PREVIOUS_GRAMMAR, lineage_wakeup={})
BEFORE = json.dumps(PREVIOUS_GRAMMAR, separators=(",", ":")).replace("'", "''")
AFTER = json.dumps(GRAMMAR, separators=(",", ":")).replace("'", "''")
FORWARD = PREVIOUS_SQL.replace(BEFORE, AFTER)
if FORWARD == PREVIOUS_SQL:
    raise RuntimeError("Previous sealed instruction grammar not found")


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0236_pulse_lineage_name_index")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(FORWARD, PREVIOUS_SQL),
    ]
