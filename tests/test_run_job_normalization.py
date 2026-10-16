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


@pytest.fixture
def historical_schema(isolated_migration_database, monkeypatch):
    """Old rows belong to historical models on the actual old schema."""
    executor = MigrationExecutor(connection)
    target = [("core", "0088_archive_run_instructions")]
    executor.migrate(target)
    historical = executor.loader.project_state(target).apps
    monkeypatch.setitem(globals(), "apps", historical)
    monkeypatch.setitem(
        globals(), "CollectionRun", historical.get_model("core", "CollectionRun")
    )
    monkeypatch.setitem(
        globals(), "CollectionJob", historical.get_model("core", "CollectionJob")
    )
    return historical


def legacy_persist(contract, *args, **kwargs):
    historic_contract = apps.get_model("core", "MetricCollectionContract").objects.get(
        pk=contract.pk
    )
    return previous_module("benchmark_metric_store").persist_source(
        historic_contract, *args, **kwargs
    )


def previous_module(name, historical=None):
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
    # The frozen caller imports the model state it actually deployed against.
    # Never emulate removed ORM fields through a current compatibility manager.
    model_apps = historical or apps
    for symbol, value in list(vars(module).items()):
        if hasattr(value, "_meta") and value._meta.app_label == "core":
            setattr(
                module, symbol, model_apps.get_model("core", value._meta.model_name)
            )
    if name == "hf_catalog":
        from core.models import Product

        # Historical models deliberately omit Python methods; restore the
        # deployed read-through property without changing persisted state.
        module.Product.hf_namespace = Product.hf_namespace
        original = module.get_publisher

        def historical_publisher(*args, **kwargs):
            result = original(*args, **kwargs)
            return model_apps.get_model("core", "CompanyAccount").objects.get(
                pk=result.pk
            )

        module.get_publisher = historical_publisher
    return module


def previous_catalog_module(historical=None):
    return previous_module("hf_catalog", historical)


@pytest.mark.parametrize(
    "status,budget", [("pending", 1), ("partial", 2), ("success", 50)]
)
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.usefixtures("historical_schema")
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


@pytest.mark.usefixtures("historical_schema")
def test_build_skips_all_jobless_running_rows_but_strict_catchup_refuses_them():
    from tests.test_benchmark_download_persistence import configured, payload

    numeric = legacy_persist(configured(), "hf", "d" * 64, payload())
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


@pytest.mark.usefixtures("historical_schema")
def test_catalog_run_lookup_preserves_jobless_history_without_writes():
    resolve_catalog_run = previous_catalog_module().resolve_catalog_run

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


@pytest.mark.usefixtures("historical_schema")
def test_frozen_legacy_bootstrap_launcher_runs_only_with_its_historical_orm(
    settings, monkeypatch
):
    import httpx

    from core import models
    from tests.test_benchmark_download_persistence import configured, payload

    contract = configured()
    batch = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "pw-benchmark-production-bootstrap:" + str(contract.pk) + ":hf",
    )
    run = legacy_persist(contract, "hf", "9" * 64, payload(), batch_id=batch)
    settings.BENCHMARK_COLLECTION_ENABLED = True
    # Keep the current command's own imports bound to current model classes;
    # only the frozen inline caller receives its historical ORM imports.
    importlib.import_module("monitor.management.commands.collect_benchmark_due")
    monkeypatch.setattr(models, "MetricCollectionRun", CollectionRun)
    monkeypatch.setattr(
        models,
        "MetricCollectionContract",
        apps.get_model("core", "MetricCollectionContract"),
    )

    def no_provider_request(*args, **kwargs):
        raise AssertionError("Retained bootstrap and disabled schedule need no request")

    monkeypatch.setattr(httpx.Client, "send", no_provider_request)
    script = (
        Path(__file__).parent
        / "fixtures/collection_schema/legacy_benchmark_launcher.txt"
    ).read_text()
    script = script.replace("75c4a856-385b-429a-9b03-c7e023ea6f73", str(contract.pk))
    exec(compile(script, "historical_legacy_benchmark_launcher.py", "exec"), {})  # noqa: S102 - frozen historical deployed payload
    assert CollectionRun.objects.count() == 1
    assert CollectionRun.objects.get(pk=run.pk).observations.count() == 1


@pytest.mark.usefixtures("historical_schema")
def test_phase2_reader_includes_finished_old_writer_evidence_after_catchup():
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
    run = previous.persist_source(
        apps.get_model("core", "MetricCollectionContract").objects.get(pk=contract.pk),
        "hf",
        "f" * 64,
        payload(123),
    )
    assert run.job_id is None and run.status == "success"
    MigrationExecutor(connection).migrate([("core", "0089_job_owned_run_instructions")])
    report = resource_statistics(
        contract_id=contract.pk, source="hf", identifier="lab/Model"
    )
    assert {v["run_id"] for v in report["values"]} == {str(run.pk)}
    assert "123" in {v["value"] for v in report["values"]}


def test_scope_copy_mismatch_is_rejected_before_it_can_weaken_a_claim():
    from django.db import IntegrityError, transaction

    from core.collection_state import claim_job, fenced_run

    claim = claim_job(ready().pk)
    with (
        pytest.raises(IntegrityError, match="instruction copy mismatch"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE collection_runs SET scope = %s WHERE id = %s",
            ['{"wrong": true}', claim.run_id],
        )
    with fenced_run(claim) as (_, run):
        assert run.pk == claim.run_id


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.usefixtures("historical_schema")
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
    from tests.test_benchmark_download_persistence import configured, payload

    numeric = legacy_persist(configured(), "hf", "e" * 64, payload(9007199254740993))
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
@pytest.mark.usefixtures("historical_schema")
def test_archive_rejects_existing_job_copy_mismatch(helper):

    module = importlib.import_module(MIGRATION)
    owner = ready()
    CollectionRun.objects.create(
        job_id=owner.pk,
        source_id=owner.source_id,
        purpose=owner.purpose,
        scope={"wrong": True},
        status="success",
        completed_at=timezone.now(),
        ingestion_key="7" * 64,
    )
    with (
        connection.schema_editor() as editor,
        pytest.raises(ValueError, match="instruction mismatch"),
    ):
        getattr(module, helper)(apps, editor)


@pytest.mark.usefixtures("historical_schema")
def test_archives_cannot_become_ready_or_due():
    from core.collection_jobs import set_job_state
    from core.collection_scheduling import due_job
    from core.collection_state import claim_job

    module = importlib.import_module(MIGRATION)
    from core.models import DataSource

    run = CollectionRun.objects.create(
        source_id=DataSource.objects.get(pk="hf").pk,
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
@pytest.mark.usefixtures("historical_schema")
def test_archive_known_identity_collision_never_reassigns_or_overwrites(collision):
    from tests.test_collection_jobs import job

    module = importlib.import_module(MIGRATION)
    owner = job()
    run = CollectionRun.objects.create(
        source_id=owner.source_id,
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
@pytest.mark.usefixtures("historical_schema")
def test_archive_retry_after_committed_batch_preserves_ids(monkeypatch):
    from core.models import DataSource

    module = importlib.import_module(MIGRATION)
    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    first = CollectionRun.objects.create(
        id=uuid.UUID(int=1),
        source_id=DataSource.objects.get(pk="hf").pk,
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
