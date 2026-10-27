"""Typed X backfill admission keeps checkpoint and rejection evidence."""

import pytest
from django.db import IntegrityError, transaction

from core.collection_capture import read_document, run_report_document
from core.collection_state import (
    checkpoint_scope,
    claim_job,
    finish_run,
    import_scope_checkpoints,
    record_rejection,
)
from core.models import CollectionRun, CollectionScopeRun
from tests.test_backfill_collection import ready_job

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_typed_checkpoint_import_is_idempotent_and_does_not_write_run_report():
    job = ready_job()
    claim = claim_job(job.pk, invocation_id="typed-import", manual_authorized=True)
    provenance = {"format": "pilot-v1", "file_sha256": "a" * 64}
    for _ in range(2):
        import_scope_checkpoints(
            claim, definition_sha256=job.definition_sha256,
            scopes=job.scope["units"], provenance=provenance, typed=True,
        )
    run = job.runs.get(pk=claim.run_id)
    assert not hasattr(run, "report")
    query = run.scopes.get(scope_kind="x_query")
    assert query.job_target_id is not None and not hasattr(query, "envelopes")
    marker = run.scopes.get(scope_kind="x_checkpoint_import")
    assert marker.phase == "typed-import-v1"
    evidence = read_document(marker.legacy_archive)
    assert evidence["provenance"] == provenance
    assert evidence["historical_attempt_timestamps"] is None
    assert CollectionScopeRun.objects.filter(run=run).count() == 2


def test_typed_rejection_keeps_original_invocation_without_mutable_report():
    job = ready_job()
    rejected = record_rejection(
        job.pk, invocation_id="rejected-invocation", reason="live_lock_busy",
        report={"waited_seconds": 7}, typed=True,
    )
    assert not hasattr(rejected, "report")
    assert rejected.error_code == "live_lock_busy"
    attempt = rejected.attempts.get()
    assert attempt.source_invocation_id == "rejected-invocation"
    assert attempt.outcome == "aborted" and attempt.stop_reason == "live_lock_busy"
    assert run_report_document(rejected)["waited_seconds"] == 7
    assert record_rejection(
        job.pk, invocation_id="rejected-invocation", reason="live_lock_busy",
        typed=True,
    ).pk == rejected.pk


def test_archive_import_result_run_cannot_be_attached_to_an_x_query():
    job = ready_job()
    claim = claim_job(job.pk, invocation_id="scope-guard", manual_authorized=True)
    import_scope_checkpoints(
        claim, definition_sha256=job.definition_sha256,
        scopes=job.scope["units"], provenance={"format": "fixture"}, typed=True,
    )
    query = CollectionScopeRun.objects.get(run_id=claim.run_id, scope_kind="x_query")
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionScopeRun.objects.filter(pk=query.pk).update(result_run_id=claim.run_id)


@pytest.mark.parametrize("operation", ["checkpoint", "finish", "reject", "import"])
def test_detached_legacy_document_apis_refuse_before_changing_claim(operation):
    job = ready_job()
    claim = claim_job(job.pk, manual_authorized=True, typed=True)
    run = CollectionRun.objects.get(pk=claim.run_id)
    before = (run.status, run.lease_token, run.completed_at, run.scopes.count())
    actions = {
        "checkpoint": lambda: checkpoint_scope(claim, **job.scope["units"][0]),
        "finish": lambda: finish_run(claim, status="success"),
        "reject": lambda: record_rejection(
            job.pk, invocation_id="legacy-rejection", reason="busy",
        ),
        "import": lambda: import_scope_checkpoints(
            claim, definition_sha256=job.definition_sha256,
            scopes=job.scope["units"], provenance={"format": "fixture"},
        ),
    }
    with pytest.raises(ValueError, match="legacy collection document API is unavailable"):
        actions[operation]()
    run.refresh_from_db()
    job.refresh_from_db()
    assert (run.status, run.lease_token, run.completed_at, run.scopes.count()) == before
    assert job.active_run_id == run.pk and job.last_attempt_id == run.pk
    assert job.runs.count() == 1
    assert run.attempts.get().outcome == "running"


def test_unprojected_legacy_campaign_refuses_claim_without_reserving_execution():
    from core.collection_jobs import set_job_state
    from tests.test_data_source_backfill import legacy_campaign_job

    job = set_job_state(legacy_campaign_job().pk, "ready")
    assert job.campaign_id is None
    with pytest.raises(ValueError, match="legacy collection document API is unavailable"):
        claim_job(job.pk)
    job.refresh_from_db()
    assert job.active_run_id is None and job.last_attempt_id is None
    assert not job.runs.exists()
