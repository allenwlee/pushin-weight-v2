"""Job instructions are immutable; execution is fenced by a database claim."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone

from core.collection_jobs import register_job, set_job_state
from core.collection_state import BusyJob, StaleClaim, claim_job, finish_run
from core.models import CollectionJob, CollectionRun, DataSource

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def job(*, purpose="catalog", mode="historical", key="test-job"):
    source, _ = DataSource.objects.get_or_create(
        id="github" if purpose == "catalog" else "x",
        defaults={"name": "Test source", "source_type": "social"},
    )
    source.enabled, source.adapter_key = True, "test-collector-v1"
    source.save()
    return register_job(
        job_key=key,
        source=source,
        purpose=purpose,
        operation="github_catalog" if purpose == "catalog" else "x_backfill",
        mode=mode,
        definition={
            "version": 1,
            "scope": {"owners": ["publisher"]},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 20, "bytes": 100000, "seconds": 60, "items": 100},
        },
    )


def ready(**kwargs):
    obj = job(**kwargs)
    return set_job_state(obj.pk, "ready")


def test_register_paused_and_idempotent():
    first = job()
    assert first.state == "paused"
    assert first.active_run_id is None
    assert job().pk == first.pk
    assert CollectionJob.objects.count() == 1
    assert CollectionRun.objects.count() == 0


def test_definition_change_requires_new_identity():
    obj = job()
    changed = {**obj.definition, "scope": {"owners": ["different"]}}
    with pytest.raises(ValueError, match="immutable"):
        register_job(
            job_key=obj.job_key,
            source=obj.source,
            purpose=obj.purpose,
            operation=obj.operation,
            mode=obj.mode,
            definition=changed,
        )


def test_only_one_additional_table_and_existing_names():
    assert CollectionJob._meta.db_table == "collection_jobs"
    assert {
        "collection_jobs",
        "collection_runs",
        "collection_scope_runs",
        "collection_observations",
        "metric_values",
    } <= set(connection.introspection.table_names())


def test_second_claim_cannot_replace_active_worker():
    obj = ready()
    first = claim_job(obj.pk)
    with pytest.raises(BusyJob):
        claim_job(obj.pk)
    obj.refresh_from_db()
    assert obj.active_run_id == first.run_id


def test_expired_catalog_claim_resumes_logical_run_and_fences_old_token():
    obj = ready()
    first = claim_job(obj.pk)
    CollectionRun.objects.filter(pk=first.run_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    second = claim_job(obj.pk)
    assert first.run_id == second.run_id
    assert first.lease_token != second.lease_token
    with pytest.raises(StaleClaim):
        finish_run(first, status="success")
    finish_run(second, status="success")


def test_partial_catalog_is_resumable_but_content_partial_is_terminal():
    catalog = ready()
    c = claim_job(catalog.pk)
    finish_run(c, status="partial", retry_at=timezone.now() + timedelta(minutes=1))
    run = CollectionRun.objects.get(pk=c.run_id)
    assert run.completed_at is None
    content = ready(purpose="content", key="content")
    c = claim_job(content.pk, manual_authorized=True)
    finish_run(c, status="partial")
    assert CollectionRun.objects.get(pk=c.run_id).completed_at is not None


def test_pause_fences_active_writer():
    obj = ready()
    claim = claim_job(obj.pk)
    set_job_state(obj.pk, "paused")
    with pytest.raises(StaleClaim):
        finish_run(claim, status="success")


@pytest.mark.django_db(transaction=True)
def test_two_database_connections_claim_once():
    obj = ready()

    def attempt():
        close_old_connections()
        try:
            return claim_job(obj.pk).run_id
        except BusyJob:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert CollectionRun.objects.count() == 1
