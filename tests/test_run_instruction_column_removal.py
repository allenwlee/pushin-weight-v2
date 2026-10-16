"""The final physical drop preserves executions and job-backed enforcement."""

import json
import re
import uuid
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.benchmark_metric_store import persist_source
from core.collection_state import claim_job, finish_run
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    MetricValue,
    SourceMetric,
)
from tests.collection_fixtures import evidence_job
from tests.test_benchmark_download_persistence import configured, payload
from tests.test_collection_jobs import ready

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]
BRIDGE = [("core", "0089_job_owned_run_instructions")]
FINAL = [("core", "0090_remove_run_instruction_columns")]
COPIES = {"source_id", "purpose", "contract_id", "scope"}


def run_columns():
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "collection_runs"
            )
        }


def function_definition(name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef(%s::regprocedure)", [name + "()"])
        return cursor.fetchone()[0]


def test_current_runs_have_no_physical_instruction_columns():
    assert not run_columns() & COPIES
    assert run_columns() == {field.column for field in CollectionRun._meta.local_fields}
    body = function_definition("collection_run_job_instructions")
    assert not re.search(
        r"\b(?:NEW|OLD)\.(?:source_id|purpose|contract_id|scope)\b", body, re.IGNORECASE
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_0089_to_0090_preserves_rows_clocks_evidence_views_and_instruction_links():
    executor = MigrationExecutor(connection)
    executor.migrate(BRIDGE)
    metric = persist_source(configured(), "hf", "a" * 64, payload(9007199254740993))
    timestamp = timezone.now()
    catalog_job = evidence_job(
        source_id="hf", scope={"namespaces": ["publisher"], "flag": False}
    )
    catalog = CollectionRun.objects.create(
        job=catalog_job,
        status="partial",
        ingestion_key="b" * 64,
        started_at=timestamp,
        observed_at=timestamp,
        source_as_of=timestamp,
        raw_payload={"keep": [0, False]},
        request_params={"cursor": "next"},
        source_metadata={"native": "unchanged"},
        report={"original": True},
        invocations=[{"requests": 2}],
        request_count=2,
    )
    scope = catalog.scopes.create(
        scope_key="publisher",
        cursor="saved",
        ownership={"keep": 0},
        envelopes=[{"status": "ok"}],
    )
    CollectionObservation.objects.create(
        run=catalog,
        scope_run=scope,
        source_identifier="publisher/model",
        source_subject_kind="repository",
        observation_key="c" * 64,
        observed_at=timestamp,
        listing={"keep": False},
        envelopes=[{"raw": [1]}],
    )
    content_job = evidence_job(
        source_id="x", purpose="content", scope={"posts": ["actual"]}
    )
    CollectionRun.objects.create(
        job=content_job,
        status="aborted",
        ingestion_key="d" * 64,
        started_at=timestamp,
        completed_at=timestamp,
        error_code="original",
    )
    CollectionRun.objects.create(
        job=metric.job,
        status="running",
        ingestion_key="e" * 64,
        started_at=timestamp,
        lease_token=uuid.uuid4(),
        lease_expires_at=timestamp + timedelta(minutes=5),
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM collection_runs ORDER BY id")
        columns = [c.name for c in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT c.relname, c.oid, c.relfilenode FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('collection_runs','metric_collection_runs','metric_observations') ORDER BY c.relname"
        )
        relations = cursor.fetchall()
        cursor.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name, ordinal_position"
        )
        physical = set(cursor.fetchall())
        cursor.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='collection_runs'::regclass ORDER BY conname"
        )
        constraints = cursor.fetchall()
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='collection_runs' AND indexname='idx_metric_run_outcome'"
        )
        outcome_index = cursor.fetchall()
    snapshots = {
        model: list(model.objects.order_by("pk").values())
        for model in (
            CollectionJob,
            CollectionObservation,
            MetricValue,
            SourceMetric,
            type(scope),
        )
    }
    job_guard = function_definition("collection_job_immutable_instructions")
    executor = MigrationExecutor(connection)
    executor.migrate(FINAL)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM collection_runs ORDER BY id")
        final_columns = [c.name for c in cursor.description]
        final_rows = [
            dict(zip(final_columns, row, strict=True)) for row in cursor.fetchall()
        ]
        assert set(columns) - set(final_columns) == COPIES
        assert set(final_columns) - set(columns) == set()
        assert final_rows == [
            {k: v for k, v in row.items() if k not in COPIES} for row in rows
        ]
        cursor.execute(
            "SELECT c.relname, c.oid, c.relfilenode FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('collection_runs','metric_collection_runs','metric_observations') ORDER BY c.relname"
        )
        assert cursor.fetchall() == relations
        cursor.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name, ordinal_position"
        )
        final_physical = set(cursor.fetchall())
        assert physical - final_physical == {
            ("collection_runs", name) for name in COPIES
        }
        assert final_physical - physical == set()
        cursor.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='collection_runs'::regclass ORDER BY conname"
        )
        assert cursor.fetchall() == [
            row
            for row in constraints
            if not (
                row[1].startswith("FOREIGN KEY (source_id)")
                or row[1].startswith("FOREIGN KEY (contract_id)")
                # PostgreSQL 18 catalogs the removed columns' NOT NULL rules.
                or row[1] in {f"NOT NULL {column}" for column in COPIES}
            )
        ]
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='collection_runs' AND indexname='idx_metric_run_outcome'"
        )
        assert cursor.fetchall() == outcome_index
        cursor.execute("SELECT * FROM metric_collection_runs WHERE id=%s", [metric.pk])
        view_columns = [c.name for c in cursor.description]
        projected = dict(zip(view_columns, cursor.fetchone(), strict=True))
        if isinstance(projected["scope"], str):
            projected["scope"] = json.loads(projected["scope"])
        assert len(view_columns) == 25
        assert (
            projected["source_id"],
            projected["purpose"],
            projected["contract_id"],
            projected["scope"],
        ) == (
            metric.job.source_id,
            metric.job.purpose,
            metric.job.contract_id,
            metric.job.definition["scope"],
        )
        for view in ("metric_collection_runs", "metric_observations"):
            cursor.execute("SELECT pg_get_viewdef(%s::regclass, true)", [view])
            assert not re.search(
                r"\br\.(?:source_id|purpose|contract_id|scope)\b", cursor.fetchone()[0]
            )
    for model, expected in snapshots.items():
        assert list(model.objects.order_by("pk").values()) == expected
    assert function_definition("collection_job_immutable_instructions") == job_guard
    assert not run_columns() & COPIES
    call_command("normalize_collection_run_jobs", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE metric_collection_runs SET report=%s WHERE id=%s",
            [json.dumps({"post_drop": "ordinary execution update"}), metric.pk],
        )
        assert cursor.rowcount == 1
    metric.refresh_from_db()
    assert metric.report == {"post_drop": "ordinary execution update"}
    # The unchanged ORM-free preceding application still writes after the drop.
    later = persist_source(metric.job.contract, "hf", "f" * 64, payload(42))
    assert (
        later.job_id == metric.job_id
        and later.observations.get()
        .values.get(source_metric__metric_key="downloads")
        .integer_value
        == 42
    )
    claim = claim_job(ready(key="post-drop-catalog").pk)
    finish_run(claim, status="success")
    assert CollectionRun.objects.get(pk=claim.run_id).completed_at is not None
    with pytest.raises(IrreversibleError):
        MigrationExecutor(connection).migrate(BRIDGE)
    assert not run_columns() & COPIES


