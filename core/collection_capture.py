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


def _has_legacy_fields(model, *names):
    present = {field.name for field in model._meta.fields}
    return all(name in present for name in names)


def observation_object_documents(observation):
    """Return a catalog object's captured fields, preferring frozen legacy evidence."""
    if observation.projection_kind == "github-catalog-object-v1":
        from core.github_catalog import observation_documents

        return observation_documents(observation)
    if observation.projection_kind == "hf-native-history-v1":
        from core.model_native_history import observation_documents

        return observation_documents(observation)
    if observation.projection_kind in {"publication-window-v1", "publication-row-v1"}:
        from core.model_history_publications import observation_documents

        return observation_documents(observation)
    if observation.projection_kind == "openrouter-catalog-object-v1":
        from core.model_inventory import openrouter_observation_documents

        return openrouter_observation_documents(observation)
    if (observation.legacy_archive_id is not None
            and observation.legacy_archive.capture_kind == "hf_inventory_evidence"):
        from core.hf_inventory_capture import inventory_documents

        return inventory_documents(observation)
    if observation.observation_kind == "hf_catalog_listing":
        require(
            observation.run.job.source_id == "hf" and observation.scope_run_id is not None,
            "HF listing has no namespace owner",
        )
        links = list(
            observation.inputs.filter(input_role="listing")
            .select_related("input_request__archive", "input_request__scope_run")
        )
        require(links, "HF listing needs captured page input")
        matching = []
        for link in links:
            request = link.input_request
            require(
                request is not None and request.scope_run_id == observation.scope_run_id
                and request.scope_run.run_id == observation.run_id
                and request.transport_outcome == "received" and request.http_status == 200
                and request.archive_id is not None
                and link.input_sha256 == request.archive.content_sha256,
                "HF listing capture ownership or checksum changed",
            )
            locator = link.row_locator
            require(
                isinstance(locator, str) and locator.isascii() and locator.isdecimal()
                and str(int(locator)) == locator,
                "HF listing position is invalid",
            )
            page = read_document(request.archive)
            position = int(locator)
            require(
                isinstance(page, list) and position < len(page)
                and isinstance(page[position], dict),
                "HF listing page or position is invalid",
            )
            listing = page[position]
            native_id = listing.get("id") or listing.get("modelId")
            require(
                isinstance(native_id, str)
                and native_id.casefold() == observation.source_identifier.casefold(),
                "HF listing identity changed",
            )
            if digest(listing) == observation.payload_sha256:
                matching.append(listing)
        require(
            matching and all(item == matching[0] for item in matching),
            "HF selected listing is absent or conflicts with its capture",
        )
        return matching[0], {}, {}
    if observation.legacy_archive_id is None:
        require(
            _has_legacy_fields(
                type(observation), "listing", "dimensions", "source_metadata",
            ),
            "unarchived observation has no retained source document",
        )
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


