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
import os
from contextlib import ExitStack
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from monitor.staging_acceptance import (
    MAX_RESULTS,
    PreparedStagingAcceptance,
    StagingAcceptanceError,
    bounded_runtime_settings,
    bounded_twitter_client_factory,
    prepare_staging_acceptance,
)


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
        parser.add_argument(
            "--staging-acceptance",
            metavar="CALL_ID",
            default=None,
            help=(
                "Run one fail-closed, five-result staging acceptance call. "
                "Requires the dedicated staging service and database."
            ),
        )

    def handle(self, *args, **options) -> None:
        prepared: PreparedStagingAcceptance | None = None
        with ExitStack() as command_stack:
            if options.get("staging_acceptance") is not None:
                from django.db import connection

                from scripts.database_lock import (
                    DatabaseLockError,
                    acquire_harvest_coordination_lock,
                )
                from scripts.staging_refresh.policy import load_policy
                from x_monitor.config import load_config

                policy = load_policy(Path("config/staging_refresh.yaml"))
                try:
                    prepared = prepare_staging_acceptance(
                        call_id=options["staging_acceptance"],
                        options=options,
                        cfg=load_config(Path("config.yaml")),
                        environ=os.environ,
                        database=connection,
                        policy=policy,
                    )
                except StagingAcceptanceError as exc:
                    raise CommandError(str(exc)) from exc

                database_url = os.environ.get(policy.target.environment)
                if not database_url:
                    raise CommandError("staging_harvest_coordination_url_missing")
                try:
                    command_stack.enter_context(
                        acquire_harvest_coordination_lock(
                            database_url,
                            environment=prepared.profile.environment,
                        )
                    )
                except DatabaseLockError as exc:
                    raise CommandError(str(exc)) from exc
                options["_staging_acceptance_prepared"] = prepared

            # The Celery task owns the lock for enqueued work. Dry runs are
            # read-only planning and intentionally do not contend with writers.
            if options["enqueue"] or options["dry_run"]:
                return self._handle(*args, **options)

            from monitor.run_lock import harvest_writer_lock

            with harvest_writer_lock(
                execution_mode=(
                    "staging-acceptance" if prepared is not None else "live"
                ),
                entrypoint="management.run_cycle",
                environment=(prepared.profile.environment if prepared else None),
            ) as lease:
                if not lease.acquired:
                    payload = lease.contention.as_dict() if lease.contention else {}
                    if options["as_json"] or prepared is not None:
                        output = {"status": "skipped", **payload}
                        if prepared is not None:
                            output["staging_acceptance"] = prepared.profile.as_dict()
                        self.stdout.write(json.dumps(output))
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
        prepared: PreparedStagingAcceptance | None = options.get(
            "_staging_acceptance_prepared"
        )
        # Stash operator-supplied filters in Django settings so cycle.py
        # can read them without us having to change its constructor. This
        # pattern keeps the cross-cutting "operator wants a bounded cycle"
        # signal out of the cycle's own API surface.
        if prepared is None and options["brands"] is not None:
            settings.X_MONITOR_CYCLE_BRAND_FILTER = options["brands"]
        if prepared is None and options["limit_per_call"] is not None:
            settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = options["limit_per_call"]
        if prepared is None and options["max_pages_per_call"] is not None:
            settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = options["max_pages_per_call"]
        if prepared is None and options["skip_fetch"]:
            settings.X_MONITOR_CYCLE_SKIP_FETCH = True

        if options["enqueue"]:
            from monitor.tasks import run_cycle as run_cycle_task

            async_result = run_cycle_task.delay(dry_run=options["dry_run"])
            if options["as_json"]:
                self.stdout.write(
                    json.dumps(
                        {
                            "enqueued": True,
                            "task_id": async_result.id,
                            "dry_run": options["dry_run"],
                        }
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Enqueued cycle as task {async_result.id}")
                )
            return

        from monitor.cycle import CycleRunner
        from x_monitor.config import load_config
        from x_monitor.relevancy import build_binary_relevancy_llm_call

        # Plan 2026-08-01-001 U2: load Config once at process start and
        # thread it into CycleRunner.
        cfg = (
            prepared.config
            if prepared is not None
            else load_config(Path("config.yaml"))
        )

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
        except Exception as exc:  # noqa: BLE001 - keep the existing no-op fallback
            self.stderr.write(
                f"warn: failed to build relevancy client: {exc}; gate will be no-op"
            )
        relevancy_llm_call = build_binary_relevancy_llm_call(
            client=relevancy_client,
            model=cfg.llm.relevancy_model,
            timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
        )

        runner_options = {
            "cfg": cfg,
            "dry_run": options["dry_run"],
            "cycle_kind": "manual",
            "_relevancy_llm_call": relevancy_llm_call,
        }
        if prepared is not None:
            runner_options["_backfill_call_ids"] = [prepared.profile.selected_call]
        runner = CycleRunner(**runner_options)

        try:
            with ExitStack() as stack:
                if prepared is not None:
                    stack.enter_context(bounded_runtime_settings(settings))
                    stack.enter_context(bounded_twitter_client_factory())
                stats = runner.run()
        except Exception as exc:
            if prepared is None:
                raise
            stats = {
                "run_id": "",
                "finished_at": "",
                "status": "aborted",
                "totals": {},
                "calls": [],
                "post_fetch": {},
                "errors": [f"runner_exception:{type(exc).__name__}"],
            }

        from monitor.trend_narrative_dispatch import (
            dispatch_harvest_completion,
        )

        if prepared is not None:
            acceptance_status, selected_call = self._acceptance_status(
                stats,
                selected_call=prepared.profile.selected_call,
            )
            if acceptance_status == "failed":
                stats["status"] = "aborted"
            if acceptance_status == "accepted":
                try:
                    dispatch = dispatch_harvest_completion(stats, dry_run=False)
                except Exception:  # noqa: BLE001 - preserve secret-free JSON boundary
                    from monitor.trend_narrative_dispatch import (
                        NarrativeDispatchResult,
                    )

                    dispatch = NarrativeDispatchResult(status="dispatch_error")
            else:
                from monitor.trend_narrative_dispatch import NarrativeDispatchResult

                dispatch = NarrativeDispatchResult(status="ineligible")
            self.stdout.write(
                json.dumps(
                    self._acceptance_output(
                        prepared=prepared,
                        stats=stats,
                        selected_call=selected_call,
                        acceptance_status=acceptance_status,
                        dispatch=dispatch,
                    ),
                    indent=2,
                    default=str,
                )
            )
            return

        dispatch_harvest_completion(stats, dry_run=options["dry_run"])

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

    @staticmethod
    def _acceptance_status(
        stats: dict,
        *,
        selected_call: str,
    ) -> tuple[str, dict]:
        call = next(
            (
                row
                for row in stats.get("calls", [])
                if row.get("call_id") == selected_call
            ),
            {},
        )
        call_status = str(call.get("status") or "missing")
        n_results = int(call.get("n_results") or 0)
        n_persisted = int(call.get("n_inserted") or 0) + int(call.get("n_updated") or 0)
        n_enrichment_claimed = int(
            stats.get("post_fetch", {}).get("n_enrichment_claimed") or 0
        )
        # ``no_results`` is CycleRunner's successful-empty terminal status.
        # Truncation and cursor-write outcomes remain failures here because a
        # staging acceptance cannot prove its full bounded coverage from them.
        hard_failure = (
            stats.get("status") not in {"completed", "degraded"}
            or bool(stats.get("errors"))
            or call_status not in {"completed", "no_results"}
            or n_results > MAX_RESULTS
        )
        if hard_failure:
            return "failed", call
        if n_results >= 1 and n_persisted >= 1 and n_enrichment_claimed >= 1:
            return "accepted", call
        return "inconclusive", call

    @staticmethod
    def _acceptance_output(
        *,
        prepared: PreparedStagingAcceptance,
        stats: dict,
        selected_call: dict,
        acceptance_status: str,
        dispatch,
    ) -> dict:
        total_keys = (
            "n_calls_run",
            "n_results",
            "n_inserted",
            "n_updated",
            "n_persist_failed",
            "n_attributed",
        )
        call_keys = (
            "call_id",
            "status",
            "n_results",
            "n_kept",
            "n_inserted",
            "n_updated",
            "n_persist_failed",
            "cursor_advanced",
        )
        totals = stats.get("totals", {})
        return {
            "status": acceptance_status,
            "staging_acceptance": prepared.profile.as_dict(),
            "cycle": {
                "run_id": str(stats.get("run_id") or ""),
                "status": str(stats.get("status") or ""),
                "totals": {key: totals.get(key, 0) for key in total_keys},
                "selected_call": {
                    key: selected_call.get(key)
                    for key in call_keys
                    if key in selected_call
                },
                "post_fetch": {
                    "n_enrichment_claimed": int(
                        stats.get("post_fetch", {}).get("n_enrichment_claimed") or 0
                    )
                },
                "error_count": len(stats.get("errors", [])),
            },
            "headline_dispatch": {
                "status": dispatch.status,
                "task_id": dispatch.task_id,
            },
        }
