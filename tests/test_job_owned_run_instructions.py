"""PostgreSQL cutover keeps evidence, old readers and lifecycle enforcement."""

import uuid

import pytest
from django.core.exceptions import FieldDoesNotExist, FieldError
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.collection_state import claim_direct_run, register_direct_job
from core.models import CollectionJob, CollectionRun
from tests.collection_fixtures import evidence_job
from tests.test_benchmark_download_persistence import configured, payload

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def instructions(purpose):
    return evidence_job(
        source_id="x" if purpose == "content" else "hf",
        purpose=purpose,
        contract_id=configured().pk if purpose == "metric" else None,
        scope={"retained": [False, 0]},
    )


@pytest.mark.parametrize("purpose", ["metric", "catalog", "content"])
@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "running",
        "partial",
        "interrupted",
        "success",
        "failed",
        "aborted",
        "invalid",
    ],
)
@pytest.mark.parametrize("completed", [False, True])
def test_job_backed_lifecycle_matrix(purpose, status, completed):
    job = instructions(purpose)
    if purpose == "catalog":
        allowed = status in (
            {"success", "failed", "aborted"}
            if completed
            else {"pending", "running", "partial", "interrupted"}
        )
    else:
        allowed = status in (
            {"success", "partial", "failed", "aborted"} if completed else {"running"}
        )
    values = {
        "job": job,
        "status": status,
        "ingestion_key": "a" * 64,
        "completed_at": timezone.now() if completed else None,
        "lease_token": uuid.uuid4(),
        "lease_expires_at": timezone.now(),
    }
    if allowed:
        run = CollectionRun.objects.create(**values)
        assert run.purpose == purpose
    else:
        with pytest.raises(IntegrityError), transaction.atomic():
            CollectionRun.objects.create(**values)


@pytest.mark.parametrize(
    "purpose,status",
    [
        ("metric", "success"),
        ("metric", "running"),
        ("catalog", "running"),
        ("content", "running"),
    ],
)
def test_required_leases_are_still_enforced(purpose, status):
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.create(
            job=instructions(purpose),
            status=status,
            ingestion_key="a" * 64,
            completed_at=timezone.now() if status == "success" else None,
        )


def test_job_is_mandatory_and_removed_fields_are_not_queryable():
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.create(status="pending", ingestion_key="a" * 64)
    for name in ("source", "purpose", "contract", "scope"):
        with pytest.raises(FieldDoesNotExist):
            CollectionRun._meta.get_field(name)
        with pytest.raises(FieldError):
            CollectionRun.objects.filter(**{name: None}).exists()
    call_command("normalize_collection_run_jobs", verbosity=0)


@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", uuid.UUID(int=123)),
        ("source_id", "x"),
        ("purpose", "content"),
        ("contract_id", uuid.UUID(int=234)),
        ("operation", "other"),
        ("mode", "historical"),
        ("job_key", "changed"),
        ("definition", {"scope": {"changed": True}}),
        ("definition_sha256", "f" * 64),
    ],
)
def test_instructions_are_immutable_even_before_first_reference(linked, field, value):
    job = instructions("catalog")
    if linked:
        CollectionRun.objects.create(job=job, status="pending", ingestion_key="a" * 64)
    with (
        pytest.raises(IntegrityError, match="instructions are immutable"),
        transaction.atomic(),
    ):
        CollectionJob.objects.filter(pk=job.pk).update(**{field: value})
    CollectionJob.objects.filter(pk=job.pk).update(
        state="paused", next_due_at=None, active_run=None
    )
    job.refresh_from_db()
    assert job.state == "paused"


@pytest.mark.usefixtures("collection_instruction_bridge")
def test_phase1_models_can_read_and_save_phase2_inserts_for_all_purposes():
    historical = (
        MigrationExecutor(connection)
        .loader.project_state([("core", "0088_archive_run_instructions")])
        .apps
    )
    OldRun = historical.get_model("core", "CollectionRun")
    for index, purpose in enumerate(("catalog", "content", "metric")):
        job = instructions(purpose)
        run = CollectionRun.objects.create(
            job=job,
            status="success",
            completed_at=timezone.now(),
            lease_expires_at=timezone.now(),
            ingestion_key=f"{index + 1:x}" * 64,
        )
        old = OldRun.objects.get(pk=run.pk)
        assert (old.source_id, old.purpose, old.contract_id, old.scope) == (
            job.source_id,
            job.purpose,
            job.contract_id,
            job.definition["scope"],
        )
        old.report = {"phase1": "saved"}
        old.save()
        run.refresh_from_db()
        assert run.report == old.report
        # The preceding writer still supplies valid physical copies on INSERT.
        previous = OldRun.objects.create(
            job_id=job.pk,
            source_id=job.source_id,
            purpose=job.purpose,
            contract_id=job.contract_id,
            scope=job.definition["scope"],
            status="success",
            completed_at=timezone.now(),
            lease_expires_at=timezone.now(),
            ingestion_key=f"{index + 4:x}" * 64,
        )
        assert (
            CollectionRun.objects.get(pk=previous.pk).scope == job.definition["scope"]
        )


