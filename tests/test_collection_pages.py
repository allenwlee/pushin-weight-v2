"""Real PostgreSQL constraints and typed-only checkpoint/continuation evidence."""

from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, transaction

from core.collection_pages import (
    adopt_unprojected_page_receipts,
    append_page_receipt,
    copy_continuation_scopes,
    page_receipt_parity_batch,
    page_receipts,
    project_page_receipts_batch,
)
from core.collection_state import claim_job, import_scope_checkpoints
from core.models import (
    CollectionObservation,
    CollectionRequest,
    CollectionRun,
    CollectionScopeRun,
    Post,
)
from core.provider_batches import record_post_membership
from tests.test_backfill_collection import ready_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def scope():
    job = ready_job()
    claim = claim_job(job.pk, invocation_id="typed-page-fixture", manual_authorized=True)
    import_scope_checkpoints(claim, definition_sha256=job.definition_sha256,
                             scopes=job.scope["units"], provenance={"format": "fixture"})
    return CollectionScopeRun.objects.get(run_id=claim.run_id, scope_kind="x_query")


def test_ordered_grouped_checkpoint_preserves_duplicates_and_null_vs_empty_ids(scope):
    Post.objects.create(tweet_id="kept", text="captured")
    with transaction.atomic():
        record_post_membership(scope.run, scope, ["kept"])
    observed = datetime(2026, 8, 9, 0, 1, tzinfo=UTC).isoformat()
    envelope = {
        "observed_at": observed, "pages_received": 3, "raw_count": 4,
        "collection_drained": True, "reason": "no_next_page", "post_ids": ["kept"],
        "received_post_ids": ["kept", "kept", None, ""],
        "exclusions": [
            {"appearance": 1, "post_id": "kept", "reason": "duplicate_native_id"},
            {"appearance": 2, "post_id": None, "reason": "missing_native_id"},
            {"appearance": 3, "post_id": "", "reason": "missing_native_id"},
        ],
        "relevancy_degraded": ["timeout", "timeout"],
    }
    child = append_page_receipt(scope, envelope, cursor="known-checkpoint")
    assert child.pages_received == 3 and child.cursor == "known-checkpoint"
    assert CollectionRequest.objects.count() == 0
    scope.envelopes = [{"deliberately": "unusable legacy state"}]
    scope.save(update_fields=["envelopes"])
    restored = page_receipts(scope)[0]
    for key, value in envelope.items():
        assert restored[key] == value
    assert child.legacy_archive_id is not None
    appearances = child.observations.filter(observation_kind="x_page_appearance")
    assert appearances.count() == 4
    assert not appearances.filter(source_subject_kind="post").exists()
    assert CollectionObservation.objects.filter(source_subject_kind="post").count() == 1


def test_unknown_old_timestamp_and_empty_page_remain_distinct(scope):
    scope.envelopes = [{"post_ids": [], "collection_drained": True}]
    scope.save(update_fields=["envelopes"])
    assert project_page_receipts_batch(after_id=scope.pk - 1).inserted == 1
    assert project_page_receipts_batch(after_id=scope.pk - 1).inserted == 0
    assert page_receipt_parity_batch(after_id=scope.pk - 1).mismatched == 0
    append_page_receipt(scope, {"post_ids": [], "received_post_ids": [], "raw_count": 0,
                               "pages_received": 1, "collection_drained": True})
    old, empty = page_receipts(scope)
    assert "observed_at" not in old and "raw_count" not in old and "received_post_ids" not in old
    assert empty["raw_count"] == 0 and empty["received_post_ids"] == []
    assert scope.child_scopes.count() == 2 and not CollectionRequest.objects.exists()
    assert page_receipt_parity_batch(after_id=scope.pk - 1).mismatched == 1


