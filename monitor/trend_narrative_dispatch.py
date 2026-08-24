"""Transport-neutral post-harvest envelope and isolated Celery dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import connection, transaction

from x_monitor.config import load_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NarrativeDispatchResult:
    status: str
    task_id: str = ""


def dispatch_harvest_completion(
    stats: dict[str, Any],
    *,
    dry_run: bool,
    task=None,
) -> NarrativeDispatchResult:
    """Enqueue after eligible completion without changing harvest outcome."""
    envelope = _eligible_envelope(stats, dry_run=dry_run)
    if envelope is None:
        return NarrativeDispatchResult(status="ineligible")
    try:
        config = load_config(Path("config.yaml")).headline_narrative
    except Exception:
        logger.exception("headline dispatch config unavailable")
        return NarrativeDispatchResult(status="config_error")
    if not config.enqueue_active:
        return NarrativeDispatchResult(status="disabled")
    if task is None:
        from monitor.tasks import refresh_trend_narratives

        task = refresh_trend_narratives

    if connection.in_atomic_block:
        transaction.on_commit(
            lambda: _apply_safely(
                task,
                envelope=envelope,
                expires=config.task_expiry_seconds,
            )
        )
        return NarrativeDispatchResult(status="scheduled_after_commit")
    return _apply_safely(
        task,
        envelope=envelope,
        expires=config.task_expiry_seconds,
    )


def _eligible_envelope(
    stats: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any] | None:
    source_cycle_id = str(stats.get("run_id") or "")
    completed_at = str(stats.get("finished_at") or "")
    outcome = str(stats.get("status") or "")
    if (
        dry_run
        or outcome not in {"completed", "degraded"}
        or not source_cycle_id
        or not completed_at
    ):
        return None
    return {
        "schema_version": 1,
        "source_cycle_id": source_cycle_id,
        "completed_at": completed_at,
        "outcome": outcome,
        "dry_run": False,
    }


def _apply_safely(task, *, envelope: dict[str, Any], expires: int):
    try:
        if task.__module__ == "monitor.tasks":
            from monitor.trend_narrative_queue import update_latest_envelope

            update_latest_envelope(envelope, ttl_seconds=expires)
        result = task.apply_async(
            args=[envelope],
            queue="trend-narratives",
            expires=expires,
        )
    except Exception:
        logger.exception(
            "headline broker dispatch failed for source=%s",
            envelope["source_cycle_id"],
        )
        return NarrativeDispatchResult(status="broker_error")
    return NarrativeDispatchResult(
        status="enqueued",
        task_id=str(getattr(result, "id", "") or ""),
    )
