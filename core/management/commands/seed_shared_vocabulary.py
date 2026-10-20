"""Seed pinned shared catalogues without provider calls or caller cutover."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.shared_vocabulary import CATALOGUES, seed_shared_vocabulary


class Command(BaseCommand):
    help = "Validate pinned inputs and insert missing shared vocabulary rows."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default", choices=tuple(connections))
        parser.add_argument("--catalogue", action="append", choices=tuple(CATALOGUES))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            counts = seed_shared_vocabulary(
                database=options["database"],
                catalogues=None
                if options["catalogue"] is None
                else tuple(options["catalogue"]),
                dry_run=options["dry_run"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options["verbosity"]:
            action = "Validated" if options["dry_run"] else "Ensured"
            for name, count in counts.items():
                self.stdout.write(f"{action} {count} seed records: {name}")
