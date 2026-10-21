"""Preview or apply bounded exact event/opportunity timezone references."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.intelligence_time_zones import OWNERS, map_intelligence_time_zones


class Command(BaseCommand):
    help = "Preview/apply exact timezone references without changing source evidence."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, choices=tuple(OWNERS))
        parser.add_argument("--database", default="default", choices=tuple(connections))
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--max-batches", type=int, default=10)
        parser.add_argument("--after-id", type=int, default=0)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("--apply and --dry-run cannot be combined")
        try:
            result = map_intelligence_time_zones(
                **{
                    key: options[key]
                    for key in (
                        "owner",
                        "database",
                        "batch_size",
                        "max_batches",
                        "after_id",
                        "apply",
                    )
                }
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options["verbosity"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
