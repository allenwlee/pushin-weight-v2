"""Find saved repository release observations for bounded identity reconciliation."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0217_release_native_id_index")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionobservation",
            index=models.Index(
                fields=["source_identifier", "id"], name="idx_rel_repo_observation",
                condition=models.Q(observation_kind="releases"),
            ),
        ),
    ]
