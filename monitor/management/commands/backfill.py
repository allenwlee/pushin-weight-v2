"""Backfill: run harvest cycles with date-bounded search window.

Designed for gradual, resumable execution that coexists with the regular
15-min harvest cron. Each invocation processes a small batch of calls,
writes progress to a state file, and exits. Run it repeatedly (e.g. via a
Render cron or manual invocations) until all calls complete.

Usage:
    # Dry-run to see what would happen
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --dry-run

    # Run one batch (default: 3 calls per batch)
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00

    # Run with larger batch size
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --batch-size 6

    # Resume from previous state automatically (state file keyed on since/until)
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00

    # Reset and start over
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --reset

State file: data/backfill/<since_epoch>-<until_epoch>.json
"""

from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from x_monitor.config import load_config

# Estimated daily post volume across all brands — from Jul 21 baseline.
_EST_DAILY_POSTS = 2_350
# Typical number of calls per cycle.
_EST_CALLS_PER_CYCLE = 6
# TwitterAPI.io page cap.
_TWEETS_PER_PAGE = 20
# Safety ceilings.
_MAX_PAGES_CEILING = 100
_MAX_RESULTS_CEILING = 1_000
# Multiplier on computed params for headroom.
_SAFETY_MARGIN = 2.0
# Where state files live.
_STATE_DIR = Path("data/backfill")


