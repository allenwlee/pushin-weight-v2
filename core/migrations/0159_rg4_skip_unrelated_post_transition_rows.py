"""Retain homepage invalidation without copying unrelated Post payloads."""

from django.db import migrations

from ._rg4_home_count_write_v1 import install

# ruff: noqa: RUF012


class Migration(migrations.Migration):
    dependencies = [("core", "0158_rg4_scope_geography_write_triggers")]
    operations = [migrations.RunPython(install)]
