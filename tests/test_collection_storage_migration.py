"""The collection archive copy is exact, repeatable, and detects live changes."""

from datetime import UTC, datetime

import pytest

from core.collection_capture import read_document
from core.collection_storage_migration import (
    archive_legacy_batch,
    product_match_target_mismatch_counts,
    project_arena_publication_batch,
    project_benchmark_provenance_batch,
    project_product_match_targets_batch,
    project_run_ingestion_mode,
    project_run_invocations_batch,
    project_scope_bounds_batch,
    project_x_query_targets_batch,
    provenance_mismatch_counts,
    scope_bounds_mismatch_counts,
    stale_legacy_archive_count,
    x_query_target_mismatch_counts,
)
from core.models import CollectionObservation
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

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_historical_invocations_get_distinct_attempts_without_invented_outcomes():
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

    result = project_run_invocations_batch()
    assert result.inserted == 2
    attempts = list(run.attempts.order_by("ordinal"))
    assert [attempt.ordinal for attempt in attempts] == [1, 2]
    assert [attempt.outcome for attempt in attempts] == ["legacy_unknown"] * 2
    assert all(attempt.finished_at is None and not attempt.accounting_complete for attempt in attempts)
    assert attempts[0].attempt_key == digest({"job": str(job.pk), "invocation": "first"})
    assert project_run_invocations_batch().inserted == 0
    assert project_run_invocations_batch(verify_only=True).inserted == 0

    attempts[0].started_at = datetime(2026, 10, 20, 9, tzinfo=UTC)
    attempts[0].save(update_fields=["started_at"])
    with pytest.raises(ValueError, match="historical attempt differs"):
        project_run_invocations_batch(verify_only=True)


def test_invocation_copy_accepts_existing_attempt_with_non_uuid_identity():
    from core.collection_state import claim_job
    from tests.test_collection_jobs import ready

    job = ready()
    claim = claim_job(job.pk, invocation_id="operator-run-1")
    assert project_run_invocations_batch(verify_only=True).inserted == 0
    assert project_run_invocations_batch().inserted == 0
    assert job.runs.get(pk=claim.run_id).attempts.get().outcome == "running"


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
    _, _, scope = execution()
    scope.scope_kind = "x_query"
    scope.ownership = {
        "call_id": "B1", "query": "exact source query",
        "since_epoch": 1783809000, "until_epoch": 1783809300,
    }
    scope.save(update_fields=["scope_kind", "ownership"])
    assert x_query_target_mismatch_counts() == (0, 1)
    result = project_x_query_targets_batch(after_id=scope.pk - 1)
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

    run.refresh_from_db()
    scope.refresh_from_db()
    observation.refresh_from_db()
    assert read_document(run.legacy_archive)["raw_payload"] == {
        "items": [{"id": "one"}]
    }
    assert read_document(scope.legacy_archive)["ownership"] == {"query": "example"}
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
