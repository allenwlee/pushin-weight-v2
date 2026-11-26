"""An older trigger cannot be paired with the online publication protocol."""

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from core.materializations import refresh_materialization, sqlstate
from monitor.each_chart_facts import EACH_FACTS

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
MIGRATION = "0241_each_refresh_tracking"
PREVIOUS = "0240_materialization_refresh_tracking"


def test_reverse_guard_rejects_an_in_flight_online_refresh():
    reverse_sql = import_module(f"core.migrations.{MIGRATION}")._REVERSE_CAPABILITY
    assert refresh_materialization(EACH_FACTS, force=True)["status"] == "refreshed"
    observed = []

    def attempt_reverse():
        try:
            with transaction.atomic(), connections["default"].cursor() as cursor:
                cursor.execute(reverse_sql)
        except DatabaseError as error:
            return sqlstate(error)
        finally:
            connections["default"].close()
        return "unexpected-success"

    def during_refresh(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("REFRESH MATERIALIZED VIEW"):
            with ThreadPoolExecutor(max_workers=1) as pool:
                observed.append(pool.submit(attempt_reverse).result(timeout=5))
        return result

    with connection.execute_wrapper(during_refresh):
        assert refresh_materialization(EACH_FACTS, force=True)["status"] == "refreshed"
    assert observed == ["55P03"]


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0245_home_sentiment_recent_boundary")], indirect=True)
def test_new_online_refresher_refuses_reversed_tracking_migration(migration_rehearsal_schema):
    executor = MigrationExecutor(connection)
    executor.migrate([("core", PREVIOUS)])
    try:
        assert refresh_materialization(EACH_FACTS, force=True) == {"status": "unavailable"}
    finally:
        MigrationExecutor(connection).migrate([("core", "0245_home_sentiment_recent_boundary")])
