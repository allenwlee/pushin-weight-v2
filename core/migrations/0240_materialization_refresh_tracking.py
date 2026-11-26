from importlib import import_module
from typing import ClassVar

from django.db import migrations, models

_HOME_FUNCTIONS = import_module(
    "core.migrations.0094_shared_materialization_state"
)._NEW_FUNCTIONS
_POST_UPDATE_FUNCTION = import_module(
    "core.migrations._rg4_home_count_write_v1"
).SQL.split("DROP TRIGGER home_counts_update ON posts;", 1)[0]
_ORIGINAL_FUNCTIONS = _HOME_FUNCTIONS + _POST_UPDATE_FUNCTION
_GLOBAL_DIRTY = "dirty_since = '0001-01-01 00:00:00+00'::timestamptz"
_DATED_DIRTY = "dirty_since = least(dirty_since, changed_since)"
assert _ORIGINAL_FUNCTIONS.count(_GLOBAL_DIRTY) == 2
assert _ORIGINAL_FUNCTIONS.count(_DATED_DIRTY) == 2
_TRACKING_FUNCTIONS = _ORIGINAL_FUNCTIONS.replace(
    _GLOBAL_DIRTY,
    _GLOBAL_DIRTY + ", refresh_dirty_since = CASE WHEN refresh_generation IS NOT NULL "
    "THEN '0001-01-01 00:00:00+00'::timestamptz ELSE refresh_dirty_since END",
).replace(
    _DATED_DIRTY,
    _DATED_DIRTY + ", refresh_dirty_since = CASE WHEN refresh_generation IS NOT NULL "
    "THEN least(refresh_dirty_since, changed_since) ELSE refresh_dirty_since END",
)


class Migration(migrations.Migration):

    dependencies: ClassVar[list] = [
        ('core', '0239_provider_announcement_instruction'),
    ]

    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s'", reverse_sql=migrations.RunSQL.noop),
        migrations.AddField(
            model_name='materializationstate',
            name='refresh_dirty_since',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='materializationstate',
            name='refresh_generation',
            field=models.PositiveBigIntegerField(null=True),
        ),
        migrations.RunSQL(_TRACKING_FUNCTIONS, reverse_sql=_ORIGINAL_FUNCTIONS),
    ]
