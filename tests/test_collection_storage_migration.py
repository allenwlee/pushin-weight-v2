"""The collection archive copy is exact, repeatable, and detects live changes."""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from core.collection_capture import archive_document, read_document
from core.collection_storage_migration import (
    archive_legacy_batch,
    archive_metric_payload_batch,
    product_match_target_mismatch_counts,
    project_arena_publication_batch,
    project_benchmark_provenance_batch,
    project_metric_request_coordinates_batch,
    project_product_match_targets_batch,
    project_run_continuations_batch,
    project_run_ingestion_mode,
    project_run_invocations_batch,
    project_scope_bounds_batch,
    project_x_query_targets_batch,
    provenance_mismatch_counts,
    scope_bounds_mismatch_counts,
    stale_legacy_archive_count,
    x_query_target_mismatch_counts,
)
from core.models import CollectionObservation, CollectionScopeRun
from tests.test_collection_relational_storage import execution


def test_arena_publication_copy_rebuilds_an_empty_cohort_without_duplicate_rows():
    from core.benchmark_metric_store import persist_source
    from core.measurement_taxonomy import digest
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    run = persist_source(
        contract,
        "arena",
        digest("rg6-empty-arena-publication"),
        {
            "status": "ok",
            "config": "text_style_control",
            "coverage": "publication_window",
            "rows": [],
        },
        source_metadata={"publication_dates": ["2026-09-27"]},
    )
    markers = CollectionObservation.objects.filter(
        run=run, observation_kind="publication_marker"
    )
    assert markers.count() == 1
    assert project_arena_publication_batch(verify_only=True).inserted == 0
    markers.delete()
    with pytest.raises(ValueError, match="incomplete"):
        project_arena_publication_batch(verify_only=True)
    assert project_arena_publication_batch().inserted == 1
    assert project_arena_publication_batch().inserted == 0
    assert project_arena_publication_batch(verify_only=True).scanned == 1


@pytest.mark.django_db(transaction=True)
def test_new_arena_publication_marker_needs_no_retiring_json_columns():
    from core.benchmark_metric_store import persist_source, record_arena_publications
    from core.measurement_taxonomy import digest
    from tests.test_benchmark_download_persistence import provider_contract
    from tests.test_hf_catalog_retirement import denied_retirement_columns

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    run = persist_source(
        contract, "arena", digest("rg6-arena-typed-publication"),
        {"status": "ok", "config": "text_style_control", "rows": [],
         "coverage": "publication_window"},
    )
    with denied_retirement_columns():
        assert record_arena_publications(run, ["2026-09-29"]) == 1
        marker = CollectionObservation.objects.get(
            run=run, observation_kind="publication_marker",
            published_date=datetime(2026, 9, 29, tzinfo=UTC).date(),
        )
        assert marker.publication_complete is True


def test_metric_time_provenance_copy_is_bounded_and_preserves_typed_only_values():
    from core.benchmark_metric_store import persist_source
    from core.collection_corrections import TIME_BASIS_FIELDS
    from core.collection_storage_migration import project_metric_time_provenance_batch
    from core.models import MetricValue
    from tests.test_benchmark_download_persistence import configured, payload

    contract = configured()
    legacy = persist_source(contract, "hf", "7" * 64, payload())
    typed = persist_source(contract, "hf", "8" * 64, payload())
    rows = MetricValue.objects.filter(observation__run__in=[legacy, typed]).order_by("pk")
    before = list(rows.values())
    first_id = before[0]["id"]
    MetricValue.objects.filter(observation__run=legacy).update(
        **{field: None for field in TIME_BASIS_FIELDS}
    )
    typed.observations.update(source_metadata={})
    with pytest.raises(ValueError, match="not projected"):
        project_metric_time_provenance_batch(
            after_id=first_id - 1, batch_size=1, verify_only=True
        )
    first = project_metric_time_provenance_batch(after_id=first_id - 1, batch_size=1)
    assert (first.last_id, first.scanned, first.updated) == (first_id, 1, 1)
    assert project_metric_time_provenance_batch(
        after_id=first_id - 1, batch_size=1
    ).updated == 0
    rest = project_metric_time_provenance_batch(after_id=first_id, batch_size=10)
    assert rest.scanned == len(before) - 1
    assert list(rows.values()) == before
    assert project_metric_time_provenance_batch(
        after_id=first_id - 1, batch_size=10, verify_only=True
    ).updated == 0


def test_metric_time_provenance_copy_uses_latest_correction_and_refuses_drift():
    from datetime import timedelta

    from core.benchmark_metric_store import persist_source
    from core.collection_corrections import (
        TIME_BASIS_FIELDS,
        TIME_STATE_FIELDS,
        record_timing_correction,
    )
    from core.collection_storage_migration import project_metric_time_provenance_batch
    from core.models import MetricValue
    from tests.test_benchmark_download_persistence import configured, payload

    run = persist_source(configured(), "hf", "9" * 64, payload())
    value = MetricValue.objects.filter(observation__run=run).order_by("pk").first()
    state = {
        field: (value.source_timezone_reference_id or "unknown")
        if field == "source_timezone" else getattr(value, field)
        for field in (*TIME_STATE_FIELDS, *TIME_BASIS_FIELDS)
    }
    revised = {**state, "window_end_basis": "later_review"}
    correction = record_timing_correction(
        value, before=state, after=revised, policy="fixture-review-v1", reason="review",
    )
    MetricValue.objects.filter(pk=value.pk).update(
        **{field: None for field in TIME_BASIS_FIELDS}
    )
    assert project_metric_time_provenance_batch(
        after_id=value.pk - 1, batch_size=1
    ).updated == 1
    value.refresh_from_db()
    assert value.window_end_basis == "later_review"
    assert value.corrections.get().pk == correction.pk
    MetricValue.objects.filter(pk=value.pk).update(window_end_basis="conflicting_review")
    with pytest.raises(ValueError, match="conflicts"):
        project_metric_time_provenance_batch(after_id=value.pk - 1, batch_size=1)
    value.refresh_from_db()
    assert value.window_end_basis == "conflicting_review"
    MetricValue.objects.filter(pk=value.pk).update(
        window_end_basis="later_review",
        window_end_at=value.window_end_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="after-image conflicts"):
        project_metric_time_provenance_batch(after_id=value.pk - 1, batch_size=1)


