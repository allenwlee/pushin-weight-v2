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
from core.models import CollectionObservation, CollectionRequest
from monitor.backfill_retry import RetryControl

CATEGORY = "x_backfill_staging"
APPEARANCE_KIND = "x_request_appearance"


def _legacy_report(run):
    """Explicit write-boundary adoption only; operational readers are typed."""
    if run.report:
        return run.report
    if run.legacy_archive_id:
        document = read_document(run.legacy_archive)
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
    request = CollectionRequest.objects.select_for_update().select_related("scope_run__run").get(pk=request.pk)
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
            source_dataset=request.scope_run.source_dataset,
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
