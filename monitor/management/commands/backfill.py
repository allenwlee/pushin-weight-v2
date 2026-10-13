"""Backfill: run harvest cycles with date-bounded search window.

Each explicit invocation processes finite call/time-slice units through the
shared runner and saves committed provider cursors on the executing host.
The default unit is 15 minutes and the default batch is one unit. Fixed bounds,
policy and limits must match the checkpoint to resume. No scheduler is started.

Usage:
    # Dry-run to see what would happen
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --dry-run

    # Run one scoped unit
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --brands qwen --call-ids B1

    # Bound the entire invocation, including all model roles and HTTP retries
    python manage.py backfill --since 2026-08-09T00:00Z --until 2026-08-09T00:15Z \
        --brands qwen --call-ids B1 --max-api-requests 10 --max-llm-calls 60

    # Plan a single-brand, single-call historical recovery
    python manage.py backfill --since 2026-08-13 --until 2026-08-15 \
        --brands dots --call-ids B1 --dry-run

    # Resume from previous state automatically (state file keyed on since/until)
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --brands qwen --call-ids B1

    # Reset and start over
    python manage.py backfill --since 2026-07-22T05:00 --until 2026-07-23T21:00 --brands qwen --call-ids B1 --reset

State file: data/backfill/<since_epoch>-<until_epoch>[-<scope_hash>].json
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time as _time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from x_monitor.config import load_config

# Retained only as a validated compatibility option; never estimates volume.
_SAFETY_MARGIN = 2.0
# Where state files live.
_STATE_DIR = Path("data/backfill")
_RUNTIME_SETTING_NAMES = (
    "X_MONITOR_CYCLE_SINCE_TIME",
    "X_MONITOR_CYCLE_UNTIL_TIME",
    "X_MONITOR_CYCLE_LIMIT_PER_CALL",
    "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL",
    "X_MONITOR_CYCLE_BRAND_FILTER",
)
_MISSING_SETTING = object()
_COMPLETE_CALL_STATUSES = frozenset({"completed", "no_results"})
_BLOCKED_PROGRESS_REASONS = frozenset({
    "invalid_primary_window", "invalid_continuation", "clipped_page", "nonprogressing_cursor",
})


def _parse_iso(ts: str) -> int:
    """Parse ISO dates/timestamps; unqualified timestamps mean UTC."""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp())
    except (ValueError, OverflowError) as exc:
        raise CommandError(f"Invalid ISO timestamp '{ts}'.") from exc


def _state_path(
    since_epoch: int,
    until_epoch: int,
    scope_key: str | None = None,
) -> Path:
    suffix = f"-{scope_key}" if scope_key else ""
    return _STATE_DIR / f"{since_epoch}-{until_epoch}{suffix}.json"


def _scope_key(*, brands: list[str], call_ids: list[str]) -> str | None:
    """Keep independently scoped backfills from sharing completion state."""
    if not brands and not call_ids:
        return None
    payload = json.dumps(
        {
            "brands": sorted(set(brands)),
            "call_ids": sorted(set(call_ids)),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _load_state(state_file: Path) -> dict | None:
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text())


def _save_state(state_file: Path, state: dict) -> None:
    """Replace a fully flushed checkpoint without destroying the prior one."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=state_file.parent,
            prefix=f".{state_file.name}.", suffix=".tmp", delete=False,
        ) as target:
            temporary = Path(target.name)
            json.dump(state, target, indent=2, default=str)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(state_file)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _selected_call_status(stats: dict, call_id: str) -> str:
    """Return one call receipt status, or a safe incomplete sentinel."""
    matching_calls = [
        call
        for call in stats.get("calls", [])
        if str(call.get("call_id") or "") == call_id
    ]
    if not matching_calls:
        return "missing_call_receipt"
    if len(matching_calls) != 1:
        return "ambiguous_call_receipt"
    return str(matching_calls[0].get("status") or "missing_call_status")


