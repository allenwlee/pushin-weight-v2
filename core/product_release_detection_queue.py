"""Bounded, durable post-release detection without holding up harvesting."""

import hashlib
import logging
from contextlib import contextmanager
from datetime import timedelta
from time import monotonic

from django.db import connection, transaction
from django.db.models import Case, Exists, F, OuterRef, Q, Value, When
from django.db.models.functions import Greatest
from django.utils import timezone

from core import models

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
ENQUEUE_BATCH_SIZE = 2000
DEFAULT_DRAIN_LIMIT = 50


@contextmanager
def _bounded_queue_lock():
    """Bound queue writes without loosening or leaking caller timeouts."""
    with connection.cursor() as cursor:
        cursor.execute("""SELECT current_setting('lock_timeout'),
                                 current_setting('statement_timeout'),
                                 (SELECT setting::bigint FROM pg_settings WHERE name = 'lock_timeout'),
                                 (SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout')""")
        lock_previous, statement_previous, lock_ms, statement_ms = cursor.fetchone()
        cursor.execute("SELECT set_config('lock_timeout', %s, true), set_config('statement_timeout', %s, true)",
                       [f'{min(lock_ms or 250, 250)}ms', f'{min(statement_ms or 2000, 2000)}ms'])
    # On failure the surrounding savepoint or Post transaction rolls back SET.
    yield
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', %s, true), set_config('statement_timeout', %s, true)",
                       [lock_previous, statement_previous])