@pytest.mark.parametrize("basis", [[], {"unknowns": []}, {"basis": "x" * 129}])
def test_metric_time_provenance_copy_refuses_invalid_retained_explanations(basis):
    from core.benchmark_metric_store import persist_source
    from core.collection_corrections import TIME_BASIS_FIELDS
    from core.collection_storage_migration import project_metric_time_provenance_batch
    from core.models import MetricValue
    from tests.test_benchmark_download_persistence import configured, payload

    run = persist_source(configured(), "hf", "b" * 64, payload())
    value = MetricValue.objects.filter(observation__run=run).order_by("pk").first()
    observation = value.observation
    observation.source_metadata["reported_time"]["metrics"][value.source_metric.metric_key] = basis
    observation.save(update_fields=["source_metadata"])
    MetricValue.objects.filter(pk=value.pk).update(**dict.fromkeys(TIME_BASIS_FIELDS))
    before = MetricValue.objects.filter(pk=value.pk).values().get()
    with pytest.raises(ValueError, match="(must be an object|is invalid)"):
        project_metric_time_provenance_batch(after_id=value.pk - 1, batch_size=1)
    assert MetricValue.objects.filter(pk=value.pk).values().get() == before


def test_metric_payload_archive_copy_preserves_legacy_payload_and_detects_drift():
    from core.benchmark_metric_store import persist_source
    from core.measurement_taxonomy import digest
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract("arena", ["rating"])
    run = persist_source(
        contract, "arena", digest("rg6-archive-payload"),
        {"status": "ok", "config": "text_style_control", "rows": [],
         "coverage": "publication_window"},
    )
    assert run.raw_payload is None
    assert read_document(run.payload_archive)["coverage"] == "publication_window"
    run.raw_payload = read_document(run.payload_archive)
    run.payload_archive = None
    run.save(update_fields=["raw_payload", "payload_archive"])
    with pytest.raises(ValueError, match="missing"):
        archive_metric_payload_batch(verify_only=True)
    assert archive_metric_payload_batch().archived == 1
    assert archive_metric_payload_batch().archived == 0
    assert archive_metric_payload_batch(verify_only=True).scanned == 1
    run.refresh_from_db()
    assert read_document(run.payload_archive) == run.raw_payload
    run.raw_payload = {**run.raw_payload, "status": "changed"}
    run.save(update_fields=["raw_payload"])
    with pytest.raises(ValueError, match="digest differs"):
        archive_metric_payload_batch(verify_only=True)


def test_historical_run_continuation_copy_is_repeatable_and_rejects_changed_owner():
    from core.measurement_taxonomy import digest
    from core.models import CollectionRun

    previous, _, _ = execution()
    successor = CollectionRun.objects.create(
        job=previous.job,
        ingestion_key=digest("rg6-historical-continuation"),
        status="success",
        completed_at=datetime(2026, 10, 26, 3, tzinfo=UTC),
        report={"continued_from": str(previous.pk)},
    )
    with pytest.raises(ValueError, match="not projected"):
        project_run_continuations_batch(verify_only=True)
    assert project_run_continuations_batch().updated == 1
    assert project_run_continuations_batch().updated == 0
    assert project_run_continuations_batch(verify_only=True).scanned == 1
    successor.refresh_from_db()
    assert successor.continuation_of_id == previous.pk
    previous.continuation_of = successor
    previous.save(update_fields=["continuation_of"])
    with pytest.raises(ValueError, match="forms a cycle"):
        project_run_continuations_batch(verify_only=True)
    previous.continuation_of = None
    previous.save(update_fields=["continuation_of"])
    successor.report = {"continued_from": str(successor.pk)}
    successor.save(update_fields=["report"])
    with pytest.raises(ValueError, match="different run owner"):
        project_run_continuations_batch(verify_only=True)


