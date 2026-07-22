"""Management command: run one x-monitor v2 harvest cycle on demand.

Usage:
    python manage.py run_cycle                           # one cycle, live mode
    python manage.py run_cycle --dry-run                 # plan calls only, no network
    python manage.py run_cycle --async                   # enqueue via Celery, return immediately
    python manage.py run_cycle --json                    # emit stats JSON to stdout
    python manage.py run_cycle --brands minimax,qwen     # filter to specific brands
    python manage.py run_cycle --limit-per-call 20       # cap tweets per API call
    python manage.py run_cycle --skip-fetch              # plan + attribute + persist only
    python manage.py run_cycle --max-pages-per-call 3    # pagination cap

`--brands`, `--limit-per-call`, `--skip-fetch`, and `--max-pages-per-call`
are threaded through to CycleRunner via Django settings so cycle.py stays
untouched. Modeled on pushin_weight/crawler/management/commands/run_cycle.py.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run one x-monitor v2 harvest cycle."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Plan calls only; don't fetch tweets or write to the DB.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="enqueue",
            help="Enqueue the cycle as a Celery task and return immediately.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit cycle stats as JSON to stdout (instead of a human summary).",
        )
        parser.add_argument(
            "--brands",
            type=str,
            default=None,
            help="Comma-separated brand nicknames to filter the cycle (e.g. 'minimax,qwen').",
        )
        parser.add_argument(
            "--limit-per-call",
            type=int,
            default=None,
            help="Cap tweets returned per TwitterAPI.io call (default: 50).",
        )
        parser.add_argument(
            "--skip-fetch",
            action="store_true",
            dest="skip_fetch",
            help="Plan + attribute + persist only; skip TwitterAPI.io fetch.",
        )
        parser.add_argument(
            "--max-pages-per-call",
            type=int,
            default=None,
            help="Cap pagination depth per TwitterAPI.io call (default: 5).",
        )

    def handle(self, *args, **options) -> None:
        # Stash operator-supplied filters in Django settings so cycle.py
        # can read them without us having to change its constructor. This
        # pattern keeps the cross-cutting "operator wants a bounded cycle"
        # signal out of the cycle's own API surface.
        if options["brands"] is not None:
            settings.X_MONITOR_CYCLE_BRAND_FILTER = options["brands"]
        if options["limit_per_call"] is not None:
            settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = options["limit_per_call"]
        if options["max_pages_per_call"] is not None:
            settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = options["max_pages_per_call"]
        if options["skip_fetch"]:
            settings.X_MONITOR_CYCLE_SKIP_FETCH = True

        if options["enqueue"]:
            from monitor.tasks import run_cycle as run_cycle_task

            async_result = run_cycle_task.delay(dry_run=options["dry_run"])
            if options["as_json"]:
                self.stdout.write(
                    json.dumps({
                        "enqueued": True,
                        "task_id": async_result.id,
                        "dry_run": options["dry_run"],
                    })
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Enqueued cycle as task {async_result.id}"
                    )
                )
            return

        from monitor.cycle import CycleRunner

        runner = CycleRunner(
            dry_run=options["dry_run"],
            cycle_kind="manual",
        )
        stats = runner.run()

        if options["as_json"]:
            self.stdout.write(json.dumps(stats, indent=2, default=str))
        else:
            if stats["status"] == "completed":
                style = self.style.SUCCESS
            elif stats["status"] == "degraded":
                style = self.style.WARNING
            else:
                style = self.style.ERROR

            self.stdout.write(
                style(
                    f"Cycle {stats['run_id']}: {stats['status']} "
                    f"({stats['totals']['n_calls_planned']} calls planned, "
                    f"{stats['totals'].get('n_calls_run', 0)} run, "
                    f"{stats['totals'].get('n_inserted', 0)} inserted)"
                )
            )
            if stats.get("errors"):
                self.stdout.write(self.style.WARNING(f"  Errors: {stats['errors']}"))
