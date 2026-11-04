"""Typed, precommit receipts for staging X responses, without retained bodies.

Request appearances belong to their physical request. A later page checkpoint
records processing decisions separately; a lost in-memory body never deletes the
known received IDs or implies an identical subsequent response.
"""

import re

from django.db import transaction
from django.utils import timezone

from core.collection_capture import read_document
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionEvidenceArchive,
    CollectionObservation,
    CollectionObservationInput,
    CollectionRequest,
)
from monitor.backfill_retry import RetryControl

CATEGORY = "x_backfill_staging"
APPEARANCE_KIND = "x_request_appearance"
RETRY_REVIEW_KIND = 'x_staging_retry_approval'


@transaction.atomic
def adopt_retry_reviews(run, *, verify_only=False):
    """Preserve already-recorded operator consents; never grant a new retry.

    An observation records the review fact and its actual review clock. Its
    typed input points to the original unknown request, rather than pretending
    that a response was received. The reason remains immutable source evidence.
    """
    from core.benchmark_metric_store import aware_instant
    from core.collection_capture import archive_legacy, read_document
    from core.models import CollectionJob, CollectionRun

    CollectionJob.objects.select_for_update().only('pk').get(pk=run.job_id)
    run = CollectionRun.objects.select_for_update().only('pk', 'job_id', 'legacy_archive_id').get(pk=run.pk)
    approvals = _legacy_report(run).get('staging_unknown_retries', {})
    require(isinstance(approvals, dict) and len(approvals) <= 1000,
            'invalid historical retry review set')
    copied = 0
    for identifier, approval in approvals.items():
        require(isinstance(approval, dict) and set(approval) == {'reason', 'at'}
                and isinstance(approval['reason'], str) and 0 < len(approval['reason']) <= 4096,
                'invalid historical retry review')
        at = aware_instant(approval['at'])
        request = CollectionRequest.objects.select_for_update().get(pk=identifier)
        require(request.attempt.run_id == run.pk and request.request_category == CATEGORY
                and request.http_method == 'GET' and request.transport_outcome == 'unknown'
                and request.error_code == 'operator_reconciled_interruption'
                and request.received_at is None and request.http_status is None
                and request.archive_id is None and not request.accounting_complete,
                'historical retry review does not match an unknown request')
        key = digest([RETRY_REVIEW_KIND, identifier, approval])
        observation = CollectionObservation.objects.filter(run=run, observation_key=key).first()
        if observation is None:
            require(not verify_only, 'historical retry review is not projected')
            observation = CollectionObservation.objects.create(run=run,
                source_identifier=identifier, source_subject_kind='aggregate',
                observation_kind=RETRY_REVIEW_KIND, observation_key=key,
                observed_at=at, processing_outcome='approved',
                legacy_archive=archive_legacy(approval))
            CollectionObservationInput.objects.create(observation=observation,
                input_request=request, input_role='reconciled_request',
                row_locator='report.staging_unknown_retries.' + identifier,
                input_sha256=digest(approval))
            copied += 1
        require(observation.observation_kind == RETRY_REVIEW_KIND
                and observation.processing_outcome == 'approved'
                and observation.observed_at == at
                and read_document(observation.legacy_archive) == approval
                and observation.inputs.filter(input_request=request,
                    input_role='reconciled_request', input_sha256=digest(approval)).exists(),
                'historical retry review projection changed')
    return copied


def has_retry_review(request, job_id):
    from core.benchmark_metric_store import aware_instant

    links = list(CollectionObservationInput.objects.filter(input_request=request,
        input_role='reconciled_request', observation__run__job_id=job_id,
        observation__observation_kind=RETRY_REVIEW_KIND,
        observation__processing_outcome='approved', observation__status='ok')
        .select_related('observation__legacy_archive').defer('observation__legacy_archive__body')[:2])
    require(len(links) <= 1, 'historical retry review is ambiguous')
    if not links:
        return False
    link = links[0]
    observation = link.observation
    require(observation.source_identifier == str(request.pk)
            and observation.source_subject_kind == 'aggregate'
            and observation.legacy_archive_id is not None
            and observation.legacy_archive.byte_count <= 32 * 1024,
            'historical retry review evidence is invalid')
    evidence = read_document(observation.legacy_archive)
    require(isinstance(evidence, dict) and set(evidence) == {'reason', 'at'}
            and isinstance(evidence['reason'], str) and bool(evidence['reason'])
            and observation.observed_at == aware_instant(evidence['at'])
            and link.input_sha256 == digest(evidence), 'historical retry review evidence changed')
    return True


def _legacy_report(run):
    """Explicit write-boundary adoption only; operational readers are typed."""
    if any(field.name == "report" for field in type(run)._meta.fields) and run.report:
        return run.report
    if run.legacy_archive_id:
        archive = CollectionEvidenceArchive.objects.only('pk', 'byte_count').get(pk=run.legacy_archive_id)
        require(archive.byte_count <= 16 * 1024**2,
                'staging report archive exceeds adoption byte limit')
        document = read_document(archive)
        require(isinstance(document, dict) and isinstance(document.get("report"), dict),
                "staging legacy report archive is invalid")
        return document["report"]
    return {}


def adopt_retry_state(run):
    state = RetryControl.from_run(run)
    if state is not None:
        return state
    saved = _legacy_report(run).get("staging_retry")
    require(saved is not None or not CollectionRequest.objects.filter(
        attempt__run=run, request_category=CATEGORY,
    ).exists(), "staging retry state is missing; reconcile before retry")
    state = RetryControl.restore(saved)
    state.save(run)
    return state


