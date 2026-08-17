"""Durable, selectively date-bounded harvest recovery."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.backfill import (
    BackfillPlan,
    CoverageInterval,
    build_plan,
    parse_utc,
    persist_plan,
    validate_job_plan,
)
from x_monitor.config import load_config

DEFAULT_BUCKET_MINUTES = 15
DEFAULT_MIN_GAP_MINUTES = 60
DEFAULT_REQUEST_BUDGET = 3
DEFAULT_LLM_CALL_BUDGET = 20


def _parse_brands(raw: str | None) -> list[str]:
    return [brand.strip() for brand in (raw or "").split(",") if brand.strip()]


def _intervals_from_job(job) -> tuple[CoverageInterval, ...]:
    return tuple(CoverageInterval.from_dict(value) for value in job.selected_intervals)


def _state_counts(job) -> Counter:
    if job is None:
        return Counter()
    return Counter(job.windows.values_list("state", flat=True))


def _remaining_rows(job, plan: BackfillPlan) -> int:
    if job is None:
        return plan.work_rows
    return job.windows.exclude(state="completed").count()


class Command(BaseCommand):
    help = (
        "Recover a historical UTC range through durable job-owned harvest "
        "windows, optionally selecting inferred zero-post gaps."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since",
            help="Historical lower bound (ISO-8601; naive values are UTC).",
        )
        parser.add_argument(
            "--until",
            help="Historical exclusive upper bound (ISO-8601; naive values are UTC).",
        )
        parser.add_argument(
            "--detect-gaps",
            action="store_true",
            help=(
                "Select only fully elapsed zero-post bucket runs. This cannot "
                "detect partial outages; use an explicit range for known downtime."
            ),
        )
        parser.add_argument(
            "--bucket-minutes",
            type=int,
            default=DEFAULT_BUCKET_MINUTES,
            help=f"Detection bucket width (default: {DEFAULT_BUCKET_MINUTES}).",
        )
        parser.add_argument(
            "--min-gap-minutes",
            type=int,
            default=DEFAULT_MIN_GAP_MINUTES,
            help=(
                "Minimum consecutive zero-post duration "
                f"(default: {DEFAULT_MIN_GAP_MINUTES})."
            ),
        )
        parser.add_argument(
            "--brands",
            help="Comma-separated brand filter stored in the durable job identity.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_REQUEST_BUDGET,
            help=(
                "Maximum one-page TwitterAPI search requests this invocation "
                f"(default: {DEFAULT_REQUEST_BUDGET})."
            ),
        )
        parser.add_argument(
            "--max-llm-calls",
            type=int,
            default=DEFAULT_LLM_CALL_BUDGET,
            help=(
                "Maximum actual relevance/translation/classification client "
                "invocations, including retries and repairs "
                f"(default: {DEFAULT_LLM_CALL_BUDGET})."
            ),
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=5,
            help="Seconds between bounded requests, outside the writer lock.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview selection, current call fan-out, and cost without writes.",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show matching durable job progress without writes or provider calls.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete only the exact matching recovery job and its owned windows.",
        )
        parser.add_argument(
            "--quarantined",
            action="store_true",
            help="Replay only scheduled (non-job) quarantined recall-debt rows.",
        )
        parser.add_argument(
            "--retry-quarantined",
            action="store_true",
            help=(
                "Replay only quarantined rows owned by the exact matching "
                "backfill job; --since and --until are required."
            ),
        )

    def handle(self, *args, **options) -> None:
        self._validate_options(options)
        if options["quarantined"]:
            return self._handle_scheduled_quarantine(options)

        cfg, plan, rates = self._preflight(options)

        from core.models import BackfillJob

        job = BackfillJob.objects.filter(key=plan.key).first()
        if job is not None:
            try:
                validate_job_plan(job, plan)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

        self._print_plan(plan, job, rates, options)

        if options["status"]:
            if job is None:
                self.stdout.write("No matching durable backfill job.")
            return

        if options["reset"]:
            if job is None:
                raise CommandError("No matching durable backfill job to reset")
            if options["dry_run"]:
                self.stdout.write(f"Would reset job {job.key} (dry-run).")
            else:
                self._reset_job(job)
            return

        if options["dry_run"]:
            return
        if options["retry_quarantined"] and job is None:
            raise CommandError("No matching durable backfill job to retry")
        if not plan.intervals and job is None:
            self.stdout.write("No qualifying inferred gaps; no job was created.")
            return

        try:
            job = persist_plan(plan)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if job.state == BackfillJob.State.COMPLETED:
            self.stdout.write("Backfill job is already complete.")
            return

        self._execute_job(
            job,
            plan,
            cfg,
            options,
            retry_quarantined=options["retry_quarantined"],
        )

    def _validate_options(self, options) -> None:
        if options["status"] and options["reset"]:
            raise CommandError("--status and --reset cannot be combined")
        if options["retry_quarantined"] and options["reset"]:
            raise CommandError("--retry-quarantined and --reset cannot be combined")
        if options["batch_size"] <= 0:
            raise CommandError("--batch-size must be positive")
        if options["max_llm_calls"] < 0:
            raise CommandError("--max-llm-calls must be non-negative")
        if options["pause"] < 0:
            raise CommandError("--pause must be non-negative")
        if options["bucket_minutes"] <= 0:
            raise CommandError("--bucket-minutes must be positive")
        if options["min_gap_minutes"] <= 0:
            raise CommandError("--min-gap-minutes must be positive")
        if options["quarantined"]:
            conflicts = [
                flag
                for flag in (
                    "since",
                    "until",
                    "brands",
                    "detect_gaps",
                    "reset",
                    "retry_quarantined",
                )
                if options.get(flag)
            ]
            if conflicts:
                rendered = ", ".join(f"--{flag.replace('_', '-')}" for flag in conflicts)
                raise CommandError(
                    "--quarantined is scheduled-ledger-only and cannot be combined "
                    f"with {rendered}"
                )
            return
        if not options.get("since"):
            raise CommandError("--since is required unless --quarantined is used")
        if not options.get("until"):
            raise CommandError("--until is required unless --quarantined is used")

    def _preflight(self, options):
        try:
            since = parse_utc(options["since"])
            until = parse_utc(options["until"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        cfg = load_config(Path("config.yaml"))
        try:
            plan = build_plan(
                cfg,
                since=since,
                until=until,
                detect_gaps=options["detect_gaps"],
                bucket_minutes=options["bucket_minutes"],
                min_gap_minutes=options["min_gap_minutes"],
                brand_filter=_parse_brands(options.get("brands")),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        try:
            from scripts.harvest_cost import load_pricing

            rates = load_pricing(repo_root=Path.cwd())
        except Exception as exc:
            from scripts.harvest_cost import PricingError

            if isinstance(exc, PricingError):
                raise CommandError(
                    f"TwitterAPI pricing preflight failed: {exc}"
                ) from exc
            raise
        return cfg, plan, rates

    def _print_plan(self, plan, job, rates, options) -> None:
        intervals = _intervals_from_job(job) if job is not None else plan.intervals
        mode = (
            "inferred zero-coverage gaps"
            if plan.selection_mode == "detected_gaps"
            else "explicit range"
        )
        self.stdout.write(
            f"Backfill {'status' if options['status'] else 'preview'}: {mode}"
        )
        self.stdout.write(
            f"Requested: {plan.since.isoformat()} → {plan.until.isoformat()}"
        )
        self.stdout.write(f"Intervals ({len(intervals)}):")
        for interval in intervals:
            self.stdout.write(
                f"  - {interval.since.isoformat()} → {interval.until.isoformat()}"
            )
        if not intervals:
            self.stdout.write("  - none")
        if plan.selection_mode == "detected_gaps":
            self.stdout.write(
                "Partial outages are not detectable from current post coverage; "
                "use an explicit range for known downtime."
            )

        call_ids = ", ".join(call.call_id for call in plan.calls)
        self.stdout.write(f"Calls ({len(plan.calls)}): {call_ids}")
        counts = _state_counts(job)
        total_rows = job.windows.count() if job is not None else plan.work_rows
        remaining = _remaining_rows(job, plan)
        if job is not None:
            states = ", ".join(
                f"{state}={count}" for state, count in sorted(counts.items())
            )
            self.stdout.write(
                f"Job: {job.key} state={job.state}; work rows={total_rows}; {states}"
            )
        else:
            self.stdout.write(f"Work rows: {total_rows} planned; {remaining} remaining")

        per_request_max = max(
            rates.call_floor_credits,
            rates.tweet_credits * 20,
        )
        min_credits = remaining * rates.call_floor_credits
        max_credits = remaining * per_request_max
        invocation_requests = min(options["batch_size"], remaining)
        self.stdout.write(
            "TwitterAPI credits (one first-pass request per remaining row): "
            f"{min_credits:.0f}–{max_credits:.0f} "
            f"(${rates.usd(min_credits):.4f}–${rates.usd(max_credits):.4f}); "
            f"next invocation ≤ {invocation_requests} requests."
        )
        self.stdout.write(
            "Dense windows may truncate, so additional requests may be required; "
            "each request is capped at one page / 20 returned tweets."
        )

    def _build_runner(self, cfg, options, *, brand_filter=None):
        from monitor.cycle import CycleRunner
        from x_monitor.reattribute import build_relevancy_client_from_env
        from x_monitor.relevancy import build_binary_relevancy_llm_call

        relevancy_client = build_relevancy_client_from_env(cfg)
        relevancy_llm_call = build_binary_relevancy_llm_call(
            client=relevancy_client,
            model=cfg.llm.relevancy_model,
            timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
        )
        return CycleRunner(
            cfg=cfg,
            dry_run=False,
            cycle_kind="backfill",
            _brand_filter=(list(brand_filter) if brand_filter is not None else None),
            _max_llm_calls=options["max_llm_calls"],
            _relevancy_llm_call=relevancy_llm_call,
        )

    @staticmethod
    def _build_api():
        from x_monitor.apify import TwitterApiClient

        api = TwitterApiClient.from_env()
        # Durable work owns retries. A --batch-size N invocation therefore
        # makes at most N actual advanced-search HTTP attempts.
        api.max_retries = 0
        return api

    def _run_bounded_requests(
        self,
        *,
        runner,
        api,
        options,
        entrypoint: str,
        label: str,
        job=None,
        include_quarantined: bool = False,
    ) -> dict[str, int]:
        from monitor.run_lock import harvest_writer_lock

        requests_run = 0
        completed = 0
        llm_calls = 0
        for request_index in range(options["batch_size"]):
            if request_index and options["pause"]:
                time.sleep(options["pause"])

            with harvest_writer_lock(
                execution_mode="backfill",
                entrypoint=entrypoint,
            ) as lease:
                if not lease.acquired:
                    owner = (
                        lease.contention.owner_context
                        if lease.contention is not None
                        else "unknown owner"
                    )
                    self.stdout.write(
                        f"{label} paused: shared harvest writer lock is held ({owner})."
                    )
                    break
                try:
                    result = runner.replay_backlog_only(
                        backfill_job=job,
                        include_quarantined=include_quarantined,
                        request_limit=1,
                        api=api,
                    )
                except (RuntimeError, ValueError) as exc:
                    self.stderr.write(f"{label} stopped before completion: {exc}")
                    break

            reports = result.get("backlog_replays", [])
            if not reports:
                break
            report = reports[0]
            llm_calls = int(result.get("llm_calls", llm_calls))
            if report.get("status") == "deadline_exhausted":
                self.stdout.write(f"{label} deadline guard deferred the next request.")
                break
            requests_run += 1
            completed += report.get("status") == "completed"
            self.stdout.write(
                f"{label} {requests_run}/{options['batch_size']}: "
                f"{report.get('call_id', '?')} → {report.get('status', 'unknown')}"
            )
            if job is not None:
                job.refresh_from_db()
                if job.state == "completed":
                    break

        return {
            "requests": requests_run,
            "completed": completed,
            "llm_calls": llm_calls,
        }

    def _execute_job(
        self,
        job,
        plan,
        cfg,
        options,
        *,
        retry_quarantined: bool,
    ) -> None:
        try:
            api = self._build_api()
        except RuntimeError as exc:
            self.stderr.write(f"Backfill stopped before provider setup: {exc}")
            return
        runner = self._build_runner(
            cfg,
            options,
            brand_filter=plan.brand_filter,
        )
        run = self._run_bounded_requests(
            runner=runner,
            api=api,
            options=options,
            entrypoint="management.backfill",
            label="Backfill request",
            job=job,
            include_quarantined=retry_quarantined,
        )

        job.refresh_from_db()
        counts = _state_counts(job)
        remaining = job.windows.exclude(state="completed").count()
        self.stdout.write(
            f"Backfill job {job.state}: requests={run['requests']}, "
            f"remaining_rows={remaining}, llm_calls={run['llm_calls']}; "
            + ", ".join(f"{state}={count}" for state, count in sorted(counts.items()))
        )

    def _reset_job(self, job) -> None:
        from monitor.run_lock import harvest_writer_lock

        with harvest_writer_lock(
            execution_mode="backfill",
            entrypoint="management.backfill.reset",
        ) as lease:
            if not lease.acquired:
                raise CommandError(
                    "Backfill reset deferred: the shared harvest writer lock is held"
                )
            job_key = job.key
            job.delete()
        self.stdout.write(f"Reset job {job_key} and only its owned windows.")

    def _handle_scheduled_quarantine(self, options) -> None:
        from core.models import HarvestBacklogWindow

        rows = HarvestBacklogWindow.objects.filter(
            backfill_job__isnull=True,
            state=HarvestBacklogWindow.State.QUARANTINED,
        )
        count = rows.count()
        if options["dry_run"] or options["status"]:
            self.stdout.write(f"Quarantined harvest intervals: {count}")
            return
        if count == 0:
            self.stdout.write("No scheduled quarantined harvest intervals to replay.")
            return

        cfg = load_config(Path("config.yaml"))
        try:
            api = self._build_api()
        except RuntimeError as exc:
            self.stderr.write(f"Scheduled quarantine stopped before provider setup: {exc}")
            return
        runner = self._build_runner(cfg, options)
        run = self._run_bounded_requests(
            runner=runner,
            api=api,
            options=options,
            entrypoint="management.backfill.quarantined",
            label="Scheduled quarantine request",
            include_quarantined=True,
        )
        self.stdout.write(
            "Scheduled quarantined replay: "
            f"requests={run['requests']}, completed={run['completed']}, "
            f"llm_calls={run['llm_calls']}."
        )
