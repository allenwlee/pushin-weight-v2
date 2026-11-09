"""Accelerate exact-identifier lookup for unlinked historical model data."""

from typing import ClassVar

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0225_official_company_credential_provenance")]
    operations: ClassVar[list] = [
        AddIndexConcurrently(
            model_name="collectionobservation",
            index=models.Index(
                fields=["source_identifier", "source_subject_kind", "id"],
                name="idx_obs_native_chart",
                condition=models.Q(
                    mapping__isnull=True,
                    source_subject_kind__in=["model", "repository"],
                ),
            ),
        ),
    ]