def test_legacy_writer_adoption_preserves_membership_set_and_exact_archive_sequence(scope):
    from core.collection_capture import archive_legacy, read_document

    for identifier in ("a", "b"):
        Post.objects.create(tweet_id=identifier, text="captured")
    with transaction.atomic():
        record_post_membership(scope.run, scope, ["a", "b"])
    envelope = {"post_ids": ["b", "a", "b"], "collection_drained": True}
    scope.envelopes = [envelope]
    scope.legacy_archive = archive_legacy({"envelopes": [envelope], "ownership": scope.ownership})
    scope.save(update_fields=["envelopes", "legacy_archive"])
    with transaction.atomic():
        adopt_unprojected_page_receipts(scope)
    child = scope.child_scopes.get()
    assert child.legacy_archive_id == scope.legacy_archive_id
    assert read_document(child.legacy_archive)["envelopes"][0]["post_ids"] == ["b", "a", "b"]
    assert set(page_receipts(scope)[0]["post_ids"]) == {"a", "b"}


def test_unresolved_legacy_membership_fails_before_replacing_old_envelopes(scope):
    scope.envelopes = [{"post_ids": ["missing"]}]
    scope.save(update_fields=["envelopes"])
    with pytest.raises(ValueError, match="membership is missing"), transaction.atomic():
        adopt_unprojected_page_receipts(scope)
    scope.refresh_from_db()
    assert scope.envelopes == [{"post_ids": ["missing"]}]
    assert not scope.child_scopes.exists()


def test_historical_page_can_reference_post_credited_to_another_query(scope):
    Post.objects.create(tweet_id="shared-query-post", text="captured")
    other = CollectionScopeRun.objects.create(
        run=scope.run, scope_kind="x_query", scope_key="other-query",
        ownership=scope.ownership,
    )
    with transaction.atomic():
        record_post_membership(scope.run, other, ["shared-query-post"])
    scope.envelopes = [{"post_ids": ["shared-query-post"], "collection_drained": True}]
    scope.save(update_fields=["envelopes"])
    result = project_page_receipts_batch(after_id=scope.pk - 1, batch_size=1)
    assert result.scanned == result.inserted == 1
    assert page_receipt_parity_batch(after_id=scope.pk - 1, batch_size=1).mismatched == 0
    marker = scope.child_scopes.get(scope_kind="x_page_checkpoint").observations.get(
        observation_kind="x_page_checkpoint",
    )
    assert marker.inputs.get(input_role="retained_post").input_observation.scope_run_id == other.pk


def test_first_writer_rejects_changed_or_extra_typed_receipts_but_allows_cleared_json(scope):
    envelope = {"post_ids": [], "received_post_ids": [], "raw_count": 0, "collection_drained": False}
    child = append_page_receipt(scope, envelope)
    scope.envelopes = [envelope]
    CollectionScopeRun.objects.filter(pk=child.pk).update(enumeration_complete=True)
    with pytest.raises(ValueError, match="differs from its saved checkpoint"):
        adopt_unprojected_page_receipts(scope)
    CollectionScopeRun.objects.filter(pk=child.pk).update(enumeration_complete=False)
    append_page_receipt(scope, envelope)
    with pytest.raises(ValueError, match="exceed the supplied checkpoint"):
        adopt_unprojected_page_receipts(scope)
    scope.envelopes = []
    adopt_unprojected_page_receipts(scope)
    assert len(page_receipts(scope)) == 2


def test_retiring_column_archive_sweeps_preserve_typed_page_source_archive(scope):
    from core.collection_storage_migration import (
        archive_legacy_batch,
        stale_legacy_archive_count,
    )

    child = append_page_receipt(scope, {"received_post_ids": [None], "raw_count": 1,
                                       "exclusions": [{"appearance": 0, "post_id": None, "reason": "missing_native_id"}],
                                       "relevancy_degraded": ["timeout"]})
    marker = child.observations.get(observation_kind="x_page_checkpoint")
    original_archive = child.legacy_archive_id
    assert archive_legacy_batch("collection_scope_runs").archived == 1
    assert archive_legacy_batch("collection_scope_runs", repair_stale=True).archived == 0
    assert archive_legacy_batch("collection_observations").archived == 0
    assert archive_legacy_batch("collection_observations", repair_stale=True).archived == 0
    assert stale_legacy_archive_count("collection_scope_runs") == 0
    assert stale_legacy_archive_count("collection_observations") == 0
    scope.refresh_from_db()
    child.refresh_from_db()
    marker.refresh_from_db()
    assert scope.legacy_archive_id is not None
    assert child.legacy_archive_id == marker.legacy_archive_id == original_archive
    assert not child.observations.exclude(pk=marker.pk).filter(legacy_archive__isnull=False).exists()


