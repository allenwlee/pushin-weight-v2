"""The compatible release preserves old writers before job-only reader cutover."""

import hashlib
import importlib
import types
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.models import CollectionJob, CollectionRun
from tests.test_collection_jobs import ready

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]
MIGRATION = "core.migrations.0088_archive_run_instructions"


def previous_module(name):
    """Exact core source at 2023a3ad, runnable without local Git history.

    Fixtures are byte-for-byte exports of the pre-U17 caller, rather than a
    reconstruction of its behavior. Hashes pin that historical provenance.
    """
    hashes = {
        "hf_catalog": "a25fcf26cf74060788172e4e9cb16bebf88ab6847151d619c09c59aa85591356",
        "benchmark_metric_store": "783fd5cda24bcee98a752f19e0dbb86eff9e9647a227cc10390991849a8065ab",
    }
    path = (
        Path(__file__).parent
        / "fixtures"
        / "collection_compat"
        / f"{name}_2023a3ad.py.txt"
    )
    source = path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == hashes[name]
    module = types.ModuleType(f"previous_{name}")
    exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102 - trusted historical caller fixture
    return module


def previous_catalog_module():
    return previous_module("hf_catalog")


@pytest.mark.parametrize(
    "status,budget", [("pending", 1), ("partial", 2), ("success", 50)]
)
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_build_leaves_catalog_resumable_by_loaded_previous_caller(status, budget):
    from tests.test_hf_catalog_runner import api, scope

    executor = MigrationExecutor(connection)
    executor.migrate([("core", "0087_source_statistics_snapshot")])
    previous = previous_catalog_module()
    first = previous.execute_catalog(scope=scope(), hf=api(budget=budget))
    run = CollectionRun.objects.get(pk=first["run_id"])
    if status == "pending":
        CollectionRun.objects.filter(pk=run.pk).update(status="pending")
    else:
        assert run.status == status
    before = list(run.scopes.order_by("pk").values())
    MigrationExecutor(connection).migrate([("core", "0088_archive_run_instructions")])
    run.refresh_from_db()
    assert run.job_id is None
    assert run.status == status
    assert list(run.scopes.order_by("pk").values()) == before
    assert previous.execute_catalog(run_id=run.pk, hf=api())["complete"]
    run.refresh_from_db()
    assert run.job_id is None
    assert CollectionJob.objects.count() == 0


def test_build_skips_all_jobless_running_rows_but_strict_catchup_refuses_them():
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_persistence import configured, payload

    numeric = persist_source(configured(), "hf", "d" * 64, payload())
    CollectionRun.objects.filter(pk=numeric.pk).update(
        job=None, status="running", completed_at=None, lease_token=None
    )
    catalog = CollectionRun.objects.create(
        source_id="hf", purpose="catalog", status="running", ingestion_key="e" * 64
    )
    before = list(CollectionRun.objects.order_by("pk").values())
    module = importlib.import_module(MIGRATION)
    with connection.schema_editor(atomic=False) as editor:
        module.archive_inactive_run_instructions(apps, editor)
    assert list(CollectionRun.objects.order_by("pk").values()) == before
    with (
        connection.schema_editor(atomic=False) as editor,
        pytest.raises(ValueError, match="must finish"),
    ):
        module.archive_run_instructions(apps, editor)
    catalog.refresh_from_db()
    assert catalog.job_id is None and catalog.lease_token is None


def test_catalog_run_lookup_preserves_jobless_history_without_writes():
    from core.hf_catalog import resolve_catalog_run

    run = CollectionRun.objects.create(
        source_id="hf", purpose="catalog", status="pending", ingestion_key="f" * 64
    )
    jobs_before = CollectionJob.objects.count()
    resolved = resolve_catalog_run(run.pk)
    assert resolved.pk == run.pk
    assert resolved.job_id is None
    run.refresh_from_db()
    assert run.job_id is None
    assert CollectionJob.objects.count() == jobs_before


def test_phase1_reader_includes_finished_jobless_write_after_migration():
    from django.db.migrations.recorder import MigrationRecorder

    from core.collection_reports import resource_statistics
    from tests.test_benchmark_download_persistence import configured, payload

    assert (
        MigrationRecorder(connection)
        .migration_qs.filter(app="core", name="0088_archive_run_instructions")
        .exists()
    )
    previous = previous_module("benchmark_metric_store")
    contract = configured()
    run = previous.persist_source(contract, "hf", "f" * 64, payload(123))
    assert run.job_id is None and run.status == "success"
    report = resource_statistics(
        contract_id=contract.pk, source="hf", identifier="lab/Model"
    )
    assert {v["run_id"] for v in report["values"]} == {str(run.pk)}
    assert "123" in {v["value"] for v in report["values"]}


