"""Plan or execute an arbitrary historical X window or ordered campaign."""

import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from scripts.backfill_campaign import manifest, run
from scripts.backfill_month import (
    check_deadline,
    execution_options,
    run_phases,
    selected_runtime,
    validate_recipe,
)
from x_monitor.config import load_config


def unverified_windows(result):
    """Name each window a final assessment left unverified; empty when verified.

    ``run`` returns assess_campaign's report, verified only when every window
    is. ``run_phases`` returns compact per-window rows without that overall
    status, so any unverified row decides. A missing assessment is unverified.
    """
    if isinstance(result, list):
        rows = result
    elif isinstance(result, dict):
        if result.get("status") == "verified":
            return []
        # An unverified report names its failed windows, or else its own status.
        rows = [row for row in result.get("windows") or [] if row.get("status") != "verified"]
        rows = rows or [{"status": result.get("status")}]
    else:
        rows = [{"status": "final_assessment_missing"}]
    named = []
    for row in rows:
        if row.get("status") == "verified":
            continue
        window = row.get("window") or {}
        label = {"window": window.get("index"), "since": window.get("since"), "until": window.get("until")}
        label |= {key: row.get(key) for key in ("phase", "status", "error_code", "source_collection_job")}
        named.append({key: value for key, value in label.items() if value is not None})
    return named