def test_metric_request_dates_copy_into_existing_scope_fields():
    from core.benchmark_metric_store import persist_source
    from core.measurement_taxonomy import digest
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    run = persist_source(
        contract, "arena", digest("rg6-metric-request-window"),
        {
            "status": "ok", "config": "text_style_control",
            "coverage": "publication_window", "rows": [],
        },
        source_metadata={"publication_dates": ["2026-09-27"]},
        request_params={"start_date": "2026-09-27", "end_date": "2026-09-28"},
    )
    scope = run.scopes.get(scope_kind="metric_fetch", scope_key="source")
    scope.delete()
    run.request_params = {"start_date": "2026-09-27", "end_date": "2026-09-28"}
    run.save(update_fields=["request_params", "updated_at"])
    with pytest.raises(ValueError, match="not fully projected"):
        project_metric_request_coordinates_batch(verify_only=True)
    assert project_metric_request_coordinates_batch().updated == 1
    scope = run.scopes.get(scope_kind="metric_fetch", scope_key="source")
    assert scope.requested_start_date.isoformat() == "2026-09-27"
    assert scope.requested_end_date.isoformat() == "2026-09-28"
    assert project_metric_request_coordinates_batch().updated == 0
    assert project_metric_request_coordinates_batch(verify_only=True).scanned == 1
    scope.requested_end_date = datetime(2026, 9, 29, tzinfo=UTC).date()
    scope.save(update_fields=["requested_end_date"])
    with pytest.raises(ValueError, match="option changed"):
        project_metric_request_coordinates_batch()

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_historical_invocations_get_distinct_attempts_without_invented_outcomes():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.measurement_taxonomy import digest
    from core.models import CollectionRun
    from tests.test_collection_jobs import ready

    job = ready()
    run = CollectionRun.objects.create(
        job=job,
        ingestion_key=digest("rg6-invocation-copy"),
        status="success",
        completed_at=datetime(2026, 10, 20, 12, tzinfo=UTC),
        invocations=[
            {"invocation_id": "first", "started_at": "2026-10-20T10:00:00+00:00"},
            {"invocation_id": "second", "started_at": "2026-10-20T11:00:00+00:00"},
        ],
    )
    with pytest.raises(ValueError, match="missing historical attempt"):
        project_run_invocations_batch(verify_only=True)

    with CaptureQueriesContext(connection) as queries:
        result = project_run_invocations_batch()
    assert all('"raw_payload"' not in query["sql"] for query in queries)
    assert all('"definition"' not in query["sql"] for query in queries)
    assert result.inserted == 2
    attempts = list(run.attempts.order_by("ordinal"))
    assert [attempt.ordinal for attempt in attempts] == [1, 2]
    assert [attempt.outcome for attempt in attempts] == ["legacy_unknown"] * 2
    assert all(attempt.finished_at is None and not attempt.accounting_complete for attempt in attempts)
    assert attempts[0].attempt_key == digest({"job": str(job.pk), "invocation": "first"})
    assert [attempt.source_invocation_id for attempt in attempts] == ["first", "second"]
    assert project_run_invocations_batch().inserted == 0
    assert project_run_invocations_batch(verify_only=True).inserted == 0

    attempts[0].source_invocation_id = None
    attempts[0].save(update_fields=["source_invocation_id"])
    with pytest.raises(ValueError, match="invocation identity is not projected"):
        project_run_invocations_batch(verify_only=True)
    assert project_run_invocations_batch().updated == 1
    attempts[0].refresh_from_db()
    assert attempts[0].source_invocation_id == "first"
    attempts[0].source_invocation_id = "different"
    attempts[0].save(update_fields=["source_invocation_id"])
    with pytest.raises(ValueError, match="invocation identity differs"):
        project_run_invocations_batch()
    attempts[0].source_invocation_id = "first"
    attempts[0].save(update_fields=["source_invocation_id"])

    attempts[0].started_at = datetime(2026, 10, 20, 9, tzinfo=UTC)
    attempts[0].save(update_fields=["started_at"])
    with pytest.raises(ValueError, match="historical attempt differs"):
        project_run_invocations_batch(verify_only=True)


def test_scope_cursor_copy_preserves_order_duplicates_and_refuses_conflicts():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.collection_storage_migration import project_scope_cursors_batch
    from core.models import CollectionScopeCursorReceipt, CollectionScopeRun

    _, _, scope = execution()
    CollectionScopeRun.objects.filter(pk=scope.pk).update(
        cursor_history=["first", "same", "same", "next"],
    )
    with pytest.raises(ValueError, match="not projected"):
        project_scope_cursors_batch(after_id=scope.pk - 1, batch_size=1, verify_only=True)
    with CaptureQueriesContext(connection) as queries:
        result = project_scope_cursors_batch(after_id=scope.pk - 1, batch_size=1)
    assert all('"envelopes"' not in query["sql"] for query in queries)
    assert (result.last_id, result.scanned, result.updated) == (scope.pk, 1, 1)
    assert list(scope.cursor_receipts.order_by("position").values_list(
        "position", "cursor"
    )) == [(1, "first"), (2, "same"), (3, "same"), (4, "next")]
    assert project_scope_cursors_batch().updated == 0
    assert project_scope_cursors_batch(verify_only=True).scanned == 1
    assert project_scope_cursors_batch(after_id=scope.pk).scanned == 0
    assert not scope.requests.exists()
    CollectionScopeCursorReceipt.objects.filter(scope_run=scope, position=2).update(
        cursor="conflict",
    )
    with pytest.raises(ValueError, match="differs"):
        project_scope_cursors_batch()


@pytest.mark.parametrize("history", [[{"page": 1}], [None], "cursor"])
def test_scope_cursor_copy_rejects_unsupported_legacy_evidence(history):
    from core.collection_storage_migration import project_scope_cursors_batch
    from core.models import CollectionScopeRun

    _, _, scope = execution()
    CollectionScopeRun.objects.filter(pk=scope.pk).update(cursor_history=history)
    with pytest.raises(ValueError, match="cursor history"):
        project_scope_cursors_batch()
    assert not scope.cursor_receipts.exists()