def test_scope_copy_mismatch_fences_a_claim():
    from core.collection_state import StaleClaim, claim_job, fenced_run

    claim = claim_job(ready().pk)
    CollectionRun.objects.filter(pk=claim.run_id).update(scope={"wrong": True})
    with pytest.raises(StaleClaim), fenced_run(claim):
        pytest.fail("mismatched legacy instructions were admitted")


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_0087_to_0088_preserves_every_existing_field_and_is_retryable():
    executor = MigrationExecutor(connection)
    before = [("core", "0087_source_statistics_snapshot")]
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    Source = old.get_model("core", "DataSource")
    Run = old.get_model("core", "CollectionRun")
    Scope = old.get_model("core", "CollectionScopeRun")
    Observation = old.get_model("core", "CollectionObservation")
    source = Source.objects.get(pk="hf")
    timestamp = timezone.now()
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_persistence import configured, payload

    numeric = persist_source(configured(), "hf", "e" * 64, payload(9007199254740993))
    # Simulate an old deployed writer without manufacturing a second collector.
    numeric_job = numeric.job_id
    Run.objects.filter(pk=numeric.pk).update(job=None)
    old.get_model("core", "CollectionJob").objects.filter(pk=numeric_job).delete()
    content = Run.objects.create(
        source=Source.objects.get(pk="x"),
        purpose="content",
        status="aborted",
        completed_at=timestamp,
        ingestion_key="f" * 64,
        report={"rejection": True},
    )
    runs = []
    for index, status in enumerate(("pending", "partial", "interrupted", "success")):
        run = Run.objects.create(
            id=uuid.uuid4(),
            source=source,
            purpose="catalog",
            status=status,
            scope={"namespaces": ["lab"], "unknown": None, "flag": False},
            ingestion_key=str(index) * 64,
            raw_payload={"keep": [0, False]},
            invocations=[{"requests": 2}],
            report={"original": "unchanged"},
            completed_at=timestamp if status == "success" else None,
            request_params={"cursor": "next"},
            source_metadata={"sha": "abc"},
        )
        scope = Scope.objects.create(run=run, scope_key="lab", ownership={"keep": 1})
        Observation.objects.create(
            run=run,
            scope_run=scope,
            source_identifier="lab/model",
            source_subject_kind="repository",
            observation_key=str(index) * 64,
            observed_at=timestamp,
            source_metadata={"native": [False, 0]},
        )
        runs.append(run)
    snapshots = {
        model: list(model.objects.order_by("pk").values())
        for model in (Run, Scope, Observation, old.get_model("core", "MetricValue"))
    }
    executor = MigrationExecutor(connection)
    executor.migrate([("core", "0088_archive_run_instructions")])
    module = importlib.import_module(MIGRATION)
    with connection.schema_editor() as editor:
        module.archive_run_instructions(old, editor)
    for model, expected in snapshots.items():
        actual = list(model.objects.order_by("pk").values())
        if model is Run:
            for row in actual:
                assert row["job_id"] is not None
                row["job_id"] = None
        assert actual == expected
    Job = old.get_model("core", "CollectionJob")
    assert Job.objects.count() == len(runs) + 2
    numeric.refresh_from_db()
    content.refresh_from_db()
    assert numeric.job.contract_id == numeric.contract_id
    assert content.job.purpose == "content"
    for job in Job.objects.all():
        assert job.state == "completed" and job.operation == "archived_run"
        assert job.next_due_at is None and job.next_retry_at is None
        assert job.active_run_id is None
        assert job.definition["budgets"] is None
        assert job.definition["schedule"] is None
        assert (
            job.definition["historical_instructions"] == "unknown_beyond_stored_fields"
        )


@pytest.mark.parametrize(
    "helper", ["archive_run_instructions", "archive_inactive_run_instructions"]
)
def test_archive_rejects_existing_job_copy_mismatch(helper):
    from core.collection_state import claim_job, finish_run

    module = importlib.import_module(MIGRATION)
    claim = claim_job(ready().pk)
    finish_run(claim, status="success")
    CollectionRun.objects.filter(pk=claim.run_id).update(scope={"wrong": True})
    with (
        connection.schema_editor() as editor,
        pytest.raises(ValueError, match="instruction mismatch"),
    ):
        getattr(module, helper)(apps, editor)


def test_archives_cannot_become_ready_or_due():
    from core.collection_jobs import set_job_state
    from core.collection_scheduling import due_job
    from core.collection_state import claim_job

    module = importlib.import_module(MIGRATION)
    from core.models import DataSource

    run = CollectionRun.objects.create(
        source=DataSource.objects.get(pk="hf"),
        purpose="catalog",
        status="pending",
        scope={"actual": True},
        ingestion_key="a" * 64,
    )
    with connection.schema_editor() as editor:
        module.archive_run_instructions(apps, editor)
    run.refresh_from_db()
    with pytest.raises(ValueError):
        set_job_state(run.job_id, "ready")
    with pytest.raises(ValueError):
        claim_job(run.job_id)
    assert not due_job(run.job)["due"]
    assert CollectionJob.objects.get(pk=run.job_id).state == "completed"


