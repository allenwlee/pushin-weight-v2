"""Current typed records and retained evidence after RG6 ORM detachment.

The 17 one-time copier test functions (21 cases) live in immutable pre-detachment
commit 8785ea769c14b19e574f8197499e34f6bdf8850f, where their historical-schema
checks were run before detachment. They cover the retired conversion, not the
current runtime. Keep that evidence scoped to its revision; tests here require
the detached ORM and do not restore the removed fields or run historical copiers.
"""

import hashlib
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from django.db import transaction

from core.collection_capture import (
    archive_legacy,
    observation_object_documents,
    read_document,
    run_report_document,
    scope_object_documents,
)
from core.collection_state import claim_job
from core.models import CollectionObservation, CollectionRun, CollectionScopeRun
from tests.test_collection_jobs import ready
from tests.test_hf_catalog_retirement import RETIRED, denied_retirement_columns

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def detached_collection_models():
    # The denied-column helper must not hide an accidentally restored ORM field.
    for model, retired in RETIRED.items():
        assert retired.isdisjoint(field.name for field in model._meta.fields)


def execution(*, purpose="catalog"):
    job = ready(purpose=purpose)
    claim = claim_job(job.pk, typed=True, manual_authorized=purpose == "content")
    run = CollectionRun.objects.get(pk=claim.run_id)
    scope = CollectionScopeRun.objects.create(run=run, scope_key="publisher")
    return run, run.attempts.get(), scope


def test_new_arena_publication_marker_needs_no_retiring_json_columns():
    from core.benchmark_metric_store import persist_source, record_arena_publications
    from core.measurement_taxonomy import digest
    from tests.test_benchmark_download_persistence import provider_contract

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
        assert record_arena_publications(run, ["2026-09-29"]) == 0
        marker = CollectionObservation.objects.get(
            run=run, observation_kind="publication_marker",
            published_date=datetime(2026, 9, 29, tzinfo=UTC).date(),
        )
        assert marker.publication_complete is True


def test_typed_resume_preserves_original_non_uuid_invocation_and_attempt():
    from core.collection_state import finish_run

    job = ready()
    with denied_retirement_columns():
        first = claim_job(job.pk, invocation_id="operator-run-1", typed=True)
        run = finish_run(
            first, status="partial", typed=True, request_count=0,
            physical_accounting_complete=True,
        )
        original = run.attempts.values().get()
        assert original["source_invocation_id"] == "operator-run-1"
        assert original["outcome"] == "partial" and original["finished_at"]
        second = claim_job(job.pk, invocation_id="operator-run-2", typed=True)
        assert second.run_id == first.run_id
        assert second.attempt_id != first.attempt_id
        assert run.attempts.filter(pk=first.attempt_id).values().get() == original
        resumed = run.attempts.get(pk=second.attempt_id)
        assert resumed.source_invocation_id == "operator-run-2"
        assert resumed.ordinal == 2 and resumed.outcome == "running"
        assert resumed.finished_at is None and not resumed.requests.exists()


def test_x_prefetch_reads_pinned_query_when_archived_ownership_is_stale():
    from core.collection_state import ensure_x_query_target, x_scope_ownership
    from monitor.backfill_prefetch import _params

    run, _, scope = execution(purpose="content")
    scope.scope_kind = "x_query"
    scope.requested_start_at = datetime.fromtimestamp(1783809000, UTC)
    scope.requested_end_at = datetime.fromtimestamp(1783809300, UTC)
    with transaction.atomic():
        scope.job_target = ensure_x_query_target(
            run.job, scope.scope_key, query_text="original query", call_id="B1",
            start_at=scope.requested_start_at, end_at=scope.requested_end_at,
        )
    stale = {
        "call_id": "B1", "query": "stale query",
        "since_epoch": 1783809000, "until_epoch": 1783809300,
    }
    scope.legacy_archive = archive_legacy({
        "ownership": stale, "cursor_history": [], "envelopes": [],
    })
    scope.save(update_fields=[
        "scope_kind", "requested_start_at", "requested_end_at", "job_target",
        "legacy_archive",
    ])

    with denied_retirement_columns():
        scope.refresh_from_db()
        assert x_scope_ownership(scope)["query"] == "original query"
        assert "original query" in _params(scope)["query"]
        assert "stale query" not in _params(scope)["query"]
        assert read_document(scope.legacy_archive)["ownership"] == stale


