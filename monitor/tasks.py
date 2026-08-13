"""Celery tasks for monitor.

`run_cycle` is the main entry point — invoked by the Render cron or on-demand
via `python manage.py run_cycle --async`. Celery beat is intentionally not a
production scheduler.

The actual cycle logic lives in `monitor.cycle.CycleRunner`; this file
just wires the cycle loop to Celery + Django.
"""

from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

from x_monitor.config import load_config

logger = logging.getLogger(__name__)


@shared_task(
    name="monitor.tasks.refresh_trend_narratives",
    bind=False,
    autoretry_for=(),
    max_retries=0,
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=11 * 60,
    time_limit=12 * 60,
)
def refresh_trend_narratives(
    envelope: dict[str, object],
) -> dict[str, object]:
    """Consume one committed harvest envelope on the headline-only queue."""
    from monitor.trend_narrative_queue import coalesce_envelope
    from monitor.trend_narrative_tasks import (
        process_trend_narrative_envelope,
    )

    newest = coalesce_envelope(envelope)
    if newest is None:
        return {
            "status": "superseded_source",
            "source_cycle_id": envelope.get("source_cycle_id", ""),
            "slots_consumed": 0,
            "transport_started": 0,
            "published": 0,
            "failed": 0,
            "errors": [],
        }
    return process_trend_narrative_envelope(newest)


@shared_task(name="monitor.tasks.run_cycle", bind=True, max_retries=2)
def run_cycle(self, dry_run: bool = False) -> dict:
    """Run one x-monitor v2 harvest cycle.

    Returns a stats dict that Celery stores in the result backend.
    """
    if dry_run:
        return _execute_cycle(dry_run=True)

    from monitor.run_lock import harvest_writer_lock

    with harvest_writer_lock(
        execution_mode="live",
        entrypoint="celery.run_cycle",
    ) as lease:
        if not lease.acquired:
            contention = lease.contention.as_dict() if lease.contention else {}
            logger.warning("monitor run_cycle skipped: %s", contention)
            return {
                "status": "skipped",
                "degraded": {"writer_lock": contention},
                "calls": [],
                "totals": {"n_calls_planned": 0, "n_calls_run": 0},
            }
        return _execute_cycle(dry_run=False)


def _execute_cycle(*, dry_run: bool) -> dict:
    from monitor.cycle import CycleRunner
    from x_monitor.relevancy import build_binary_relevancy_llm_call

    logger.info("monitor run_cycle starting (dry_run=%s)", dry_run)
    cfg = load_config(Path("config.yaml"))
    relevancy_client = None
    try:
        from x_monitor.reattribute import build_anthropic_client_from_env

        relevancy_client = build_anthropic_client_from_env(cfg)
    except Exception as exc:
        logger.warning("failed to build relevancy client: %s", exc)
    relevancy_llm_call = build_binary_relevancy_llm_call(
        client=relevancy_client,
        model=cfg.llm.relevancy_model,
        timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
    )
    runner = CycleRunner(cfg=cfg,
        dry_run=dry_run,
        cycle_kind="scheduled",
        _relevancy_llm_call=relevancy_llm_call,
    )
    try:
        stats = runner.run()
        from monitor.trend_narrative_dispatch import (
            dispatch_harvest_completion,
        )

        dispatch_harvest_completion(stats, dry_run=dry_run)
        logger.info("monitor run_cycle complete: %s", stats.get("status"))
        return stats
    except Exception as exc:
        logger.exception("monitor run_cycle failed: %s", exc)
        # Don't auto-retry — Celery beat will fire the next cycle on schedule
        raise
