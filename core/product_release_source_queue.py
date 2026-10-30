"""Durable, bounded detection for saved public source observations."""

import logging
from datetime import timedelta
from time import monotonic

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core import models

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def queue_reviewed_mapping(mapping):
    """Record bounded replay work atomically with a dedicated GitHub review."""
    if not connection.in_atomic_block:
        raise ValueError("mapping reconciliation needs the review transaction")
    if (mapping.source_id != "github" or mapping.purpose != "catalog"
            or mapping.source_subject_kind != "repository"
            or mapping.identity_snapshot.get("role") not in {"dedicated_model", "dedicated_product"}):
        return None
    first = models.CollectionObservation.objects.filter(
        source_identifier=mapping.normalized_identifier, observation_kind="releases",
        run__job__source_id="github", run__job__operation="github_catalog",
    ).order_by("pk").first()
    if first is None:
        return None
    marker, _ = models.CollectionScopeRun.objects.get_or_create(
        run_id=first.run_id, scope_kind="release_mapping_reconcile",
        scope_key=f"{mapping.pk}:{mapping.mapping_hash}",
        defaults={"resource_observation": first, "phase": "mapping-reconcile-v1"},
    )
    if marker.phase != "mapping-reconcile-v1":
        raise ValueError("mapping reconciliation marker conflict")
    from core.product_release_acquisition import dispatch_due_recovery

    dispatch_due_recovery()
    return marker


def drain_mapping_reconciliations(*, limit=25, page_size=50, max_seconds=15):
    """Requeue finite pages of releases after review, with a durable cursor."""
    if (type(limit) is not int or not 1 <= limit <= 100
            or type(page_size) is not int or not 1 <= page_size <= 100
            or not 0 < max_seconds <= 120 or connection.vendor != "postgresql"):
        raise ValueError("invalid mapping reconciliation budget")
    due = models.CollectionScopeRun.objects.filter(
        scope_kind="release_mapping_reconcile", outcome="pending", raw_count__lt=MAX_ATTEMPTS,
    ).filter(Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now()))
    ids = list(due.order_by("retry_at", "pk").values_list("pk", flat=True)[:limit])
    result = {"processed": 0, "queued": 0, "failed": 0, "busy": 0}
    deadline = monotonic() + max_seconds
    for marker_id in ids:
        if monotonic() >= deadline:
            break
        try:
            with transaction.atomic():
                marker = due.select_for_update(skip_locked=True).filter(pk=marker_id).first()
                if marker is None:
                    result["busy"] += 1
                    continue
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                mapping_id, mapping_hash = marker.scope_key.split(":", 1)
                mapping = models.SourceSubjectMapping.objects.get(pk=mapping_id)
                if (mapping.mapping_hash != mapping_hash or mapping.source_id != "github"
                        or mapping.identity_snapshot.get("role") not in {"dedicated_model", "dedicated_product"}):
                    raise ValueError("reviewed mapping changed")
                after = int(marker.cursor or 0)
                rows = list(models.CollectionObservation.objects.filter(
                    source_identifier=mapping.normalized_identifier, observation_kind="releases",
                    run__job__source_id="github", run__job__operation="github_catalog", pk__gt=after,
                ).order_by("pk").values_list("pk", flat=True)[:page_size + 1])
                page = rows[:page_size]
                if page:
                    selected = enqueue_saved_observations(page, reconcile=True)
                    if any(row["outcome"] in {"missing", "ineligible", "failed"} for row in selected["observations"]):
                        raise ValueError("review reconciliation source invalid")
                    marker.cursor = str(page[-1])
                done = len(rows) <= page_size
                marker.outcome = "complete" if done else "pending"
                marker.execution_state = "completed" if done else "pending"
                marker.coverage_state = "complete" if done else "partial"
                marker.enumeration_complete = done
                marker.save(update_fields=["cursor", "outcome", "execution_state", "coverage_state", "enumeration_complete"])
            result["processed"] += 1
            result["queued"] += len(page)
        except Exception:
            logger.exception("Mapping reconciliation failed for marker %s", marker_id)
            result["failed"] += 1
            with transaction.atomic():
                marker = due.select_for_update(skip_locked=True).filter(pk=marker_id).first()
                if marker is None:
                    continue
                marker.raw_count += 1
                terminal = marker.raw_count >= MAX_ATTEMPTS
                marker.outcome = "failed" if terminal else "pending"
                marker.execution_state = "failed" if terminal else "pending"
                marker.coverage_state = "unavailable" if terminal else "partial"
                marker.error_code = "mapping_reconciliation_error"
                marker.retry_at = None if terminal else timezone.now() + timedelta(hours=6)
                marker.save(update_fields=["raw_count", "outcome", "execution_state", "coverage_state", "error_code", "retry_at"])
    result["due_remaining"] = due.exists()
    return result


def enqueue_github_release(observation, *, captured_row=None):
    """Commit one immutable observation and its detection marker together."""
    if not connection.in_atomic_block:
        raise ValueError("source detection marker needs the collection transaction")
    if (observation.run.job.source_id != "github"
            or observation.run.job.operation != "github_catalog"
            or observation.observation_kind != "releases"
            or observation.post_id is not None):
        raise ValueError("public GitHub release observation required")
    from core.collection_capture import observation_object_documents
    from core.measurement_taxonomy import digest

    row = observation_object_documents(observation)[0] if captured_row is None else captured_row
    if (not isinstance(row, dict) or row.get("draft") is not False or not row.get("published_at")
            or digest(row) != observation.payload_sha256
            or observation.resource_snapshot.resource_kind != "releases"):
        raise ValueError("saved public release evidence does not match")
    marker, _ = models.CollectionScopeRun.objects.get_or_create(
        run_id=observation.run_id, scope_kind="release_detection", scope_key=str(observation.pk),
        defaults={"resource_observation": observation, "phase": "source-detection-v1"},
    )
    if marker.resource_observation_id != observation.pk or marker.phase != "source-detection-v1":
        raise ValueError("source detection marker identity conflict")
    return marker


