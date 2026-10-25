"""Expose scalar chart provenance without granting source-document access."""

from django.db import migrations

from ._benchmark_serving_v1 import install

# ruff: noqa: RUF012


class Migration(migrations.Migration):
    dependencies = [("core", "0166_rg5_reference_source_guards")]
    operations = [migrations.RunPython(install)]