@pytest.mark.parametrize("purpose", ["metric", "catalog", "content"])
def test_job_backed_lifecycle_updates_after_physical_drop(purpose):
    assert not run_columns() & COPIES
    contract_id = configured().pk if purpose == "metric" else None
    job = evidence_job(
        source_id="x" if purpose == "content" else "hf",
        purpose=purpose,
        contract_id=contract_id,
    )
    run = CollectionRun.objects.create(
        job=job,
        ingestion_key="a" * 64,
        lease_token=uuid.uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    completed = None if purpose == "catalog" else timezone.now()
    with (
        pytest.raises(IntegrityError, match="lifecycle mismatch"),
        transaction.atomic(),
    ):
        CollectionRun.objects.filter(pk=run.pk).update(
            status="partial", completed_at=timezone.now() if completed is None else None
        )
    CollectionRun.objects.filter(pk=run.pk).update(
        status="partial", completed_at=completed
    )
    run.refresh_from_db()
    assert (
        run.status == "partial"
        and run.completed_at == completed
        and run.job_id == job.pk
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"success_count": 1},
        {"ingestion_key": "bad"},
        {"payload_sha256": "x" * 64},
        {"status": "running"},
    ],
)
def test_local_run_checks_survive_physical_drop(changes):
    assert not run_columns() & COPIES
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf"), status="pending", ingestion_key="a" * 64
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.filter(pk=run.pk).update(**changes)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_drop_lock_timeout_rolls_back_function_and_columns_then_retry_succeeds():
    import psycopg

    MigrationExecutor(connection).migrate(BRIDGE)
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf"), status="pending", ingestion_key="a" * 64
    )
    original = function_definition("collection_run_job_instructions")
    with psycopg.connect(**connection.get_connection_params()) as reader:
        reader.execute("SELECT id FROM collection_runs WHERE id=%s", [run.pk])
        with pytest.raises(OperationalError, match="lock timeout"):
            MigrationExecutor(connection).migrate(FINAL)
        assert run_columns() & COPIES == COPIES
        assert function_definition("collection_run_job_instructions") == original
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM django_migrations WHERE app='core' AND name='0090_remove_run_instruction_columns'"
            )
            assert cursor.fetchone()[0] == 0
        reader.rollback()
    MigrationExecutor(connection).migrate(FINAL)
    assert not run_columns() & COPIES
    run.refresh_from_db()
    assert run.status == "pending" and run.completed_at is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_scope_sql_null_rejection_and_present_json_values_match_the_bridge():
    from psycopg.types.json import Jsonb

    observations = []
    for release, target in enumerate((BRIDGE, FINAL)):
        MigrationExecutor(connection).migrate(target)
        outcomes = []
        for index, definition in enumerate(
            (
                {},
                {"scope": None},
                {"scope": {}},
                {"scope": []},
                {"scope": False},
                {"scope": 0},
                {"scope": "stored"},
            )
        ):
            job_id = uuid.uuid4()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO collection_jobs (id, job_key, source_id, purpose, operation, mode, definition, definition_sha256, state, created_at, updated_at) VALUES (%s,%s,'hf','catalog','archived_run','historical',%s,%s,'completed',%s,%s)",
                    [
                        job_id,
                        f"scope-parity:{release}:{index}",
                        Jsonb(definition),
                        "a" * 64,
                        timezone.now(),
                        timezone.now(),
                    ],
                )
            if "scope" not in definition:
                with pytest.raises(IntegrityError) as failure, transaction.atomic():
                    CollectionRun.objects.create(
                        job_id=job_id,
                        status="pending",
                        ingestion_key=f"{release}{index}" * 32,
                    )
                assert failure.value.__cause__.sqlstate == "23502"
                outcomes.append("sql-null-rejected")
            else:
                run = CollectionRun.objects.create(
                    job_id=job_id,
                    status="pending",
                    ingestion_key=f"{release}{index}" * 32,
                )
                assert run.scope == definition["scope"]
                assert type(run.scope) is type(definition["scope"])
                outcomes.append(run.scope)
        observations.append(outcomes)
    assert (
        observations[0]
        == observations[1]
        == ["sql-null-rejected", None, {}, [], False, 0, "stored"]
    )