def test_invocation_copy_accepts_existing_attempt_with_non_uuid_identity():
    from core.collection_state import claim_job
    from tests.test_collection_jobs import ready

    job = ready()
    claim = claim_job(job.pk, invocation_id="operator-run-1")
    assert job.runs.get(pk=claim.run_id).attempts.get().source_invocation_id == "operator-run-1"
    assert project_run_invocations_batch(verify_only=True).inserted == 0
    assert project_run_invocations_batch().inserted == 0
    assert job.runs.get(pk=claim.run_id).attempts.get().outcome == "running"


def test_archived_catalog_invocations_keep_known_usage_and_finish_clocks():
    from core.measurement_taxonomy import digest
    from core.models import CollectionAttempt, CollectionJob, CollectionRun
    from tests.test_collection_jobs import ready

    source = ready().source
    definition = {
        "version": 1, "scope": {},
        "execution": {"executable": False},
    }
    job = CollectionJob.objects.create(
        job_key="rg6-archived-invocations", source=source,
        purpose="catalog", operation="archived_run", mode="manual",
        definition=definition, definition_sha256=digest(definition),
        state="completed",
    )
    run = CollectionRun.objects.create(
        job=job,
        ingestion_key=digest("rg6-archived-invocations"),
        status="success",
        completed_at=datetime(2026, 10, 20, 12, tzinfo=UTC),
        invocations=[
            {
                "started_at": "2026-10-20T10:00:00+00:00",
                "ended_at": "2026-10-20T10:30:00+00:00",
                "outcome": "partial", "requests": 4, "retries": 1,
                "max_requests": 10, "max_models": None,
                "max_response_bytes": 1024, "max_total_bytes": 2048,
                "last_request": {"endpoint": "models"},
            },
            {
                "started_at": "2026-10-20T11:00:00+00:00",
                "ended_at": "2026-10-20T12:00:00+00:00",
                "outcome": "complete", "requests": 5, "retries": 0,
                "max_requests": 2**63 - 1, "max_models": 20,
                "last_request": {"endpoint": "models"},
            },
        ],
    )
    CollectionAttempt.objects.create(
        run=run, attempt_key=digest([str(run.pk), "lease-token"]),
        ordinal=1, started_at=datetime(2026, 10, 20, 10, tzinfo=UTC),
        finished_at=datetime(2026, 10, 20, 10, 30, tzinfo=UTC),
        outcome="partial", actual_requests=4, reserved_requests=10,
    )
    with pytest.raises(ValueError, match="not projected"):
        project_run_invocations_batch(verify_only=True)
    copied = project_run_invocations_batch()
    assert (copied.inserted, copied.updated) == (1, 1)
    first, second = run.attempts.order_by("ordinal")
    assert first.source_invocation_id is None and second.source_invocation_id is None
    assert [first.outcome, second.outcome] == ["partial", "success"]
    assert [first.actual_requests, second.actual_requests] == [4, 5]
    assert [first.reserved_requests, second.reserved_requests] == [10, None]
    assert first.retry_count == 1
    assert first.response_byte_limit == 1024
    assert first.reserved_bytes == 2048
    assert [first.effective_items, second.effective_items] == [None, 20]
    assert first.finished_at == datetime(2026, 10, 20, 10, 30, tzinfo=UTC)
    assert project_run_invocations_batch(verify_only=True).inserted == 0
    CollectionAttempt.objects.create(
        run=run, attempt_key=digest([str(run.pk), "pre-receipt-crash"]),
        ordinal=3, outcome="interrupted",
    )
    assert project_run_invocations_batch(verify_only=True).inserted == 0
    assert archive_legacy_batch("collection_runs").archived == 1
    run.refresh_from_db()
    assert read_document(run.legacy_archive)["invocations"][1]["max_requests"] == 2**63 - 1


def test_x_scope_bounds_copy_rechecks_older_rows_and_rejects_invalid_epochs():
    _, _, scope = execution()
    scope.scope_kind = "x_query"
    scope.ownership = {
        "call_id": "B1", "query": "test query",
        "since_epoch": 1783809000, "until_epoch": 1783809300,
    }
    scope.save(update_fields=["scope_kind", "ownership"])
    assert scope_bounds_mismatch_counts() == (0, 1)
    assert project_scope_bounds_batch(after_id=scope.pk - 1).updated == 1
    scope.refresh_from_db()
    assert scope.requested_start_at == datetime.fromtimestamp(1783809000, UTC)
    assert scope.requested_end_at == datetime.fromtimestamp(1783809300, UTC)
    assert scope_bounds_mismatch_counts() == (0, 0)

    scope.ownership["until_epoch"] = 1783809600
    scope.save(update_fields=["ownership"])
    assert scope_bounds_mismatch_counts() == (0, 1)
    assert project_scope_bounds_batch(after_id=scope.pk - 1).updated == 1
    assert scope_bounds_mismatch_counts() == (0, 0)

    scope.ownership["since_epoch"] = "bad"
    scope.save(update_fields=["ownership"])
    assert scope_bounds_mismatch_counts() == (1, 0)
    with pytest.raises(ValueError, match="invalid historical request bounds"):
        project_scope_bounds_batch(after_id=scope.pk - 1)