@pytest.mark.parametrize(
    "column,value",
    [
        ("source_id", "x"),
        ("purpose", "content"),
        ("contract_id", uuid.UUID(int=123)),
        ("scope", '{"wrong": true}'),
    ],
)
@pytest.mark.usefixtures("collection_instruction_bridge")
def test_legacy_updates_cannot_change_instruction_copies(column, value):
    run = CollectionRun.objects.create(
        job=instructions("catalog"), status="pending", ingestion_key="a" * 64
    )
    with (
        pytest.raises(IntegrityError, match="instruction copy mismatch"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"UPDATE collection_runs SET {column} = %s WHERE id = %s", [value, run.pk]
        )
    run.refresh_from_db()
    assert run.scope == {"retained": [False, 0]}


def test_compatibility_views_keep_old_order_and_base_columns_writable():
    from core.benchmark_metric_store import persist_source

    run = persist_source(configured(), "hf", "a" * 64, payload())
    expected = [
        "id",
        "batch_id",
        "ingestion_key",
        "status",
        "started_at",
        "lease_expires_at",
        "observed_at",
        "completed_at",
        "source_as_of",
        "source_url",
        "request_params",
        "source_metadata",
        "request_count",
        "selected_count",
        "success_count",
        "payload_sha256",
        "raw_payload",
        "error_code",
        "contract_id",
        "source_id",
        "purpose",
        "scope",
        "invocations",
        "report",
        "updated_at",
    ]
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM metric_collection_runs WHERE id = %s", [run.pk])
        assert [column.name for column in cursor.description] == expected
        cursor.execute(
            "UPDATE metric_collection_runs SET report = %s WHERE id = %s",
            ['{"view": true}', run.pk],
        )
        assert cursor.rowcount == 1
        cursor.execute(
            "UPDATE metric_observations SET source_metadata = %s WHERE run_id = %s",
            ['{"view": true}', run.pk],
        )
        assert cursor.rowcount == 1
        cursor.execute("""
            SELECT DISTINCT a.attname FROM pg_depend d
            JOIN pg_rewrite rw ON rw.oid = d.objid
            JOIN pg_class v ON v.oid = rw.ev_class
            JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
            WHERE v.relname IN ('metric_collection_runs', 'metric_observations')
              AND d.refobjid = 'collection_runs'::regclass
              AND a.attname IN ('source_id', 'purpose', 'contract_id', 'scope')
        """)
        assert cursor.fetchall() == []
    for alias in ("source_id", "purpose", "contract_id", "scope"):
        with (
            pytest.raises(DatabaseError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                f"UPDATE metric_collection_runs SET {alias} = {alias} WHERE id = %s",
                [run.pk],
            )
    run.refresh_from_db()
    assert run.report == {"view": True}


def test_stale_direct_object_cannot_replace_a_new_job_identity():
    first = instructions("catalog")
    run = CollectionRun.objects.create(
        job=first, status="pending", ingestion_key="a" * 64
    )
    second = register_direct_job(
        source_id="hf",
        purpose="catalog",
        scope={"other": True},
        driver="execute_catalog",
        limits={"fixture": True},
    )
    CollectionRun.objects.filter(pk=run.pk).update(job=second)
    with pytest.raises(ValueError, match="changed while acquiring ownership"):
        claim_direct_run(
            run, driver="execute_catalog", seconds=60, limits={"seconds": 60}
        )
    assert CollectionRun.objects.get(pk=run.pk).job_id == second.pk


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_cutover_preserves_all_evidence_and_physical_compatibility_copies():
    from tests.test_run_job_normalization import previous_module

    target = [("core", "0088_archive_run_instructions")]
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    old = executor.loader.project_state(target).apps
    contract = configured()
    previous = previous_module("benchmark_metric_store", old)
    historic_contract = old.get_model("core", "MetricCollectionContract").objects.get(
        pk=contract.pk
    )
    numeric = previous.persist_source(
        historic_contract, "hf", "a" * 64, payload(9007199254740993)
    )
    OldRun = old.get_model("core", "CollectionRun")
    catalog = OldRun.objects.create(
        source_id="hf",
        purpose="catalog",
        scope={"unknown": None, "false": False},
        status="partial",
        ingestion_key="b" * 64,
        raw_payload={"keep": [0, False]},
        report={"original": True},
        invocations=[{"requests": 2}],
    )
    scope = old.get_model("core", "CollectionScopeRun").objects.create(
        run=catalog,
        scope_key="publisher",
        cursor="saved",
        ownership={"keep": False},
        envelopes=[{"status": "ok"}],
    )
    old.get_model("core", "CollectionObservation").objects.create(
        run=catalog,
        scope_run=scope,
        source_identifier="publisher/model",
        source_subject_kind="repository",
        observation_key="d" * 64,
        listing={"keep": [False, 0]},
    )
    OldRun.objects.create(
        source_id="x",
        purpose="content",
        scope={"original": [1]},
        status="aborted",
        ingestion_key="c" * 64,
        completed_at=timezone.now(),
    )
    linked_job = register_direct_job(
        source_id="hf",
        purpose="catalog",
        scope={"already": "linked"},
        driver="execute_catalog",
        limits={"fixture": True},
    )
    OldRun.objects.create(
        job_id=linked_job.pk,
        source_id="hf",
        purpose="catalog",
        scope=linked_job.definition["scope"],
        status="pending",
        ingestion_key="e" * 64,
    )
    before = list(OldRun.objects.order_by("pk").values())
    evidence = {
        name: list(old.get_model("core", name).objects.order_by("pk").values())
        for name in (
            "CollectionScopeRun",
            "CollectionObservation",
            "MetricValue",
            "SourceMetric",
        )
    }
    # The command must select historical apps while mandatory linkage is absent.
    call_command("normalize_collection_run_jobs", verbosity=0)
    first_jobs = dict(OldRun.objects.values_list("pk", "job_id"))
    MigrationExecutor(connection).migrate([("core", "0089_job_owned_run_instructions")])
    after = list(OldRun.objects.order_by("pk").values())
    for row, expected in zip(after, before, strict=True):
        assert row["job_id"] == first_jobs[row["id"]]
        row["job_id"] = expected["job_id"]
        assert row == expected
    for name, rows in evidence.items():
        assert list(old.get_model("core", name).objects.order_by("pk").values()) == rows
    assert (
        CollectionRun.objects.get(pk=numeric.pk).job.contract_id == numeric.contract_id
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'collection_runs' AND column_name IN ('source_id', 'purpose', 'contract_id', 'scope')"
        )
        assert len(cursor.fetchall()) == 4
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_metric_run_outcome'"
        )
        assert "(job_id, status, completed_at)" in cursor.fetchone()[0]
    call_command("normalize_collection_run_jobs", verbosity=0)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("isolated_migration_database")
def test_cutover_rejects_running_jobless_source_attempt_without_inventing_facts():
    target = [("core", "0088_archive_run_instructions")]
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    old = executor.loader.project_state(target).apps
    Run = old.get_model("core", "CollectionRun")
    run = Run.objects.create(
        source_id="hf", purpose="catalog", status="running", ingestion_key="a" * 64
    )
    with pytest.raises(ValueError, match="must finish"):
        MigrationExecutor(connection).migrate(
            [("core", "0089_job_owned_run_instructions")]
        )
    run.refresh_from_db()
    assert (run.status, run.completed_at, run.job_id) == ("running", None, None)
    assert old.get_model("core", "CollectionJob").objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("collection_instruction_bridge")
def test_legacy_run_update_does_not_acquire_a_job_row_lock():
    import psycopg

    job = instructions("catalog")
    run = CollectionRun.objects.create(
        job=job, status="pending", ingestion_key="a" * 64
    )
    historical = (
        MigrationExecutor(connection)
        .loader.project_state([("core", "0088_archive_run_instructions")])
        .apps
    )
    legacy = historical.get_model("core", "CollectionRun").objects.get(pk=run.pk)
    with psycopg.connect(**connection.get_connection_params()) as holder:
        holder.execute(
            "SELECT id FROM collection_jobs WHERE id = %s FOR UPDATE", [job.pk]
        )
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '500ms'")
            legacy.report = {"no_lock_inversion": True}
            legacy.save()
        holder.rollback()
    assert CollectionRun.objects.get(pk=run.pk).report == {"no_lock_inversion": True}


@pytest.mark.django_db(transaction=True)
def test_instruction_mutation_is_rejected_during_uncommitted_first_reference():
    import psycopg

    job = instructions("catalog")
    with transaction.atomic():
        run = CollectionRun.objects.create(
            job=job, status="pending", ingestion_key="a" * 64
        )
        with psycopg.connect(
            **connection.get_connection_params(), autocommit=True
        ) as other:
            assert (
                other.execute(
                    "SELECT count(*) FROM collection_runs WHERE job_id = %s", [job.pk]
                ).fetchone()[0]
                == 0
            )
            with pytest.raises(
                psycopg.errors.CheckViolation, match="instructions are immutable"
            ):
                other.execute(
                    "UPDATE collection_jobs SET definition = %s WHERE id = %s",
                    ['{"scope": {"changed": true}}', job.pk],
                )
    assert CollectionRun.objects.get(pk=run.pk).scope == job.definition["scope"]
