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
from tests.test_backfill_collection import ready_job

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_checkpoint_rolls_back_evidence_and_cursor():
    obj = ready_job()
    claim = claim_job(obj.pk, manual_authorized=True, typed=True)
    obj.refresh_from_db()
    assert obj.last_attempt_id == claim.run_id
    assert obj.last_attempt_attempt_id == claim.attempt_id
    unit = obj.scope["units"][0]
    scope = checkpoint_scope(claim, **{**unit, "cursor": "page2"}, typed=True)

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
            claim, **{**unit, "cursor": "page3"}, typed=True, write=bad_write
        )
    scope.refresh_from_db()
    assert scope.cursor == "page2"
    assert CollectionObservation.objects.count() == 0


def test_cursor_receipts_preserve_order_duplicates_and_reset_atomically():
    from core.models import CollectionRequest, CollectionScopeCursorReceipt

    obj = ready_job()
    claim = claim_job(obj.pk, manual_authorized=True, typed=True)
    unit = obj.scope["units"][0]
    scope = checkpoint_scope(
        claim, **{**unit, "cursor": "next", "cursor_history": ["first", "duplicate", "duplicate"]}, typed=True,
    )
    assert list(scope.cursor_receipts.order_by("position").values_list(
        "position", "cursor"
    )) == [(1, "first"), (2, "duplicate"), (3, "duplicate")]
    assert CollectionRequest.objects.count() == 0
    from core.collection_capture import archive_legacy

    archive = archive_legacy({"ownership": {}, "envelopes": [], "cursor_history": []})
    CollectionScopeRun.objects.filter(pk=scope.pk).update(legacy_archive=archive)
    scope.refresh_from_db()
    assert scope.recorded_cursors == ["first", "duplicate", "duplicate"]
    with pytest.raises(ValueError, match="cursor history"):
        checkpoint_scope(
            claim, **{**unit, "cursor": "bad", "cursor_history": [{"cursor": "unknown"}]}, typed=True,
        )
    scope.refresh_from_db()
    assert scope.cursor == "next"
    assert scope.recorded_cursors == ["first", "duplicate", "duplicate"]
    checkpoint_scope(claim, **{**unit, "cursor_history": []}, typed=True)
    assert not CollectionScopeCursorReceipt.objects.filter(scope_run=scope).exists()
    scope.refresh_from_db()
    assert scope.recorded_cursors == []


def test_backfill_continuation_copies_scopes_without_rewriting_old_attempt():
    other_unit = {
        "scope_key": "B1:other", "scope_kind": "x_query",
        "ownership": {"call_id": "B1", "query": "Qwen", "since_epoch": 1786233600, "until_epoch": 1786234500},
        "cursor": "pending", "cursor_history": [], "outcome": "pending", "enumeration_complete": False,
    }
    obj = ready_job(extra_units=[other_unit])
    first = claim_job(obj.pk, manual_authorized=True, typed=True)
    unit = obj.scope["units"][0]
    old = checkpoint_scope(
        first, **{**unit, "cursor": "next", "outcome": "complete", "cursor_history": ["first", "previous"]}, typed=True,
    )
    checkpoint_scope(first, **other_unit, typed=True)
    activity = CollectionScopeRun.objects.create(
        run_id=first.run_id, scope_kind="resource_group", scope_key="saved:detail",
        parent_scope=old, phase="detail", outcome="ok",
    )
    finish_run(first, status="partial", typed=True, physical_accounting_complete=True, request_count=0)
    second = claim_job(obj.pk, manual_authorized=True, continue_from=first.run_id, typed=True)
    assert second.run_id != first.run_id
    assert CollectionScopeRun.objects.filter(run_id=second.run_id, scope_kind="x_query").count() == 2
    activity.refresh_from_db()
    assert activity.run_id == first.run_id and activity.parent_scope_id == old.pk
    old.refresh_from_db()
    assert old.run_id == first.run_id and old.cursor == "next"
    assert CollectionScopeRun.objects.get(
        run_id=second.run_id, scope_key=unit["scope_key"]
    ).recorded_cursors == ["first", "previous"]


def test_rejected_invocation_has_receipt_but_does_not_replace_claim():
    obj = ready_job()
    claim = claim_job(obj.pk, manual_authorized=True, typed=True)
    rejected = record_rejection(
        obj.pk, invocation_id="busy-invocation", reason="live_lock_busy", typed=True
    )
    obj.refresh_from_db()
    assert obj.active_run_id == claim.run_id
    assert rejected.pk != claim.run_id and rejected.status == "aborted"
    assert rejected.lease_token is None and rejected.request_count == 0
    assert rejected.completed_at <= timezone.now()
    assert (
        record_rejection(
            obj.pk, invocation_id="busy-invocation", reason="live_lock_busy", typed=True
        ).pk
        == rejected.pk
    )


def test_new_invocations_never_copy_previous_scopes_without_continuation():
    obj = ready_job()
    first = claim_job(obj.pk, manual_authorized=True, typed=True)
    checkpoint_scope(first, **{**obj.scope["units"][0], "outcome": "complete"}, typed=True)
    finish_run(first, status="partial", typed=True, physical_accounting_complete=True, request_count=0)
    second = claim_job(obj.pk, manual_authorized=True, typed=True)
    assert not CollectionScopeRun.objects.filter(run_id=second.run_id, scope_kind="x_query").exists()
    run = CollectionRun.objects.get(pk=second.run_id)
    assert not hasattr(run, "invocations")
    assert run.attempts.count() == 1


def test_pilot_import_preserves_unknown_attempt_clocks_without_fabricating_runs():
    obj = ready_job()
    claim = claim_job(obj.pk, manual_authorized=True, typed=True)
    imported = import_scope_checkpoints(
        claim,
        definition_sha256=obj.definition_sha256,
        scopes=[{**obj.scope["units"][0], "cursor": "next"}],
        provenance={"format": "pilot-v1", "file_sha256": "a" * 64},
        typed=True,
    )
    assert CollectionRun.objects.count() == 1
    from core.collection_capture import read_document

    marker = imported.scopes.get(scope_kind="x_checkpoint_import")
    assert read_document(marker.legacy_archive)["historical_attempt_timestamps"] is None
    assert imported.scopes.get(scope_kind="x_query").cursor == "next"
