"""Plan or execute an arbitrary historical X window or ordered campaign."""

import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from scripts.backfill_campaign import manifest, run
from x_monitor.config import load_config


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
            help="JSON campaign: windows with since/until, optional name and supplemental_queries.",
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
        cfg = load_config(Path("config.yaml"))
        try:
            revision = options["runtime_revision"]
            if revision is not None:
                if not options["manifest"]:
                    raise CommandError("--runtime-revision requires --manifest")
                if not re.fullmatch(r"[0-9a-f]{40}", revision):
                    raise CommandError("--runtime-revision requires a full 40-character commit SHA")
            if options["manifest"]:
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
                        "--manifest owns all saved instructions; omit new scope options"
                    )
                frozen = json.loads(options["manifest"].read_text())
            else:
                config = {}
                if options["windows"]:
                    if options["since"] or options["until"]:
                        raise CommandError("select --windows or --since/--until")
                    config = json.loads(options["windows"].read_text())
                    windows = [
                        (row["since"], row["until"]) for row in config["windows"]
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
                )
            self.result = frozen
            if options["execute"]:
                execution = {"evaluate_at_end": options["evaluate_at_end"]}
                if revision is not None:
                    execution["runtime_revision"] = revision
                run(frozen, cfg, **execution)
            else:
                self.stdout.write(json.dumps(frozen, sort_keys=True))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
