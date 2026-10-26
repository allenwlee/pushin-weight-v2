"""Typed X checkpoint receipts. Archived envelopes are migration evidence only.

A checkpoint may aggregate several provider pages. Appearance positions describe
that checkpoint's received sequence, never invented physical HTTP requests.
"""

from typing import NamedTuple

from django.db import connection, transaction
from django.utils import timezone

from core.benchmark_metric_store import aware_instant
from core.collection_capture import archive_legacy
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionObservation,
    CollectionObservationInput,
    CollectionRequest,
    CollectionScopeRareHit,
    CollectionScopeRequestUse,
    CollectionScopeRun,
)

PAGE_KIND = "x_page_checkpoint"
APPEARANCE_KIND = "x_page_appearance"
RETAINED = {"retained_post", "retained_inbox", "unaccounted"}


def _scope_compatibility():
    return {"ownership": {}} if any(
        field.name == "ownership" for field in CollectionScopeRun._meta.fields
    ) else {}


@transaction.atomic
def append_page_receipt(scope, envelope, *, cursor=None, legacy_archive=None):
    """Caller fences its run; this transaction also supports bounded old-data copy."""
    scope = CollectionScopeRun.objects.select_for_update().select_related("run").get(pk=scope.pk)
    require(scope.scope_kind == "x_query", "page receipt requires an X query scope")
    ordinal = scope.child_scopes.filter(scope_kind=PAGE_KIND).count()
    received = envelope.get("received_post_ids", [])
    require(type(received) is list and all(value is None or type(value) is str for value in received),
            "received IDs must preserve the original string/null sequence")
    exclusions = envelope.get("exclusions", [])
    excluded = {entry["appearance"]: entry for entry in exclusions}
    require(len(excluded) == len(exclusions) and all(
        type(position) is int and 0 <= position < len(received)
        and entry.get("post_id") == received[position]
        and type(entry.get("reason")) is str and 0 < len(entry["reason"]) <= 64
        and entry["reason"] not in RETAINED
        for position, entry in excluded.items()
    ), "invalid page exclusions")
    for field in ("raw_count", "pages_received", "retry_after_seconds"):
        value = envelope.get(field)
        require(value is None or type(value) is int and value >= 0, "invalid page " + field)
    if "received_post_ids" in envelope and "raw_count" in envelope:
        require(len(received) == envelope["raw_count"], "page received count differs from raw count")
    for field in ("collection_drained", "prefetch_replayed"):
        require(field not in envelope or type(envelope[field]) is bool, "invalid page " + field)
    observed_at = aware_instant(envelope["observed_at"]) if envelope.get("observed_at") else None
    archive = legacy_archive or archive_legacy(envelope)
    child = CollectionScopeRun.objects.create(
        run=scope.run, parent_scope=scope, source_dataset=scope.source_dataset,
        job_target=scope.job_target, scope_kind=PAGE_KIND,
        scope_key=digest(["x-page", scope.pk, ordinal]), **_scope_compatibility(),
        checkpoint_ordinal=ordinal, pages_received=envelope.get("pages_received"),
        raw_count=envelope.get("raw_count", 0), raw_count_known="raw_count" in envelope,
        received_ids_known="received_post_ids" in envelope,
        prefetch_replayed=envelope.get("prefetch_replayed"),
        response_status_code=envelope.get("response_status_code"),
        retry_after_seconds=envelope.get("retry_after_seconds"),
        phase="publication" if envelope.get("rare_gate_publication") else "page",
        outcome=envelope.get("reason") or "unknown", cursor=cursor,
        enumeration_complete=envelope.get("collection_drained", False),
        execution_state="completed", coverage_state="complete" if envelope.get("collection_drained") else "partial",
        legacy_archive=archive,
    )
    marker = CollectionObservation.objects.create(
        run=scope.run, scope_run=child, source_dataset=scope.source_dataset,
        source_subject_kind="aggregate", source_identifier=child.scope_key,
        observation_kind=PAGE_KIND, observation_key=digest(["x-page", child.pk]),
        original_retrieved_at=observed_at, observed_at=observed_at or timezone.now(),
        processing_outcome=envelope.get("reason"), legacy_archive=archive,
        payload_sha256=archive.content_sha256,
    )
    retained = set(envelope.get("post_ids", []))
    inbox = set(envelope.get("inbox_post_ids", []))
    appearances = [CollectionObservation(
        run=scope.run, scope_run=child, source_dataset=scope.source_dataset,
        source_subject_kind="post_appearance", source_identifier=identifier or "",
        source_identifier_is_null=identifier is None, receipt_ordinal=position,
        observation_kind=APPEARANCE_KIND, observation_key=digest(["x-appearance", child.pk, position]),
        original_retrieved_at=observed_at, observed_at=marker.observed_at,
        processing_outcome=(excluded[position]["reason"] if position in excluded else
                            "retained_post" if identifier in retained else
                            "retained_inbox" if identifier in inbox else "unaccounted"),
    ) for position, identifier in enumerate(received)]
    CollectionObservation.objects.bulk_create(appearances)
    # Membership remains on its original query/run. Historical deduplication
    # can credit a post to another query in the same job; prefer this run when
    # choosing the existing membership that this checkpoint used.
    members = {}
    for observation in CollectionObservation.objects.filter(
        run__job_id=scope.run.job_id, scope_run__scope_kind="x_query",
        source_subject_kind="post", post_id__in=retained,
    ).order_by("pk"):
        identifier = str(observation.post_id)
        if identifier not in members or observation.run_id == scope.run_id:
            members[identifier] = observation
    require(set(members) == retained, "page stored Post membership is missing")
    CollectionObservationInput.objects.bulk_create([
        CollectionObservationInput(observation=marker, input_observation=member, input_role="retained_post")
        for member in members.values()
    ])
    hit_ids = set(envelope.get("rare_hit_ids", []))
    from core.models import RareTypeSearchHit

    require(RareTypeSearchHit.objects.filter(pk__in=hit_ids).count() == len(hit_ids), "page rare hit is missing")
    CollectionScopeRareHit.objects.bulk_create([
        CollectionScopeRareHit(scope_run=child, rare_hit_id=identifier) for identifier in hit_ids
    ])
    if envelope.get("prefetch_request_id"):
        request = CollectionRequest.objects.select_related("scope_run__run").get(pk=envelope["prefetch_request_id"])
        require(request.scope_run.run.job_id == scope.run.job_id
                and str(request.scope_run.run_id) == envelope["prefetch_request_run_id"]
                and request.transport_outcome == "received" and request.http_status == 200
                and (request.archive_id is not None or request.request_category == "x_backfill_staging")
                and observed_at is not None,
                "page request identity or capture is invalid")
        CollectionScopeRequestUse.objects.create(scope_run=child, request=request, ordinal=0, observed_at=observed_at)
        # The database requires direct request inputs to share the request's
        # run. Cross-run replay keeps its lineage through the checkpoint's
        # ScopeRequestUse; it must never move or duplicate the original request.
        if request.scope_run.run_id == scope.run_id:
            CollectionObservationInput.objects.bulk_create([
                CollectionObservationInput(observation=observation, input_request=request, input_role="source_page")
                for observation in [marker, *appearances]
            ])
    CollectionObservation.objects.bulk_create([
        CollectionObservation(
            run=scope.run, scope_run=child, source_dataset=scope.source_dataset,
            source_subject_kind="aggregate", source_identifier=child.scope_key,
            observation_kind="x_page_diagnostic", receipt_ordinal=position,
            observation_key=digest(["x-page-diagnostic", child.pk, position]),
            processing_outcome=reason, original_retrieved_at=observed_at, observed_at=marker.observed_at,
        ) for position, reason in enumerate(envelope.get("relevancy_degraded", []))
    ])
    return child


