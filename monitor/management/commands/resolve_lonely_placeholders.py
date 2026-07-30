"""Resolve lonely placeholder rows via cron-managed TwitterAPI apply.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Units U2-U5.

Reuses Phase 2 helpers from `reconcile_account_duplicates` for the
apply path (do NOT rewrite -- the apply is correct and tested). Adds
the cron-friendly wrapper around it: re-entrant apply at 5 QPS,
dead-letter log, exit summary, SAVEPOINT-per-row safety.

Why a separate command instead of `--lonely-only` on the existing
reconcile command:

  - `--lonely-only` runs the legacy path: per-group TwitterAPI lookup,
    aiohttp pre-pass with `workers=N` (which hit the v6 port-exhaustion
    incident at workers=100), and exits when one batch finishes. No
    SAVEPOINT per row, no dead-letter log, no exit summary, no rate
    gating at 5 QPS.
  - This command implements those properties; it imports the Phase 2
    helpers (`_find_lonely_placeholders`, `_ensure_canonical_account_row`,
    `_repoint_fk`) and wraps them with the cron-style safety net.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from monitor.management.commands.reconcile_account_duplicates import (
    _ensure_canonical_account_row,
    _find_lonely_placeholders,
    _repoint_fk,
)
from monitor.reconcile.apply_loop import run_apply_loop


# KTD1 + KTD7 from the plan.
DEFAULT_RATE_QPS = 5.0
DEFAULT_CONCURRENCY = 2
DEFAULT_MAX_SECONDS = 3300
DEFAULT_BATCH_SIZE = 200

# KTD5 + KTD6 -- log paths on fuchitalee's home dir.
DEFAULT_APPLY_LOG = Path.home() / "lonely-apply.log"
DEFAULT_DEAD_LETTER_LOG = Path.home() / "lonely-apply-dead-letter.log"


class Command(BaseCommand):
    help = (
        "Resolve lonely placeholder rows via TwitterAPI apply. "
        "Re-entrant across cron ticks; per-row SAVEPOINT; dead-letter "
        "log + exit summary written to ~/lonely-apply*.log. "
        "Default is --dry-run; pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Actually write to the DB (default is dry-run).",
        )
        parser.add_argument(
            "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
            help=f"Rows per TwitterAPI lookup batch (default {DEFAULT_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
            help=f"Stop after this many seconds with partial=true "
                 f"(default {DEFAULT_MAX_SECONDS} = 55min, leaves slack under 1h).",
        )
        parser.add_argument(
            "--rate-qps", type=float, default=DEFAULT_RATE_QPS,
            help=f"Max TwitterAPI queries per second (default {DEFAULT_RATE_QPS}).",
        )
        parser.add_argument(
            "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
            help=f"Max in-flight aiohttp requests (default {DEFAULT_CONCURRENCY}, "
                 f"TCPConnector(limit=N)).",
        )
        parser.add_argument(
            "--skip-dead-lettered", action="store_true", default=True,
            help="Read ~/lonely-apply-dead-letter.log on startup and skip those handles (default True).",
        )
        parser.add_argument(
            "--no-skip-dead-lettered", dest="skip_dead_lettered", action="store_false",
            help="Re-attempt every handle, even ones dead-lettered in prior runs.",
        )
        parser.add_argument(
            "--apply-log", type=Path, default=DEFAULT_APPLY_LOG,
            help=f"Exit-summary log path (default {DEFAULT_APPLY_LOG}).",
        )
        parser.add_argument(
            "--dead-letter-log", type=Path, default=DEFAULT_DEAD_LETTER_LOG,
            help=f"Dead-letter log path (default {DEFAULT_DEAD_LETTER_LOG}).",
        )
        parser.add_argument(
            "--json", action="store_true",
            help="Emit the exit summary as a single JSON object on stdout.",
        )

    def handle(self, *args, **opts):
        apply_mode = bool(opts["apply"])
        max_seconds = int(opts["max_seconds"])
        skip_dead_lettered = bool(opts["skip_dead_lettered"])

        started_at = time.time()
        started_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at))

        # Load dead-lettered handles from prior runs.
        dead_letter_set: set[str] = set()
        if skip_dead_lettered:
            dead_letter_set = self._load_dead_letter_set(opts["dead_letter_log"])

        # Register SIGTERM handler so cron `timeout` produces a clean partial summary.
        self._received_signal: list = [None]
        signal.signal(signal.SIGTERM, lambda *_: self._mark_signal("SIGTERM"))
        signal.signal(signal.SIGINT, lambda *_: self._mark_signal("SIGINT"))

        # Find candidate lonely placeholders.
        with connection.cursor() as cur:
            groups = _find_lonely_placeholders(cur)
        candidates = [(h, a) for h, a in groups if h not in dead_letter_set]
        total = len(candidates)

        if not apply_mode:
            # Dry-run summary; no TwitterAPI calls, no DB writes.
            summary = {
                "started_at": started_iso,
                "finished_at": started_iso,
                "dry_run": True,
                "total_placeholders": total,
                "skipped_dead_lettered": len(dead_letter_set),
                "looked_up": 0,
                "resolved": 0,
                "dead_lettered": 0,
                "retried_after_429": 0,
                "rate_actual_qps": 0.0,
                "max_time_wait_sockets": 0,
                "partial": False,
                "dead_letter_reasons": {},
            }
            self._emit_summary(summary, opts)
            return

        # APPLY MODE: delegate to monitor.reconcile.apply_loop.run_apply_loop.
        api_key = os.environ.get("TWITTERAPI_IO_API_KEY")
        try:
            summary = run_apply_loop(
                candidate_placeholders=candidates,
                api_key=api_key,
                rate_qps=float(opts["rate_qps"]),
                concurrency=int(opts["concurrency"]),
                batch_size=int(opts["batch_size"]),
                max_seconds=float(max_seconds),
                apply_log_path=Path(opts["apply_log"]),
                dead_letter_log_path=Path(opts["dead_letter_log"]),
                received_signal_ref=self._received_signal,
            )
        except Exception as exc:
            crashed_at = time.time()
            summary = {
                "started_at": started_iso,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(crashed_at)),
                "dry_run": False,
                "total_placeholders": total,
                "looked_up": 0,
                "resolved": 0,
                "dead_lettered": 0,
                "retried_after_429": 0,
                "rate_actual_qps": 0.0,
                "max_time_wait_sockets": 0,
                "partial": True,
                "dead_letter_reasons": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._emit_summary(summary, opts)
            raise

        self._emit_summary(summary, opts)

    # --- helpers ----------------------------------------------------

    def _mark_signal(self, name: str) -> None:
        self._received_signal[0] = name

    def _load_dead_letter_set(self, path: Path) -> set[str]:
        if not path.exists():
            return set()
        out: set[str] = set()
        try:
            with path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        h = entry.get("handle")
                        if h:
                            out.add(h)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return out
        return out

    def _emit_summary(self, summary: dict, opts: dict) -> None:
        line = json.dumps(summary, sort_keys=True)
        if opts.get("json"):
            self.stdout.write(line)
        else:
            self.stdout.write("resolve_lonely_placeholders summary:")
            for k, v in summary.items():
                self.stdout.write(f"  {k}: {v}")
        try:
            with opts["apply_log"].open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass