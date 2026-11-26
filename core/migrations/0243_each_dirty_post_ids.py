"""Bounded per-post invalidation for exact reuse of published Each facts."""
from importlib import import_module
from typing import ClassVar

from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models

_previous = import_module('core.migrations.0241_each_refresh_tracking')._tracked
assert _previous.count('    candidate timestamptz;') == 1
assert _previous.count("    IF changed_since < date_trunc") == 1
assert _previous.count('dirty_since=least(dirty_since,changed_since), ') == 1
assert _previous.count("dirty_since='0001-01-01 00:00:00+00'::timestamptz, ") == 1

_functions = _previous.replace(
    '    candidate timestamptz;',
    '    candidate timestamptz;\n    old_key text;\n    new_key text;',
).replace(
    "    IF changed_since < date_trunc",
    """    IF TG_OP <> 'TRUNCATE' THEN
        IF TG_TABLE_NAME='posts' THEN
            old_key := OLD.tweet_id;
            new_key := NEW.tweet_id;
        ELSE
            IF TG_OP <> 'INSERT' THEN old_key := OLD.post_id; END IF;
            IF TG_OP <> 'DELETE' THEN new_key := NEW.post_id; END IF;
        END IF;
    END IF;
    IF changed_since < date_trunc""",
).replace(
    'dirty_since=least(dirty_since,changed_since), ',
    """dirty_since=least(dirty_since,changed_since),
            dirty_post_ids=CASE WHEN TG_OP='TRUNCATE' THEN NULL
                WHEN old_key COLLATE "C" IS NOT DISTINCT FROM new_key COLLATE "C"
                THEN each_dirty_append(dirty_post_ids, old_key)
                ELSE each_dirty_append(each_dirty_append(dirty_post_ids, old_key), new_key) END,
            refresh_dirty_post_ids=CASE WHEN refresh_generation IS NULL THEN refresh_dirty_post_ids
                WHEN TG_OP='TRUNCATE' THEN NULL
                WHEN old_key COLLATE "C" IS NOT DISTINCT FROM new_key COLLATE "C"
                THEN each_dirty_append(refresh_dirty_post_ids, old_key)
                ELSE each_dirty_append(each_dirty_append(refresh_dirty_post_ids, old_key), new_key) END, """,
).replace(
    "dirty_since='0001-01-01 00:00:00+00'::timestamptz, ",
    "dirty_since='0001-01-01 00:00:00+00'::timestamptz, "
    "dirty_post_ids=NULL, refresh_dirty_post_ids=CASE WHEN refresh_generation IS NOT NULL "
    "THEN NULL ELSE refresh_dirty_post_ids END, ",
)

_HELPER = '''
CREATE FUNCTION each_dirty_append(ids text[], item text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT CASE WHEN ids IS NULL OR item IS NULL THEN ids
        WHEN octet_length(item) > 256 THEN NULL
        WHEN item COLLATE "C" = ANY(ids COLLATE "C") THEN ids
        WHEN cardinality(ids) >= 512 THEN NULL
        ELSE array_append(ids,item) END
$fn$;
CREATE FUNCTION each_facts_dirty_post_ids_v1() RETURNS boolean
LANGUAGE sql IMMUTABLE AS 'SELECT TRUE';
CREATE FUNCTION each_dirty_ids_valid(ids text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT cardinality(ids) <= 512 AND coalesce(array_ndims(ids), 1) = 1
        AND NOT EXISTS (SELECT 1 FROM unnest(ids) item
                        WHERE item IS NULL OR octet_length(item) > 256)
$fn$;
ALTER TABLE materialization_state ADD CONSTRAINT ck_each_dirty_post_ids_size
    CHECK (dirty_post_ids IS NULL OR each_dirty_ids_valid(dirty_post_ids));
ALTER TABLE materialization_state ADD CONSTRAINT ck_each_refresh_dirty_post_ids_size
    CHECK (refresh_dirty_post_ids IS NULL OR each_dirty_ids_valid(refresh_dirty_post_ids));
'''
_REVERSE_GUARD = '''
SET LOCAL lock_timeout = '2s';
DO $guard$
BEGIN
    IF NOT pg_try_advisory_xact_lock(726514095) THEN
        RAISE EXCEPTION 'each facts refresh is active' USING ERRCODE = '55P03';
    END IF;
END
$guard$;
'''
_REVERSE_HELPER = '''
ALTER TABLE materialization_state DROP CONSTRAINT ck_each_dirty_post_ids_size;
ALTER TABLE materialization_state DROP CONSTRAINT ck_each_refresh_dirty_post_ids_size;
DROP FUNCTION each_facts_dirty_post_ids_v1();
DROP FUNCTION each_dirty_ids_valid(text[]);
DROP FUNCTION each_dirty_append(text[],text);
'''


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [('core', '0242_general_feed_recent_index')]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s'", reverse_sql=migrations.RunSQL.noop),
        migrations.AddField('materializationstate', 'dirty_post_ids', ArrayField(models.TextField(db_collation='C'), null=True)),
        migrations.AddField('materializationstate', 'refresh_dirty_post_ids', ArrayField(models.TextField(db_collation='C'), null=True)),
        migrations.RunSQL(_HELPER, reverse_sql=_REVERSE_HELPER),
        migrations.RunSQL(_functions, reverse_sql=_previous),
        migrations.RunSQL(migrations.RunSQL.noop, reverse_sql=_REVERSE_GUARD),
    ]
