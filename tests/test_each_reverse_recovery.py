"""A retry must finish reversal after its atomic storage teardown committed."""
from importlib import import_module

import pytest
from django.db import connection


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_reverse_resumes_after_storage_teardown_before_index_drop():
    assert connection.settings_dict['NAME'].startswith('test_')
    migration = import_module('core.migrations.0235_each_chart_facts')
    try:
        with connection.schema_editor(atomic=False) as editor:
            migration.drop_storage(None, editor)
            migration.backwards(None, editor)
        with connection.cursor() as cursor:
            cursor.execute('SELECT to_regclass(%s),to_regclass(%s),to_regclass(%s),to_regclass(%s)',
                           ['each_brand_post_facts_source', 'each_brand_post_facts', migration.COVER_NAME, migration.WIDE_NAME])
            assert cursor.fetchone() == (None, None, None, None)
    finally:
        # Restore only these task-owned objects, even for the expected red run.
        with connection.schema_editor(atomic=False) as editor:
            migration.forwards(None, editor)
