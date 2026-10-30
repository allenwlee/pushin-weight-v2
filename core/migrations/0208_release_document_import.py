"""Allow bounded document imports and finish the requested homepage-field revert."""

import json
from importlib import import_module
from typing import ClassVar

from django.db import migrations

PREVIOUS = import_module("core.migrations.0112_collection_publication_options")
GRAMMAR = dict(PREVIOUS.OPTIONS, release_document_import={})
FORWARD = PREVIOUS.FORWARD.replace(
    json.dumps(PREVIOUS.OPTIONS, separators=(",", ":")).replace("'", "''"),
    json.dumps(GRAMMAR, separators=(",", ":")).replace("'", "''"),
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0207_company_url")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(FORWARD, PREVIOUS.FORWARD),
        migrations.RunSQL(
            """DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM companies WHERE url IS NOT NULL AND url <> '') THEN
                RAISE EXCEPTION 'Company.url contains values; preserve them before removal';
            END IF;
            END $$;""",
            migrations.RunSQL.noop,
        ),
        migrations.RemoveField(model_name="company", name="url"),
    ]