def test_continuation_copies_typed_receipts_and_remaps_sibling_scopes(scope):
    from core.collection_capture import archive_legacy

    observed = datetime(2026, 8, 9, 0, 1, tzinfo=UTC).isoformat()
    request = CollectionRequest.objects.create(
        attempt=scope.run.attempts.get(), scope_run=scope, ordinal=1,
        transport_outcome="received", http_status=200, archive=archive_legacy({"tweets": []}),
    )
    append_page_receipt(scope, {"observed_at": observed, "pages_received": 2, "raw_count": 2,
                               "prefetch_request_id": str(request.pk),
                               "prefetch_request_run_id": str(scope.run_id), "prefetch_replayed": False,
                               "received_post_ids": [None, None], "post_ids": [],
                               "exclusions": [{"appearance": i, "post_id": None, "reason": "missing_native_id"}
                                              for i in range(2)], "collection_drained": False}, cursor="next")
    numeric_parent = CollectionScopeRun.objects.create(run=scope.run, scope_kind="numeric_projection",
                                                       scope_key="projection", ownership={})
    resource = scope.child_scopes.get().observations.get(observation_kind="x_page_checkpoint")
    CollectionScopeRun.objects.create(run=scope.run, scope_kind="projection_input", scope_key="input",
                                      parent_scope=numeric_parent, prerequisite_scope=scope,
                                      resource_observation=resource, ownership={})
    CollectionScopeRun.objects.filter(run=scope.run).update(envelopes=[])
    previous = scope.run
    run = CollectionRun.objects.get(pk=previous.pk)
    run.pk = None
    from uuid import uuid4
    run.id = uuid4()
    run.ingestion_key = "f" * 64
    run.save(force_insert=True)
    with transaction.atomic():
        copy_continuation_scopes(previous, run)
    copied = run.scopes.get(scope_kind="x_query")
    assert page_receipts(copied) == page_receipts(scope)
    assert copied.child_scopes.get().cursor == "next"
    input_scope = run.scopes.get(scope_kind="projection_input")
    assert input_scope.parent_scope.run_id == run.pk and input_scope.prerequisite_scope_id == copied.pk
    assert input_scope.resource_observation_id == resource.pk
    assert run.scopes.filter(scope_kind="x_query").count() == 1
    assert CollectionRequest.objects.get().scope_run_id == scope.pk
    assert copied.request_uses.get().request_id == request.pk
    copied_child = copied.child_scopes.get()
    assert copied_child.request_uses.get().observed_at.isoformat() == observed
    assert copied_child.request_uses.get().request_id == request.pk
    assert not copied_child.observations.filter(inputs__input_request=request).exists()
    assert scope.child_scopes.get().observations.filter(inputs__input_request=request).count() == 3


@pytest.mark.parametrize("change", [{"receipt_ordinal": None}, {"receipt_ordinal": -1},
                                  {"source_identifier_is_null": None}, {"source_identifier": "invented"}])
def test_appearance_constraints_reject_bulk_update(scope, change):
    child = append_page_receipt(scope, {"received_post_ids": [None], "raw_count": 1,
                                       "exclusions": [{"appearance": 0, "post_id": None, "reason": "missing_native_id"}]})
    with pytest.raises(IntegrityError), transaction.atomic():
        child.observations.filter(observation_kind="x_page_appearance").update(**change)


def test_checkpoint_constraints_reject_missing_parent_duplicate_order_and_bad_http(scope):
    child = append_page_receipt(scope, {"received_post_ids": [], "raw_count": 0})
    for change in ({"parent_scope": None}, {"checkpoint_ordinal": -1}, {"raw_count_known": None},
                   {"response_status_code": 600}):
        with pytest.raises(IntegrityError), transaction.atomic():
            CollectionScopeRun.objects.filter(pk=child.pk).update(**change)
    second = append_page_receipt(scope, {"received_post_ids": [], "raw_count": 0})
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionScopeRun.objects.filter(pk=second.pk).update(checkpoint_ordinal=0)
