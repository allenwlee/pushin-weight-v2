"""Find earlier observations of a public native release without a table scan."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0216_release_source_detection_index")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionresourcesnapshot",
            index=models.Index(fields=["native_stable_id"], name="idx_release_native_id",
                               condition=models.Q(resource_kind="releases")),
        ),
    ]