def test_x_query_target_copy_preserves_frozen_query_and_detects_pin_drift():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _, _, scope = execution()
    scope.scope_kind = "x_query"
    scope.ownership = {
        "call_id": "B1", "query": "exact source query",
        "since_epoch": 1783809000, "until_epoch": 1783809300,
    }
    scope.save(update_fields=["scope_kind", "ownership"])
    assert x_query_target_mismatch_counts() == (0, 1)
    with CaptureQueriesContext(connection) as queries:
        result = project_x_query_targets_batch(after_id=scope.pk - 1)
    owner_selects = [
        query["sql"] for query in queries
        if 'FROM "collection_scope_runs"' in query["sql"]
        and 'JOIN "collection_jobs"' in query["sql"]
    ]
    assert owner_selects and all('"definition"' not in sql for sql in owner_selects)
    assert result.scanned == result.updated == 1
    scope.refresh_from_db()
    assert scope.job_target.search_query.query_text == "exact source query"
    assert scope.job_target.target_role == "B1"
    assert scope.job_target.requested_start_at == datetime.fromtimestamp(1783809000, UTC)
    assert x_query_target_mismatch_counts() == (0, 0)
    assert project_x_query_targets_batch(after_id=scope.pk - 1).updated == 0

    scope.job_target.target_role = "A"
    scope.job_target.save(update_fields=["target_role"])
    assert x_query_target_mismatch_counts() == (0, 1)
    with pytest.raises(ValueError, match="differs from scope ownership"):
        project_x_query_targets_batch(after_id=scope.pk - 1)


def test_x_prefetch_reads_pinned_query_when_legacy_ownership_is_stale():
    from core.collection_state import x_scope_ownership
    from monitor.backfill_prefetch import _params

    _, _, scope = execution()
    scope.scope_kind = "x_query"
    scope.ownership = {
        "call_id": "B1", "query": "original query",
        "since_epoch": 1783809000, "until_epoch": 1783809300,
    }
    scope.save(update_fields=["scope_kind", "ownership"])
    project_x_query_targets_batch(after_id=scope.pk - 1)
    scope.refresh_from_db()
    scope.ownership = {**scope.ownership, "query": "stale query"}
    scope.save(update_fields=["ownership"])

    assert x_scope_ownership(scope)["query"] == "original query"
    assert "original query" in _params(scope)["query"]
    assert "stale query" not in _params(scope)["query"]
    assert x_query_target_mismatch_counts() == (0, 1)


def test_recurring_x_query_target_keeps_query_fixed_and_window_on_scope():
    from core.collection_jobs import register_job
    from core.collection_state import ensure_x_query_target, x_scope_ownership
    from core.models import CollectionRun, CollectionScopeRun, SearchQuery
    from tests.test_collection_jobs import ready

    source = ready(purpose="content").source
    query = SearchQuery.objects.create(
        query_id="x-cycle:" + hashlib.sha256(b"fixed query").hexdigest(),
        query_text="fixed query",
    )
    job = register_job(
        job_key="rg6-scheduled-query-pin",
        source=source, purpose="content", operation="x_cycle", mode="recurring",
        definition={"version": 2, "options": {"adapter": "twitterapi"}},
        settings={
            "owner_kind": "source", "schedule_kind": "interval",
            "schedule_driver": "external_render_cron", "interval_seconds": 900,
            "max_requests": 100, "max_bytes": 1000000,
            "max_seconds": 300, "max_items": 2000,
        },
        targets=[{
            "target_key": "B1", "target_kind": "query", "target_role": "B1",
            "resolution_state": "resolved", "search_query_id": query.pk,
        }],
    )
    run = CollectionRun.objects.create(
        job=job, ingestion_key="b" * 64, status="success",
        completed_at=datetime(2026, 10, 25, 12, tzinfo=UTC),
    )
    lower = datetime(2026, 10, 25, 10, tzinfo=UTC)
    upper = datetime(2026, 10, 25, 11, tzinfo=UTC)
    target = ensure_x_query_target(
        job, "B1", query_text="fixed query", call_id="B1",
        start_at=lower, end_at=upper,
    )
    scope = CollectionScopeRun.objects.create(
        run=run, scope_kind="x_query", scope_key="B1", job_target=target,
        ownership={}, requested_start_at=lower, requested_end_at=upper,
    )
    assert scope_bounds_mismatch_counts() == (0, 0)
    assert project_scope_bounds_batch(after_id=scope.pk - 1).updated == 0
    assert project_x_query_targets_batch(after_id=scope.pk - 1).updated == 0
    assert x_query_target_mismatch_counts() == (0, 0)
    assert target.requested_start_at is None and target.requested_end_at is None
    assert x_scope_ownership(scope) == {
        "call_id": "B1", "query": "fixed query",
        "since_epoch": int(lower.timestamp()), "until_epoch": int(upper.timestamp()),
    }
    next_lower = datetime(2026, 10, 25, 11, tzinfo=UTC)
    next_upper = datetime(2026, 10, 25, 12, tzinfo=UTC)
    next_run = CollectionRun.objects.create(
        job=job, ingestion_key="c" * 64, status="success",
        completed_at=datetime(2026, 10, 25, 13, tzinfo=UTC),
    )
    next_scope = CollectionScopeRun.objects.create(
        run=next_run, scope_kind="x_query", scope_key="B1", job_target=target,
        ownership={}, requested_start_at=next_lower, requested_end_at=next_upper,
    )
    assert scope_bounds_mismatch_counts() == (0, 0)
    assert x_query_target_mismatch_counts() == (0, 0)
    assert ensure_x_query_target(
        job, "B1", query_text="fixed query", call_id="B1",
        start_at=next_lower, end_at=next_upper,
    ).pk == target.pk
    assert x_scope_ownership(next_scope)["since_epoch"] == int(next_lower.timestamp())
    with pytest.raises(ValueError, match="frozen X query target differs"):
        ensure_x_query_target(
            job, "B1", query_text="changed query", call_id="B1",
            start_at=lower, end_at=upper,
        )
    next_scope.job_target = None
    with pytest.raises(ValueError, match="requires a typed query target"):
        x_scope_ownership(next_scope)


