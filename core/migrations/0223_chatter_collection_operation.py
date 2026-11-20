"""Register Chatter in the existing sealed collection instruction grammar."""

import json
from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS = import_module("core.migrations.0210_release_acquisition_operation")
GRAMMAR = dict(PREVIOUS.GRAMMAR, chatter_search={
    "credential_purpose": "string", "workflow_version": "string", "pricing_sha256": "string",
})
BEFORE = json.dumps(PREVIOUS.GRAMMAR, separators=(",", ":")).replace("'", "''")
AFTER = json.dumps(GRAMMAR, separators=(",", ":")).replace("'", "''")
FORWARD = PREVIOUS.FORWARD.replace(BEFORE, AFTER)
if FORWARD == PREVIOUS.FORWARD:
    raise RuntimeError("Previous sealed instruction grammar not found")


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0222_merge_chatter_and_affiliation_permissions")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(FORWARD, PREVIOUS.FORWARD),
    ]
