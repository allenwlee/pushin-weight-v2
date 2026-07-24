"""One-time backfill: fetch Jul 22-23 2026 posts from TwitterAPI.io.

Usage:
    python manage.py backfill_jul22_23 --dry-run    # plan only, show what would run
    python manage.py backfill_jul22_23               # fetch + classify + persist

Reuses the existing CycleRunner with since_time clamped to Jul 22 00:00 UTC.
TwitterAPI.io automatically adds until_time:<now>, so this fetches everything
from Jul 22 to the present — the pipeline's dedup logic handles already-ingested
posts (Jul 24+).

Delete this file after the backfill completes successfully.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand

JUL22_EPOCH = int(datetime(2026, 7, 22, 0, 0, 0, tzinfo=timezone.utc).timestamp())


class Command(BaseCommand):
    help = "One-time backfill of Jul 22-23 posts from TwitterAPI.io."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Plan calls only; don't fetch or write.",
        )

    def handle(self, *args, **options) -> None:
        # Clamp the search window to Jul 22 00:00 UTC onward
        settings.X_MONITOR_CYCLE_SINCE_TIME = JUL22_EPOCH

        # Also apply a generous limit per call to capture the full window
        settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = 200
        settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = 10

        from monitor.cycle import CycleRunner

        runner = CycleRunner(
            dry_run=options["dry_run"],
            cycle_kind="manual",
        )
        stats = runner.run()

        self.stdout.write(
            json.dumps(
                {
                    "run_id": stats["run_id"],
                    "status": stats["status"],
                    "since_time_epoch": JUL22_EPOCH,
                    "since_time_utc": "2026-07-22T00:00:00Z",
                    "dry_run": options["dry_run"],
                    "n_calls_planned": stats["totals"].get("n_calls_planned", 0),
                    "n_calls_run": stats["totals"].get("n_calls_run", 0),
                    "n_inserted": stats["totals"].get("n_inserted", 0),
                    "n_posts_seen": stats["totals"].get("n_posts_seen", 0),
                    "errors": stats.get("errors", []),
                },
                indent=2,
                default=str,
            )
        )
