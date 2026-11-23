"""Allow sealed instructions for an independent announcement poll."""
import json
from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS = import_module("core.migrations.0230_chatter_source_resource_admission").FORWARD
PREVIOUS_GRAMMAR = import_module("core.migrations.0223_chatter_collection_operation").GRAMMAR
GRAMMAR = dict(PREVIOUS_GRAMMAR, provider_announcements={})
BEFORE = json.dumps(PREVIOUS_GRAMMAR, separators=(",", ":")).replace("'", "''")
AFTER = json.dumps(GRAMMAR, separators=(",", ":")).replace("'", "''")
FORWARD = PREVIOUS.replace(BEFORE, AFTER)
if FORWARD == PREVIOUS:
    raise RuntimeError("Previous sealed instruction grammar not found")


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0238_collection_request_provider")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(
            "ALTER TABLE collection_requests VALIDATE CONSTRAINT fk_collection_request_provider",
            migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "ALTER TABLE collection_requests VALIDATE CONSTRAINT ck_collection_request_returned_count",
            migrations.RunSQL.noop,
        ),
        migrations.RunSQL(FORWARD, PREVIOUS),
    ]
