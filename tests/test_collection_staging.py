"""Precommit source appearances, preserved unknowns, and typed-only recovery."""

import hashlib
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.db.models.expressions import RawSQL

from core.collection_capture import begin_request, finish_request
from core.collection_staging import (
    account_staging_response,
    adopt_retry_state,
    adopt_staging_receipt,
    ensure_staging_bytes,
    staging_receipt,
    write_staging_receipt,
)
from core.collection_state import claim_job, fenced_run, import_scope_checkpoints
from core.models import (
    CollectionAttempt,
    CollectionObservationInput,
    CollectionRequest,
    CollectionRun,
    CollectionScopeRun,
)
from monitor.backfill_retry import RetryControl
from tests.test_backfill_staging import staged_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def execution(monkeypatch):
    job = staged_job(monkeypatch, 1)
    claim = claim_job(job.pk, invocation_id="typed-staging", manual_authorized=True)
    import_scope_checkpoints(claim, definition_sha256=job.definition_sha256,
                             scopes=job.scope["units"], provenance={"format": "fixture"})
    scope = CollectionScopeRun.objects.get(run_id=claim.run_id, scope_kind="x_query")
    return claim, scope


def received(execution, ids, *, save_metadata=True):
    claim, scope = execution
    with fenced_run(claim):
        request = begin_request(CollectionAttempt.objects.get(pk=claim.attempt_id), scope,
                                endpoint_url="https://api.twitterapi.io/twitter/tweet/advanced_search",
                                request_category="x_backfill_staging")
        request = finish_request(request, outcome="received", http_status=200, response_bytes=123)
        metadata = {"raw_count": len(ids), "returned_ids": ids, "body_sha256": "a" * 64, "body_lost": False}
        if save_metadata:
            request = write_staging_receipt(request, metadata)
    return request, metadata


def test_received_sequence_is_durable_before_posts_or_page_commit(execution):
    request, metadata = received(execution, ["same", "same", None, ""])
    assert staging_receipt(request) == metadata
    rows = list(request.received_appearances.order_by("receipt_ordinal"))
    assert [row.source_identifier_is_null for row in rows] == [False, False, True, False]
    assert all(row.scope_run_id is None and row.run_id == execution[0].run_id for row in rows)
    assert not CollectionObservationInput.objects.filter(observation__in=rows).exists()
    assert not execution[1].child_scopes.exists()
    assert request.archive_id is None and request.selection_accounted is False
    second, _ = received(execution, ["same"])
    assert second.received_appearances.get().receipt_ordinal == 0


def test_empty_and_unknown_replies_are_distinct(execution):
    empty, _ = received(execution, [])
    assert staging_receipt(empty)["returned_ids"] == []
    claim, scope = execution
    with fenced_run(claim):
        unknown = begin_request(CollectionAttempt.objects.get(pk=claim.attempt_id), scope,
                                endpoint_url="https://api.twitterapi.io/twitter/tweet/advanced_search",
                                request_category="x_backfill_staging")
        unknown = finish_request(unknown, outcome="transport_error", error_code="Timeout")
        unknown = write_staging_receipt(unknown, {"raw_count": None, "returned_ids": None,
                                                 "body_sha256": None, "body_lost": False})
    assert staging_receipt(unknown)["returned_ids"] is None
    assert not unknown.received_appearances.exists()
    assert unknown.selection_accounted is False and unknown.response_bytes is None


def test_receipt_and_selection_accounting_are_atomic_and_idempotent(execution):
    claim, _ = execution
    with fenced_run(claim) as (_, run):
        ensure_staging_bytes(run)
    request, _ = received(execution, ["one", "one"])
    response = {"raw_results": 2, "response_bytes": 123}
    with pytest.raises(RuntimeError), fenced_run(claim) as (_, run):
        assert account_staging_response(run, request, response)
        raise RuntimeError("fixture after accounting before commit")
    request.refresh_from_db()
    assert request.selection_accounted is False
    with fenced_run(claim) as (_, run):
        assert account_staging_response(run, request, response)
        assert not account_staging_response(run, request, response)
    run.refresh_from_db()
    assert run.selected_count == 2 and run.physical_bytes_received == 123
    assert "prefetch_accounted_requests" not in run.report


