"""Cursor and evidence commit together; content continuation preserves attempts."""

import pytest
from django.utils import timezone

from core.collection_state import (
    checkpoint_scope,
    claim_job,
    finish_run,
    import_scope_checkpoints,
    record_rejection,
)
from core.models import CollectionObservation, CollectionRun, CollectionScopeRun
from tests.test_collection_jobs import ready

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_checkpoint_rolls_back_evidence_and_cursor():
    obj = ready()
    claim = claim_job(obj.pk)
    scope = checkpoint_scope(claim, scope_key="publisher", ownership={}, cursor="page2")

    def bad_write(run, scoped):
        CollectionObservation.objects.create(
            run=run,
            scope_run=scoped,
            resource_key="repo:1",
            source_identifier="1",
            source_subject_kind="repository",
            observation_key="a" * 64,
        )
        raise RuntimeError("simulated write failure")

    with pytest.raises(RuntimeError, match="simulated"):
        checkpoint_scope(
            claim, scope_key="publisher", ownership={}, cursor="page3", write=bad_write
        )
    scope.refresh_from_db()
    assert scope.cursor == "page2"
    assert CollectionObservation.objects.count() == 0


def test_backfill_continuation_copies_scopes_without_rewriting_old_attempt():
    obj = ready(purpose="content")
    first = claim_job(obj.pk, manual_authorized=True)
    old = checkpoint_scope(
        first, scope_key="slice1", ownership={}, cursor="next", outcome="complete"
    )
    checkpoint_scope(first, scope_key="slice2", ownership={}, cursor="pending")
    finish_run(first, status="partial")
    second = claim_job(obj.pk, manual_authorized=True, continue_from=first.run_id)
    assert second.run_id != first.run_id
    assert CollectionScopeRun.objects.filter(run_id=second.run_id).count() == 2
    old.refresh_from_db()
    assert old.run_id == first.run_id and old.cursor == "next"


def test_rejected_invocation_has_receipt_but_does_not_replace_claim():
    obj = ready(purpose="content")
    claim = claim_job(obj.pk, manual_authorized=True)
    rejected = record_rejection(
        obj.pk, invocation_id="busy-invocation", reason="live_lock_busy"
    )
    obj.refresh_from_db()
    assert obj.active_run_id == claim.run_id
    assert rejected.pk != claim.run_id and rejected.status == "aborted"
    assert rejected.lease_token is None and rejected.request_count == 0
    assert rejected.completed_at <= timezone.now()
    assert (
        record_rejection(
            obj.pk, invocation_id="busy-invocation", reason="live_lock_busy"
        ).pk
        == rejected.pk
    )


def test_scheduled_invocations_never_copy_previous_scopes():
    obj = ready(purpose="content", mode="manual")
    first = claim_job(obj.pk, manual_authorized=True)
    checkpoint_scope(first, scope_key="old-cycle", ownership={}, outcome="complete")
    finish_run(first, status="success")
    second = claim_job(obj.pk, manual_authorized=True)
    assert CollectionScopeRun.objects.filter(run_id=second.run_id).count() == 0


def test_pilot_import_preserves_unknown_attempt_clocks_without_fabricating_runs():
    obj = ready(purpose="content")
    claim = claim_job(obj.pk, manual_authorized=True)
    imported = import_scope_checkpoints(
        claim,
        definition_sha256=obj.definition_sha256,
        scopes=[{"scope_key": "slice", "ownership": {}, "cursor": "next"}],
        provenance={"format": "pilot-v1", "file_sha256": "a" * 64},
    )
    assert CollectionRun.objects.count() == 1
    assert imported.report["checkpoint_import"]["historical_attempt_timestamps"] is None
    assert imported.scopes.get().cursor == "next"
