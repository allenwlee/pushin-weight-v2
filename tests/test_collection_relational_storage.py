"""Shared collection records preserve resource, response and execution grains."""

import hashlib
import uuid

import pytest
from django.db import IntegrityError, connection, transaction

from core.collection_state import claim_job
from core.models import (
    CollectionAttempt,
    CollectionCorrection,
    CollectionEvidenceArchive,
    CollectionJobTarget,
    CollectionMetricGap,
    CollectionObservation,
    CollectionObservationInput,
    CollectionRequest,
    CollectionResourceSnapshot,
    CollectionRun,
    CollectionScopeRun,
)
from tests.test_collection_jobs import ready

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def execution():
    job = ready()
    run = CollectionRun.objects.get(pk=claim_job(job.pk).run_id)
    attempt = run.attempts.get()
    scope = CollectionScopeRun.objects.create(
        run=run,
        scope_key="publisher",
        ownership={},
    )
    return run, attempt, scope


def test_real_claim_and_resume_record_two_attempts_for_one_catalog_run():
    from core.collection_state import finish_run

    job = ready()
    first = claim_job(job.pk)
    finish_run(first, status="partial", request_count=1)
    second = claim_job(job.pk)
    assert first.run_id == second.run_id
    attempts = list(
        CollectionAttempt.objects.filter(run_id=first.run_id).order_by("ordinal")
    )
    assert [row.ordinal for row in attempts] == [1, 2]
    assert attempts[0].outcome == "partial" and attempts[0].finished_at
    assert attempts[1].outcome == "running" and attempts[1].finished_at is None
    assert first.attempt_id == attempts[0].pk and second.attempt_id == attempts[1].pk


@pytest.mark.parametrize("purpose", ["catalog", "metric", "content"])
@pytest.mark.parametrize("stop", ["yield", "pause"])
def test_typed_partial_resume_keeps_one_logical_run_and_updates_separate_states(
    purpose,
    stop,
):
    from core.collection_jobs import register_job, set_job_state
    from core.collection_state import checkpoint_scope, finish_run
    from core.models import DataSource
    from tests.test_source_metric_projection import configured

    contract = configured()[0] if purpose == "metric" else None
    source_id = (
        "hf" if purpose == "metric" else "x" if purpose == "content" else "arena"
    )
    source, _ = DataSource.objects.get_or_create(
        pk=source_id,
        defaults={
            "name": source_id,
            "source_type": "social" if purpose == "content" else "benchmark",
        },
    )
    if purpose != "content":
        source.enabled, source.adapter_key = True, source_id + "-v1"
        source.save()
    job = register_job(
        job_key="typed-resume",
        source=source,
        purpose=purpose,
        operation={
            "catalog": "model_inventory",
            "metric": "collect_metrics",
            "content": "x_backfill",
        }[purpose],
        mode="historical",
        contract=contract,
        definition={"version": 2, "options": {}},
        settings={
            "owner_kind": "source",
            "schedule_kind": "manual",
            "schedule_driver": "manual",
            "max_requests": 10,
            "max_seconds": 30,
            "max_bytes": 10000,
            "max_items": 100,
        },
    )
    set_job_state(job.pk, "ready")
    first = claim_job(job.pk, invocation_id="first", manual_authorized=True)
    scope = checkpoint_scope(
        first, scope_key="one", ownership={}, enumeration_complete=False
    )
    if stop == "pause":
        from core.collection_state import StaleClaim

        set_job_state(job.pk, "paused")
        with pytest.raises(StaleClaim):
            finish_run(first, status="success", request_count=0)
        run = CollectionRun.objects.get(pk=first.run_id)
        attempt = run.attempts.get()
        assert attempt.outcome == "interrupted" and attempt.finished_at is None
        set_job_state(job.pk, "ready")
    else:
        run = finish_run(first, status="partial", request_count=0)
    assert (
        run.completed_at is None
        and run.execution_state == ("interrupted" if stop == "pause" else "yielded")
        and run.coverage_state == "partial"
    )
    second = claim_job(job.pk, invocation_id="second", manual_authorized=True)
    assert second.run_id == first.run_id and second.attempt_id != first.attempt_id
    assert CollectionScopeRun.objects.get(pk=scope.pk).run_id == second.run_id
    checkpoint_scope(
        second,
        scope_key="one",
        ownership={},
        enumeration_complete=True,
        outcome="complete",
    )
    run = finish_run(second, status="success", request_count=0)
    assert run.execution_state == "completed" and run.coverage_state == "complete"
    assert run.attempts.count() == 2


def test_exactly_nine_source_independent_tables_are_added():
    names = set(connection.introspection.table_names())
    assert {
        "collection_campaigns",
        "collection_job_targets",
        "collection_attempts",
        "collection_requests",
        "collection_evidence_archives",
        "collection_observation_inputs",
        "collection_resource_snapshots",
        "collection_metric_gaps",
        "collection_corrections",
    } <= names
    assert not {"collection_resource_files", "collection_resource_links"} & names


