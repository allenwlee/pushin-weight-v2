"""Known job facts have one owner; the remaining instruction is strictly bounded."""

import pytest
from django.db import IntegrityError, transaction

from core.collection_jobs import register_job
from core.collection_state import claim_job
from core.models import CollectionJob, CollectionJobTarget, DataSource

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def typed_job(*, key="typed", options=None):
    source, _ = DataSource.objects.get_or_create(
        id="arena",
        defaults={"name": "Arena", "source_type": "benchmark"},
    )
    return register_job(
        job_key=key,
        source=source,
        purpose="catalog",
        operation="model_inventory",
        mode="historical",
        definition={"version": 2, "options": options or {}},
        settings={
            "owner_kind": "source",
            "owner_account_id": None,
            "schedule_kind": "manual",
            "schedule_driver": "manual",
            "max_requests": 10,
            "max_bytes": 10000,
            "max_seconds": 30,
            "max_items": 100,
        },
        targets=[
            {
                "target_key": "missing-model",
                "target_kind": "product",
                "target_role": "selected",
                "resolution_state": "unresolved",
                "gap_reason": "unmatched_source_identifier",
                "native_identifier": "unmatched-model",
            }
        ],
    )


def test_typed_registration_seals_settings_and_relational_membership_once():
    job = typed_job()
    assert typed_job().pk == job.pk
    assert job.definition == {"version": 2, "options": {}}
    assert job.instruction_version == 2 and job.instructions_sealed_at
    assert job.owner_kind == "source" and job.max_requests == 10
    assert job.state == "paused" and job.authority_enabled is False
    assert CollectionJobTarget.objects.filter(job=job).count() == 1


def test_legacy_run_pointer_write_resolves_to_the_latest_actual_attempt():
    from core.collection_jobs import set_job_state

    job = typed_job()
    job.source.enabled, job.source.adapter_key = True, "arena-history-v1"
    job.source.save()
    set_job_state(job.pk, "ready")
    claim = claim_job(job.pk, manual_authorized=True)
    CollectionJob.objects.filter(pk=job.pk).update(last_attempt_attempt=None)
    CollectionJob.objects.filter(pk=job.pk).update(last_attempt_id=claim.run_id)
    job.refresh_from_db()
    assert job.last_attempt_id == claim.run_id
    assert job.last_attempt_attempt_id == claim.attempt_id


@pytest.mark.parametrize(
    "options",
    [
        {"brands": ["mistral"]},
        {"max_requests": 100},
        {"future_option": True},
        {"ingest_metadata": "yes"},
    ],
)
def test_instruction_document_rejects_entities_unknown_options_and_wrong_types(options):
    with pytest.raises(ValueError):
        typed_job(options=options)


def test_sealed_relational_settings_cannot_change_through_bulk_update():
    job = typed_job()
    with pytest.raises(IntegrityError, match="sealed"), transaction.atomic():
        type(job).objects.filter(pk=job.pk).update(max_requests=999)


def test_sealed_targets_cannot_change_through_bulk_update():
    job = typed_job()
    with pytest.raises(IntegrityError, match="sealed"), transaction.atomic():
        CollectionJobTarget.objects.filter(job=job).update(native_identifier="changed")


def test_recurring_typed_job_is_found_by_dispatch_only_after_explicit_authority(
    settings,
):
    from django.utils import timezone

    from core.collection_jobs import set_job_state
    from core.collection_scheduling import dispatch_due, take_collection_authority

    settings.BENCHMARK_COLLECTION_ENABLED = True
    source = typed_job().source
    source.enabled, source.adapter_key = True, "arena-history-v1"
    source.save()
    job = register_job(
        job_key="typed-daily",
        source=source,
        purpose="catalog",
        operation="model_inventory",
        mode="recurring",
        definition={"version": 2, "options": {}},
        targets=(),
        settings={
            "owner_kind": "source",
            "schedule_kind": "interval",
            "schedule_driver": "shared",
            "interval_seconds": 86400,
            "routine_role": "inventory",
            "max_requests": 2,
            "max_bytes": 10000,
            "max_seconds": 30,
            "max_items": 100,
        },
    )
    set_job_state(job.pk, "ready")
    now = timezone.now()
    before = dispatch_due(now=now)
    assert len(before) == 1 and before[0]["reason"] == "unclaimed_collection_role"
    take_collection_authority(job.pk)
    after = dispatch_due(now=now)
    assert after[0]["due"]
    job.refresh_from_db()
    source.refresh_from_db()
    assert job.authority_enabled
    assert "collection_role_authorities" not in source.metadata


def test_recurring_resume_keeps_current_slot_but_new_day_starts_new_collection(
    settings,
):
    from datetime import UTC, datetime, timedelta

    from core.collection_jobs import set_job_state
    from core.collection_scheduling import due_job, take_collection_authority
    from core.collection_state import claim_job, finish_run
    from core.models import CollectionRun

    settings.BENCHMARK_COLLECTION_ENABLED = True
    source = typed_job().source
    source.enabled, source.adapter_key = True, "arena-history-v1"
    source.save()
    job = register_job(
        job_key="typed-slots",
        source=source,
        purpose="catalog",
        operation="model_inventory",
        mode="recurring",
        definition={"version": 2, "options": {}},
        settings={
            "owner_kind": "source",
            "schedule_kind": "daily_utc",
            "schedule_driver": "shared",
            "daily_utc_hour": 10,
            "routine_role": "inventory",
            "max_requests": 2,
            "max_bytes": 10000,
            "max_seconds": 30,
            "max_items": 100,
        },
    )
    now = datetime(2026, 10, 20, 11, tzinfo=UTC)
    set_job_state(job.pk, "ready", now=now)
    take_collection_authority(job.pk)
    first = claim_job(job.pk, now=now)
    finish_run(first, status="partial", now=now)
    resumed = claim_job(job.pk, now=now + timedelta(minutes=15))
    assert resumed.run_id == first.run_id
    finish_run(resumed, status="partial", now=now + timedelta(minutes=15))
    tomorrow = now + timedelta(days=1)
    job.refresh_from_db()
    assert due_job(job, now=tomorrow)["slot"] == tomorrow.replace(hour=10).isoformat()
    next_day = claim_job(job.pk, now=tomorrow)
    assert next_day.run_id != first.run_id
    original = CollectionRun.objects.get(pk=first.run_id)
    latest = CollectionRun.objects.get(pk=next_day.run_id)
    assert original.scheduled_slot_at == now.replace(hour=10)
    assert original.status == "partial" and original.coverage_state == "partial"
    assert latest.scheduled_slot_at == tomorrow.replace(hour=10)
    assert original.attempts.count() == 2 and latest.attempts.count() == 1
