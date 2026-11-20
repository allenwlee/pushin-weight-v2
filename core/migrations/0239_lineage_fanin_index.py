"""Bound each lineage relationship-kind lookup in UUID order."""

from typing import ClassVar

from django.contrib.postgres.operations import (
    AddIndexConcurrently,
    RemoveIndexConcurrently,
)
from django.db import migrations, models
from django.db.models.functions import MD5, Upper


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0238_lineage_wakeup_ready_index")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="eventdossierclaim",
            index=models.Index(
                MD5(Upper("assertion_text")), models.F("id"),
                condition=models.Q(scope_key__startswith="pulse-lineage-v1:", source_archive__isnull=False),
                name="idx_ed_lineage_hash_id",
            ),
        ),
        RemoveIndexConcurrently(model_name="eventdossierclaim", name="idx_ed_lineage_name_hash"),
    ]
