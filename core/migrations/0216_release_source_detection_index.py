"""Index durable source-observation detection work without blocking writers."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0215_dossier_claim_product_index")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionscoperun",
            index=models.Index(fields=["retry_at", "id"], name="idx_rel_source_detect_due",
                condition=models.Q(scope_kind="release_detection", outcome="pending")),
        ),
    ]
