"""Add a rebuildable Post-grain sentiment projection and online invalidation."""
from importlib import import_module
from typing import ClassVar

from django.db import migrations

from core.migrations._home_sentiment_masks_v1 import BUILD_SQL, SOURCE_SQL

_previous = import_module('core.migrations.0243_each_dirty_post_ids')._functions
_old_key = "WHERE dataset_key='each.brand_post_facts.v1'"
if _previous.count(_old_key) != 2:
    raise RuntimeError('Expected both existing Each dataset predicates')


def _replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(f'Expected exactly one migration SQL anchor: {old!r}')
    return source.replace(old, new)


_invalidate, _identity = _previous.split('CREATE OR REPLACE FUNCTION each_facts_brand_identity()', 1)
_invalidate = _replace_once(_invalidate, '    candidate timestamptz;', '    candidate timestamptz;\n    summary_relevant boolean;')
_invalidate = _replace_once(
    _invalidate,
    "    IF changed_since < date_trunc",
    '''    summary_relevant := TG_TABLE_NAME IN ('posts','posts_brands',
        'posts_brands_classification_states','posts_brands_signals','posts_untracked_brand_promotions');
    IF TG_OP='UPDATE' AND TG_TABLE_NAME='posts' THEN
        summary_relevant := OLD.tweet_id COLLATE "C" IS DISTINCT FROM NEW.tweet_id COLLATE "C"
            OR OLD.created_at IS DISTINCT FROM NEW.created_at;
    ELSIF TG_OP='UPDATE' AND TG_TABLE_NAME='posts_brands_signals' THEN
        summary_relevant := OLD.post_id COLLATE "C" IS DISTINCT FROM NEW.post_id COLLATE "C"
            OR OLD.brand_id COLLATE "C" IS DISTINCT FROM NEW.brand_id COLLATE "C"
            OR OLD.sentiment COLLATE "C" IS DISTINCT FROM NEW.sentiment COLLATE "C";
    ELSIF TG_OP='UPDATE' AND TG_TABLE_NAME='posts_untracked_brand_promotions' THEN
        summary_relevant := OLD.post_id COLLATE "C" IS DISTINCT FROM NEW.post_id COLLATE "C";
    END IF;
    IF changed_since < date_trunc''',
)
_invalidate = _replace_once(
    _invalidate,
    _old_key,
    "WHERE dataset_key='each.brand_post_facts.v1' "
    "OR (dataset_key='home.post_sentiment_facts.v1' AND summary_relevant)",
)
_both = _invalidate + 'CREATE OR REPLACE FUNCTION each_facts_brand_identity()' + _replace_once(
    _identity,
    _old_key, "WHERE dataset_key IN ('each.brand_post_facts.v1','home.post_sentiment_facts.v1')",
)
_flag_function = _previous.split('CREATE OR REPLACE FUNCTION each_facts_brand_identity()', 1)[0]
_flag_function = _replace_once(_flag_function, 'each_facts_invalidate()', 'home_sentiment_flags_invalidate()')
_flag_function = _replace_once(_flag_function, _old_key, "WHERE dataset_key='home.post_sentiment_facts.v1'")

_FORWARD = _both + _flag_function + '''
CREATE TRIGGER home_sentiment_flags_insert AFTER INSERT ON posts_unsanctioned_flags
FOR EACH ROW EXECUTE FUNCTION home_sentiment_flags_invalidate();
CREATE TRIGGER home_sentiment_flags_delete AFTER DELETE ON posts_unsanctioned_flags
FOR EACH ROW EXECUTE FUNCTION home_sentiment_flags_invalidate();
CREATE TRIGGER home_sentiment_flags_update AFTER UPDATE ON posts_unsanctioned_flags
FOR EACH ROW WHEN (OLD.post_id COLLATE "C" IS DISTINCT FROM NEW.post_id COLLATE "C")
EXECUTE FUNCTION home_sentiment_flags_invalidate();
CREATE TRIGGER home_sentiment_flags_truncate AFTER TRUNCATE ON posts_unsanctioned_flags
FOR EACH STATEMENT EXECUTE FUNCTION home_sentiment_flags_invalidate();
CREATE FUNCTION home_sentiment_masks_v1() RETURNS boolean
LANGUAGE sql IMMUTABLE AS 'SELECT TRUE';
'''
_REVERSE = '''
DROP FUNCTION home_sentiment_masks_v1();
DROP TRIGGER home_sentiment_flags_insert ON posts_unsanctioned_flags;
DROP TRIGGER home_sentiment_flags_delete ON posts_unsanctioned_flags;
DROP TRIGGER home_sentiment_flags_update ON posts_unsanctioned_flags;
DROP TRIGGER home_sentiment_flags_truncate ON posts_unsanctioned_flags;
DROP FUNCTION home_sentiment_flags_invalidate();
''' + _previous
_GUARD = '''
SET LOCAL lock_timeout = '2s';
DO $guard$
BEGIN
    IF NOT pg_try_advisory_xact_lock(726514095)
       OR NOT pg_try_advisory_xact_lock(726514097) THEN
        RAISE EXCEPTION 'materialization refresh is active' USING ERRCODE = '55P03';
    END IF;
END
$guard$;
'''


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [('core', '0243_each_dirty_post_ids')]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout = '2s'", reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(
            "INSERT INTO materialization_state(dataset_key,source_generation) VALUES ('home.post_sentiment_facts.v1',0)",
            reverse_sql="DELETE FROM materialization_state WHERE dataset_key='home.post_sentiment_facts.v1'",
        ),
        migrations.RunSQL(
            SOURCE_SQL + ';\n' + BUILD_SQL
            + 'CREATE UNIQUE INDEX home_post_sentiment_facts_key ON home_post_sentiment_facts(post_id);',
            reverse_sql='DROP MATERIALIZED VIEW home_post_sentiment_facts; DROP VIEW home_post_sentiment_facts_source;',
        ),
        migrations.RunSQL(_FORWARD, reverse_sql=_REVERSE),
        migrations.RunSQL(migrations.RunSQL.noop, reverse_sql=_GUARD),
    ]
