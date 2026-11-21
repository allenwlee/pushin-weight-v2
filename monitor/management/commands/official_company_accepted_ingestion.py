"""Prepare a read-only preview of saved official-account acceptances."""

import json

from django.core.management.base import BaseCommand, CommandError

from core.official_company_accepted_ingestion import (
    apply_preview,
    freeze_accepted,
    preview_accepted,
    read_accepted,
)
from core.official_company_queue_pass import read_manifest


class Command(BaseCommand):
    help = "Freeze, preview, or apply saved official-company evaluator results."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("freeze", "preview", "apply"))
        parser.add_argument("--queue", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--preview")
        parser.add_argument("--allow-production", action="store_true")
        parser.add_argument(
            "--max-writes", type=int, help="Maximum new registration attempts in this run."
        )

    def handle(self, *args, **options):
        try:
            if options["allow_production"] and options["action"] != "apply":
                raise ValueError("--allow-production is only valid for apply")
            if options["max_writes"] is not None and options["action"] != "apply":
                raise ValueError("--max-writes is only valid for apply")
            queue = read_manifest(options["queue"], allow_isolated_fixture=True)
            if options["action"] == "freeze":
                if options["preview"]:
                    raise ValueError("freeze does not accept --preview")
                result = freeze_accepted(queue=queue, path=options["manifest"])
                summary = {"count": result["count"], "sha256": result["sha256"]}
            elif options["action"] == "preview":
                if not options["preview"]:
                    raise ValueError("preview requires --preview")
                manifest = read_accepted(options["manifest"], queue=queue)
                result = preview_accepted(
                    queue=queue, manifest=manifest, path=options["preview"]
                )
                summary = {
                    "count": len(result["members"]),
                    "counts": result["counts"],
                    "sha256": result["sha256"],
                }
            else:
                from pathlib import Path

                from x_monitor.config import OfficialCompanyConfig

                if not options["preview"]:
                    raise ValueError("apply requires --preview")
                manifest = read_accepted(options["manifest"], queue=queue)
                preview = json.loads(Path(options["preview"]).read_text())
                summary = {
                    "members": apply_preview(
                        queue=queue,
                        manifest=manifest,
                        preview=preview,
                        allow_production=options["allow_production"],
                        frozen_list_path=options["manifest"],
                        max_writes=options["max_writes"],
                        cfg=OfficialCompanyConfig(
                            enabled=True, registration_enabled=True
                        ),
                    )
                }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(summary, sort_keys=True))