def page_receipts(scope):
    """Read typed receipts; post_ids are membership sets, received IDs are ordered.

    The exact legacy post_ids sequence remains in the referenced archive. All
    operational consumers reconcile membership with set/distinct semantics.
    """
    result = []
    children = scope.child_scopes.filter(scope_kind=PAGE_KIND).order_by("checkpoint_ordinal")
    for child in children.prefetch_related("observations__inputs__input_observation", "request_uses__request__scope_run", "rare_hit_memberships"):
        require(child.checkpoint_ordinal == len(result), "page checkpoint order is incomplete")
        observations = list(child.observations.all())
        marker = next(row for row in observations if row.observation_kind == PAGE_KIND)
        appearances = sorted((row for row in observations if row.observation_kind == APPEARANCE_KIND),
                             key=lambda row: row.receipt_ordinal)
        require([row.receipt_ordinal for row in appearances] == list(range(len(appearances))),
                "page appearance order is incomplete")
        envelope = {
            "post_ids": sorted(str(link.input_observation.post_id) for link in marker.inputs.all()
                               if link.input_role == "retained_post"),
            "collection_drained": child.enumeration_complete,
        }
        if marker.original_retrieved_at is not None:
            envelope["observed_at"] = marker.original_retrieved_at.isoformat()
        if child.phase == "publication":
            envelope["rare_gate_publication"] = True
        else:
            envelope["reason"] = marker.processing_outcome
        for field in ("pages_received", "prefetch_replayed", "response_status_code", "retry_after_seconds"):
            if getattr(child, field) is not None:
                envelope[field] = getattr(child, field)
        if child.raw_count_known:
            envelope["raw_count"] = child.raw_count
        if child.received_ids_known:
            received = [None if row.source_identifier_is_null else row.source_identifier for row in appearances]
            envelope.update(
                received_post_ids=received,
                distinct_received_count=len({identifier for identifier in received if identifier}),
                exclusions=[{"appearance": row.receipt_ordinal, "post_id": received[row.receipt_ordinal],
                             "reason": row.processing_outcome} for row in appearances if row.processing_outcome not in RETAINED],
                relevancy_degraded=[row.processing_outcome for row in sorted(
                    (row for row in observations if row.observation_kind == "x_page_diagnostic"),
                    key=lambda row: row.receipt_ordinal)],
            )
            inbox = [row.source_identifier for row in appearances if row.processing_outcome == "retained_inbox"]
            if inbox:
                envelope["inbox_post_ids"] = inbox
        hits = list(child.rare_hit_memberships.values_list("rare_hit_id", flat=True))
        if hits:
            envelope["rare_hit_ids"] = sorted(hits)
        uses = list(child.request_uses.all())
        require(len(uses) <= 1, "grouped checkpoint cannot imply multiple physical requests")
        if uses:
            envelope.update(prefetch_request_id=str(uses[0].request_id),
                            prefetch_request_run_id=str(uses[0].request.scope_run.run_id))
        result.append(envelope)
    return result


