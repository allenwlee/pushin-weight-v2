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
from pathlib import Path

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
        # The Celery task owns the lock for enqueued work. Dry runs are
        # read-only planning and intentionally do not contend with writers.
        if options["enqueue"] or options["dry_run"]:
            return self._handle(*args, **options)

        from monitor.run_lock import harvest_writer_lock

        with harvest_writer_lock(
            execution_mode="live",
            entrypoint="management.run_cycle",
        ) as lease:
            if not lease.acquired:
                payload = lease.contention.as_dict() if lease.contention else {}
                if options["as_json"]:
                    self.stdout.write(json.dumps({"status": "skipped", **payload}))
                else:
                    self.stderr.write(
                        self.style.WARNING(
                            "Cycle skipped: shared harvest writer lock is held "
                            f"({payload.get('owner_context', 'unknown owner')})."
                        )
                    )
                return None
            return self._handle(*args, **options)

    def _handle(self, *args, **options) -> None:
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
        from x_monitor.config import load_config
        from x_monitor.relevancy import build_binary_relevancy_llm_call

        # Plan 2026-08-01-001 U2: load Config once at process start and
        # thread it into CycleRunner.
        cfg = load_config(Path("config.yaml"))

        # U6 runtime wire-in: build the Anthropic-backed llm_call
        # for the binary relevancy gate. Returns None if the env is
        # not configured; the cycle then runs with the gate as a
        # no-op (KEEP — multilingual keep bias).
        relevancy_client = None
        try:
            from x_monitor.reattribute import (
                build_anthropic_client_from_env,
            )
            relevancy_client = build_anthropic_client_from_env(cfg)
        except Exception as exc:
            self.stderr.write(
                f"warn: failed to build relevancy client: {exc}; "
                f"gate will be no-op"
            )
        relevancy_llm_call = build_binary_relevancy_llm_call(
            client=relevancy_client,
            model=cfg.llm.relevancy_model,
            timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
        )

        runner = CycleRunner(cfg=cfg, 
            dry_run=options["dry_run"],
            cycle_kind="manual",
            _relevancy_llm_call=relevancy_llm_call,
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
