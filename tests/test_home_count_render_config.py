"""The new provider-free job must not inherit collection credentials/schedules."""

from pathlib import Path

import yaml


def test_count_maintenance_has_only_owned_database_configuration():
    blueprint = yaml.safe_load(Path("render.yaml").read_text())
    name = "pushinweight-home-counts"
    jobs = [service for service in blueprint["services"] if service["name"] == name]
    assert len(jobs) == 1, "declare exactly one isolated count maintenance job"
    job = jobs[0]
    assert job["type"] == "cron"
    assert job["startCommand"] == "python manage.py refresh_materializations"
    assert job["schedule"] == "7,22,37,52 * * * *"
    environment = {item["key"]: item for item in job["envVars"]}
    assert set(environment) == {
        "PYTHON_VERSION",
        "DEBUG",
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT",
        "DATABASE_URL",
        "PW_SERVING_DATABASE_ROLE",
    }
    assert environment["DATABASE_URL"]["fromDatabase"]["name"] == "pushinweight-db-shadow"
    assert environment["PW_SERVING_DATABASE_ROLE"]["value"] == "pushinweight_web_serving"


def test_schema_integration_does_not_provision_staging_count_maintenance():
    blueprint = yaml.safe_load(Path("render-staging.yaml").read_text())
    assert all(
        service["name"] != "pushinweight-staging-home-counts"
        and service.get("startCommand") != "python manage.py refresh_materializations"
        for service in blueprint["services"]
    ), "staging count-cron provisioning is excluded from this delivery"


def test_materialization_definition_preserves_home_defaults_and_allows_each_limits():
    from dataclasses import replace

    from monitor.home_count_summary import HOME_COUNTS

    assert HOME_COUNTS.refresh_timeout == "120s"
    assert HOME_COUNTS.advance_barrier is False
    each = replace(HOME_COUNTS, refresh_timeout="90s", advance_barrier=True)
    assert each.refresh_timeout == "90s"
    assert each.advance_barrier is True


def test_advance_barrier_retries_without_holding_transaction_or_source_locks(monkeypatch):
    from contextlib import contextmanager
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from django.db import DatabaseError

    from core import materializations

    target = datetime(2026, 11, 19, tzinfo=UTC)
    events = []
    active = False

    @contextmanager
    def atomic():
        nonlocal active
        assert not active
        active = True
        try:
            yield
        finally:
            active = False

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            events.append((sql, active))
            if sql.startswith("LOCK TABLE"):
                error = DatabaseError("source writer is active")
                error.__cause__ = type("LockUnavailable", (Exception,), {"sqlstate": "55P03"})()
                raise error

        def fetchone(self):
            return target - timedelta(days=1), target

    definition = materializations.MaterializationDefinition(
        dataset_key="test.barrier.v1", relation="test_barrier", source_tables=("posts",),
        lock_id=123, cutoff_sql="clock_timestamp()", advance_barrier=True,
    )
    fake = SimpleNamespace(
        cursor=Cursor, in_atomic_block=False,
        ops=SimpleNamespace(quote_name=lambda name: '"' + name + '"'),
    )
    monkeypatch.setattr(materializations, "connection", fake)
    monkeypatch.setattr(materializations.transaction, "atomic", atomic)

    def sleep(delay):
        assert not active, "failed attempt must release its transaction before waiting"
        assert delay == 0.2
        events.append(("sleep", active))

    monkeypatch.setattr(materializations.time, "sleep", sleep)
    assert materializations._prepare_advance(definition) == (False, None)
    locks = [(sql, transaction_open) for sql, transaction_open in events if sql.startswith("LOCK")]
    assert len(locks) == 10
    assert all(sql == 'LOCK TABLE "posts" IN SHARE MODE NOWAIT' and transaction_open
               for sql, transaction_open in locks)
    assert sum(sql == "sleep" for sql, _ in events) == 9
    assert not active


def test_home_definition_never_takes_the_each_advance_barrier(monkeypatch):
    from core import materializations
    from monitor.home_count_summary import HOME_COUNTS

    class NoDatabase:
        def cursor(self):
            raise AssertionError("homepage must retain its existing refresh path")

    monkeypatch.setattr(materializations, "connection", NoDatabase())
    assert materializations._prepare_advance(HOME_COUNTS) == (True, None)


def test_registered_command_attempts_each_after_home_failure_and_reports_both(monkeypatch):
    import json
    from io import StringIO
    from types import SimpleNamespace

    import pytest
    from django.core.management.base import CommandError

    from monitor.management.commands import refresh_materializations

    definitions = tuple(SimpleNamespace(dataset_key=key) for key in (
        "home.brand_time_counts.v1", "each.brand_post_facts.v1",
    ))
    seen = []
    monkeypatch.setattr(refresh_materializations, "registered_definitions", lambda: definitions)

    def refresh(definition):
        seen.append(definition.dataset_key)
        if definition is definitions[0]:
            raise RuntimeError("private database detail must not become JSON output")
        return {"status": "refreshed", "generation": 3}

    monkeypatch.setattr(refresh_materializations, "refresh_materialization", refresh)
    output = StringIO()
    command = refresh_materializations.Command(stdout=output)
    with pytest.raises(CommandError, match="home.brand_time_counts.v1"):
        command.handle()
    assert seen == [item.dataset_key for item in definitions]
    assert json.loads(output.getvalue()) == {
        definitions[0].dataset_key: {"status": "unavailable", "error": "RuntimeError"},
        definitions[1].dataset_key: {"status": "refreshed", "generation": 3},
    }
