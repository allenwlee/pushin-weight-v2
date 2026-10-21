"""Preview/apply references without changing existing label identities or copy."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.geography_label_locales import OWNERS, map_geography_label_locales


class Command(BaseCommand):
    help = "Preview/apply bounded shared locale references on country/region labels."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, choices=tuple(OWNERS))
        parser.add_argument("--database", default="default", choices=tuple(connections))
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--max-batches", type=int, default=10)
        parser.add_argument("--after-owner-key")
        parser.add_argument("--after-lang")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("--apply and --dry-run cannot be combined")
        try:
            result = map_geography_label_locales(
                **{
                    key: options[key]
                    for key in (
                        "owner",
                        "database",
                        "batch_size",
                        "max_batches",
                        "after_owner_key",
                        "after_lang",
                        "apply",
                    )
                }
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options["verbosity"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
