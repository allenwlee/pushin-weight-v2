"""Reconcile write-efficient bridges on already advanced databases."""

from django.db import migrations

from ._rg4_geography_write_performance_v1 import install

# ruff: noqa: RUF012


class Migration(migrations.Migration):
    dependencies = [("core", "0157_rg4_geolocation_reference_cutover")]
    operations = [migrations.RunPython(install)]