def project_page_receipts(scope, envelopes, *, cursor=None, legacy_archive=None):
    """Explicit old-data/write-boundary copy. Normal readers use page_receipts."""
    count = scope.child_scopes.filter(scope_kind=PAGE_KIND).count()
    require(count <= len(envelopes), "typed page receipts exceed the supplied checkpoint")
    if count:
        require([_receipt_semantics(e) for e in page_receipts(scope)]
                == [_receipt_semantics(e) for e in envelopes[:count]],
                "typed page receipt differs from its saved checkpoint")
    for envelope in envelopes[count:]:
        append_page_receipt(scope, envelope, cursor=cursor, legacy_archive=legacy_archive)


def adopt_unprojected_page_receipts(scope):
    """Migration-only adoption, called under the importer's run fence.

    An empty retired column is allowed after successful projection. A surviving
    old prefix must be adopted before deploying typed-only checkpoint callers,
    or its missing owners fail the transaction. Runtime readers never call this.
    """
    if scope.envelopes:
        project_page_receipts(scope, scope.envelopes, legacy_archive=scope.legacy_archive)


class PageProjectionBatch(NamedTuple):
    last_id: int
    scanned: int
    inserted: int


@transaction.atomic
def project_page_receipts_batch(*, after_id=0, batch_size=100):
    """Explicit migration of a bounded query-scope batch, before JSON retirement.

    Stored Post membership and rare-hit adoption must run first. Old receipt
    timestamps are copied only when present; no request or page cursor is inferred.
    """
    require(type(after_id) is int and after_id >= 0, "invalid page migration cursor")
    require(type(batch_size) is int and 1 <= batch_size <= 500, "invalid page migration batch size")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
    scopes = list(CollectionScopeRun.objects.select_for_update().filter(
        scope_kind="x_query", pk__gt=after_id,
    ).order_by("pk")[:batch_size])
    inserted = 0
    for scope in scopes:
        if not scope.envelopes:
            continue  # Most historical query scopes have no page receipt.
        before = scope.child_scopes.filter(scope_kind=PAGE_KIND).count()
        project_page_receipts(scope, scope.envelopes, legacy_archive=scope.legacy_archive)
        inserted += scope.child_scopes.filter(scope_kind=PAGE_KIND).count() - before
    return PageProjectionBatch(scopes[-1].pk if scopes else after_id, len(scopes), inserted)


