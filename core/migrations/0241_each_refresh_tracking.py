from importlib import import_module
from typing import ClassVar

from django.db import migrations

_original = import_module('core.migrations.0235_each_chart_facts').TRIGGER_SQL.split('CREATE TRIGGER each_facts_brand_identity', 1)[0]
_original = _original.replace('CREATE FUNCTION ', 'CREATE OR REPLACE FUNCTION ')
assert _original.count('dirty_since=least(dirty_since,changed_since)') == 1
assert _original.count("dirty_since='0001-01-01 00:00:00+00'::timestamptz") == 1
_tracked = _original.replace(
    'dirty_since=least(dirty_since,changed_since)',
    'dirty_since=least(dirty_since,changed_since), '
    'refresh_dirty_since=CASE WHEN refresh_generation IS NOT NULL '
    'THEN least(refresh_dirty_since,changed_since) ELSE refresh_dirty_since END',
).replace(
    "dirty_since='0001-01-01 00:00:00+00'::timestamptz",
    "dirty_since='0001-01-01 00:00:00+00'::timestamptz, "
    "refresh_dirty_since=CASE WHEN refresh_generation IS NOT NULL "
    "THEN '0001-01-01 00:00:00+00'::timestamptz ELSE refresh_dirty_since END",
)

_CAPABILITY = """
CREATE FUNCTION each_facts_online_tracking_v1() RETURNS boolean
LANGUAGE sql IMMUTABLE AS 'SELECT TRUE';
"""
_REVERSE_CAPABILITY = """
SET LOCAL lock_timeout = '2s';
DO $guard$
BEGIN
    IF NOT pg_try_advisory_xact_lock(726514095) THEN
        RAISE EXCEPTION 'each facts refresh is active' USING ERRCODE = '55P03';
    END IF;
END
$guard$;
DROP FUNCTION each_facts_online_tracking_v1();
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [('core', '0240_materialization_refresh_tracking')]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s'", reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(_tracked, reverse_sql=_original),
        migrations.RunSQL(_CAPABILITY, reverse_sql=_REVERSE_CAPABILITY),
    ]
