"""Bound scheduler selection to unfinished ready lineage wakeups."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0229_lineage_wakeup_instruction_guard")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionjob",
            index=models.Index(
                fields=["updated_at", "id"], name="idx_lineage_wakeup_ready",
                condition=models.Q(operation="lineage_wakeup", state="ready", last_success__isnull=True),
            ),
        ),
    ]
