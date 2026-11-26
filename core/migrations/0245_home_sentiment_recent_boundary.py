"""Build a recent sentiment summary alongside the existing published prefix."""
from importlib import import_module
from typing import ClassVar

from django.db import migrations

from core.migrations._home_sentiment_masks_v1 import BUILD_SQL, CUTOFF

_previous = import_module('core.migrations.0244_home_sentiment_masks')
_OLD_LIMIT = "date_trunc('day', clock_timestamp(), 'UTC') - interval '1 day'"
_NEW_LIMIT = "date_bin('2 hours', clock_timestamp(), '2000-01-01 00:00:00+00'::timestamptz) - interval '15 minutes'"
_NEW_CUTOFF = "date_bin('2 hours', transaction_timestamp(), '2000-01-01 00:00:00+00'::timestamptz) - interval '15 minutes'"
_V1 = 'home.post_sentiment_facts.v1'
_V2 = 'home.post_sentiment_facts.v2'
_EACH = 'each.brand_post_facts.v1'
# Every historical writer locks all three publication rows in the same order,
# even when it changes only one dataset. A transaction may mix recent and old
# source writes, so locking only the rows changed by each statement can deadlock.
_LOCK_ROWS = f'''PERFORM 1 FROM materialization_state
    WHERE dataset_key IN ('{_EACH}','{_V1}','{_V2}')
    ORDER BY dataset_key COLLATE "C" FOR UPDATE;
'''


def _before_update(source):
    return _previous._replace_once(
        source, '        UPDATE materialization_state SET',
        '        ' + _LOCK_ROWS + '        UPDATE materialization_state SET',
    )


_invalidate = _previous._replace_once(_previous._invalidate, _OLD_LIMIT, _NEW_LIMIT)
_invalidate = _previous._replace_once(
    _invalidate, f'IF changed_since < {_NEW_LIMIT} THEN',
    f'IF changed_since < {_NEW_LIMIT} AND (summary_relevant OR changed_since < {_OLD_LIMIT}) THEN',
)
_invalidate = _previous._replace_once(
    _invalidate,
    f"WHERE dataset_key='{_EACH}' OR (dataset_key='{_V1}' AND summary_relevant)",
    f"WHERE (dataset_key='{_EACH}' AND changed_since < {_OLD_LIMIT}) "
    f"OR (dataset_key='{_V1}' AND summary_relevant AND changed_since < {_OLD_LIMIT}) "
    f"OR (dataset_key='{_V2}' AND summary_relevant)",
)
_invalidate = _before_update(_invalidate)
_identity = 'CREATE OR REPLACE FUNCTION each_facts_brand_identity()' + _previous._both.split(
    'CREATE OR REPLACE FUNCTION each_facts_brand_identity()', 1,
)[1]
_identity = _previous._replace_once(
    _identity, f"WHERE dataset_key IN ('{_EACH}','{_V1}')",
    f"WHERE dataset_key IN ('{_EACH}','{_V1}','{_V2}')",
)
_identity = _before_update(_identity)
_flag = _previous._replace_once(_previous._flag_function, _OLD_LIMIT, _NEW_LIMIT)
_flag = _previous._replace_once(
    _flag, f"WHERE dataset_key='{_V1}'",
    f"WHERE (dataset_key='{_V1}' AND changed_since < {_OLD_LIMIT}) OR dataset_key='{_V2}'",
)
_flag = _before_update(_flag)
_new_build = _previous._replace_once(BUILD_SQL, CUTOFF, _NEW_CUTOFF)
_new_build = _previous._replace_once(
    _new_build, 'CREATE MATERIALIZED VIEW home_post_sentiment_facts AS',
    'CREATE MATERIALIZED VIEW home_post_sentiment_facts_v2 AS',
)
_GUARD = _previous._GUARD + '\nLOCK TABLE materialization_state IN ACCESS EXCLUSIVE MODE NOWAIT;\n'
_FORWARD = (
    f"INSERT INTO materialization_state(dataset_key,source_generation) VALUES ('{_V2}',0);\n"
    + _new_build
    + 'CREATE UNIQUE INDEX home_post_sentiment_facts_v2_key ON home_post_sentiment_facts_v2(post_id);\n'
    + _invalidate + _identity + _flag
    + "CREATE FUNCTION home_sentiment_masks_v2() RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT TRUE';"
)
_REVERSE = (
    'DROP FUNCTION home_sentiment_masks_v2();\n'
    + _previous._both + _previous._flag_function
    + 'DROP MATERIALIZED VIEW home_post_sentiment_facts_v2;\n'
    + f"DELETE FROM materialization_state WHERE dataset_key='{_V2}';\n"
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [('core', '0244_home_sentiment_masks')]
    operations: ClassVar[list] = [
        migrations.RunSQL(_GUARD, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(_FORWARD, reverse_sql=_REVERSE),
        migrations.RunSQL(migrations.RunSQL.noop, reverse_sql=_GUARD),
    ]
