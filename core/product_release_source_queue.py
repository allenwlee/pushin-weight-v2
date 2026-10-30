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


def enqueue_saved_observations(observation_ids):
    """Explicitly select existing public release observations for replay."""
    if (not isinstance(observation_ids, (tuple, list)) or not 1 <= len(observation_ids) <= 100
            or any(type(value) is not int or value <= 0 for value in observation_ids)):
        raise ValueError("select 1..100 source observation IDs")
    rows = []
    for observation_id in dict.fromkeys(observation_ids):
        try:
            with transaction.atomic():
                observation = models.CollectionObservation.objects.select_related("run__job", "resource_snapshot").get(
                    pk=observation_id,
                )
                marker = enqueue_github_release(observation)
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
