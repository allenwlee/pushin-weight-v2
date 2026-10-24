"""Retire RG4 compatibility storage after the observed 5cf3104c production drain.

Recovery requires the tested replacement-only deletion revision or a forward fix.
The legacy columns are deliberately not reconstructed by migration reversal.
"""

from django.db import migrations

from ._rg4_retirement_v1 import prepare_retirement, remove_storage

# ruff: noqa: RUF012


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0159_rg4_skip_unrelated_post_transition_rows")]
    operations = [
        migrations.RunPython(prepare_retirement, atomic=False),
        migrations.RunPython(remove_storage, atomic=True),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.DeleteModel(name="PersonNameType"),
            migrations.DeleteModel(name="ReleaseDisclosureState"),
        ]),
    ]