@pytest.mark.parametrize("collision", ["id", "key"])
def test_archive_known_identity_collision_never_reassigns_or_overwrites(collision):
    from tests.test_collection_jobs import job

    module = importlib.import_module(MIGRATION)
    owner = job()
    run = CollectionRun.objects.create(
        source=owner.source,
        purpose="catalog",
        status="pending",
        ingestion_key="b" * 64,
    )
    if collision == "id":
        CollectionJob.objects.filter(pk=owner.pk).update(
            id=uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"pushinweight:archived-collection-run:v1:{run.pk}",
            )
        )
    else:
        CollectionJob.objects.filter(pk=owner.pk).update(
            job_key=f"archive:run:{run.pk}"
        )
    before = list(CollectionJob.objects.values())
    with (
        connection.schema_editor(atomic=False) as editor,
        pytest.raises(ValueError, match="collision"),
    ):
        module.archive_run_instructions(apps, editor)
    run.refresh_from_db()
    assert run.job_id is None
    assert list(CollectionJob.objects.values()) == before


@pytest.mark.django_db(transaction=True)
def test_archive_retry_after_committed_batch_preserves_ids(monkeypatch):
    from core.models import DataSource

    module = importlib.import_module(MIGRATION)
    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    first = CollectionRun.objects.create(
        id=uuid.UUID(int=1),
        source=DataSource.objects.get(pk="hf"),
        purpose="catalog",
        status="pending",
        ingestion_key="a" * 64,
    )
    active = CollectionRun.objects.create(
        id=uuid.UUID(int=2),
        source=first.source,
        purpose="catalog",
        status="running",
        ingestion_key="b" * 64,
        lease_token=uuid.uuid4(),
        lease_expires_at=timezone.now(),
    )
    with (
        connection.schema_editor(atomic=False) as editor,
        pytest.raises(ValueError, match="must finish"),
    ):
        module.archive_run_instructions(apps, editor)
    first.refresh_from_db()
    preserved = first.job_id
    assert preserved is not None
    assert CollectionJob.objects.count() == 1
    CollectionRun.objects.filter(pk=active.pk).update(status="interrupted")
    with connection.schema_editor(atomic=False) as editor:
        module.archive_run_instructions(apps, editor)
    first.refresh_from_db()
    assert first.job_id == preserved
    assert CollectionJob.objects.count() == 2


def test_direct_claim_cannot_replace_a_job_assigned_after_object_was_loaded():
    from core.collection_state import claim_direct_run
    from core.models import DataSource

    module = importlib.import_module(MIGRATION)
    stale = CollectionRun.objects.create(
        source=DataSource.objects.get(pk="hf"),
        purpose="catalog",
        status="pending",
        ingestion_key="c" * 64,
    )
    with connection.schema_editor(atomic=False) as editor:
        module.archive_run_instructions(apps, editor)
    actual = CollectionRun.objects.get(pk=stale.pk)
    with pytest.raises(ValueError, match="changed while acquiring"):
        claim_direct_run(
            stale, driver="execute_catalog", seconds=60, limits={"seconds": 60}
        )
    actual.refresh_from_db()
    assert actual.job.operation == "archived_run"
    assert actual.status == "pending"
    assert CollectionJob.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_fence_checks_wall_clock_after_waiting_for_job_lock():
    import time
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event

    import psycopg
    from django.db import close_old_connections

    from core.collection_state import StaleClaim, claim_job, fenced_run

    claim = claim_job(ready().pk)
    entered = Event()

    def attempt():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET application_name = 'u17-fence-expiry-test'")
            entered.set()
            with pytest.raises(StaleClaim), fenced_run(claim):
                pytest.fail("a lease that expired during lock wait was admitted")
        finally:
            close_old_connections()

    params = connection.get_connection_params()
    with (
        ThreadPoolExecutor(max_workers=1) as pool,
        psycopg.connect(**params) as holder,
        holder.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT id FROM collection_jobs WHERE id = %s FOR UPDATE",
            [claim.job_id],
        )
        pending = pool.submit(attempt)
        assert entered.wait(5)
        deadline = time.monotonic() + 5
        while True:
            cursor.execute("SELECT pg_stat_clear_snapshot()")
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                "WHERE application_name = 'u17-fence-expiry-test' AND wait_event_type = 'Lock')"
            )
            if cursor.fetchone()[0]:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        cursor.execute(
            "UPDATE collection_runs SET lease_expires_at = %s WHERE id = %s",
            [timezone.now() - timedelta(seconds=1), claim.run_id],
        )
        holder.commit()
        pending.result(timeout=5)
