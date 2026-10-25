"""Retire RG5 storage only after the separately deployed cutover has drained.

Recovery requires the tested replacement-only deletion revision or a forward
repair. Migration reversal deliberately does not recreate obsolete columns.
"""

from django.db import migrations

from ._rg5_retirement_v1 import prepare_retirement, remove_storage

# ruff: noqa: RUF012


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0167_benchmark_serving_provenance")]
    operations = [
        migrations.RunPython(prepare_retirement, atomic=False),
        migrations.RunPython(remove_storage, atomic=True),
    ]
