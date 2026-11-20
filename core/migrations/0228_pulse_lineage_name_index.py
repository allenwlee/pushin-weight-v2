"""Index existing and future lineage leads without blocking active writers."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models
from django.db.models.functions import MD5, Upper


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0227_pulse_product_category_guard")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="eventdossierclaim",
            index=models.Index(
                MD5(Upper("assertion_text")),
                condition=models.Q(scope_key__startswith="pulse-lineage-v1:"),
                name="idx_ed_lineage_name_hash",
            ),
        ),
    ]
