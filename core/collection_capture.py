"""Shared immutable source captures and individually accounted transport calls.

Request intent is committed before dispatch. Finalization and cursor publication
remain inside the caller's fenced transaction; this module never calls a provider.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from urllib.parse import parse_qsl, unquote, urlsplit

from django.db import transaction
from django.utils import timezone

from core.measurement_taxonomy import digest, require
from core.models import (
    HTTP_METHODS,
    CollectionAttempt,
    CollectionEvidenceArchive,
    CollectionObservationInput,
    CollectionRequest,
)


def archive_document(
    body,
    *,
    encoding="wire-bytes-v1",
    media_type="application/json",
    capture_kind="response",
):
    """Deduplicate bytes without deduplicating actual requests."""
    require(isinstance(body, bytes), "capture body must be bytes")
    require(
        encoding
        in {
            "wire-bytes-v1",
            "decoded-body-v1",
            "selected-json-canonical-v1",
            "legacy-json-canonical-v1",
            "legacy-jsonb-text-v1",
        },
        "unsupported capture encoding",
    )
    fingerprint = hashlib.sha256(body).hexdigest()
    archive, _ = CollectionEvidenceArchive.objects.get_or_create(
        content_sha256=fingerprint,
        encoding=encoding,
        defaults={
            "body": body,
            "byte_count": len(body),
            "media_type": media_type,
            "capture_kind": capture_kind,
        },
    )
    require(
        bytes(archive.body) == body and archive.byte_count == len(body),
        "capture hash collision",
    )
    return archive


def archive_legacy(document):
    """JSONB no longer proves original wire formatting; label that distinction."""
    body = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return archive_document(
        body, encoding="legacy-json-canonical-v1", capture_kind="legacy_snapshot"
    )


def read_document(archive):
    """Return whole source evidence for parsing/replay, never execution settings."""
    body = bytes(archive.body)
    require(
        hashlib.sha256(body).hexdigest() == archive.content_sha256,
        "capture checksum mismatch",
    )
    return json.loads(body)


def observation_object_documents(observation):
    """Return a catalog object's captured fields, preferring frozen legacy evidence."""
    if observation.legacy_archive_id is None:
        return observation.listing, observation.dimensions, observation.source_metadata
    document = read_document(observation.legacy_archive)
    require(
        isinstance(document, dict)
        and all(isinstance(document.get(key), dict) for key in (
            "listing", "dimensions", "source_metadata",
        )),
        "invalid archived observation object",
    )
    return document["listing"], document["dimensions"], document["source_metadata"]


def scope_object_documents(scope):
    """Return checkpoint wording from its preserved document after retirement."""
    # Live additive writers may still advance a copied scope. The final frozen
    # delta repairs its archive before old columns are removed.
    if scope.legacy_archive_id is None or any((
        scope.ownership, scope.cursor_history, scope.envelopes,
    )):
        return scope.ownership, scope.cursor_history, scope.envelopes
    document = read_document(scope.legacy_archive)
    require(
        isinstance(document, dict)
        and isinstance(document.get("ownership"), dict)
        and all(isinstance(document.get(key), list) for key in (
            "cursor_history", "envelopes",
        )),
        "invalid archived scope document",
    )
    return document["ownership"], document["cursor_history"], document["envelopes"]


def checked_endpoint(url):
    require(isinstance(url, str), "request URL required")
    parsed = urlsplit(url)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password,
        "public HTTPS endpoint required",
    )
    prohibited = {
        "authorization",
        "api_key",
        "apikey",
        "access_token",
        "token",
        "password",
        "secret",
        "key",
    }
    require(
        not any(key.casefold() in prohibited for key, _ in parse_qsl(parsed.query)),
        "credential-bearing URL cannot be stored",
    )
    return url


