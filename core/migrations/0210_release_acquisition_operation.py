"""Permit the typed, manually dispatched release-acquisition operation."""

import json
from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS = import_module("core.migrations.0208_release_document_import")
GRAMMAR = dict(PREVIOUS.GRAMMAR, release_acquisition={})
BEFORE = json.dumps(PREVIOUS.GRAMMAR, separators=(",", ":")).replace("'", "''")
AFTER = json.dumps(GRAMMAR, separators=(",", ":")).replace("'", "''")
FORWARD = PREVIOUS.FORWARD.replace(BEFORE, AFTER)
if FORWARD == PREVIOUS.FORWARD:
    raise RuntimeError("Previous sealed instruction grammar not found")


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0209_dossier_claim_collection_job")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(FORWARD, PREVIOUS.FORWARD),
    ]