def test_scheduled_cycle_registration_reuses_plan_and_rotates_changed_query():
    from core.x_cycle_lineage import register_scheduled_cycle

    calls = [
        SimpleNamespace(call_id="A", query_string="from:publisher"),
        SimpleNamespace(call_id="B1", query_string="product release"),
    ]
    limits = {"requests": 100, "bytes": 1000000, "seconds": 300, "items": 2000}
    first = register_scheduled_cycle(calls, limits=limits)
    repeated = register_scheduled_cycle(calls, limits=limits)
    assert first.pk == repeated.pk
    assert first.state == "paused"
    assert list(first.targets.order_by("ordinal").values_list(
        "target_key", "search_query__query_text", "requested_start_at",
    )) == [
        ("A", "from:publisher", None), ("B1", "product release", None),
    ]
    changed = register_scheduled_cycle([
        calls[0], SimpleNamespace(call_id="B1", query_string="new product release"),
    ], limits=limits)
    assert changed.pk != first.pk
    assert changed.job_key != first.job_key


def test_scheduled_scope_records_post_without_claiming_backfill_enrichment():
    from core.models import (
        CollectionObservation,
        CollectionObservationInput,
        CollectionScopeRun,
        Post,
        PostEnrichmentState,
    )
    from core.x_cycle_lineage import ScheduledCycleLineage

    call = SimpleNamespace(call_id="B1", query_string="product release")
    limits = {"requests": 100, "bytes": 1000000, "seconds": 300, "items": 2000}
    lineage = ScheduledCycleLineage.start(
        [call], limits=limits, invocation_id="scheduled-lineage-test",
    )
    scope_id = lineage.begin_call(call, since_epoch=1783809000, until_epoch=1783809300)
    api = SimpleNamespace(
        base_url="https://api.twitterapi.io", on_exchange_start=None,
        on_exchange_finish=None,
    )
    lineage.bind_api(api, scope_id)
    request = api.on_exchange_start(
        "/twitter/tweet/advanced_search",
        {"query": "product release", "cursor": "page-2"},
    )
    api.on_exchange_finish(request, {
        "outcome": "received", "status_code": 200,
        "body": b'{"tweets":[],"next_cursor":"page-3"}', "error_type": None,
    })
    lineage.unbind_api(api)
    post = Post.objects.create(tweet_id="scheduled-lineage-post", text="Qwen", lang="en")
    PostEnrichmentState.objects.create(post=post)
    assert lineage.finish_call(
        scope_id, post_ids=[post.pk], page_by_post={str(post.pk): 1},
        raw_count=2, outcome="ok", complete=True,
    ) == 1
    scope = CollectionScopeRun.objects.get(pk=scope_id)
    assert scope.raw_count == 2 and scope.coverage_state == "complete"
    assert CollectionObservation.objects.filter(
        run_id=lineage.claim.run_id, scope_run=scope, post=post,
    ).exists()
    assert CollectionObservationInput.objects.filter(
        observation__scope_run=scope, observation__post=post,
        input_request=request,
    ).exists()
    assert PostEnrichmentState.objects.get(post=post).source_collection_job_id is None
    assert request.cursor_before == "page-2"
    request.refresh_from_db()
    assert request.transport_outcome == "received"
    assert request.cursor_after == "page-3"
    assert bytes(request.archive.body) == b'{"tweets":[],"next_cursor":"page-3"}'
    run = lineage.finish(success=True)
    assert run.request_count == 1
    assert run.attempts.get().accounting_complete


def test_scheduled_request_crash_cannot_be_reported_as_complete():
    from core.models import CollectionRequest
    from core.x_cycle_lineage import ScheduledCycleLineage

    call = SimpleNamespace(call_id="A", query_string="from:publisher")
    lineage = ScheduledCycleLineage.start(
        [call],
        limits={"requests": 10, "bytes": 100000, "seconds": 300, "items": 100},
        invocation_id="scheduled-crash-test",
    )
    scope_id = lineage.begin_call(call, since_epoch=1783809000, until_epoch=1783809300)
    request = lineage.begin_exchange(
        scope_id, endpoint_url="https://api.twitterapi.io/twitter/tweet/advanced_search",
        params={"query": "from:publisher"},
    )
    with pytest.raises(ValueError, match="receipt is unfinished"):
        lineage.finish(success=True)
    assert CollectionRequest.objects.get(pk=request.pk).transport_outcome == "pending"
    lineage.finish_exchange(request, {
        "outcome": "transport_error", "status_code": None,
        "body": None, "error_type": "Timeout",
    })
    lineage.finish_call(
        scope_id, post_ids=[], raw_count=0, outcome="error", complete=False,
    )
    run = lineage.finish(success=False)
    assert run.request_count == 1
    assert not run.attempts.get().accounting_complete
    assert run.attempts.get().unknown_sent_requests == 1


