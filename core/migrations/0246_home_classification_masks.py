"""Add an online, rebuildable classification projection beside older readers."""
from importlib import import_module
from typing import ClassVar

from django.db import migrations

from core.migrations._home_classification_masks_v3 import BUILD, SOURCE

_previous = import_module('core.migrations.0245_home_sentiment_recent_boundary')
_replace = _previous._previous._replace_once
_V3 = 'home.post_classification_facts.v3'
_old_rows = "'each.brand_post_facts.v1','home.post_sentiment_facts.v1','home.post_sentiment_facts.v2'"
_new_rows = _old_rows + ", '" + _V3 + "'"


def _lock_v3(source):
    return _replace(source, _old_rows, _new_rows)


_invalidate = _lock_v3(_previous._invalidate)
_invalidate = _replace(
    _invalidate, '(summary_relevant OR changed_since <',
    "(summary_relevant OR TG_TABLE_NAME IN ('posts_brands_signals','posts_brands_product_labels') OR changed_since <",
)
_invalidate = _replace(
    _invalidate,
    "OR (dataset_key='home.post_sentiment_facts.v2' AND summary_relevant);",
    "OR (dataset_key='home.post_sentiment_facts.v2' AND summary_relevant) "
    f"OR (dataset_key='{_V3}' AND (summary_relevant OR TG_TABLE_NAME IN "
    "('posts_brands_signals','posts_brands_product_labels')));",
)
# This function names the same set twice: its lock and its invalidation update.
_identity = _previous._identity.replace(_old_rows, _new_rows)
if _previous._identity.count(_old_rows) != 2:
    raise RuntimeError('Unexpected brand identity invalidation definition')
_flag = _lock_v3(_previous._flag)
_flag = _replace(_flag, "OR dataset_key='home.post_sentiment_facts.v2';",
                 f"OR dataset_key='home.post_sentiment_facts.v2' OR dataset_key='{_V3}';")
_FORWARD = (
    f"INSERT INTO materialization_state(dataset_key,source_generation) VALUES ('{_V3}',0);\n"
    + SOURCE + ';\n' + BUILD
    + 'CREATE UNIQUE INDEX home_post_classification_facts_key ON home_post_classification_facts(post_id);\n'
    + _invalidate + _identity + _flag
    + "CREATE FUNCTION home_classification_masks_v3() RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT TRUE';"
)
_REVERSE = (
    'DROP FUNCTION home_classification_masks_v3();\n'
    + _previous._invalidate + _previous._identity + _previous._flag
    + 'DROP MATERIALIZED VIEW home_post_classification_facts;\n'
    + 'DROP VIEW home_post_classification_facts_source;\n'
    + f"DELETE FROM materialization_state WHERE dataset_key='{_V3}';\n"
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [('core', '0245_home_sentiment_recent_boundary')]
    operations: ClassVar[list] = [
        migrations.RunSQL(_previous._GUARD, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(_FORWARD, reverse_sql=_REVERSE),
        migrations.RunSQL(migrations.RunSQL.noop, reverse_sql=_previous._GUARD),
    ]
