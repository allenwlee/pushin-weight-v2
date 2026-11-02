"""Build the source-claim Product lookup index without blocking writers."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0214_dossier_claim_reported_product")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="eventdossierclaim",
            index=models.Index(fields=["reported_product"], condition=models.Q(reported_product__isnull=False),
                               name="idx_ed_claim_reported_product"),
        ),
    ]