def test_legacy_product_match_scope_pins_existing_subject_and_input_digest():
    from django.utils import timezone

    from core.collection_jobs import register_job
    from core.measurement_taxonomy import digest
    from core.models import CollectionRun, CollectionScopeRun, DataSource
    from tests.test_collection_matching import catalog_fixture, preview

    brand, product, _ = catalog_fixture()
    report = preview(brand)
    choice = report["products"][0]["candidates"][0]
    definition = {
        "version": 1,
        "schedule": {"kind": "manual", "driver": "manual"},
        "budgets": {"requests": 1, "bytes": 32768, "seconds": 120, "items": 50},
        "scope": {
            "ruleset": "product-crosswalk-v1",
            "preview_sha256": report["input_sha256"],
            "cutoff": report["cutoff"], "brands": report["brands"],
            "matches": [choice],
            "review": {"reviewed_by": "owner", "basis": "exact match",
                       "candidate_ids": [choice["candidate_id"]]},
        },
    }
    job = register_job(
        job_key="legacy-match:" + digest(choice), source=DataSource.objects.get(pk="arena"),
        purpose="catalog", operation="match_crosswalk", mode="historical",
        definition=definition,
    )
    run = CollectionRun.objects.create(
        job=job, ingestion_key=digest("legacy-product-match"),
        status="success", completed_at=timezone.now(),
    )
    scope = CollectionScopeRun.objects.create(
        run=run, scope_kind="product_match", scope_key=choice["candidate_id"],
        ownership={"product_key": str(product.product_key),
                   "input_sha256": choice["input_sha256"]},
    )
    assert product_match_target_mismatch_counts() == (0, 1)
    assert project_product_match_targets_batch(after_id=scope.pk - 1).updated == 1
    scope.refresh_from_db()
    assert scope.job_target.subject.product_id == product.product_key
    assert scope.job_target.selection_sha256 == choice["input_sha256"]
    assert product_match_target_mismatch_counts() == (0, 0)
    assert project_product_match_targets_batch(after_id=scope.pk - 1).updated == 0


def test_legacy_documents_are_archived_once_and_changed_rows_are_reconciled():
    run, _, scope = execution()
    run.source_metadata = {"ingestion_mode": "direct"}
    run.raw_payload = {"items": [{"id": "one"}]}
    run.save(update_fields=["source_metadata", "raw_payload"])
    scope.ownership = {"query": "example"}
    scope.save(update_fields=["ownership"])
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        source_identifier="one",
        source_subject_kind="model",
        observation_key="a" * 64,
        dimensions={"config": "text"},
        source_metadata={"history_basis": "reported"},
    )

    for table in (
        "collection_runs", "collection_scope_runs", "collection_observations"
    ):
        assert archive_legacy_batch(table).archived == 1
        assert archive_legacy_batch(table).archived == 0
        assert stale_legacy_archive_count(table) == 0

    CollectionObservation.objects.create(
        run=run, scope_run=scope, source_identifier="two",
        source_subject_kind="model", observation_key="b" * 64,
    )
    assert stale_legacy_archive_count("collection_observations", batch_size=1) == 1
    assert archive_legacy_batch("collection_observations").archived == 1
    assert stale_legacy_archive_count("collection_observations", batch_size=1) == 0

    run.refresh_from_db()
    scope.refresh_from_db()
    observation.refresh_from_db()
    assert read_document(run.legacy_archive)["raw_payload"] == {
        "items": [{"id": "one"}]
    }
    assert read_document(scope.legacy_archive)["ownership"] == {"query": "example"}
    from core.collection_capture import scope_object_documents

    scope.envelopes = [{"state": "newer_live_checkpoint"}]
    scope.save(update_fields=["envelopes"])
    assert scope_object_documents(scope)[2] == [{"state": "newer_live_checkpoint"}]
    scope.ownership, scope.cursor_history, scope.envelopes = {}, [], []
    scope.save(update_fields=["ownership", "cursor_history", "envelopes"])
    assert scope_object_documents(scope) == ({"query": "example"}, [], [])
    assert read_document(observation.legacy_archive)["dimensions"] == {
        "config": "text"
    }
    run.report = {"retry": 2}
    run.save(update_fields=["report"])
    assert stale_legacy_archive_count("collection_runs") == 1
    assert archive_legacy_batch("collection_runs", repair_stale=True).archived == 1
    run.refresh_from_db()
    assert read_document(run.legacy_archive)["report"] == {"retry": 2}
    assert stale_legacy_archive_count("collection_runs") == 0