def run_report_document(run):
    """Read a completed run's report after its old JSON column is cleared."""
    job = run.job
    metric_reportable = job.purpose == "metric" and (
        job.operation == "collect_metrics"
        or job.operation == "legacy_direct"
        and job.definition.get("execution", {}).get("driver") == "persist_source"
        and job.contract_id is not None
    )
    if (
        job.source_id == "x" and job.purpose == "content"
        and job.operation == "x_backfill"
        and run.scopes.filter(
            scope_kind="x_backfill_result", scope_key="result",
            phase="backfill_result_v1",
        ).exists()
    ):
        from monitor.backfill_collection import backfill_report

        return backfill_report(run)
    if (
        job.source_id == "github" and job.purpose == "catalog"
        and job.operation == "github_catalog"
        and run.scopes.filter(phase="typed-github-catalog-v1").exists()
    ):
        from core.github_catalog import catalog_report

        return catalog_report(run)
    if (
        job.purpose == "catalog" and job.operation == "match_crosswalk"
        and run.scopes.filter(
            scope_kind="match_execution", scope_key="execution",
            phase="typed-product-match-v1",
        ).exists()
    ):
        from core.collection_matching import match_report

        return match_report(run)
    if (
        job.purpose == "catalog" and job.operation == "model_history"
        and run.scopes.filter(
            scope_kind="history_execution", scope_key="execution",
            phase="typed-history-v1",
        ).exists()
    ):
        from core.model_history_collection import history_report

        return history_report(run)
    if (
        metric_reportable and run.scopes.filter(
            scope_kind="numeric_projection", scope_key="saved-evidence",
            phase="projection_results_v1",
        ).exists()
    ):
        from core.source_metric_projection import projection_report

        projection = projection_report(run)
        attempt = run.attempts.order_by("-ordinal").only("accounting_complete").first()
        return {
            "projection": projection,
            "coverage": projection["coverage"],
            "physical_accounting_complete": (
                attempt.accounting_complete is True if attempt else False
            ),
        }
    if (
        metric_reportable and run.scopes.filter(
            scope_kind="metric_execution", scope_key="execution",
            phase="typed-metric-v1",
        ).exists()
    ):
        attempt = run.attempts.order_by("-ordinal").only("accounting_complete").first()
        return {
            "schedule_slot": run.scheduled_slot_at.isoformat() if run.scheduled_slot_at else None,
            "physical_bytes_received": run.physical_bytes_received,
            "physical_accounting_complete": attempt.accounting_complete is True if attempt else False,
        }
    if (
        job.purpose == "catalog"
        and (
            job.source_id == "hf" and job.operation in {"hf_catalog", "model_inventory"}
            or job.source_id == "openrouter" and job.operation == "model_inventory"
        )
        and run.scopes.filter(
            scope_kind="inventory_execution", scope_key="execution",
            phase="typed-inventory-v1",
        ).exists()
    ):
        from core.model_inventory import inventory_report

        return inventory_report(run)
    direct_hf_catalog = job.job_key.startswith("direct:execute_catalog:")
    archived_hf_catalog = (
        job.operation == "archived_run"
        and job.job_key == f"archive:run:{run.pk}"
        and job.definition.get("execution") == {"driver": "none", "executable": False}
        and isinstance(job.scope, dict)
        and {"inventory_version", "namespaces", "rules", "gaps"} <= set(job.scope)
    )
    if (
        job.source_id == "hf"
        and job.purpose == "catalog"
        and (direct_hf_catalog or archived_hf_catalog)
    ):
        from core.hf_catalog import catalog_report

        return catalog_report(run)
    retained_report = (
        run.report if _has_legacy_fields(type(run), "report") else None
    )
    if retained_report:
        return retained_report
    if run.legacy_archive_id is None:
        require(retained_report is not None, "unarchived run has no retained report")
        return retained_report
    document = read_document(run.legacy_archive)
    require(
        isinstance(document, dict) and isinstance(document.get("report"), dict),
        "invalid archived run report",
    )
    return document["report"]


def scope_object_documents(scope):
    """Return checkpoint wording from its preserved document after retirement."""
    # Live additive writers may still advance a copied scope. The final frozen
    # delta repairs its archive before old columns are removed.
    retained_fields = _has_legacy_fields(
        type(scope), "ownership", "cursor_history", "envelopes",
    )
    if retained_fields and (scope.legacy_archive_id is None or any((
        scope.ownership, scope.cursor_history, scope.envelopes,
    ))):
        return scope.ownership, scope.cursor_history, scope.envelopes
    require(scope.legacy_archive_id is not None, "unarchived scope has no retained document")
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
def capture_budget(claim, budget, *, scope_kind, scope_key, ownership, typed=False, **coordinates):
    """Bind existing public clients to a database scope for this execution only."""
    from core.collection_state import checkpoint_scope, fenced_run
    from core.models import CollectionScopeRun

    if typed:
        require(scope_kind == "metric_fetch", "typed budget capture needs a metric fetch scope")
        with fenced_run(claim) as (job, _):
            require(job.contract_id is not None, "metric capture needs a contract")
            contract = job.contract
        scope = checkpoint_scope(
            claim, scope_kind=scope_kind, scope_key=scope_key,
            ownership=ownership, projection_contract=contract,
            typed=True, **coordinates,
        )
    else:
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


def attach_metric_requests(run, observations, *, endpoint_paths=None):
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
    if source == "opencode":
        require(endpoint_paths is not None and len(endpoint_paths) == len(observations),
                "OpenCode request coordinates must come from the current capture")
    inputs, updated = [], []
    for position, observation in enumerate(observations):
        coordinate = (
            observation.source_identifier.casefold()
            if source == "hf"
            else endpoint_paths[position]
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