class Command(BaseCommand):
    help = (
        "Collect and enrich historical X windows, with optional aggregate evaluation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--since", help="Inclusive date or ISO time, UTC if no offset."
        )
        parser.add_argument(
            "--until", help="Exclusive date or ISO time, UTC if no offset."
        )
        parser.add_argument(
            "--windows",
            type=Path,
            help=(
                "JSON campaign: windows with since/until, optional name and supplemental_queries. "
                "A window may add spend_basis (reservation or settled)."
            ),
        )
        parser.add_argument(
            "--campaign-name", help="Stable name for the saved collection instructions."
        )
        parser.add_argument(
            "--model-concurrency",
            type=int,
            default=None,
            help="Ordinary model calls in flight (default32).",
        )
        parser.add_argument(
            "--evaluate-at-end",
            action="store_true",
            help="Defer recoverable failures, attempt all windows, then assess every stored member.",
        )
        parser.add_argument(
            "--manifest",
            type=Path,
            help="Resume an exact previously saved plan, preserving limits and deadline.",
        )
        parser.add_argument(
            "--runtime-revision",
            help="Full tested commit SHA to run a saved --manifest; its original instructions stay unchanged.",
        )
        parser.add_argument(
            "--month-recipe",
            type=Path,
            help="Original compact month recipe; requires an explicit --phase.",
        )
        parser.add_argument(
            "--phase",
            choices=["collect", "enrich", "all"],
            help="Collect the entire range before any ordinary enrichment.",
        )
        parser.add_argument(
            "--enrichment-concurrency",
            type=int,
            default=None,
            help="Model calls in flight, 1 through the saved ceiling (default8).",
        )
        parser.add_argument(
            "--collection-concurrency",
            type=int,
            default=None,
            help="Concurrent HTTP fetches, 1–20 (default1).",
        )
        parser.add_argument(
            "--collection-starts-per-second",
            type=float,
            default=None,
            help="Physical search request start rate (default10).",
        )
        parser.add_argument(
            "--response-storage", choices=["archive", "staging", "database"], default=None,
            help="New instructions only: database saves Posts and receipts in the dedicated backfill database.",
        )
        parser.add_argument("--collection-unlimited-requests", action="store_true",
                            help="Explicit collect-only override: remove cumulative X request cap; retain attempt budgets.")
        parser.add_argument("--collection-no-deadline", action="store_true",
                            help="Explicit collect-only override: remove calendar expiry; retain request/attempt timeouts.")
        parser.add_argument(
            "--runtime-attestation",
            type=Path,
            help="Month runtime JSON: runtime_revision and source_sha256; paired with --runtime-revision.",
        )
        parser.add_argument("--database-relocation", type=Path, help="Verified storage relocation receipt for preserved jobs.")
        parser.add_argument("--database-relocation-sha256", help="Expected SHA256 of the relocation receipt.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--execute",
            action="store_true",
            help="Run the planned collection and enrichment. Without this flag, only print a plan.",
        )
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Print a plan without provider requests or database writes.",
        )

    def handle(self, *args, **options):
        from monitor.backfill_database import relocated_database
        try:
            with relocated_database(options.get("database_relocation"), options.get("database_relocation_sha256")):
                return self._handle(*args, **options)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _handle(self, *args, **options):
        try:
            phase = options["phase"]
            if options["response_storage"] is not None:
                if options["manifest"] or options["month_recipe"]:
                    raise CommandError("saved instructions own response storage")
                if options["response_storage"] == "staging" and phase != "collect":
                    raise CommandError("staging acquisition requires --phase collect; promote before enrichment")
            preferences = {
                "collection_unlimited_requests": options["collection_unlimited_requests"],
                "collection_no_deadline": options["collection_no_deadline"],
                "enrichment_concurrency": options["enrichment_concurrency"],
                "collection_concurrency": 1
                if options["collection_concurrency"] is None
                else options["collection_concurrency"],
                "collection_starts_per_second": 10
                if options["collection_starts_per_second"] is None
                else options["collection_starts_per_second"],
            }
            if phase is None and (
                options["month_recipe"]
                or options["collection_unlimited_requests"] or options["collection_no_deadline"]
                or any(options[k] is not None for k in (
                    "enrichment_concurrency", "collection_concurrency", "collection_starts_per_second"))
            ):
                raise CommandError(
                    "--month-recipe and execution preferences require --phase"
                )
            if phase is not None:
                execution_options(
                    {"direct_concurrency": 32}, phase=phase, **preferences
                )
            if options["manifest"] and options["month_recipe"]:
                raise CommandError("select --manifest or --month-recipe")
            if options["runtime_attestation"] and (
                not options["month_recipe"] or not options["runtime_revision"]
            ):
                raise CommandError(
                    "--runtime-attestation requires --month-recipe and --runtime-revision"
                )
            revision = options["runtime_revision"]
            if revision is not None:
                if not (options["manifest"] or options["month_recipe"]):
                    raise CommandError(
                        "--runtime-revision requires --manifest or --month-recipe"
                    )
                if not re.fullmatch(r"[0-9a-f]{40}", revision):
                    raise CommandError(
                        "--runtime-revision requires a full 40-character commit SHA"
                    )
            if options["manifest"] or options["month_recipe"]:
                if any(
                    options[key]
                    for key in [
                        "since",
                        "until",
                        "windows",
                        "campaign_name",
                        "model_concurrency",
                    ]
                ):
                    raise CommandError(
                        "--manifest or --month-recipe owns all saved instructions; omit new scope options"
                    )
                frozen = json.loads(
                    (options["manifest"] or options["month_recipe"]).read_text()
                )
                if options["month_recipe"]:
                    validate_recipe(frozen)
                    if revision is not None and options["runtime_attestation"] is None:
                        raise CommandError(
                            "month --runtime-revision requires --runtime-attestation"
                        )
            cfg = load_config(Path("config.yaml"))
            if not (options["manifest"] or options["month_recipe"]):
                config = {}
                if options["windows"]:
                    if options["since"] or options["until"]:
                        raise CommandError("select --windows or --since/--until")
                    config = json.loads(options["windows"].read_text())
                    # Plain bounds keep today's input; any other window field
                    # goes to the manifest, which validates and rejects unknowns.
                    windows = [
                        (row["since"], row["until"])
                        if set(row) <= {"since", "until"} else row
                        for row in config["windows"]
                    ]
                else:
                    if not options["since"] or not options["until"]:
                        raise CommandError(
                            "provide both --since and --until, or --windows, or --manifest"
                        )
                    windows = [(options["since"], options["until"])]
                name = (
                    options["campaign_name"]
                    or config.get("name")
                    or "x-backfill-"
                    + hashlib.sha256(json.dumps(windows).encode()).hexdigest()[:16]
                )
                supplements = [
                    (row["call_id"], row["query"])
                    for row in config.get("supplemental_queries", [])
                ]
                frozen = manifest(
                    cfg,
                    windows=windows,
                    campaign_name=name,
                    supplemental_queries=supplements,
                    direct_concurrency=32
                    if options["model_concurrency"] is None
                    else options["model_concurrency"],
                    response_storage=options["response_storage"] or "archive",
                )
            runtime = None
            if options["runtime_attestation"]:
                runtime = json.loads(options["runtime_attestation"].read_text())
                if selected_runtime(frozen, runtime)["runtime_revision"] != revision:
                    raise CommandError("month runtime attestation revision mismatch")
            if phase is not None:
                execution_options(frozen, phase=phase, **preferences)
                if not options["collection_no_deadline"]:
                    check_deadline((frozen.get("spec") or frozen)["deadline"])
            self.result = frozen
            if options["execute"]:
                execution = {"evaluate_at_end": options["evaluate_at_end"]}
                if revision is not None:
                    execution["runtime_revision"] = revision
                if phase is None:
                    result = run(frozen, cfg, **execution)
                else:
                    if runtime is not None:
                        execution["runtime_attestation"] = runtime
                    result = run_phases(frozen, cfg, phase=phase, **preferences, **execution)
                # Raised only after the runner returns, so every receipt is saved
                # and no campaign job is paused. Exit 3: finished, not verified.
                unverified = unverified_windows(result) if options["evaluate_at_end"] else []
                if unverified:
                    raise CommandError(
                        "final assessment not verified: "
                        + json.dumps(unverified, sort_keys=True, default=str)
                        + "; receipts are saved in each job's CollectionRun.report['backfill_campaign']",
                        returncode=3,
                    )
            else:
                self.stdout.write(json.dumps(frozen, sort_keys=True))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
