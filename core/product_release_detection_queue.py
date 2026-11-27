"""Bounded, durable post-release detection without holding up harvesting."""

import hashlib
import logging
from collections import deque
from contextlib import contextmanager
from datetime import timedelta
from time import monotonic

from django.db import connection, transaction
from django.db.models import Case, Exists, F, OuterRef, Q, Subquery, Value, When
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


def enqueue_saved_post(post_id, *, evidence_ready=False):
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
                 attempts = CASE WHEN %s OR product_release_detection_states.completed_at >= product_release_detection_states.requested_at
                                 THEN 0 ELSE product_release_detection_states.attempts END,
                 retry_at = CASE WHEN %s OR product_release_detection_states.completed_at >= product_release_detection_states.requested_at
                                 THEN NULL ELSE product_release_detection_states.retry_at END,
                 error_code = CASE WHEN %s OR product_release_detection_states.completed_at >= product_release_detection_states.requested_at
                                   THEN '' ELSE product_release_detection_states.error_code END""",
            [post_id, timezone.now(), evidence_ready, evidence_ready, evidence_ready],
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


def _classified_drain_ids(due, limit):
    """Prioritize saved release answers without sorting the entire backlog by judgment history."""
    from core.classification_contract import COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
    from core.classified_product_releases import TARGETED_RELEASE_REVISION
    from x_monitor.attribution import _TWO_ROLE_ALLOWED_REVISION_TRIPLETS

    oldest = ("requested_at", "post_id")
    newest = ("-requested_at", "-post_id")
    # Bound the expensive per-post judgment checks. Include both ends of the
    # ordinary queue and the posts with actual source-linked finding claims:
    # an entire harvest page can otherwise consist of ordinary feed finals.
    probe_size = max(20, limit)
    by_age = due.values_list("post_id", flat=True)
    ids = set(by_age.order_by(*oldest)[:probe_size + 1])
    if len(ids) > probe_size:
        ids.update(by_age.order_by(*newest)[:probe_size])
        anchors = models.EventDossierClaim.objects.filter(
            scope_key__startswith="pulse-finding-v1:", event_dossier_source__post_id__isnull=False,
        ).values("event_dossier_source__post_id")
        with_findings = by_age.filter(post_id__in=anchors)
        ids.update(with_findings.order_by(*oldest)[:probe_size])
        ids.update(with_findings.order_by(*newest)[:probe_size])
    if not ids:
        return []

    selected = models.PostBrandClassificationState.objects.filter(
        post_id=OuterRef("post_id"), selected_final_judgment__isnull=False,
    )
    # Older selected feed finals can still carry a compressed prompt revision
    # without the release manifest. Only the publisher writes that manifest.
    combined = selected.filter(
        brand_id=OuterRef("brand_id"),
        prompt_version__in=[row[2] for row in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS],
        selected_final_judgment__changes_json__has_key="release_output",
    ).annotate(nonempty=Q(selected_final_judgment__changes_json__release_output__finding_keys__0__isnull=False))
    brand_results = models.PostBrand.objects.filter(post_id=OuterRef("post_id")).annotate(
        has_findings=Subquery(combined.values("nonempty")[:1]),
    )
    # A newly attached brand with no manifest makes the combined publication
    # pending. NULL sorts first, so one brand's older result cannot mask it.
    complete = brand_results.order_by(F("has_findings").asc(nulls_first=True)).values("has_findings")[:1]
    release_only = models.PostBrandClassificationJudgment.objects.filter(
        post_id=OuterRef("post_id"), stage="content", selector_version="pulse-release-only-v1",
        validation_state="release_only",
        prompt_version__in=[*[row[0] for row in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS], TARGETED_RELEASE_REVISION],
    ).annotate(nonempty=Q(changes_json__release_output__finding_keys__0__isnull=False))
    feed = Exists(selected.filter(prompt_version__in=[
        row[2] for row in _TWO_ROLE_ALLOWED_REVISION_TRIPLETS if row[2].startswith("stage1-two-role-merge-0731-v")
    ]))
    # Only read a boolean from each manifest. None means no such publication;
    # False means a published empty output. The locked reader still validates
    # the revision, complete brand set, fingerprint and extraction freshness.
    rows = due.filter(post_id__in=ids).annotate(
        combined=Subquery(complete),
        partial=Subquery(release_only.order_by("-created_at", "-pk").values("nonempty")[:1]),
        feed=feed,
    ).order_by(*oldest)
    findings, negatives, classified, waiting = deque(), [], [], []
    for post_id, combined, partial, feed_final in rows.values_list("post_id", "combined", "partial", "feed"):
        if combined or partial:
            findings.append(post_id)
        elif combined is not None or partial is not None:
            negatives.append(post_id)
        elif feed_final:
            classified.append(post_id)
        else:
            waiting.append(post_id)
        if limit == 1 and (combined is not None or partial is not None):
            # Preserve FIFO between published generations on a one-slot drain:
            # an association requeued at the tail must yield to a saved negative.
            return [post_id]
    recovery = negatives + classified + waiting
    page = []
    while findings and len(page) < limit:
        page.append(findings.pop())
        if findings and len(page) < limit:
            page.append(findings.popleft())
    if page and recovery and limit > 1:
        page.insert(min(2, limit - 1), recovery.pop(0))
    return (page + recovery)[:limit]


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
    if classified_only:
        ids = _classified_drain_ids(due, limit)
    else:
        ids = list(due.order_by("requested_at", "post_id").values_list("post_id", flat=True)[:limit])
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
                    # A reply can cite this post as its parent. The parent's
                    # durable outbox is also the wakeup for stale dependent
                    # evidence; enqueue inside this transaction so a worker
                    # crash cannot lose that wakeup.
                    dependent_query = models.TargetedExtractionState.objects.filter(
                        post__in_reply_to_id=post_id, role="model_release_extraction",
                        prompt_version="model-release-extraction-v2", status="succeeded", updated_at__lte=requested,
                    )
                    dependents = list(dependent_query.select_for_update(skip_locked=True).order_by("post_id")[:50])
                    for dependent in dependents:
                        dependent_id = dependent.post_id
                        if read_publication_findings(dependent_id) is None:
                            enqueue_saved_post(dependent_id)
                        models.TargetedExtractionState.objects.filter(pk=dependent.pk, status="succeeded").update(
                            updated_at=requested + timedelta(microseconds=1),
                        )
                    if dependent_query.exists():
                        models.ProductReleaseDetectionState.objects.filter(
                            post_id=post_id, requested_at=requested,
                        ).update(retry_at=timezone.now())
                        result["busy"] += 1
                        continue
                    findings = read_publication_findings(post_id)
                    if findings is None:
                        from pathlib import Path
                        from x_monitor.config import load_config

                        targeted_enabled = load_config(Path("config.yaml")).targeted_extraction.enabled
                        from x_monitor.attribution import _TWO_ROLE_ALLOWED_REVISION_TRIPLETS

                        two_role_revisions = {row[2] for row in _TWO_ROLE_ALLOWED_REVISION_TRIPLETS
                                              if row[2].startswith("stage1-two-role-merge-0731-v")}

                        outstanding = models.TargetedExtractionState.objects.filter(
                            post_id=post_id, role="model_release_extraction",
                            prompt_version="model-release-extraction-v2", status__in=["pending", "failed"],
                        ).first()
                        if outstanding is not None:
                            from pathlib import Path
                            from x_monitor.config import load_config

                            if outstanding.attempts >= load_config(Path("config.yaml")).harvest.enrichment.max_attempts:
                                models.ProductReleaseDetectionState.objects.filter(
                                    post_id=post_id, requested_at=requested,
                                ).update(attempts=MAX_ATTEMPTS, retry_at=None, error_code="release_extraction_exhausted")
                                result["failed"] += 1
                                continue

                        if outstanding is None and targeted_enabled:
                            from core.classified_product_releases import selected_release_revision
                            from core.targeted_extraction import request_targeted_release

                            if selected_release_revision(post_id) is not None:
                                previous = models.TargetedExtractionState.objects.filter(
                                    post_id=post_id, role="model_release_extraction",
                                    prompt_version="model-release-extraction-v2", status="succeeded",
                                ).first()
                                if previous is not None:
                                    request_targeted_release(post_id, model=previous.model, reopen=True)
                                    result["waiting_for_classification"] += 1
                                    continue

                        legacy_historical_report = enrichment.source_collection_job_id is not None
                        if legacy_historical_report:
                            from core.classified_product_releases import classifier_owns_release_extraction

                            legacy_historical_report = not classifier_owns_release_extraction(post_id)
                        if legacy_historical_report:
                            from core.product_release_pipeline import persist_source
                            from core.product_release_sources import stored_posts

                            outcome = persist_source(stored_posts([post_id])[0])
                            models.ProductReleaseDetectionState.objects.filter(
                                post_id=post_id, requested_at=requested,
                            ).update(completed_at=requested, attempts=0, retry_at=None, error_code="")
                            result["processed"] += 1
                            result["candidates"] += int(outcome["disposition"] != "no_signal")
                            continue
                        if (enrichment.source_collection_job_id is not None
                                and models.TargetedExtractionState.objects.filter(
                                    post_id=post_id, role="model_release_extraction",
                                    prompt_version="model-release-extraction-v1", status="succeeded",
                                ).exists()):
                            models.ProductReleaseDetectionState.objects.filter(
                                post_id=post_id, requested_at=requested,
                            ).update(completed_at=requested, attempts=0, retry_at=None, error_code="")
                            result["processed"] += 1
                            continue

                        brands = set(models.PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))
                        rows = list(models.PostBrandClassificationState.objects.filter(
                            post_id=post_id, brand_id__in=brands,
                        ).values_list("brand_id", "outcome", "prompt_version",
                                      "selected_final_judgment__content_judgment__canonical_judgment"))
                        from core.product_release_intake import SourceRecord, TextEvidence, detect

                        post = enrichment.post
                        texts = [TextEvidence(locator="post", kind="raw", text=post.text or "")]
                        if post.quoted_text:
                            texts.append(TextEvidence(locator="quote", kind="quote", text=post.quoted_text))
                        parent_text = models.Post.objects.filter(pk=post.in_reply_to_id).values_list("text", flat=True).first()
                        if parent_text:
                            texts.append(TextEvidence(locator="parent", kind="quote", text=parent_text))
                        candidate = detect(SourceRecord(namespace="x", source_id=str(post_id), texts=tuple(texts)))
                        completed_without_release = (
                            outstanding is None and enrichment.classification_status == "succeeded"
                            and brands and {row[0] for row in rows} == brands
                            and all(row[1] in {"classified", "context_missing"} and row[2] in two_role_revisions
                                    for row in rows)
                            and all(isinstance(row[3], dict) and "releases_updates" not in row[3].get("post_types", [])
                                    for row in rows)
                            and candidate is None
                            and not models.PostBrandSignal.objects.filter(
                                post_id=post_id, post_type_id="releases_updates",
                            ).exists()
                        )
                        if completed_without_release:
                            models.ProductReleaseDetectionState.objects.filter(
                                post_id=post_id, requested_at=requested,
                            ).update(completed_at=requested, attempts=0, retry_at=None, error_code="")
                            result["processed"] += 1
                            continue
                        if (targeted_enabled and enrichment.source_collection_job_id is None
                                and enrichment.classification_status == "succeeded" and brands
                                and {row[0] for row in rows} == brands
                                and all(row[2] in two_role_revisions for row in rows)
                                and (candidate is not None or models.PostBrandSignal.objects.filter(
                                    post_id=post_id, post_type_id="releases_updates",
                                ).exists() or any(isinstance(row[3], dict) and "releases_updates" in row[3].get("post_types", [])
                                                  for row in rows))):
                            from core.targeted_extraction import request_targeted_release

                            model = models.PostBrandClassificationJudgment.objects.filter(
                                post_id=post_id, stage="content", validation_state="validated",
                            ).order_by("-created_at").values_list("model", flat=True).first() or "unassigned"
                            request_targeted_release(post_id, model=model)
                        elif (enrichment.source_collection_job_id is None
                              and enrichment.classification_status == "succeeded" and brands
                              and {row[0] for row in rows} == brands
                              and any(row[2] not in two_role_revisions for row in rows)):
                            models.PostEnrichmentState.objects.filter(pk=post_id, classification_status="succeeded").update(
                                classification_status="pending", classification_attempts=0,
                                classification_next_attempt_at=None, classification_error_code="",
                            )
                        result["waiting_for_classification"] += 1
                        models.ProductReleaseDetectionState.objects.filter(
                            post_id=post_id, requested_at=requested,
                        ).update(retry_at=timezone.now() + timedelta(minutes=5))
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
