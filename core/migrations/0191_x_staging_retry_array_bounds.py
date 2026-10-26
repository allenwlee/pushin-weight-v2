"""Keep the bounded retry array's SQL indexes aligned with its finite checks.

Nullable and empty arrays remain valid. Nonempty arrays must start at index 1,
including arrays written directly through SQL. Resume interrupted validation by
rerunning migrate; the signed CHECK operation verifies an existing definition.
"""

from importlib import import_module
from typing import ClassVar

from django.contrib.postgres.operations import ValidateConstraint
from django.db import migrations, models
from django.db.models.lookups import Exact

AddCheckIfMissing = import_module("core.migrations.0190_x_staging_receipts").AddCheckIfMissing


class Migration(migrations.Migration):
    atomic = False

    dependencies: ClassVar = [("core", "0190_x_staging_receipts")]

    operations: ClassVar = [
        migrations.RunSQL("SET lock_timeout = '5s'; SET statement_timeout = '5min'", migrations.RunSQL.noop),
        AddCheckIfMissing(
            model_name="collectionrun",
            constraint=models.CheckConstraint(
                condition=models.Q(staging_retry_failures__isnull=True)
                | models.Q(staging_retry_failures__len=0)
                | models.Q(Exact(models.Func(
                    models.F("staging_retry_failures"), models.Value(1),
                    function="array_lower", output_field=models.IntegerField(),
                ), models.Value(1))),
                name="ck_run_staging_retry_array_bounds",
            ),
        ),
        ValidateConstraint(model_name="collectionrun", name="ck_run_staging_retry_array_bounds"),
        migrations.RunSQL("RESET lock_timeout; RESET statement_timeout", migrations.RunSQL.noop),
    ]