def _parse_iso(ts: str) -> int:
    """Parse YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS to epoch seconds (UTC)."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise CommandError(
        f"Invalid timestamp '{ts}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
    )


def _state_path(since_epoch: int, until_epoch: int) -> Path:
    return _STATE_DIR / f"{since_epoch}-{until_epoch}.json"


def _load_state(state_file: Path) -> dict | None:
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text())


def _save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, default=str))


def _compute_params(
    since_epoch: int, until_epoch: int, safety_margin: float
) -> tuple[int, int, int]:
    """Return (max_results, max_pages, est_total) with safety margin applied."""
    gap_hours = max((until_epoch - since_epoch) / 3600.0, 1.0)
    est_total = int(_EST_DAILY_POSTS * (gap_hours / 24))
    est_per_call = max(est_total // _EST_CALLS_PER_CYCLE, 50)

    max_results = int(min(est_per_call * safety_margin, _MAX_RESULTS_CEILING))
    max_results = max(max_results, 100)
    max_pages = min(
        max(int((max_results / _TWEETS_PER_PAGE) * safety_margin) + 1, 5),
        _MAX_PAGES_CEILING,
    )
    return max_results, max_pages, est_total


class Command(BaseCommand):
    help = "Run harvest cycles with date-bounded search window (batchable, resumable)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--since", type=str, required=False,
            help="Lower bound (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, UTC).",
        )
        parser.add_argument(
            "--quarantined",
            action="store_true",
            help="Replay bounded quarantined intervals without advancing live cursors.",
        )
        parser.add_argument(
            "--until", type=str, default=None,
            help="Upper bound (same format). Default: now.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Plan calls only; don't fetch or write.",
        )
        parser.add_argument(
            "--brands", type=str, default=None,
            help="Comma-separated brand nicknames to filter.",
        )
        parser.add_argument(
            "--batch-size", type=int, default=3,
            help="Max calls to execute per invocation (default: 3).",
        )
        parser.add_argument(
            "--safety-margin", type=float, default=_SAFETY_MARGIN,
            help=f"Multiplier on computed max_results/pages (default: {_SAFETY_MARGIN}).",
        )
        parser.add_argument(
            "--pause", type=int, default=5,
            help="Seconds to pause between calls within a batch (default: 5).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Discard prior state and start from the beginning.",
        )
        parser.add_argument(
            "--status", action="store_true",
            help="Print current progress and exit (no work done).",
        )
        parser.add_argument(
            "--max-results", type=int, default=None,
            help="Override computed per-call result cap.",
        )
        parser.add_argument(
            "--max-pages", type=int, default=None,
            help="Override computed per-call page cap.",
        )
        parser.add_argument(
            "--max-llm-calls", type=int, default=None,
            help="Hard cap on LLM classify batches per invocation (default: no cap).",
        )

    def handle(self, *args, **options) -> None:
        # Status and dry-run are read-only. Every explicit write-capable
        # historical run holds the same PostgreSQL lock as live harvesting.
        if options["status"] or options["dry_run"]:
            return self._handle(*args, **options)

        from monitor.run_lock import harvest_writer_lock

        with harvest_writer_lock(
            execution_mode="backfill",
            entrypoint="management.backfill",
        ) as lease:
            if not lease.acquired:
                owner = (
                    lease.contention.owner_context
                    if lease.contention is not None
                    else "unknown owner"
                )
                self.stderr.write(
                    self.style.WARNING(
                        f"Backfill skipped: shared harvest writer lock is held ({owner})."
                    )
                )
                return None
            return self._handle(*args, **options)

    def _handle(self, *args, **options) -> None:
        if options["quarantined"]:
            return self._handle_quarantined(options)
        if not options.get("since"):
            raise CommandError("--since is required unless --quarantined is used")
        since_epoch = _parse_iso(options["since"])
        until_epoch = (
            _parse_iso(options["until"])
            if options["until"]
            else int(datetime.now(timezone.utc).timestamp())
        )
        state_file = _state_path(since_epoch, until_epoch)

        # --- status-only ---
        if options["status"]:
            state = _load_state(state_file)
            if state is None:
                self.stdout.write("No state file — backfill not started yet.")
            else:
                done = state.get("calls_completed", 0)
                total = state.get("calls_total", "?")
                inserted = sum(
                    r.get("n_inserted", 0) for r in state.get("runs", [])
                )
                self.stdout.write(
                    f"Backfill {options['since']} → {options['until'] or 'now'}:  "
                    f"{done}/{total} calls done, {inserted} posts inserted so far."
                )
                if state.get("finished"):
                    self.stdout.write("State: finished ✓")
                elif state.get("calls_remaining"):
                    self.stdout.write(
                        f"Next: {state['calls_remaining'][0] if state['calls_remaining'] else 'none'}"
                    )
            return

        # --- state management ---
        if options["reset"]:
            if options["dry_run"]:
                self.stdout.write("Would reset state (dry run; no file changed).")
            else:
                state_file.unlink(missing_ok=True)
                self.stdout.write("State reset.")

        max_results, max_pages, est_total = _compute_params(
            since_epoch, until_epoch, options["safety_margin"]
        )
        if options["max_results"] is not None:
            max_results = options["max_results"]
        if options["max_pages"] is not None:
            max_pages = options["max_pages"]

        gap_hours = (until_epoch - since_epoch) / 3600.0

        # --- plan calls ---
        settings.X_MONITOR_CYCLE_SINCE_TIME = since_epoch
        settings.X_MONITOR_CYCLE_UNTIL_TIME = until_epoch
        settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = max_results
        settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = max_pages
        if options["brands"]:
            settings.X_MONITOR_CYCLE_BRAND_FILTER = options["brands"]

        since_label = options["since"]
        until_label = options["until"] or "now"

        from monitor.cycle import CycleRunner, plan_calls_for_cycle

        # Plan calls using the shared function — same as regular harvest.
        # Pass cfg explicitly to avoid a second config.yaml disk read.
        cfg = load_config(Path("config.yaml"))
        calls = plan_calls_for_cycle(cfg)
        call_ids = [c.call_id for c in calls]

        # --- load or init state ---
        state = _load_state(state_file) or {}
        completed = set(state.get("calls_completed_ids", []))
        pending = [cid for cid in call_ids if cid not in completed]

        if not state:
            state = {
                "since_epoch": since_epoch,
                "until_epoch": until_epoch,
                "since_label": since_label,
                "until_label": until_label,
                "gap_hours": round(gap_hours, 1),
                "est_total_posts": est_total,
                "max_results": max_results,
                "max_pages": max_pages,
                "calls_total": len(call_ids),
                "calls_completed_ids": [],
                "calls_completed": 0,
                "total_inserted": 0,
                "runs": [],
                "finished": False,
            }
            if not options["dry_run"]:
                _save_state(state_file, state)

        if not pending:
            self.stdout.write(
                self.style.SUCCESS(
                    f"All {len(call_ids)} calls already completed — backfill finished."
                )
            )
            state["finished"] = True
            if not options["dry_run"]:
                _save_state(state_file, state)
            return

        batch = pending[: options["batch_size"]]
        self.stdout.write(
            f"Backfill {since_label} → {until_label}  "
            f"({gap_hours:.1f}h, ~{est_total} posts expected, "
            f"max_results={max_results}, max_pages={max_pages}, "
            f"safety_margin={options['safety_margin']}x)  "
            f"Batch: {len(batch)}/{len(pending)} remaining"
            + ("  [DRY RUN]" if options["dry_run"] else "")
        )

        if options["dry_run"]:
            self.stdout.write(f"  Would execute calls: {batch}")
            return

        # --- execute batch ---
        from x_monitor.relevancy import build_binary_relevancy_llm_call

        # U6 runtime wire-in: same as run_cycle — build the Anthropic
        # llm_call for the binary relevancy gate. None when env is
        # unconfigured; gate then runs as no-op (KEEP).
        relevancy_client = None
        try:
            from x_monitor.reattribute import (
                build_anthropic_client_from_env,
            )
            relevancy_client = build_anthropic_client_from_env(cfg)
        except Exception:
            pass
        relevancy_llm_call = build_binary_relevancy_llm_call(
            client=relevancy_client,
            model=cfg.llm.relevancy_model,
            timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
        )

        for i, call_id in enumerate(batch):
            if i > 0 and options["pause"] > 0:
                self.stdout.write(f"  Pausing {options['pause']}s…")
                _time.sleep(options["pause"])

            self.stdout.write(f"  Executing call {call_id} ({i+1}/{len(batch)})…")
            try:
                cfg = load_config(Path("config.yaml"))
                runner = CycleRunner(cfg=cfg, 
                    dry_run=False,
                    cycle_kind="backfill",
                    _backfill_call_ids=[call_id],
                    _max_llm_calls=options.get("max_llm_calls"),
                    _relevancy_llm_call=relevancy_llm_call,
                )
                stats = runner.run()

                inserted = stats["totals"].get("n_inserted", 0)
                state["calls_completed_ids"].append(call_id)
                state["calls_completed"] = len(state["calls_completed_ids"])
                state["total_inserted"] = state.get("total_inserted", 0) + inserted
                state["runs"].append({
                    "call_id": call_id,
                    "run_id": stats["run_id"],
                    "status": stats["status"],
                    "n_inserted": inserted,
                    "n_calls_run": stats["totals"].get("n_calls_run", 0),
                    "errors": stats.get("errors", []),
                })
                _save_state(state_file, state)

                self.stdout.write(
                    f"    {call_id}: {inserted} inserted  "
                    f"(total so far: {state['total_inserted']})"
                )
            except Exception as exc:
                self.stderr.write(f"    {call_id}: FAILED — {exc}")
                state["runs"].append({
                    "call_id": call_id,
                    "status": "failed",
                    "error": str(exc),
                })
                _save_state(state_file, state)
                # Don't mark as completed — will retry next invocation
                continue

        # --- final state ---
        remaining_after = [cid for cid in call_ids if cid not in set(state["calls_completed_ids"])]
        if not remaining_after:
            state["finished"] = True
        state["calls_remaining"] = remaining_after
        _save_state(state_file, state)

        if state["finished"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backfill complete: {state['total_inserted']} posts inserted "
                    f"across {state['calls_completed']} calls."
                )
            )
        else:
            self.stdout.write(
                f"Batch done. {len(remaining_after)} calls remaining. "
                f"Run again to continue. State: {state_file}"
            )

    def _handle_quarantined(self, options) -> None:
        """Replay only quarantined ledger rows; never touch live cursors."""

        from core.models import HarvestBacklogWindow

        count = HarvestBacklogWindow.objects.filter(state="quarantined").count()
        if options["dry_run"] or options["status"]:
            self.stdout.write(f"Quarantined harvest intervals: {count}")
            return
        if count == 0:
            self.stdout.write("No quarantined harvest intervals to replay.")
            return

        from monitor.cycle import CycleRunner

        cfg = load_config(Path("config.yaml"))
        stats = CycleRunner(
            cfg=cfg,
            dry_run=False,
            cycle_kind="backfill",
            _max_llm_calls=options.get("max_llm_calls"),
        ).replay_backlog_only(include_quarantined=True)
        completed = sum(
            report.get("status") == "completed"
            for report in stats.get("backlog_replays", [])
        )
        self.stdout.write(
            f"Quarantined replay finished: {completed} completed; "
            f"status={stats['status']}"
        )