@transaction.atomic
def begin_request(
    attempt, scope, *, endpoint_url, method="GET", cursor=None, now=None, **options
):
    attempt = CollectionAttempt.objects.select_for_update().get(pk=attempt.pk)
    require(
        attempt.run_id == scope.run_id, "request scope and attempt must share a run"
    )
    require(method in HTTP_METHODS, "unsupported HTTP method")
    require(
        attempt.outcome == "running" and attempt.finished_at is None,
        "request requires running attempt",
    )
    require(
        attempt.lease_expires_at and attempt.lease_expires_at > (now or timezone.now()),
        "request attempt lease expired",
    )
    require(
        attempt.reserved_requests is not None
        and attempt.requests.count() < attempt.reserved_requests,
        "finite request reservation required and must not be exhausted",
    )
    allowed = {
        "requested_start_at",
        "requested_end_at",
        "requested_start_date",
        "requested_end_date",
        "request_revision",
        "request_group",
        "request_config",
        "request_category",
        "etag",
    }
    require(set(options) <= allowed, "unsupported request option")
    previous = attempt.requests.order_by("-ordinal").first()
    return CollectionRequest.objects.create(
        attempt=attempt,
        scope_run=scope,
        ordinal=previous.ordinal + 1 if previous else 1,
        endpoint_url=checked_endpoint(endpoint_url),
        http_method=method,
        cursor_before=cursor,
        started_at=now or timezone.now(),
        **options,
    )


@transaction.atomic
def finish_request(
    request,
    *,
    outcome,
    body=None,
    http_status=None,
    cursor=None,
    error_code=None,
    retry_after_at=None,
    response_bytes=None,
    body_encoding="wire-bytes-v1",
    body_media_type="application/json",
    now=None,
):
    attempt = CollectionAttempt.objects.select_for_update().get(pk=request.attempt_id)
    stored = CollectionRequest.objects.select_for_update().get(pk=request.pk)
    require(stored.transport_outcome == "pending", "request already finalized")
    require(
        outcome in {"received", "timeout", "transport_error", "unknown"},
        "unsupported transport outcome",
    )
    archive = (
        archive_document(body, encoding=body_encoding, media_type=body_media_type)
        if body is not None
        else None
    )
    stored.archive = archive
    stored.received_at = now or timezone.now() if outcome == "received" else None
    stored.transport_outcome = outcome
    stored.http_status = http_status
    stored.cursor_after = cursor
    stored.error_code = error_code
    stored.retry_after_at = retry_after_at
    require(
        response_bytes is None or type(response_bytes) is int and response_bytes >= 0,
        "invalid observed response byte count",
    )
    stored.response_bytes = (
        response_bytes
        if response_bytes is not None
        else len(body)
        if body is not None
        else None
    )
    stored.accounting_complete = outcome == "received"
    stored.save()
    attempt.actual_requests += 1
    attempt.actual_response_bytes += stored.response_bytes or 0
    attempt.unknown_sent_requests += int(outcome != "received")
    attempt.save(
        update_fields=[
            "actual_requests",
            "actual_response_bytes",
            "unknown_sent_requests",
        ]
    )
    return stored


def link_request(observation, request, *, role="response", row_locator=None):
    require(
        observation.run_id == request.attempt.run_id,
        "request input must share observation run",
    )
    require(request.archive_id is not None, "response input requires saved evidence")
    return CollectionObservationInput.objects.get_or_create(
        observation=observation,
        input_request=request,
        input_role=role,
        defaults={
            "row_locator": row_locator,
            "input_sha256": request.archive.content_sha256,
        },
    )[0]


class RequestCapture:
    """Connect a provider client to the shared intent/receipt writer."""

    def __init__(self, claim):
        self.claim = claim

    def start(self, scope, endpoint_url, *, etag=None):
        from core.collection_state import fenced_run

        with fenced_run(self.claim):
            return begin_request(
                CollectionAttempt.objects.get(pk=self.claim.attempt_id),
                scope,
                endpoint_url=endpoint_url,
                cursor=scope.cursor,
                etag=etag,
                requested_start_at=scope.requested_start_at,
                requested_end_at=scope.requested_end_at,
                requested_start_date=scope.requested_start_date,
                requested_end_date=scope.requested_end_date,
                request_revision=scope.requested_revision,
            )

    def received(
        self,
        request,
        *,
        body,
        status,
        response_bytes=None,
        error_code=None,
        media_type="application/json",
    ):
        return finish_request(
            request,
            outcome="received",
            body=body,
            http_status=status,
            response_bytes=response_bytes,
            error_code=error_code,
            body_encoding="decoded-body-v1",
            body_media_type=media_type,
        )

    def failed(self, request, *, error_code="request_error"):
        current = CollectionRequest.objects.get(pk=request.pk)
        if current.transport_outcome != "pending":
            return current
        return finish_request(request, outcome="transport_error", error_code=error_code)

    @staticmethod
    @transaction.atomic
    def response_metadata(request, *, etag=None, cursor=None, retry_after_at=None):
        """Record reply coordinates after provider-specific URL validation.

        These are transport facts, including a late reply. Cursor publication
        remains separately fenced by checkpoint_scope.
        """
        stored = CollectionRequest.objects.select_for_update().get(pk=request.pk)
        require(stored.transport_outcome == "received", "received reply required")
        require(
            etag is None
            or (
                isinstance(etag, str)
                and len(etag) <= 256
                and not any(ord(char) < 32 for char in etag)
            ),
            "invalid response ETag",
        )
        stored.response_etag = etag
        stored.cursor_after = cursor
        stored.retry_after_at = retry_after_at
        stored.save(update_fields=["response_etag", "cursor_after", "retry_after_at"])
        return stored


