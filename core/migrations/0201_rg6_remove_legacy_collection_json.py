"""Remove the thirteen RG6 legacy JSON columns after verified cutover.

The preflight requires the explicit 0201 connection setting on populated
databases. Source/archive parity and old-image drain are release prerequisites;
the setting is applied to the owner migration process only after those checks.
Reversal deliberately does not recreate obsolete source columns.
"""

from django.db import migrations

from ._rg6_retirement_v1 import prepare_retirement, remove_storage

# ruff: noqa: RUF012


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0200_merge_rg6_enrichment_budget_contract")]
    operations = [
        migrations.RunPython(prepare_retirement, atomic=False),
        migrations.RunPython(remove_storage, atomic=True),
    ]