def ensure_staging_bytes(run):
    if run.physical_bytes_received is None:
        report = _legacy_report(run)
        require("response_bytes" in report or not CollectionRequest.objects.filter(
            attempt__run=run, request_category=CATEGORY, response_bytes__gt=0,
        ).exists(), "staging byte accounting is missing; reconcile before retry")
        count = report.get("response_bytes", 0)
        require(type(count) is int and count >= 0, "invalid staging byte accounting")
        run.physical_bytes_received = count
        run.save(update_fields=["physical_bytes_received", "updated_at"])
    return run.physical_bytes_received


def staging_receipt(request):
    """Reconstruct the legacy receipt shape exclusively from typed owners."""
    require(request.body_lost is not None, "staging response accounting missing; reconcile before retry")
    rows = list(request.received_appearances.order_by("receipt_ordinal"))
    require([row.receipt_ordinal for row in rows] == list(range(len(rows))), "staging appearance order is incomplete")
    require(all(row.observation_kind == APPEARANCE_KIND and row.scope_run_id is None
                and row.run_id == request.scope_run.run_id for row in rows), "staging appearance owner changed")
    require((request.raw_count is None and not rows) or request.raw_count == len(rows),
            "staging raw count differs from received appearances")
    return {
        "raw_count": request.raw_count,
        "returned_ids": [None if row.source_identifier_is_null else row.source_identifier for row in rows]
                        if request.raw_count is not None else None,
        "body_sha256": bytes(request.response_sha256).hex() if request.response_sha256 is not None else None,
        "body_lost": request.body_lost,
    }


@transaction.atomic
def write_staging_receipt(request, metadata, *, selection_accounted=False):
    """Record source appearances before the page transaction; do not invent HTTP."""
    request = CollectionRequest.objects.select_for_update().select_related("scope_run").only(
        *(field.attname for field in CollectionRequest._meta.concrete_fields),
        'scope_run__run_id', 'scope_run__source_dataset_id',
    ).get(pk=request.pk)
    require(request.request_category == CATEGORY, "staging receipt requires a staging request")
    require(set(metadata) == {"raw_count", "returned_ids", "body_sha256", "body_lost"}, "invalid staging receipt fields")
    count, ids, fingerprint = metadata["raw_count"], metadata["returned_ids"], metadata["body_sha256"]
    require(type(metadata["body_lost"]) is bool and type(selection_accounted) is bool, "invalid staging receipt flags")
    if count is None:
        require(ids is None and fingerprint is None and not metadata["body_lost"] and not selection_accounted,
                "unknown staging response cannot have received evidence")
    else:
        require(type(count) is int and count >= 0 and type(ids) is list and count == len(ids)
                and all(value is None or type(value) is str and len(value) <= 256 for value in ids),
                "invalid staging received ID sequence")
        require(type(fingerprint) is str and re.fullmatch(r"[0-9a-f]{64}", fingerprint) is not None,
                "invalid staging body checksum")
        require(request.transport_outcome == "received" and request.response_bytes is not None,
                "staging receipt has no received transport evidence")
    if request.body_lost is not None:
        require(staging_receipt(request) == metadata and request.selection_accounted == selection_accounted,
                "staging receipt changed")
        return request
    request.raw_count = count
    request.response_sha256 = bytes.fromhex(fingerprint) if fingerprint is not None else None
    request.body_lost = metadata["body_lost"]
    request.selection_accounted = selection_accounted
    request.save(update_fields=["raw_count", "response_sha256", "body_lost", "selection_accounted"])
    observed_at = request.received_at or timezone.now()
    CollectionObservation.objects.bulk_create([
        CollectionObservation(
            request=request, run_id=request.scope_run.run_id, scope_run=None,
            source_dataset_id=request.scope_run.source_dataset_id,
            observation_kind=APPEARANCE_KIND, source_subject_kind="post_appearance",
            receipt_ordinal=position, source_identifier=value or "", source_identifier_is_null=value is None,
            processing_outcome="received", original_retrieved_at=request.received_at,
            observed_at=observed_at, observation_key=digest([APPEARANCE_KIND, str(request.pk), position]),
        ) for position, value in enumerate(ids or [])
    ])
    return request


def adopt_staging_receipt(request):
    if request.body_lost is not None:
        staging_receipt(request)
        return request
    report = _legacy_report(request.scope_run.run)
    metadata = report.get("staging_responses", {}).get(str(request.pk))
    require(metadata is not None, "staging response accounting missing; reconcile before retry")
    accounted = str(request.pk) in report.get("prefetch_accounted_requests", [])
    return write_staging_receipt(request, metadata, selection_accounted=accounted)


def account_staging_response(run, request, response):
    """Caller holds the job/run fence; selection and its marker commit together."""
    request = CollectionRequest.objects.select_for_update().select_related("scope_run__run").get(pk=request.pk)
    require(request.scope_run.run_id == run.pk, "staging response accounting owner changed")
    request = adopt_staging_receipt(request)
    ensure_staging_bytes(run)
    require(request.raw_count == response["raw_results"] and request.response_bytes == response["response_bytes"],
            "staging response accounting differs from receipt")
    if request.selection_accounted:
        return False
    require(request.raw_count is not None, "unknown staging response cannot be selected")
    run.selected_count += request.raw_count
    run.physical_bytes_received += request.response_bytes
    run.save(update_fields=["selected_count", "physical_bytes_received", "updated_at"])
    request.selection_accounted = True
    request.save(update_fields=["selection_accounted"])
    return True