def _seconds_to_next_slot() -> float:
    elapsed = _time.time() % 900
    # Give a newly due cron time to start before a manual unit can compete.
    return 0 if elapsed < 120 else 900 - elapsed


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
            help="Fixed upper bound (ISO format); required for historical runs.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Plan calls only; don't fetch or write.",
        )
        parser.add_argument(
            "--brands", type=str, default=None,
            help="Comma-separated brand nicknames; selects only their B/C calls.",
        )
        parser.add_argument(
            "--call-ids", type=str, default=None,
            help="Comma-separated logical call IDs to run (for example B1).",
        )
        parser.add_argument(
            "--batch-size", type=int, default=1,
            help="Max call/time-slice units per invocation (default: 1).",
        )
        parser.add_argument(
            "--safety-margin", type=float, default=_SAFETY_MARGIN,
            help="Deprecated compatibility option; explicit caps replace volume estimates.",
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
            "--max-results", type=int, default=100,
            help="Per-unit primary result cap, in complete 20-result pages (default: 100).",
        )
        parser.add_argument(
            "--max-pages", type=int, default=5,
            help="Per-unit primary page cap (default: 5).",
        )
        parser.add_argument(
            "--max-llm-calls", type=int, default=60,
            help="Invocation-wide model transport cap, including retries (default: 60).",
        )
        parser.add_argument("--max-api-requests", type=int, default=10,
                            help="Invocation-wide HTTP request cap (default: 10).")
        parser.add_argument("--run-seconds", type=int, default=300,
                            help="Invocation deadline in seconds (default: 300).")
        parser.add_argument("--slice-minutes", type=int, default=15,
                            help="Fixed historical unit duration (default: 15 minutes).")
        parser.add_argument("--enrichment-limit", type=int, default=5,
                            help="Frozen recovered-post cohort for inline enrichment (default: 5).")
        parser.add_argument("--state-dir", type=Path, default=None,
                            help="Durable checkpoint directory on the executing host.")
        parser.add_argument("--json", action="store_true", help="Print the final structured state.")
        parser.add_argument("--retry-blocked", action="store_true",
                            help="Explicitly retry an anomalous unit after inspecting/fixing its cause.")
        parser.add_argument("--query", default=None,
                            help="Frozen historical query for exactly one brand and B/C call; omit time operators.")

    def handle(self, *args, **options) -> None:
        previous_settings = {
            name: getattr(settings, name, _MISSING_SETTING)
            for name in _RUNTIME_SETTING_NAMES
        }
        try:
            return self._handle_guarded(*args, **options)
        finally:
            for name, value in previous_settings.items():
                if value is _MISSING_SETTING:
                    try:
                        delattr(settings, name)
                    except AttributeError:
                        pass
                else:
                    setattr(settings, name, value)

    def _handle_guarded(self, *args, **options) -> None:
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
            prepared = self._handle(*args, **options)
        if prepared is not None:
            self._execute(prepared, options)

    def _handle(self, *args, **options):
        """Prepare under a brief writer lease; execution leases each unit."""
        if options["quarantined"]:
            self._handle_quarantined(options)
            return None
        if not options.get("since"):
            raise CommandError("--since is required unless --quarantined is used")
        if not options.get("until"):
            raise CommandError("--until is required to freeze resumable historical bounds")
        since_epoch = _parse_iso(options["since"])
        until_epoch = _parse_iso(options["until"])
        if until_epoch <= since_epoch:
            raise CommandError("--until must be later than --since")
        for name in ("batch_size", "max_results", "max_pages", "max_api_requests",
                     "run_seconds", "slice_minutes", "enrichment_limit"):
            if options[name] <= 0:
                raise CommandError(f"--{name.replace('_', '-')} must be positive")
        for name in ("pause", "max_llm_calls"):
            if options[name] < 0:
                raise CommandError(f"--{name.replace('_', '-')} must be nonnegative")
        if options["max_results"] % 20:
            raise CommandError("--max-results must be a multiple of 20 to retain complete pages")
        if options["run_seconds"] > 780:
            raise CommandError("--run-seconds must fit the 15-minute schedule with a 120-second reserve")
        margin = options["safety_margin"]
        if not math.isfinite(margin) or margin <= 0:
            raise CommandError("--safety-margin must be finite and positive")
        brands = [v.strip() for v in str(options.get("brands") or "").split(",") if v.strip()]
        requested = [v.strip().upper() for v in str(options.get("call_ids") or "").split(",") if v.strip()]
        if len(requested) != len(set(requested)):
            raise CommandError("--call-ids contains duplicates")
        from x_monitor.config import VALID_CALL_IDS
        unknown = sorted(set(requested) - set(VALID_CALL_IDS))
        if unknown:
            raise CommandError("unknown --call-ids: " + ", ".join(unknown))
        query_override = options.get("query")
        if query_override is not None:
            query_override = query_override.strip()
            if not query_override or len(brands) != 1 or len(requested) != 1 or requested[0] == "A":
                raise CommandError("--query requires exactly one brand and one B/C call")
            if any(token in query_override.lower() for token in (
                "since:", "until:", "since_time:", "until_time:", "since_id:", "max_id:",
            )):
                raise CommandError("--query must omit time operators; fixed command bounds own the interval")
            if len(f"{query_override} since_time:{since_epoch} until_time:{until_epoch}") > 512:
                raise CommandError("--query exceeds the provider length cap after fixed time bounds")
        state_file = _state_path(since_epoch, until_epoch, _scope_key(brands=brands, call_ids=requested))
        if options["state_dir"] is not None:
            state_file = options["state_dir"] / state_file.name
        if options["status"]:
            state = _load_state(state_file)
            if state is None:
                self.stdout.write("No state file — backfill not started yet.")
            else:
                self.stdout.write(json.dumps(state, indent=2))
            return None

        settings.X_MONITOR_CYCLE_SINCE_TIME = since_epoch
        settings.X_MONITOR_CYCLE_UNTIL_TIME = until_epoch
        settings.X_MONITOR_CYCLE_LIMIT_PER_CALL = options["max_results"]
        settings.X_MONITOR_CYCLE_MAX_PAGES_PER_CALL = options["max_pages"]
        settings.X_MONITOR_CYCLE_BRAND_FILTER = ",".join(brands) or None
        from monitor.cycle import plan_calls_for_cycle
        cfg = load_config(Path("config.yaml"))
        disabled = sorted(set(brands) - set(cfg.enabled_models)) if brands else []
        if disabled:
            raise CommandError("--brands must be enabled models: " + ", ".join(disabled))
        calls = plan_calls_for_cycle(cfg)
        # Historical work selects the core plan; optional modern discovery has
        # separate evidence and budgets, and must not silently join a campaign.
        calls = [call for call in calls if call.call_id in VALID_CALL_IDS]
        if brands:
            calls = [call for call in calls if call.call_id != "A"]
            inapplicable = sorted(set(requested) - {call.call_id for call in calls})
            if inapplicable:
                raise CommandError(f"call IDs {', '.join(inapplicable)} are not applicable to brands {', '.join(brands)}")
        if requested:
            calls = [call for call in calls if call.call_id in requested]
        if any(call.call_id == "A" for call in calls) and not options["dry_run"]:
            raise CommandError(
                "Historical Call A requires a frozen account-population manifest; "
                "select B/C call IDs for this bounded recovery"
            )
        if not calls and (brands or requested):
            raise CommandError("backfill scope selects no logical calls")
        call_ids = [call.call_id for call in calls]
        if query_override is not None:
            calls = [replace(call, query_string=query_override, query_length=len(query_override)) for call in calls]
        if hasattr(cfg, "model_copy"):
            from monitor.backfill_resources import bounded_backfill_config

            cfg = bounded_backfill_config(cfg, enrichment_limit=options["enrichment_limit"])
        config_value = cfg.model_dump(mode="json") if hasattr(cfg, "model_dump") else {}
        limits = {name: options[name] for name in (
            "max_results", "max_pages", "max_api_requests", "max_llm_calls",
            "run_seconds", "slice_minutes", "enrichment_limit",
        )}
        identity = {
            "since_epoch": since_epoch, "until_epoch": until_epoch,
            "brands": sorted(set(brands)), "limits": limits,
            "queries": {call.call_id: getattr(call, "query_string", "") for call in calls},
            "config_digest": hashlib.sha256(json.dumps(config_value, sort_keys=True).encode()).hexdigest(),
            "database": {key: settings.DATABASES["default"].get(key) for key in ("NAME", "HOST", "USER")},
        }
        if query_override is not None:
            identity["query_override"] = query_override
        campaign_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        state = None if options["reset"] else _load_state(state_file)
        if state and (state.get("schema_version") != 2 or state.get("campaign_id") != campaign_id):
            raise CommandError("Checkpoint identity changed or is legacy; inspect it and use an explicit --reset for a new campaign")
        if not state:
            slices = range(since_epoch, until_epoch, options["slice_minutes"] * 60)
            units = [{
                "key": f"{call_id}:{lower}:{min(lower + options['slice_minutes'] * 60, until_epoch)}",
                "call_id": call_id, "since_epoch": lower,
                "until_epoch": min(lower + options["slice_minutes"] * 60, until_epoch),
                "status": "pending", "cursor": None, "seen_cursors": [], "post_ids": [],
            } for lower in slices for call_id in call_ids]
            state = {
                "schema_version": 2, "campaign_id": campaign_id, "identity": identity,
                "since_epoch": since_epoch, "until_epoch": until_epoch,
                "calls_total": len(call_ids), "calls_completed_ids": [],
                "calls_completed": 0, "calls_remaining": call_ids,
                "total_inserted": 0, "units": units, "runs": [], "finished": False,
                "enrichment_complete": False,
            }
        if options["retry_blocked"]:
            for unit in state["units"]:
                if unit["status"] == "blocked":
                    unit["status"] = "pending"
                    unit.pop("blocked_reason", None)
        pending = [unit for unit in state["units"] if unit["status"] == "pending"]
        self.stdout.write(
            f"Backfill {options['since']} → {options['until']}: "
            f"{len(pending)} pending call/time-slice units; "
            f"caps={limits}" + (" [DRY RUN]" if options["dry_run"] else "")
        )
        if options["dry_run"]:
            self.stdout.write(f"  Would execute calls: {call_ids}")
            if options["reset"]:
                self.stdout.write("Would reset state (dry run; no file changed).")
            if options["json"]:
                self.stdout.write(json.dumps({"campaign_id": campaign_id, "identity": identity}, indent=2))
            return None
        _save_state(state_file, state)
        return {"cfg": cfg, "state_file": state_file, "campaign_id": campaign_id, "call_ids": call_ids}

    def _execute(self, prepared, options):
        from monitor.backfill_resources import (
            BackfillBudget,
            BackfillContext,
        )
        from monitor.cycle import CycleRunner, _BoundedClassifierClient
        from monitor.run_lock import harvest_writer_lock
        from x_monitor.reattribute import build_relevancy_client_from_env
        from x_monitor.relevancy import build_binary_relevancy_llm_call

        budget = BackfillBudget(
            max_api_requests=options["max_api_requests"],
            max_llm_calls=options["max_llm_calls"], run_seconds=options["run_seconds"],
        )
        state_file = prepared["state_file"]
        cfg = prepared["cfg"]
        failed = False
        attempted_enrichment_units: set[str] = set()
        for attempt in range(options["batch_size"]):
            if attempt and options["pause"]:
                if budget.remaining_seconds <= options["pause"]:
                    break
                _time.sleep(options["pause"])  # No writer lease while idle.
            if _seconds_to_next_slot() <= budget.remaining_seconds + 120:
                self.stderr.write("Backfill deferred: unit deadline plus reserve does not fit before the next scheduled slot.")
                break
            with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.unit") as lease:
                if not lease.acquired:
                    self.stderr.write("Backfill skipped: shared harvest writer lock is held.")
                    break
                state = _load_state(state_file)
                if not state or state["campaign_id"] != prepared["campaign_id"]:
                    raise CommandError("Checkpoint changed before unit execution")
                pending = [u for u in state["units"] if u["status"] == "pending"]
                enrichment_pending = set(state.get("enrichment_pending_post_ids", []))
                enrichment_units = [u for u in state["units"] if enrichment_pending.intersection(
                    u.get("enrichment_cohort_post_ids", [])
                ) and u["key"] not in attempted_enrichment_units]
                if not pending and not enrichment_units:
                    failed = any(u["status"] == "blocked" for u in state["units"])
                    break
                unit = pending[0] if pending else enrichment_units[0]
                enrichment_only = not pending
                if enrichment_only:
                    attempted_enrichment_units.add(unit["key"])
                settings.X_MONITOR_CYCLE_SINCE_TIME = unit["since_epoch"]
                settings.X_MONITOR_CYCLE_UNTIL_TIME = unit["until_epoch"]
                context = BackfillContext(
                    budget=budget, cursor=unit["cursor"], seen_cursors=unit["seen_cursors"],
                    post_ids=unit["post_ids"], enrichment_limit=options["enrichment_limit"],
                    enrichment_cohort_ids=unit.get("enrichment_cohort_post_ids", []),
                    query_override=state["identity"].get("query_override"),
                )
                started = datetime.now(UTC).isoformat()
                try:
                    relevancy_client = build_relevancy_client_from_env(cfg)
                    if relevancy_client is not None:
                        relevancy_client = _BoundedClassifierClient(
                            relevancy_client, maximum_calls=budget.remaining_llm_calls, pause_seconds=0,
                            before_call=lambda: budget.claim_llm_request(cfg.harvest.relevancy_timeout_seconds),
                            after_call=budget.record_model_response,
                        )
                    relevancy = build_binary_relevancy_llm_call(
                        client=relevancy_client, model=cfg.llm.relevancy_model,
                        timeout_seconds=cfg.harvest.relevancy_timeout_seconds,
                    )
                    runner = CycleRunner(
                        cfg=cfg, cycle_kind="backfill", dry_run=False,
                        _backfill_call_ids=[unit["call_id"]], _backfill_context=context,
                        _max_llm_calls=options["max_llm_calls"], _relevancy_llm_call=relevancy,
                    )
                    stats = runner.run_backfill_enrichment() if enrichment_only else runner.run()
                    call_status = _selected_call_status(stats, unit["call_id"])
                    receipts = [c for c in stats.get("calls", []) if c.get("call_id") == unit["call_id"]]
                    call = receipts[0] if len(receipts) == 1 else {}
                    progress = call.get("backfill_progress", {})
                    # Never commit a token past failed persistence. Previously
                    # committed posts can be replayed safely through Post dedup.
                    persistence_verified = call.get("n_persist_failed") == 0
                    if persistence_verified and call_status in ("completed", "no_results", "truncated"):
                        unit["cursor"] = progress.get("cursor", unit["cursor"])
                        unit["seen_cursors"] = progress.get("seen_cursors", unit["seen_cursors"])
                        unit["post_ids"] = stats.get("recovered_post_ids", unit["post_ids"])
                    if not enrichment_only:
                        unit["status"] = (
                            "completed" if persistence_verified and progress.get("drained") is True
                            and call_status in _COMPLETE_CALL_STATUSES else "pending"
                        )
                        if progress.get("reason") in _BLOCKED_PROGRESS_REASONS:
                            unit["status"] = "blocked"
                            unit["blocked_reason"] = progress["reason"]
                    unit["enrichment_cohort_post_ids"] = stats.get("enrichment_cohort_post_ids", unit.get("enrichment_cohort_post_ids", []))
                    inserted = stats.get("totals", {}).get("n_inserted", 0)
                    state["total_inserted"] += inserted
                    state["runs"].append({
                        "unit_key": unit["key"], "call_id": unit["call_id"],
                        "started_at": started, "finished_at": datetime.now(UTC).isoformat(),
                        "run_id": stats.get("run_id"), "status": stats.get("status"),
                        "call_status": call_status, "n_inserted": inserted,
                        "n_calls_run": stats.get("totals", {}).get("n_calls_run", 0),
                        "errors": stats.get("errors", []), "summary": stats,
                    })
                    if unit["status"] != "completed":
                        self.stderr.write(f"    {unit['call_id']}: {call_status}; remains pending ({inserted} inserted)")
                    failed = (
                        stats.get("status") in ("aborted", "degraded")
                        or unit["status"] == "blocked"
                        or call_status in ("error", "persist_incomplete", "length_cap_exceeded", "enrichment_failed")
                    )
                except Exception as exc:  # noqa: BLE001 - persist failure receipt before command exit
                    state["runs"].append({
                        "unit_key": unit["key"], "call_id": unit["call_id"], "started_at": started,
                        "finished_at": datetime.now(UTC).isoformat(),
                        "status": "failed", "error": type(exc).__name__,
                    })
                    failed = True
                state["last_invocation_usage"] = budget.snapshot()
                state["calls_completed_ids"] = [
                    cid for cid in prepared["call_ids"]
                    if all(u["status"] == "completed" for u in state["units"] if u["call_id"] == cid)
                ]
                state["calls_completed"] = len(state["calls_completed_ids"])
                state["calls_remaining"] = [c for c in prepared["call_ids"] if c not in state["calls_completed_ids"]]
                state["finished"] = not state["calls_remaining"]
                self._enrichment_status(state)
                _save_state(state_file, state)
            if failed or not budget.can_start(30):
                break
        state = _load_state(state_file)
        self.result = state
        self.stdout.write(
            f"Collection {'drained' if state['finished'] else 'pending'}; "
            f"{state['total_inserted']} inserted; frozen cohort pending={len(state.get('enrichment_cohort_pending_post_ids', []))}; "
            f"all recovered enrichment pending={len(state.get('enrichment_pending_post_ids', []))}. State: {state_file}"
        )
        if options["json"]:
            self.stdout.write(json.dumps(state, indent=2, default=str))
        if failed:
            raise CommandError("Backfill attempt failed; committed checkpoint retained")

    @staticmethod
    def _enrichment_status(state):
        from core.models import PostEnrichmentState
        post_ids = list(dict.fromkeys(pid for unit in state["units"] for pid in unit["post_ids"]))
        complete = set(PostEnrichmentState.objects.filter(
            post_id__in=post_ids, translation_status=PostEnrichmentState.Status.SUCCEEDED,
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
        ).values_list("post_id", flat=True))
        state["enrichment_pending_post_ids"] = [pid for pid in post_ids if pid not in complete]
        state["enrichment_complete"] = bool(post_ids) and not state["enrichment_pending_post_ids"]
        cohort_ids = {pid for unit in state["units"] for pid in unit.get("enrichment_cohort_post_ids", [])}
        state["enrichment_cohort_pending_post_ids"] = sorted(cohort_ids - complete)
        state["enrichment_cohort_complete"] = bool(cohort_ids) and not state["enrichment_cohort_pending_post_ids"]

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
