"""Find due mapping-reconciliation work without scanning collection scopes."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0218_release_repository_observation_index")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionscoperun",
            index=models.Index(
                fields=["retry_at", "id"], name="idx_rel_mapping_recon_due",
                condition=models.Q(scope_kind="release_mapping_reconcile", outcome="pending"),
            ),
        ),
    ]