def enqueue_saved_post(post_id):
    """Write the outbox inside the transaction which persists the Post."""
    if not connection.in_atomic_block:
        raise ValueError("release detection outbox needs the Post transaction")
    with _bounded_queue_lock(), connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO product_release_detection_states
                   (post_id, requested_at, attempts, error_code)
               VALUES (%s, %s, 0, '')
               ON CONFLICT (post_id) DO UPDATE SET
                 requested_at = GREATEST(product_release_detection_states.requested_at + INTERVAL '1 microsecond', EXCLUDED.requested_at),
                 attempts = CASE WHEN product_release_detection_states.completed_at >= product_release_detection_states.requested_at
                                 THEN 0 ELSE product_release_detection_states.attempts END,
                 retry_at = CASE WHEN product_release_detection_states.completed_at >= product_release_detection_states.requested_at
                                 THEN NULL ELSE product_release_detection_states.retry_at END,
                 error_code = CASE WHEN product_release_detection_states.completed_at >= product_release_detection_states.requested_at
                                   THEN '' ELSE product_release_detection_states.error_code END""",
            [post_id, timezone.now()],
        )


def enqueue_posts(post_ids):
    """Record one reusable request per saved Post; no detector or provider work."""
    ids = sorted({str(value) for value in post_ids if value})
    queued = missing = 0
    for start in range(0, len(ids), ENQUEUE_BATCH_SIZE):
        batch = ids[start:start + ENQUEUE_BATCH_SIZE]
        try:
            with transaction.atomic(), _bounded_queue_lock():
                existing = set(models.Post.objects.filter(pk__in=batch).values_list("pk", flat=True))
                if existing:
                    now = timezone.now()
                    models.ProductReleaseDetectionState.objects.bulk_create(
                        [models.ProductReleaseDetectionState(post_id=pk, requested_at=now) for pk in sorted(existing)],
                        ignore_conflicts=True, batch_size=1000,
                    )
                    completed = Q(completed_at__isnull=False, completed_at__gte=F("requested_at"))
                    models.ProductReleaseDetectionState.objects.filter(post_id__in=existing).update(
                        requested_at=Greatest(F("requested_at") + Value(timedelta(microseconds=1)), Value(now)),
                        attempts=Case(When(completed, then=Value(0)), default=F("attempts"),
                                      output_field=models.ProductReleaseDetectionState._meta.get_field("attempts")),
                        retry_at=Case(When(completed, then=Value(None)), default=F("retry_at")),
                        error_code=Case(When(completed, then=Value("")), default=F("error_code")),
                    )
        except Exception:
            logger.exception("Release detection enqueue stopped after %s saved Posts", queued)
            return {"selected": len(ids), "queued": queued, "missing": missing,
                    "failed": missing + len(ids) - start, "status": "error"}
        missing += len(batch) - len(existing)
        queued += len(existing)
    return {"selected": len(ids), "queued": queued, "missing": missing, "failed": missing}


def drain_posts(*, limit=DEFAULT_DRAIN_LIMIT, max_seconds=30, post_ids=None, classified_only=False, before_post=None):
    """Process a bounded page; locks fence duplicate workers, not harvest writes."""
    if type(limit) is not int or not 1 <= limit <= 500 or not 0 < max_seconds <= 120:
        raise ValueError("invalid release detection budget")
    if connection.vendor != "postgresql":
        raise ValueError("release detection queue requires PostgreSQL")
    if post_ids is not None and (
        not isinstance(post_ids, (tuple, list)) or not 1 <= len(post_ids) <= 100
        or any(not isinstance(value, str) or not value or len(value) > 64 for value in post_ids)
    ):
        raise ValueError("select 1..100 Post IDs")
    deadline = monotonic() + max_seconds
    pending = Q(completed_at__isnull=True) | Q(completed_at__lt=F("requested_at"))
    due = models.ProductReleaseDetectionState.objects.filter(
        pending, Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now()), attempts__lt=MAX_ATTEMPTS,
    )
    if post_ids is not None:
        due = due.filter(post_id__in=post_ids)
    order = ["requested_at", "post_id"]
    if classified_only:
        from core.classification_contract import (
            COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS,
        )

        full_classification = Exists(models.PostBrandClassificationState.objects.filter(
            post_id=OuterRef("post_id"),
            prompt_version__in=[revision[2] for revision in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS],
            selected_final_judgment__isnull=False,
        ))
        release_only = Exists(models.PostBrandClassificationJudgment.objects.filter(
            post_id=OuterRef("post_id"), stage="content", selector_version="pulse-release-only-v1",
            validation_state="release_only",
            prompt_version__in=[revision[0] for revision in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS],
        ))
        due = due.alias(classified_ready=full_classification | release_only)
        # A backlog awaiting classification cannot occupy every bounded slot
        # ahead of newly published evidence. Full lineage is checked below.
        order.insert(0, "-classified_ready")
    ids = list(due.order_by(*order).values_list("post_id", flat=True)[:limit])
    result = {"selected": len(ids), "processed": 0, "candidates": 0, "failed": 0, "busy": 0}
    if classified_only:
        result.update(waiting_for_classification=0, unresolved=0, merged=0,
                      association_pending=0, association_limited=0)
    for post_id in ids:
        if monotonic() >= deadline:
            break
        if before_post is not None and not before_post():
            break
        requested = None
        try:
            with transaction.atomic():
                lock_key = int(hashlib.sha256(f"release-detection:{post_id}".encode()).hexdigest()[:15], 16)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_key])
                    if not cursor.fetchone()[0]:
                        result["busy"] += 1
                        continue
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                state = models.ProductReleaseDetectionState.objects.filter(
                    pending, post_id=post_id, attempts__lt=MAX_ATTEMPTS,
                ).filter(Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now())).first()
                if state is None:
                    continue
                requested = state.requested_at
                if classified_only:
                    from core.classified_product_releases import (
                        read_publication_findings,
                    )
                    from core.product_release_dossiers import (
                        resolve_saved_release_finding,
                    )

                    # Serialize with publication, while all model calls remain
                    # outside this transaction. No raw-post detector is called.
                    enrichment = models.PostEnrichmentState.objects.select_for_update(skip_locked=True).filter(post_id=post_id).first()
                    if enrichment is None:
                        result["busy"] += 1
                        continue
                    findings = read_publication_findings(post_id)
                    if findings is None:
                        result["waiting_for_classification"] += 1
                        continue
                    outcomes = [resolve_saved_release_finding(claim_id=row["anchor_claim_id"]) for row in findings]
                    unresolved = sum(row["status"] == "unresolved" for row in outcomes)
                    result["unresolved"] += unresolved
                    candidate_count = len(findings)
                else:
                    from core.product_release_pipeline import persist_source
                    from core.product_release_sources import stored_posts

                    outcome = persist_source(stored_posts([post_id])[0])
                    candidate_count = int(outcome["disposition"] != "no_signal")
                if not classified_only:
                    models.ProductReleaseDetectionState.objects.filter(
                        post_id=post_id, requested_at=requested,
                    ).update(completed_at=requested, attempts=0, retry_at=None, error_code="")
            if classified_only:
                from core.product_identity import reconcile_product_release_events
                from core.product_release_lineage import resolve_reported_lineage

                # Event graph locking comes before dossier row locks. Finish
                # identity writes first; a crash here leaves the saved generation
                # pending and replayable without another classification call.
                more_remaining = False
                merged_for_post = 0
                for row, outcome in zip(findings, outcomes):
                    if outcome["status"] == "unresolved":
                        continue
                    remaining_seconds = deadline - monotonic()
                    if remaining_seconds < 1:
                        more_remaining = True
                        break
                    association = reconcile_product_release_events(
                        claim_id=row["anchor_claim_id"], candidate_limit=DEFAULT_DRAIN_LIMIT, max_merges=1,
                        claim_limit=DEFAULT_DRAIN_LIMIT,
                        max_seconds=min(5, int(remaining_seconds)),
                    )
                    result["merged"] += len(association["merged_ids"])
                    merged_for_post += len(association["merged_ids"])
                    more_remaining |= association["more_remaining"]
                    result["association_limited"] += association.get("status") == "candidate_limit"
                    for index, _relation in enumerate(row.get("finding", {}).get("lineage_evidence", [])):
                        remaining_seconds = deadline - monotonic()
                        if remaining_seconds < 1:
                            more_remaining = True
                            break
                        lineage = resolve_reported_lineage(
                            child_claim_id=row["anchor_claim_id"], relation_index=index,
                            basis_version_id=None, max_candidates=DEFAULT_DRAIN_LIMIT,
                            max_subjects=2, max_seconds=min(5, int(remaining_seconds)),
                        )
                        more_remaining |= lineage["retryable"]
                        result["association_limited"] += lineage["status"] == "candidate_limit"
                progress = models.ProductReleaseDetectionState.objects.filter(
                    post_id=post_id, requested_at=requested,
                )
                if more_remaining:
                    deferred = {"retry_at": None, "error_code": ""}
                    if not merged_for_post:
                        # Put non-progressing work behind other ready requests.
                        # This changes queue ordering, not saved classification,
                        # and does not renew the accumulated failure allowance.
                        deferred["requested_at"] = Greatest(
                            F("requested_at") + Value(timedelta(microseconds=1)), Value(timezone.now()),
                        )
                    progress.update(**deferred)
                    result["association_pending"] += 1
                else:
                    progress.update(completed_at=requested, attempts=0, retry_at=None, error_code="")
            result["processed"] += 1
            result["candidates"] += candidate_count
        except Exception:
            logger.exception("Release detection failed for saved Post %s", post_id)
            result["failed"] += 1
            if requested is not None:
                state = models.ProductReleaseDetectionState.objects.filter(
                    pending, post_id=post_id, requested_at=requested
                ).first()
                if state is not None:
                    attempts = min(MAX_ATTEMPTS, state.attempts + 1)
                    models.ProductReleaseDetectionState.objects.filter(
                        pending, post_id=post_id, requested_at=requested, attempts=state.attempts
                    ).update(
                        attempts=attempts, retry_at=None if attempts == MAX_ATTEMPTS else timezone.now() + timedelta(hours=6),
                        error_code="processing_error",
                    )
    remaining = models.ProductReleaseDetectionState.objects.filter(
        pending, Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now()), attempts__lt=MAX_ATTEMPTS,
    )
    if post_ids is not None:
        remaining = remaining.filter(post_id__in=post_ids)
    result["due_remaining"] = remaining.exists()
    return result