class PageParityBatch(NamedTuple):
    last_id: int
    scanned: int
    mismatched: int


def _receipt_semantics(envelope):
    """Normalize only equivalences already used by the completion verifier."""
    return {
        **{key: envelope.get(key) for key in (
            "pages_received", "raw_count", "received_post_ids", "reason",
            "prefetch_request_id", "prefetch_request_run_id", "prefetch_replayed",
            "response_status_code", "retry_after_seconds",
        )},
        "observed_at": aware_instant(envelope["observed_at"]) if envelope.get("observed_at") else None,
        "collection_drained": envelope.get("collection_drained", False),
        "rare_gate_publication": envelope.get("rare_gate_publication", False),
        "post_ids": set(envelope.get("post_ids", [])),
        "inbox_post_ids": set(envelope.get("inbox_post_ids", [])),
        "rare_hit_ids": set(envelope.get("rare_hit_ids", [])),
        "exclusions": sorted(envelope.get("exclusions", []), key=lambda entry: entry["appearance"]),
        "relevancy_degraded": envelope.get("relevancy_degraded", []),
    }


def page_receipt_parity_batch(*, after_id=0, batch_size=100):
    """Walk every query scope before retirement, including empty old lists.

    Pagination uses the existing primary key; empty lists need no child-count
    query. One grouped child-count query covers the entire bounded ID range.
    """
    from django.db.models import Count

    require(type(after_id) is int and after_id >= 0, "invalid page parity cursor")
    require(type(batch_size) is int and 1 <= batch_size <= 500, "invalid page parity batch size")
    scopes = list(CollectionScopeRun.objects.filter(scope_kind="x_query", pk__gt=after_id)
                  .only("pk", "envelopes").order_by("pk")[:batch_size])
    counts = dict(CollectionScopeRun.objects.filter(scope_kind=PAGE_KIND, parent_scope_id__in=[s.pk for s in scopes])
                  .values("parent_scope_id").annotate(count=Count("pk")).values_list("parent_scope_id", "count"))
    mismatched = 0
    for scope in scopes:
        if (counts.get(scope.pk, 0) != len(scope.envelopes)
            or scope.envelopes and [_receipt_semantics(e) for e in scope.envelopes] != [
                _receipt_semantics(e) for e in page_receipts(scope)
            ]):
            mismatched += 1
    return PageParityBatch(scopes[-1].pk if scopes else after_id, len(scopes), mismatched)


def copy_continuation_scopes(previous, run):
    """Copy execution scopes, remap sibling links, retain original evidence owners."""
    from core.collection_cursors import replace_scope_cursor_history

    copies, originals = {}, {}
    for original in previous.scopes.exclude(scope_kind__in=[
        "resource_group", PAGE_KIND, "x_model_call", "x_model_usage",
        "x_backfill_result", "x_checkpoint_import", "x_backfill_execution",
        "x_cycle_execution",
    ]).order_by("pk"):
        identifier = original.pk
        cursors = original.recorded_cursors
        originals[identifier] = original
        # A new instance keeps the original identity available for page inputs.
        copy = CollectionScopeRun.objects.get(pk=identifier)
        copy.pk, copy.run = None, run
        if copy.scope_kind == "x_query" and any(
            field.name == "envelopes" for field in CollectionScopeRun._meta.fields
        ):
            copy.envelopes = []
        copy.save(force_insert=True)
        replace_scope_cursor_history(copy, cursors)
        copies[identifier] = copy
    for identifier, copy in copies.items():
        original = originals[identifier]
        for field in ("parent_scope", "prerequisite_scope"):
            previous_id = getattr(original, field + "_id")
            if previous_id in copies:
                setattr(copy, field, copies[previous_id])
        copy.save(update_fields=["parent_scope", "prerequisite_scope"])
        if copy.scope_kind == "x_query":
            from core.collection_state import record_scope_request_uses

            receipts = page_receipts(original)
            children = list(original.child_scopes.filter(scope_kind=PAGE_KIND).order_by("checkpoint_ordinal"))
            for child, envelope in zip(children, receipts, strict=True):
                append_page_receipt(copy, envelope, cursor=child.cursor, legacy_archive=child.legacy_archive)
            record_scope_request_uses(copy, receipts)
