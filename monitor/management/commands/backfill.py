"""Backfill: run a harvest cycle with date-bounded search window.

Usage:
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00
    python manage.py backfill --since 2026-07-22                    # YYYY-MM-DD = 00:00 UTC
    python manage.py backfill --since 2026-07-22 --dry-run          # plan only

max_results and max_pages are computed from the time window using an
estimated daily post rate (~2,350/day). Override with --max-results
and --max-pages.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Estimated daily post volume across all brands — derived from Jul 21 baseline.
_EST_DAILY_POSTS = 2_350
# Typical number of calls per cycle (Call A + B/C specs).
_EST_CALLS_PER_CYCLE = 6
# TwitterAPI.io hard cap per page.
_TWEETS_PER_PAGE = 20
# Safety ceiling so we never request absurd page counts.
_MAX_PAGES_CEILING = 50
_MAX_RESULTS_CEILING = 1_000


def _parse_iso(ts: str) -> int:
    """Parse an ISO-ish timestamp to epoch seconds.

    Accepts YYYY-MM-DD (→ 00:00 UTC) and YYYY-MM-DDTHH:MM:SS.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise CommandError(f"Invalid timestamp '{ts}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.")


def _compute_params(since_epoch: int, until_epoch: int) -> tuple[int, int, int]:
    """Return (max_results, max_pages, est_total_posts) for a time window."""
    gap_seconds = until_epoch - since_epoch
    gap_hours = max(gap_seconds / 3600.0, 1.0)

    # Expected total posts in this window
    est_total = int(_EST_DAILY_POSTS * (gap_hours / 24))

    # Expected per-call — each call covers a slice of the brand set
    est_per_call = max(est_total // _EST_CALLS_PER_CYCLE, 50)

    # max_results: fetch enough to capture the expected volume per call
    max_results = min(max(est_per_call, 100), _MAX_RESULTS_CEILING)
    # max_pages: enough pages at _TWEETS_PER_PAGE to deliver max_results
    max_pages = min(
        max((max_results // _TWEETS_PER_PAGE) + 1, 5),
        _MAX_PAGES_CEILING,
    )

    return max_results, max_pages, est_total


class Command(BaseCommand):
    help = "Run a harvest cycle with date-bounded search window."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since",
            type=str,
            required=True,
            help="Lower bound (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, UTC).",
        )
        parser.add_argument(
            "--until",
            type=str,
            default=None,
            help="Upper bound (same format). Default: now.",
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
        parser.add_argument(
            "--max-results",
            type=int,
            default=None,
            help="Override computed per-call result cap.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Override computed per-call page cap.",
        )

    def handle(self, *args, **options) -> None:
        since_epoch = _parse_iso(options["since"])
        until_epoch = (
            _parse_iso(options["until"])
            if options["until"]
            else int(datetime.now(timezone.utc).timestamp())
        )

        max_results, max_pages, est_total = _compute_params(since_epoch, until_epoch)
        if options["max_results"] is not None:
            max_results = options["max_results"]
        if options["max_pages"] is not None:
            max_pages = options["max_pages"]

        gap_hours = (until_epoch - since_epoch) / 3600.0

        settings.X_MONITOR_CYCLE_SINCE_TIME = since_epoch
        settings.X_MONITOR_CYCLE_UNTIL_TIME = until_epoch
        settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = max_results
        settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = max_pages
        if options["brands"]:
            settings.X_MONITOR_CYCLE_BRAND_FILTER = options["brands"]

        since_label = options["since"]
        until_label = options["until"] or "now"

        self.stdout.write(
            f"Backfill {since_label} → {until_label}  "
            f"({gap_hours:.1f}h window, ~{est_total} posts expected, "
            f"max_results={max_results}, max_pages={max_pages})"
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
                    "gap_hours": round(gap_hours, 1),
                    "est_total_posts": est_total,
                    "max_results": max_results,
                    "max_pages": max_pages,
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
