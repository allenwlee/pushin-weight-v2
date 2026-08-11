"""Celery tasks for monitor.

`run_cycle` is the main entry point — invoked by Celery beat on a
schedule or on-demand via `python manage.py run_cycle --async`.

The actual cycle logic lives in `monitor.cycle.CycleRunner`; this file
just wires the cycle loop to Celery + Django.
"""

from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

from x_monitor.config import load_config

logger = logging.getLogger(__name__)


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

    logger.info("monitor run_cycle starting (dry_run=%s)", dry_run)
    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(cfg=cfg, 
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
