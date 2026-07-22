"""Celery tasks for monitor.

`run_cycle` is the main entry point — invoked by Celery beat on a
schedule or on-demand via `python manage.py run_cycle --async`.

The actual cycle logic lives in `monitor.cycle.CycleRunner`; this file
just wires the cycle loop to Celery + Django.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="monitor.tasks.run_cycle", bind=True, max_retries=2)
def run_cycle(self, dry_run: bool = False) -> dict:
    """Run one x-monitor v2 harvest cycle.

    Returns a stats dict that Celery stores in the result backend.
    """
    from monitor.cycle import CycleRunner

    logger.info("monitor run_cycle starting (dry_run=%s)", dry_run)
    runner = CycleRunner(
        dry_run=dry_run,
        cycle_kind="scheduled",
    )
    try:
        stats = runner.run()
        logger.info("monitor run_cycle complete: %s", stats.get("status"))
        return stats
    except Exception as exc:
        logger.exception("monitor run_cycle failed: %s", exc)
        # Don't auto-retry — Celery beat will fire the next cycle on schedule
        raise