def test_unmapped_legacy_x_scope_reads_immutable_archive_after_ownership_retirement():
    from core.collection_state import x_scope_ownership

    _, _, scope = execution(purpose="content")
    ownership = {
        "call_id": "B1", "query": "archived query",
        "since_epoch": 1783809000, "until_epoch": 1783809300,
    }
    scope.scope_kind = "x_query"
    scope.legacy_archive = archive_legacy({
        "ownership": ownership, "cursor_history": [], "envelopes": [],
    })
    scope.save(update_fields=["scope_kind", "legacy_archive"])

    with denied_retirement_columns():
        scope.refresh_from_db()
        assert x_scope_ownership(scope) == ownership


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
        requested_start_at=lower, requested_end_at=upper,
    )
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
        requested_start_at=next_lower, requested_end_at=next_upper,
    )
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


def test_archived_documents_reconstruct_exact_content_without_retired_columns():
    from core.measurement_taxonomy import digest

    documents = (
        {
            "request_params": {"cursor": "opaque"},
            "source_metadata": {"original_clock": None},
            "raw_payload": {"items": ["first", "first"]},
            "invocations": [{"invocation_id": "operator-retry", "finished_at": None}],
            "report": {"requests": 2, "retry": {"unknown": True}},
        },
        {
            "ownership": {"query": "exact query"},
            "cursor_history": ["first", "same", "same"],
            "envelopes": [{"ids": []}, {"ids": None}],
        },
        {
            "listing": {"id": "publisher/repository", "counter": 0},
            "dimensions": {"config": "text", "category": None},
            "source_metadata": {"history_basis": "reported"},
            "envelopes": [{"status": "partial", "body": None}],
            "groups": {"detail": {"outcome": "failed"}},
        },
    )
    with denied_retirement_columns():
        archives = [archive_legacy(document) for document in documents]
        evidence = [(archive.pk, bytes(archive.body)) for archive in archives]
        run = CollectionRun.objects.create(
            job=ready(), ingestion_key=digest("retained historical documents"),
            status="pending", legacy_archive=archives[0],
        )
        scope = CollectionScopeRun.objects.create(
            run=run, scope_key="saved", legacy_archive=archives[1],
        )
        observation = CollectionObservation.objects.create(
            run=run, scope_run=scope, source_identifier="publisher/repository",
            source_subject_kind="repository", observation_key=digest("saved object"),
            legacy_archive=archives[2],
        )
        assert run_report_document(run) == documents[0]["report"]
        assert scope_object_documents(scope) == tuple(
            documents[1][key] for key in ("ownership", "cursor_history", "envelopes")
        )
        assert observation_object_documents(observation) == tuple(
            documents[2][key] for key in ("listing", "dimensions", "source_metadata")
        )
        for archive, document, original in zip(archives, documents, evidence, strict=True):
            archive.refresh_from_db()
            assert read_document(archive) == document
            assert (archive.pk, bytes(archive.body)) == original
        assert not run.attempts.exists() and not scope.requests.exists()
        assert not observation.inputs.exists()


def test_typed_provenance_distinguishes_absent_evidence_from_explicit_unknown():
    from core.collection_resources import project_observation_facts
    from core.measurement_taxonomy import digest

    with denied_retirement_columns():
        run, _, scope = execution()
        document = {"listing": {}, "dimensions": {}, "source_metadata": {}}
        original_archive = archive_legacy(document)
        facts = {
            "observation_kind": "repository",
            "projection_kind": "source-statistics-v1",
            "config_key": "text",
            "provider_revision": "original-revision",
            "payload_sha256": "a" * 64,
            "row_semantic_digest": bytes.fromhex("b" * 64),
            "history_reconstructed": True,
            "secondary_source": True,
            "publication_complete": False,
            "period_status": "partial",
            "archive_snapshot_date": date(2026, 10, 23),
            "reconstruction_date": date(2026, 10, 24),
        }
        observation = CollectionObservation.objects.create(
            run=run, scope_run=scope, source_identifier="publisher/repository",
            source_subject_kind="repository", observation_key=digest("typed provenance"),
            legacy_archive=original_archive, **facts,
        )
        project_observation_facts(observation)
        observation.refresh_from_db()
        assert {field: getattr(observation, field) for field in facts} == facts

        # A distinct retained source document explicitly marks only these two
        # coordinates unknown; it does not erase the omitted canonical facts.
        explicit_unknown = {
            **document, "dimensions": {"config": None},
            "source_metadata": {"projection_kind": None},
        }
        observation.legacy_archive = archive_legacy(explicit_unknown)
        observation.save(update_fields=["legacy_archive"])
        project_observation_facts(observation)
        observation.refresh_from_db()
        assert {field: getattr(observation, field) for field in facts} == {
            **facts, "config_key": None, "projection_kind": None,
        }
        original_archive.refresh_from_db()
        assert read_document(original_archive) == document
        assert read_document(observation.legacy_archive) == explicit_unknown
