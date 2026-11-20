"""Index the due local recovery work without interrupting active writers."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0239_lineage_fanin_index")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionscoperun",
            index=models.Index(
                fields=["retry_at", "id"], name="idx_pending_pub_admission",
                condition=models.Q(scope_kind="pending_publication_admission", outcome="pending"),
            ),
        ),
    ]