def test_legacy_archive_sweep_excludes_typed_only_group_and_queue_scopes():
    run, _, parent = execution()
    diagnostic = archive_document(
        b'{"version":1,"projection_error":"invalid source"}',
        encoding="selected-json-canonical-v1",
        capture_kind="numeric_projection_evidence",
    )
    projection = CollectionScopeRun.objects.create(
        run=run, scope_kind="numeric_projection", scope_key="saved-evidence",
        phase="projection_results_v1", ownership={}, legacy_archive=diagnostic,
    )
    observation = CollectionObservation.objects.create(
        run=run, scope_run=parent, source_identifier="captured",
        source_subject_kind="model", observation_key="c" * 64,
    )
    children = [
        CollectionScopeRun.objects.create(
            run=run, parent_scope=parent, scope_kind="resource_group",
            scope_key="typed-group", ownership={},
        ),
        CollectionScopeRun.objects.create(
            run=run, parent_scope=parent, scope_kind="numeric_projection_item",
            scope_key="typed-pending", ownership={},
            resource_observation=observation,
        ),
        CollectionScopeRun.objects.create(
            run=run, parent_scope=parent, scope_kind="numeric_projection_result",
            scope_key="typed-source-result", ownership={},
            resource_observation=observation,
        ),
        CollectionScopeRun.objects.create(
            run=run, parent_scope=parent, scope_kind="numeric_projection_output",
            scope_key="typed-output-result", ownership={},
            resource_observation=observation,
        ),
        CollectionScopeRun.objects.create(
            run=run, scope_kind="history_execution", scope_key="execution",
            phase="typed-history-v1", ownership={},
        ),
        CollectionScopeRun.objects.create(
            run=run, scope_kind="catalog_execution", scope_key="execution",
            phase="typed-github-catalog-v1", ownership={},
        ),
        CollectionScopeRun.objects.create(
            run=run, scope_kind="x_model_call", scope_key="typed-model",
            phase="staff_relevance_v1", ownership={},
        ),
        CollectionScopeRun.objects.create(
            run=run, scope_kind="x_model_usage", scope_key="legacy",
            phase="backfill_model_v1", ownership={},
        ),
        CollectionScopeRun.objects.create(
            run=run, scope_kind="x_backfill_result", scope_key="result",
            phase="backfill_result_v1", ownership={},
        ),
        CollectionScopeRun.objects.create(
            run=run, scope_kind="x_checkpoint_import", scope_key="typed-import",
            phase="typed-import-v1", ownership={},
        ),
    ]

    assert archive_legacy_batch("collection_scope_runs").archived == 1
    assert archive_legacy_batch("collection_scope_runs", repair_stale=True).archived == 0
    assert stale_legacy_archive_count("collection_scope_runs", batch_size=1) == 0
    parent.refresh_from_db()
    assert parent.legacy_archive_id is not None
    for child in children:
        child.refresh_from_db()
        assert child.legacy_archive_id is None
    projection.refresh_from_db()
    assert projection.legacy_archive_id == diagnostic.pk

    coverage = CollectionObservation.objects.create(
        run=run, scope_run=parent, source_identifier="typed-coverage",
        source_subject_kind="model", observation_kind="coverage",
        observation_key="d" * 64,
    )
    assert archive_legacy_batch("collection_observations").archived == 1
    assert stale_legacy_archive_count("collection_observations") == 0
    observation.refresh_from_db()
    coverage.refresh_from_db()
    assert observation.legacy_archive_id is not None
    assert coverage.legacy_archive_id is None


def test_benchmark_provenance_copy_is_bounded_and_repeatable():
    run, _, scope = execution()
    run.source_metadata = {"ingestion_mode": "direct"}
    run.save(update_fields=["source_metadata"])
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        source_identifier="historical",
        source_subject_kind="model",
        observation_key="b" * 64,
        source_metadata={
            "projection_kind": "source-statistics-v1",
            "history_basis": "reconstructed_current_relationships",
            "secondary_source": True,
            "publication_complete": False,
            "reconstruction_date": "2026-10-24",
            "archive_snapshot_date": "2026-10-23",
            "period_status": "partial",
        },
    )
    assert provenance_mismatch_counts() == (1, 1)
    assert project_run_ingestion_mode() == 1
    first = project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    )
    assert (first.last_id, first.scanned, first.updated) == (observation.pk, 1, 1)
    assert project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    ).updated == 0
    run.refresh_from_db()
    observation.refresh_from_db()
    assert run.direct_ingestion is True
    assert observation.projection_kind == "source-statistics-v1"
    assert observation.history_reconstructed is True
    assert observation.secondary_source is True
    assert observation.publication_complete is False
    assert observation.reconstruction_date.isoformat() == "2026-10-24"
    assert observation.archive_snapshot_date.isoformat() == "2026-10-23"
    assert observation.period_status == "partial"
    assert provenance_mismatch_counts() == (0, 0)

    observation.source_metadata["reconstruction_date"] = "2026-10-23"
    observation.save(update_fields=["source_metadata"])
    assert provenance_mismatch_counts() == (0, 1)
    assert project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    ).updated == 1
    observation.refresh_from_db()
    assert observation.reconstruction_date.isoformat() == "2026-10-23"
    assert provenance_mismatch_counts() == (0, 0)

    # Later writers can omit legacy copies. A final reconciliation must not
    # interpret absent JSON keys as instructions to clear canonical facts.
    observation.row_semantic_digest = bytes.fromhex("c" * 64)
    observation.source_metadata = {}
    observation.save(update_fields=["row_semantic_digest", "source_metadata"])
    canonical = {
        field: getattr(observation, field)
        for field in (
            "projection_kind", "row_semantic_digest", "archive_snapshot_date",
            "period_status", "history_reconstructed", "secondary_source",
            "publication_complete", "reconstruction_date",
        )
    }
    assert provenance_mismatch_counts() == (0, 0)
    assert project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    ).updated == 0
    observation.refresh_from_db()
    assert {field: getattr(observation, field) for field in canonical} == canonical

    # A present, explicit unknown is still historical evidence to reconcile.
    observation.source_metadata = {"projection_kind": None}
    observation.save(update_fields=["source_metadata"])
    assert provenance_mismatch_counts() == (0, 1)
    assert project_benchmark_provenance_batch(
        after_id=observation.pk - 1, batch_size=1
    ).updated == 1
    observation.refresh_from_db()
    assert observation.projection_kind is None
    assert {
        field: getattr(observation, field)
        for field in canonical if field != "projection_kind"
    } == {field: value for field, value in canonical.items() if field != "projection_kind"}
