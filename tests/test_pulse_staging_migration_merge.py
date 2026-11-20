"""Verify Pulse's migration retains the existing Chatter instruction guard."""
import pytest
from django.db import connection

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def function_definition():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('collection_typed_instruction_guard'::regproc)")
        return cursor.fetchone()[0]


def test_lineage_migration_preserves_chatter_and_restores_its_guard_on_rollback():
    from django.db.migrations.executor import MigrationExecutor

    previous = [('core', '0236_pulse_lineage_name_index')]
    latest = [('core', '0241_pulse_category_evidence_guard')]
    try:
        MigrationExecutor(connection).migrate(previous)
        old = function_definition()
        assert 'chatter_search' in old and 'chatter-trends-sources-v1' in old
        assert 'lineage_wakeup' not in old
        MigrationExecutor(connection).migrate(latest)
        combined = function_definition()
        assert 'chatter_search' in combined and 'chatter-trends-sources-v1' in combined
        assert 'lineage_wakeup' in combined
        assert 'NEW.max_requests IS NULL AND NOT' in combined
        assert 'NEW.max_items IS NULL AND NOT' in combined
    finally:
        MigrationExecutor(connection).migrate(latest)