def enqueue_saved_observations(observation_ids, *, reconcile=False):
    """Select saved releases; optionally revisit completed ones after new evidence."""
    if (not isinstance(observation_ids, (tuple, list)) or not 1 <= len(observation_ids) <= 100
            or any(type(value) is not int or value <= 0 for value in observation_ids)
            or type(reconcile) is not bool):
        raise ValueError("select 1..100 source observation IDs")
    rows = []
    for observation_id in dict.fromkeys(observation_ids):
        try:
            with transaction.atomic():
                observation = models.CollectionObservation.objects.select_related("run__job", "resource_snapshot").get(
                    pk=observation_id,
                )
                marker = enqueue_github_release(observation)
                if reconcile:
                    marker = models.CollectionScopeRun.objects.select_for_update().get(pk=marker.pk)
                    if marker.outcome == "complete":
                        marker.outcome = "pending"
                        marker.execution_state = "pending"
                        marker.coverage_state = "pending"
                        marker.enumeration_complete = False
                        marker.retry_at = None
                        marker.save(update_fields=["outcome", "execution_state", "coverage_state",
                                                   "enumeration_complete", "retry_at"])
                rows.append({"observation_id": observation_id, "outcome": marker.outcome})
        except models.CollectionObservation.DoesNotExist:
            rows.append({"observation_id": observation_id, "outcome": "missing"})
        except (ValueError, TypeError, KeyError, models.CollectionResourceSnapshot.DoesNotExist):
            rows.append({"observation_id": observation_id, "outcome": "ineligible"})
    return {"selected": len(rows), "observations": rows}


def drain_observations(*, limit=25, max_seconds=15, observation_ids=None):
    """Process saved sources without provider calls; failures stay retryable."""
    if type(limit) is not int or not 1 <= limit <= 100 or not 0 < max_seconds <= 120:
        raise ValueError("invalid source detection budget")
    if connection.vendor != "postgresql":
        raise ValueError("source detection queue requires PostgreSQL")
    if observation_ids is not None and (
        not isinstance(observation_ids, (tuple, list)) or not 1 <= len(observation_ids) <= 100
        or any(type(value) is not int or value <= 0 for value in observation_ids)
    ):
        raise ValueError("select 1..100 source observation IDs")
    from core.product_release_pipeline import ReleaseIdentityBusy, persist_source
    from core.product_release_sources import stored_observations

    due = models.CollectionScopeRun.objects.filter(
        scope_kind="release_detection", outcome="pending", raw_count__lt=MAX_ATTEMPTS,
    ).filter(Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now()))
    if observation_ids is not None:
        due = due.filter(resource_observation_id__in=observation_ids)
    marker_ids = list(due.order_by("retry_at", "pk").values_list("pk", flat=True)[:limit])
    result = {"selected": len(marker_ids), "processed": 0, "candidates": 0, "failed": 0, "busy": 0}
    deadline = monotonic() + max_seconds
    for marker_id in marker_ids:
        if monotonic() >= deadline:
            break
        try:
            with transaction.atomic():
                marker = due.select_for_update(skip_locked=True).filter(pk=marker_id).first()
                if marker is None:
                    result["busy"] += 1
                    continue
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                sources = stored_observations([marker.resource_observation_id])
                if (len(sources) != 1 or set(sources[0].limitations)
                        & {"body_over_2mb", "source_document_unavailable_or_invalid"}):
                    raise ValueError("saved source evidence is unavailable or invalid")
                outcome = persist_source(sources[0])
                marker.outcome = "complete"
                marker.execution_state = "completed"
                marker.coverage_state = "complete"
                marker.error_code = None
                marker.retry_at = None
                marker.enumeration_complete = True
                marker.save(update_fields=["outcome", "execution_state", "coverage_state", "error_code",
                                           "retry_at", "enumeration_complete"])
            result["processed"] += 1
            result["candidates"] += int(outcome["disposition"] != "no_signal")
        except ReleaseIdentityBusy:
            result["busy"] += 1
        except Exception:
            logger.exception("Source release detection failed for marker %s", marker_id)
            result["failed"] += 1
            with transaction.atomic():
                marker = models.CollectionScopeRun.objects.select_for_update(skip_locked=True).filter(
                    pk=marker_id, scope_kind="release_detection", outcome="pending",
                ).first()
                if marker is None:
                    continue
                marker.raw_count += 1
                terminal = marker.raw_count >= MAX_ATTEMPTS
                marker.outcome = "failed" if terminal else "pending"
                marker.execution_state = "failed" if terminal else "pending"
                marker.coverage_state = "unavailable" if terminal else "partial"
                marker.error_code = "source_detection_error"
                marker.retry_at = None if terminal else timezone.now() + timedelta(hours=6)
                marker.save(update_fields=["raw_count", "outcome", "execution_state", "coverage_state",
                                           "error_code", "retry_at"])
    result["due_remaining"] = due.exists()
    return result