@contextmanager
def capture_budget(claim, budget, *, scope_kind, scope_key, ownership, **coordinates):
    """Bind existing public clients to a database scope for this execution only."""
    from core.collection_state import fenced_run
    from core.models import CollectionScopeRun

    with fenced_run(claim) as (_, run):
        scope, _ = CollectionScopeRun.objects.get_or_create(
            run=run,
            scope_kind=scope_kind,
            scope_key=scope_key,
            defaults={"ownership": ownership, **coordinates},
        )
        require(scope.ownership == ownership, "request scope ownership changed")
    previous = (
        getattr(budget, "capture", None),
        getattr(budget, "collection_scope", None),
    )
    budget.capture, budget.collection_scope = RequestCapture(claim), scope
    try:
        yield scope
    finally:
        budget.capture, budget.collection_scope = previous


def capture_public_selection(request_id, payload):
    """Archive an admitted public subset without retaining unpublished members."""
    body = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    archive = archive_document(body, encoding="selected-json-canonical-v1")
    request = CollectionRequest.objects.get(pk=request_id)
    require(
        request.archive_id in (None, archive.pk), "selected evidence already differs"
    )
    request.archive = archive
    request.error_code = None
    request.save(update_fields=["archive", "error_code"])
    return archive


def attach_metric_requests(run, observations):
    """Connect directly collected metrics to their actual public replies."""
    from core.models import CollectionObservation

    requests = list(
        CollectionRequest.objects.filter(
            attempt__run=run,
            scope_run__scope_kind="metric_fetch",
            archive__isnull=False,
            transport_outcome="received",
        )
        .select_related("attempt", "archive")
        .defer("archive__body")
        .order_by("attempt__ordinal", "ordinal")
    )
    if not requests:
        return
    indexed = {}
    source = run.job.source_id
    for request in requests:
        path = unquote(urlsplit(request.endpoint_url).path)
        if source == "hf":
            if path.startswith("/api/models/"):
                coordinate = path.removeprefix("/api/models/").casefold()
            else:
                coordinate = (
                    path.removeprefix("/api/organizations/")
                    .removeprefix("/api/users/")
                    .removesuffix("/overview")
                    .casefold()
                )
        elif source == "opencode":
            coordinate = path
        else:
            coordinate = None
        indexed.setdefault(coordinate, []).append(request)
    inputs, updated = [], []
    for observation in observations:
        coordinate = (
            observation.source_identifier.casefold()
            if source == "hf"
            else observation.source_metadata.get("endpoint_path")
            if source == "opencode"
            else None
        )
        selected = indexed.get(coordinate, [])
        for request in selected:
            inputs.append(
                CollectionObservationInput(
                    observation=observation,
                    input_request=request,
                    input_role="response",
                    input_sha256=request.archive.content_sha256,
                )
            )
        if selected:
            observation.scope_run_id = selected[0].scope_run_id
            observation.input_set_sha256 = digest(
                [[str(r.pk), r.archive.content_sha256] for r in selected]
            )
            updated.append(observation)
    CollectionObservationInput.objects.bulk_create(
        inputs, ignore_conflicts=True, batch_size=1000
    )
    CollectionObservation.objects.bulk_update(
        updated, ["scope_run", "input_set_sha256"], batch_size=500
    )
