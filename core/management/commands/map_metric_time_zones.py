"""Resolve only already registered timezone identities; default to preview."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.metric_time_zones import map_metric_time_zones


class Command(BaseCommand):
    help = "Preview or apply bounded exact metric timezone references."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default", choices=tuple(connections))
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--max-batches", type=int, default=10)
        parser.add_argument("--after-metric-id", type=int, default=0)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("--apply and --dry-run cannot be combined")
        try:
            result = map_metric_time_zones(
                **{
                    key: options[key]
                    for key in (
                        "database",
                        "batch_size",
                        "max_batches",
                        "after_metric_id",
                        "apply",
                    )
                }
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options["verbosity"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
