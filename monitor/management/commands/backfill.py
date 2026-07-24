"""Backfill: run a harvest cycle with date-bounded search window.

Usage:
    python manage.py backfill --since 2026-07-22 --until 2026-07-24
    python manage.py backfill --since 2026-07-22                 # until now
    python manage.py backfill --since 2026-07-22 --dry-run       # plan only

TwitterAPI.io requires a since_time lower bound; when set, until_time defaults
to now. Both accept ISO date strings (YYYY-MM-DD) and are converted to epoch
seconds at 00:00 UTC on the given date.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _iso_date_to_epoch(date_str: str) -> int:
    """Convert YYYY-MM-DD to epoch seconds at 00:00 UTC."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        raise CommandError(f"Invalid date '{date_str}'. Use YYYY-MM-DD.")


class Command(BaseCommand):
    help = "Run a harvest cycle with date-bounded search window."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since",
            type=str,
            required=True,
            help="Lower bound date (YYYY-MM-DD, UTC).",
        )
        parser.add_argument(
            "--until",
            type=str,
            default=None,
            help="Upper bound date (YYYY-MM-DD, UTC). Default: now.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Plan calls only; don't fetch or write.",
        )
        parser.add_argument(
            "--brands",
            type=str,
            default=None,
            help="Comma-separated brand nicknames to filter.",
        )

    def handle(self, *args, **options) -> None:
        since_epoch = _iso_date_to_epoch(options["since"])
        until_epoch = _iso_date_to_epoch(options["until"]) if options["until"] else None

        settings.X_MONITOR_CYCLE_SINCE_TIME = since_epoch
        if until_epoch is not None:
            settings.X_MONITOR_CYCLE_UNTIL_TIME = until_epoch
        settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = 200
        settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = 10
        if options["brands"]:
            settings.X_MONITOR_CYCLE_BRAND_FILTER = options["brands"]

        since_label = options["since"]
        until_label = options["until"] or "now"

        self.stdout.write(
            f"Backfill {since_label} → {until_label}  "
            f"(epoch {since_epoch} → {until_epoch or 'now'})"
            + ("  [DRY RUN]" if options["dry_run"] else "")
        )

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
                    "since": since_label,
                    "until": until_label,
                    "dry_run": options["dry_run"],
                    "n_calls_planned": stats["totals"].get("n_calls_planned", 0),
                    "n_calls_run": stats["totals"].get("n_calls_run", 0),
                    "n_inserted": stats["totals"].get("n_inserted", 0),
                    "errors": stats.get("errors", []),
                },
                indent=2,
                default=str,
            )
        )
