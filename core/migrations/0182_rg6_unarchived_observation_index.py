"""Keep the bounded observation archive copy on an ordered partial index."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies: ClassVar[list] = [
        ("core", "0181_rg6_row_semantic_digest"),
    ]

    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionobservation",
            index=models.Index(
                fields=["id"],
                condition=models.Q(legacy_archive__isnull=True),
                name="idx_rg6_obs_unarchived",
            ),
        ),
    ]