def test_adopts_exact_legacy_state_then_operates_after_report_cleared(execution):
    claim, _ = execution
    request, metadata = received(execution, ["id", "id"], save_metadata=False)
    state = RetryControl(phase="open", failures=[100.123456789, 99.5, 100.123456789],
                         cooldowns=2, until=400.123456789, successes=0)
    with fenced_run(claim) as (_, run):
        run.report = {"staging_retry": state.snapshot(), "staging_responses": {str(request.pk): metadata},
                      "prefetch_accounted_requests": [str(request.pk)], "response_bytes": 123}
        run.selected_count = 2
        run.save(update_fields=["report", "selected_count"])
        assert adopt_retry_state(run).snapshot() == state.snapshot()
        assert ensure_staging_bytes(run) == 123
        request = adopt_staging_receipt(request)
        assert request.selection_accounted is True
        run.report = {}
        run.save(update_fields=["report"])
    run.refresh_from_db()
    assert RetryControl.from_run(run).snapshot() == state.snapshot()
    assert staging_receipt(request) == metadata
    with fenced_run(claim) as (_, run):
        assert not account_staging_response(run, request, {"raw_results": 2, "response_bytes": 123})


@pytest.mark.parametrize("change", [
    {"staging_retry_version": 2}, {"staging_retry_phase": 4}, {"staging_retry_cooldowns": 4},
    {"staging_retry_successes": 5}, {"staging_retry_until": float("inf")},
    {"staging_retry_until": float("nan")}, {"staging_retry_until": -1},
    {"staging_retry_failures": [1, 2, 3, 4]}, {"staging_retry_failures": [None]},
    {"staging_retry_failures": [-1]}, {"staging_retry_failures": [float("inf")]},
    {"staging_retry_failures": [float("nan")]}, {"staging_retry_phase": None},
])
def test_retry_constraints_cover_bulk_writers(execution, change):
    claim, _ = execution
    with fenced_run(claim) as (_, run):
        RetryControl().save(run)
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.filter(pk=claim.run_id).update(**change)


@pytest.mark.parametrize("array_literal", ["[0:2]={NaN,1,2}", "[0:1]={1,2}", "[2:3]={1,2}"])
def test_retry_time_check_rejects_nonstandard_array_bounds(execution, array_literal):
    claim, _ = execution
    with fenced_run(claim) as (_, run):
        RetryControl().save(run)
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.filter(pk=claim.run_id).update(
            staging_retry_failures=RawSQL("%s::double precision[]", (array_literal,)),
        )


@pytest.mark.parametrize(("array_literal", "expected"), [
    ("{}", []), ("{1,2,3}", [1, 2, 3]), ("[1:3]={3.5,1.5,3.5}", [3.5, 1.5, 3.5]),
])
def test_retry_time_check_accepts_standard_empty_and_ordered_arrays(execution, array_literal, expected):
    claim, _ = execution
    with fenced_run(claim) as (_, run):
        RetryControl().save(run)
        CollectionRun.objects.filter(pk=run.pk).update(
            staging_retry_failures=RawSQL("%s::double precision[]", (array_literal,)),
        )
        run.refresh_from_db()
        assert RetryControl.from_run(run).failures == expected


@pytest.mark.parametrize("change", [{"response_sha256": b"short"}, {"raw_count": -1},
                                  {"body_lost": None}, {"selection_accounted": None}])
def test_request_receipt_constraints_cover_bulk_writers(execution, change):
    request, _ = received(execution, [])
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRequest.objects.filter(pk=request.pk).update(**change)


def test_request_appearance_owner_and_unique_position(execution):
    request, _ = received(execution, ["a", "b"])
    appearance = request.received_appearances.order_by("receipt_ordinal").first()
    for change in ({"observation_kind": None}, {"scope_run_id": request.scope_run_id},
                   {"receipt_ordinal": 1}, {"request": None}):
        with pytest.raises(IntegrityError), transaction.atomic():
            request.received_appearances.filter(pk=appearance.pk).update(**change)
    run = CollectionRun.objects.get(pk=execution[0].run_id)
    run.pk = uuid4()
    run.ingestion_key = hashlib.sha256(str(run.pk).encode()).hexdigest()
    run.save(force_insert=True)
    with pytest.raises(IntegrityError, match="original run"), transaction.atomic():
        request.received_appearances.filter(pk=appearance.pk).update(run=run)


def test_request_appearances_are_outside_retiring_column_archive_sweep(execution):
    from core.collection_storage_migration import (
        archive_legacy_batch,
        stale_legacy_archive_count,
    )

    request, _ = received(execution, ["a"])
    assert archive_legacy_batch("collection_observations").archived == 0
    assert archive_legacy_batch("collection_observations", repair_stale=True).archived == 0
    assert stale_legacy_archive_count("collection_observations") == 0
    assert request.received_appearances.get().legacy_archive_id is None
