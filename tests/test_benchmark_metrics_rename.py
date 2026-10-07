"""A populated rename preserves the table object, measurements and sequence."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from tests.test_benchmark_download_persistence import configured, payload

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_populated_rename_and_reverse_preserve_oid_ids_foreign_keys_and_sequence():
    from core.benchmark_metric_store import persist_source
    from core.models import MetricValue, SourceMetric

    run = persist_source(configured(), "hf", "9" * 64, payload())
    before = list(
        MetricValue.objects.values_list("id", "source_metric_id", "integer_value")
    )
    definitions = list(SourceMetric.objects.values_list("id", "metric_key"))

    def state(table):
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s::regclass::oid", [table])
            oid = cursor.fetchone()[0]
            cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", [table])
            sequence = cursor.fetchone()[0]
            cursor.execute(
                "SELECT oid, conname FROM pg_constraint WHERE conrelid = %s ORDER BY oid",
                [oid],
            )
            constraints = cursor.fetchall()
            cursor.execute(
                "SELECT indexrelid FROM pg_index WHERE indrelid = %s ORDER BY indexrelid",
                [oid],
            )
            indexes = cursor.fetchall()
        return oid, sequence, constraints, indexes

    assert SourceMetric._meta.db_table == "metrics"
    original = state("metrics")
    assert original[1].endswith("source_metrics_id_seq")
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([("core", "0072_merge_benchmark_main")])
        assert state("source_metrics") == original
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, metric_key FROM source_metrics ORDER BY id")
            assert cursor.fetchall() == sorted(definitions)
        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0073_rename_metrics")])
        assert state("metrics") == original
        assert (
            list(
                MetricValue.objects.values_list(
                    "id", "source_metric_id", "integer_value"
                )
            )
            == before
        )
        assert run.observations.count() == 1
    finally:
        MigrationExecutor(connection).migrate([("core", "0073_rename_metrics")])
