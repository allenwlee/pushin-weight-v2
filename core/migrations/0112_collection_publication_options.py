"""Allow bounded publication-window settings in sealed instructions."""

import json
from copy import deepcopy
from importlib import import_module
from typing import ClassVar

from django.db import migrations

ORIGINAL = import_module("core.migrations.0101_collection_instruction_guards")
PREVIOUS = import_module("core.migrations.0109_collection_match_targets").FORWARD
OPTIONS = deepcopy(ORIGINAL.OPTION_TYPES)
OPTIONS["model_history"].update(
    {
        "publication_window_policy": "string",
        "publication_recheck_days": "number",
        "publication_window_days": "number",
    }
)
FORWARD = PREVIOUS.replace(
    ORIGINAL.grammar(),
    json.dumps(OPTIONS, separators=(",", ":")).replace("'", "''"),
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0111_collection_reply_coordinates")]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '5s'", migrations.RunSQL.noop),
        migrations.RunSQL(FORWARD, PREVIOUS),
    ]