def test_repeated_real_calls_share_body_without_losing_request_identity():
    run, attempt, scope = execution()
    body = b'{"models":[]}'
    archive = CollectionEvidenceArchive.objects.create(
        content_sha256=hashlib.sha256(body).hexdigest(),
        encoding="wire-bytes-v1",
        media_type="application/json",
        byte_count=len(body),
        body=body,
        capture_kind="response",
    )
    for ordinal in (1, 2):
        CollectionRequest.objects.create(
            attempt=attempt,
            scope_run=scope,
            ordinal=ordinal,
            endpoint_url="https://huggingface.co/api/models?author=publisher",
            http_method="GET",
            archive=archive,
            transport_outcome="received",
        )
    assert run.attempts.get().requests.count() == 2
    assert CollectionEvidenceArchive.objects.count() == 1


def test_http_method_is_a_checked_protocol_value():
    _, attempt, scope = execution()
    request = CollectionRequest.objects.create(
        attempt=attempt,
        scope_run=scope,
        ordinal=1,
        http_method="GET",
    )
    assert request.http_method == "GET"
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRequest.objects.create(
            attempt=attempt,
            scope_run=scope,
            ordinal=2,
            http_method="FETCH",
        )


def test_request_intake_rejects_unknown_http_methods_before_persisting():
    from core.collection_capture import begin_request

    _, attempt, scope = execution()
    with pytest.raises(ValueError, match="unsupported HTTP method"):
        begin_request(
            attempt,
            scope,
            endpoint_url="https://huggingface.co/api/models",
            method="FETCH",
        )
    assert CollectionRequest.objects.count() == 0


def test_attempt_ordinal_is_unique_within_logical_run():
    run, _, _ = execution()
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionAttempt.objects.create(
            run=run,
            attempt_key=uuid.uuid4().hex,
            ordinal=1,
        )


def test_input_requires_exactly_one_request_or_earlier_observation():
    run, _, scope = execution()
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        resource_key="repo",
        source_identifier="repo",
        source_subject_kind="repository",
        observation_key=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionObservationInput.objects.create(
            observation=observation,
            input_role="response",
        )


def test_snapshot_preserves_already_collected_git_clocks():
    fields = {field.name for field in CollectionResourceSnapshot._meta.fields}
    assert {
        "authored_at",
        "committed_at",
        "provider_created_at",
        "provider_modified_at",
    } <= fields
    assert not any(
        field.get_internal_type() == "JSONField"
        for field in CollectionResourceSnapshot._meta.fields
    )


def test_unresolved_target_requires_reason_instead_of_invented_identity():
    job = ready()
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionJobTarget.objects.create(
            job=job,
            target_key="missing",
            ordinal=0,
            target_kind="account",
            target_role="publisher",
            resolution_state="unresolved",
            gap_reason="",
        )


def test_no_new_collection_record_introduces_json_fields():
    for model in (
        CollectionAttempt,
        CollectionCorrection,
        CollectionEvidenceArchive,
        CollectionJobTarget,
        CollectionMetricGap,
        CollectionObservationInput,
        CollectionRequest,
        CollectionResourceSnapshot,
    ):
        assert not any(
            field.get_internal_type() == "JSONField" for field in model._meta.fields
        )


def test_archive_is_immutable_even_through_bulk_update_and_delete():
    from core.collection_capture import archive_document

    archive = archive_document(b"{}")
    for operation in (
        lambda: CollectionEvidenceArchive.objects.filter(pk=archive.pk).update(
            body=b"[]"
        ),
        lambda: CollectionEvidenceArchive.objects.filter(pk=archive.pk).delete(),
    ):
        with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
            operation()


def test_cross_run_request_is_rejected_by_database():
    _, attempt, _ = execution()
    other = CollectionRun.objects.create(
        job=ready(key="other"),
        ingestion_key="b" * 64,
        status="pending",
    )
    wrong_scope = CollectionScopeRun.objects.create(
        run=other, scope_key="other", ownership={}
    )
    with pytest.raises(IntegrityError, match="same run"), transaction.atomic():
        CollectionRequest.objects.create(
            attempt=attempt, scope_run=wrong_scope, ordinal=1
        )


def test_target_parent_cannot_cross_jobs_or_form_a_cycle():
    first_job, second_job = ready(), ready(key="another")
    first = CollectionJobTarget.objects.create(
        job=first_job,
        target_key="first",
        ordinal=0,
        target_kind="account",
        target_role="selected",
        resolution_state="unresolved",
        gap_reason="missing_account",
    )
    second = CollectionJobTarget.objects.create(
        job=second_job,
        target_key="second",
        ordinal=0,
        target_kind="account",
        target_role="selected",
        resolution_state="unresolved",
        gap_reason="missing_account",
    )
    with pytest.raises(IntegrityError, match="same job"), transaction.atomic():
        CollectionJobTarget.objects.filter(pk=first.pk).update(parent_target=second)
    child = CollectionJobTarget.objects.create(
        job=first_job,
        target_key="child",
        ordinal=1,
        parent_target=first,
        target_kind="brand",
        target_role="selected",
        resolution_state="unresolved",
        gap_reason="missing_brand",
    )
    with pytest.raises(IntegrityError, match="cycle"), transaction.atomic():
        CollectionJobTarget.objects.filter(pk=first.pk).update(parent_target=child)


def test_frozen_search_query_cannot_change_after_registration():
    from core.models import SearchQuery

    query = SearchQuery.objects.create(query_id="frozen-example", query_text="DeepSeek")
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        SearchQuery.objects.filter(pk=query.pk).update(query_text="Mistral")
